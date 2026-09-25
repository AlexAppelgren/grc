"""Hardening guards (docs/plans/briefs/HARDENING.md, task H-A): findings from the security
reviews of 2026-09-19 that were not that branch's to fix.

- **H1** `PageQuery.offset` had no upper bound, so a huge offset asked PostgreSQL to count
  past its integer range and every paginated route answered 500. It is bounded by
  `API_PAGE_OFFSET_MAX`, and above it the answer is a 422 naming the field.
- **H2** `build_principal` trusted whatever a tenant role row carried. The seeds and the
  role editor refuse a platform permission, but a row written around them would have
  handed `proposals.review` to a bank session and opened the library fence. The principal
  now keeps only the permissions of its own zone.
- **H13** `build_principal` also added every platform grant to a bank session. Platform
  grants now reach a session with no tenant only, and a bank invitation refuses an address
  that holds a platform role, at creation and again at acceptance: platform staff are
  separate accounts (`bootstrap_platform` already refuses the other direction).
- **H3** A tenant reads the audit rows without a tenant whose subject is a library record
  (apps/governance/logic.py). Nothing stopped a future writer from recording a
  tenant-derived title there, which would show one bank's words to all of them. The guard
  below walks every `record()` call in production code and pins the reviewed set. It fails
  closed on anything the source does not spell out, subject type and tenant id alike, so a
  `tenant_id=principal.tenant_id` that is None under a platform session is named rather
  than walked past (review 2026-09-20).

The H13 refusal is proved end to end through the enrolment ceremony by ID-S27 in
apps/identity/tests_scenarios.py: the route answers 422 and writes no credential.
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.governance.logic import LIBRARY_SUBJECT_TYPES
from apps.identity import invitation_logic, members_logic, roles_logic, session_logic
from apps.identity.models import (
    Invitation,
    Membership,
    PlatformRole,
    PlatformRoleAssignment,
    SessionKind,
    TenantRole,
    User,
)
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, tenancy, permissions as perms
from apps.shared.audit import Actor
from apps.shared.authentication import Principal
from apps.shared.models import Tenant
from apps.shared.testing import ScenarioTestCase, stub_session, user_principal

V1 = "/api/v1"


# ---------------------------------------------------------------------------------------
# H1: the offset is bounded
# ---------------------------------------------------------------------------------------
class PageOffsetIsBounded(ScenarioTestCase):
    """A list takes an offset up to `API_PAGE_OFFSET_MAX` and refuses more. Nothing in the
    product pages that deep, and far above the bound PostgreSQL raises on the OFFSET itself,
    which made every paginated route answer 500 to a number a caller can type."""

    def _read(self, offset: int) -> int:
        principal = user_principal(permissions={perms.AUDIT_READ}, tenant_id=uuid.uuid4())
        with stub_session(principal):
            return self.client.get(f"{V1}/audit-events?offset={offset}", **self.as_user(principal)).status_code

    def test_the_largest_offset_is_answered_and_one_more_is_refused(self) -> None:
        self.assertEqual(self._read(settings.API_PAGE_OFFSET_MAX), 200)
        self.assertEqual(self._read(settings.API_PAGE_OFFSET_MAX + 1), 422)

    def test_the_refusal_names_the_field_and_writes_nothing(self) -> None:
        # 2**63: the number that made the route answer 500 before the bound, measured
        # 2026-09-19 (psycopg NumericValueOutOfRange on the OFFSET, logged with a trace).
        principal = user_principal(permissions={perms.AUDIT_READ}, tenant_id=uuid.uuid4())
        with stub_session(principal):
            response = self.client.get(f"{V1}/audit-events?offset=9223372036854775808", **self.as_user(principal))
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["code"], "validation_error")
        self.assertIn("offset", str(body))
        self.assertEqual(self._read(-1), 422)


# ---------------------------------------------------------------------------------------
# H2 and H13: a session holds the permissions of its own zone
# ---------------------------------------------------------------------------------------
class PrincipalKeepsOneZone(TestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        self.tenant = factories.tenant(slug="hardening-zones")

    def _principal(self, user: User, tenant: Tenant | None) -> Principal | None:
        # A platform session is a row of the platform's zone. Since H-C split every mixed
        # table's write rule, a session with a bank active cannot write one, and no request
        # would: the factory above left a tenant active, so it goes off first.
        if tenant is None:
            tenancy.clear_tenant()
        bundle = session_logic.create_session(
            user=user, kind=SessionKind.FULL, tenant_id=tenant.id if tenant else None, request=None
        )
        return session_logic.build_principal(bundle.session)

    def test_a_tenant_role_row_carrying_a_platform_permission_does_not_grant_it(self) -> None:
        membership = factories.member(self.tenant, roles=("reader",))
        # A row written around the seeds and the role editor: a bad migration, a console,
        # a restored backup. The role editor and `ensure_system_roles` both refuse this.
        TenantRole.objects.filter(tenant=self.tenant, key="reader").update(
            permissions=[perms.CASES_READ, perms.PROPOSALS_REVIEW]
        )
        principal = self._principal(membership.user, self.tenant)
        assert principal is not None
        self.assertIn(perms.CASES_READ, principal.permissions)
        self.assertNotIn(perms.PROPOSALS_REVIEW, principal.permissions)
        self.assertTrue(principal.permissions <= perms.TENANT_PERMISSIONS)

    def test_a_bank_session_of_a_platform_account_carries_no_platform_grant(self) -> None:
        staff = factories.platform_user(roles=("library_editor",), email="editor@platform.test.example")
        # A membership written around the invitation guard below (an older row, a restore).
        membership = factories.member(self.tenant, roles=("reader",), user_row=staff)
        bank = self._principal(membership.user, self.tenant)
        assert bank is not None
        self.assertIn(perms.LIBRARY_READ, bank.permissions)
        self.assertNotIn(perms.PROPOSALS_REVIEW, bank.permissions)
        self.assertFalse(bank.is_platform_staff)

    def test_a_platform_session_carries_platform_grants_and_nothing_else(self) -> None:
        staff = factories.platform_user(roles=("library_editor",), email="editor2@platform.test.example")
        platform = self._principal(staff, None)
        assert platform is not None
        self.assertIn(perms.PROPOSALS_REVIEW, platform.permissions)
        self.assertTrue(platform.permissions <= perms.PLATFORM_PERMISSIONS)
        self.assertTrue(platform.is_platform_staff)


# ---------------------------------------------------------------------------------------
# H13: a bank invitation refuses a platform account
# ---------------------------------------------------------------------------------------
class BankInvitationsRefusePlatformAccounts(TestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        self.tenant = factories.tenant(slug="hardening-invites")
        self.admin = factories.member(self.tenant, roles=("admin",)).user
        self.actor = factories.user_actor(label=self.admin.name, user_id=self.admin.id)

    def _grant_platform_role(self, user: User, key: str = "library_editor") -> None:
        roles_logic.ensure_platform_roles()
        PlatformRoleAssignment.objects.create(user=user, role=PlatformRole.objects.get(key=key))

    def test_inviting_a_platform_account_is_refused_and_writes_no_invitation(self) -> None:
        staff = factories.platform_user(email="staff@platform.test.example")
        with self.assertRaises(ValidationError) as caught:
            members_logic.invite_member(
                tenant=self.tenant,
                actor=self.actor,
                invited_by=self.admin,
                email=staff.email,
                role_keys=["reader"],
                title="Analyst",
            )
        self.assertEqual(caught.exception.code, "platform_account")
        self.assertFalse(Invitation.objects.filter(tenant=self.tenant, email=staff.email).exists())
        self.assertFalse(Membership.objects.filter(tenant=self.tenant, user=staff).exists())

    def test_accepting_is_refused_when_the_platform_role_arrived_after_the_invitation(self) -> None:
        invitation = factories.invitation(self.tenant, email="late@bank.test.example")
        person = invitation_logic.get_or_create_user(invitation.email)
        self._grant_platform_role(person)
        with self.assertRaises(ValidationError) as caught:
            invitation_logic.accept_invitation(invitation, person, timezone.now())
        self.assertEqual(caught.exception.code, "platform_account")
        invitation.refresh_from_db()
        self.assertIsNone(invitation.accepted_at)
        self.assertFalse(Membership.objects.filter(tenant=self.tenant, user=person).exists())

    def test_an_ordinary_address_is_invited_and_accepted_as_before(self) -> None:
        issued = members_logic.invite_member(
            tenant=self.tenant,
            actor=self.actor,
            invited_by=self.admin,
            email="analyst@bank.test.example",
            role_keys=["reader"],
            title="Analyst",
        )
        person = invitation_logic.get_or_create_user(issued.email)
        membership = invitation_logic.accept_invitation(issued, person, timezone.now())
        assert membership is not None
        self.assertEqual([role.key for role in membership.roles.all()], ["reader"])

    def test_a_platform_invitation_is_untouched_by_the_refusal(self) -> None:
        staff = factories.platform_user(email="console@platform.test.example")
        tenancy.clear_tenant()  # the platform's own invitation is written with no bank active (H-C)
        issued = invitation_logic.create_invitation(
            tenant=None, email=staff.email, roles=[], title="Library editor", invited_by=None, actor=Actor.system("test")
        )
        self.assertIsNone(issued.invitation.tenant_id)
        self.assertIsNone(invitation_logic.accept_invitation(issued.invitation, staff, timezone.now()))


# ---------------------------------------------------------------------------------------
# H3: no tenant-derived title under a library subject with no tenant
# ---------------------------------------------------------------------------------------
APPS_DIR = Path(__file__).resolve().parent.parent

# Every `record()` call in production code whose subject type names a library record, or
# cannot be read off the source, and whose tenant id is None or cannot be read off the
# source either. A tenant reads the rows with no tenant from the shared zone, so each such
# call's actor must be the system, an agent or platform staff and its title must not be a
# tenant's words; a call whose tenant id is decided at runtime is here because nobody can
# tell from the source which zone its row lands in. The note is the review; a call that is
# not here has not been looked at, and a call that disappears takes its entry with it.
REVIEWED_LIBRARY_RECORD_CALLS: dict[str, str] = {
    "apps/taxonomy/seeds/__init__.py record('vocabulary') tenant_id=None actor=Actor.system(SEED_REASON) title=f'{list_name}:{spec.key}'": (
        "The reference seed of a library list: a system actor, and the title is the list and "
        "the row's stable key, never a tenant's words."
    ),
    "apps/taxonomy/seeds/__init__.py record('taxonomy_term') tenant_id=None actor=Actor.system(SEED_REASON) title=f\"{dimension.key}:{spec['key']}\"": (
        "The same seed for a taxonomy term: a system actor, and the title is the dimension and "
        "term keys."
    ),
    "apps/taxonomy/seeds/__init__.py record('taxonomy_term') tenant_id=None actor=Actor.system(SEED_REASON) title=f'{dimension.key}:{row.key}'": (
        "The same seed filing the term that mirrors a jurisdiction row (FP-04): a system actor, "
        "and the title is the dimension key and the jurisdiction's own key."
    ),
    "apps/taxonomy/seeds/__init__.py record('taxonomy_term') tenant_id=None actor=Actor.system(SEED_REASON) title=f'{JURISDICTION_DIMENSION}:{row.key}'": (
        "The same seed putting the link, the parent and `active` back on a mirrored term: a "
        "system actor, and the title is the dimension and jurisdiction keys."
    ),
    "apps/taxonomy/seeds/__init__.py record('taxonomy_term') tenant_id=None actor=Actor.system(SEED_REASON) title=f'{dimension}:{key}'": (
        "The same seed switching one seeded term on for seed_e2e (std-journeys, FP-S16): a "
        "system actor, and the title is the dimension and term keys the caller names in code."
    ),
    "apps/taxonomy/tenant_hooks.py record('vocabulary') tenant_id=tenant.id actor=actor title=f'{list_name}:{spec.key}'": (
        "A bank's own list row, written under its tenant id and the actor that asked for the "
        "bank (the deploy seed, the E2E seed, or the platform person creating it from the "
        "console). The guard names it because the tenant id is not a literal; the row is the "
        "bank's, and the title is the list and the row's key."
    ),
    "apps/library/seeds/library.py record(subject_type) tenant_id=None actor=Actor.system(SEED_REASON) title=key": (
        "The reference seed: a system actor, and the title is the fixture's stable key."
    ),
    "apps/proposals/apply.py record('obligation') tenant_id=None actor=actor title=obligation.stable_key": (
        "A new obligation version applied by a library editor: the title is the obligation's "
        "own stable key, the summary and scope in the row are the library's text from the "
        "moment it is approved, and the reviewer is platform staff. The proposal's title and "
        "the proposer are not in the row, so a proposal a bank member made reaches no other "
        "bank through it."
    ),
    "apps/proposals/apply.py record('vocabulary') tenant_id=None actor=actor title=f'{payload.list}:{payload.key}'": (
        "An approved proposal applied by a library editor: the key is a library fact from "
        "the moment it is approved, and the editor is platform staff."
    ),
    "apps/proposals/apply.py record('taxonomy_term') tenant_id=None actor=actor title=f'{payload.dimension}:{payload.key}'": (
        "The same door, for a taxonomy term: an approved key is public library vocabulary."
    ),
    "apps/proposals/apply.py record(SubjectType.OBLIGATION.value) tenant_id=None actor=actor title=obligation.stable_key": (
        "The re-verification stamp, the one write to the library that is not a proposal, and "
        "a new obligation applied from an approved proposal: the actor is platform staff or "
        "a platform agent, and the title is the obligation's stable key, a library fact."
    ),
    "apps/proposals/apply.py record(SubjectType.INSTRUMENT.value) tenant_id=None actor=actor title=instrument.stable_key": (
        "A new instrument applied from an approved proposal: the actor is platform staff or a "
        "platform agent, and the title is the instrument's stable key, a library fact."
    ),
    "apps/proposals/apply.py record(SubjectType.PROVISION.value) tenant_id=None actor=actor title=provision.stable_key": (
        "A new provision or a new text of one applied from an approved proposal: the actor is "
        "platform staff, the title is the provision's stable key, a library fact, and the row "
        "holds keys, version numbers and languages, never the text or the proposer."
    ),
    "apps/library/reports.py record(subject_type.value) tenant_id=tenant_id actor=actor title=subject_title": (
        "A problem report. Its tenant id is the reporter's zone, None only for platform "
        "staff, and create_report's contract is that subject_title is the record's public "
        "reference: what the reader typed goes in the report row, never in the audit title."
    ),
    "apps/taxonomy/tenant_lists_logic.py record('vocabulary') tenant_id=tenant.id actor=actor title=f'{list_name}:{row_key}'": (
        "A tenant's own copy of a list row: `tenant.id` is a bank's id and never None, so "
        "the row stays in that bank's zone and no other tenant reads it."
    ),
    "apps/taxonomy/tenant_lists_logic.py record('vocabulary') tenant_id=tenant.id actor=actor title=f'{list_name}:{key}'": (
        "The same, for the other writes on a tenant's list rows."
    ),
    "apps/taxonomy/tenant_lists_logic.py record('vocabulary') tenant_id=tenant.id actor=actor title=list_name": (
        "The same, for a reorder of one tenant's list."
    ),
    # c8-seed-org-register
    "apps/shared/e2e_seed.py record(subject_type) tenant_id=tenant.id actor=Actor.system('seed_e2e') title=title": (
        "The E2E seed's one audit row per seeded organisation and register row: the tenant id is "
        "always the activated seeded bank's, never None, so the row stays in that bank's zone; the "
        "subject types are tenant tables and the title is a seed fixture's name or stable key."
    ),
}


def production_modules() -> list[Path]:
    modules = []
    for path in sorted(APPS_DIR.rglob("*.py")):
        rel = path.relative_to(APPS_DIR).as_posix()
        if "/migrations/" in rel or rel.split("/")[-1].startswith("tests_") or rel.endswith("/testing.py"):
            continue
        modules.append(path)
    return modules


def _quotes_normalised(text: str) -> str:
    """One quote style, so a fingerprint reads the same on every machine. `ast.unparse`
    chooses the quotes itself, and which it chooses for a quote nested inside an f-string
    changed within 3.12 (PEP 701): the same seed call fingerprinted with `f"..."` here and
    `f'...'` in CI, and the reviewed list failed on a machine that had reviewed nothing new
    (2026-09-20)."""
    return text.replace('"', "'")


def _module_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level `NAME = <expr>` as source, so a call naming a constant reads like the
    value it stands for (`SUBJECT_TYPE`, `ACTOR`)."""
    constants: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            constants[node.targets[0].id] = ast.unparse(node.value)
    return constants


def _argument(call: ast.Call, name: str, constants: dict[str, str]) -> str:
    for keyword in call.keywords:
        if keyword.arg == name:
            source = ast.unparse(keyword.value)
            return constants.get(source, source) if isinstance(keyword.value, ast.Name) else source
    return "<missing>"


def _library_record_calls() -> dict[str, str]:
    """Fingerprint -> where it is, for every `record()` call that can write a row with no
    tenant under a library subject type. A subject type the source does not spell out
    counts as one, and so does a tenant id it does not spell out: both are decided at
    runtime, and `tenant_id=principal.tenant_id` is None under a platform session. The
    guard fails closed on either, because a value it cannot read is a value it cannot
    clear."""
    found: dict[str, str] = {}
    library_types = {f"'{name}'" for name in LIBRARY_SUBJECT_TYPES}
    for path in production_modules():
        rel = f"apps/{path.relative_to(APPS_DIR).as_posix()}"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = _module_constants(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func
            name = called.id if isinstance(called, ast.Name) else called.attr if isinstance(called, ast.Attribute) else None
            if name != "record":
                continue
            subject = _argument(node, "subject_type", constants)
            spelled_out = subject.startswith(("'", '"'))
            if spelled_out and subject not in library_types:
                continue  # a row no tenant ever reads (a proposal, a platform sign-in)
            fingerprint = _quotes_normalised(
                f"{rel} record({subject}) tenant_id={_argument(node, 'tenant_id', constants)} "
                f"actor={_argument(node, 'actor', constants)} "
                f"title={_argument(node, 'subject_title', constants)}"
            )
            found[fingerprint] = f"{rel}:{node.lineno}"
    return found


class LibraryAuditRowsCarryNoTenantWords(SimpleTestCase):
    """AUD-01, hardening H3. `GET /audit-events` shows every tenant the rows without a
    tenant whose subject is a library record. A title built from a tenant's own words
    there would show one bank's work to all of them, and no test would notice."""

    def test_every_such_record_call_has_been_reviewed(self) -> None:
        found = _library_record_calls()
        reviewed = {_quotes_normalised(call) for call in REVIEWED_LIBRARY_RECORD_CALLS}
        unreviewed = {
            f"{where}  ->  {fingerprint}"
            for fingerprint, where in found.items()
            if fingerprint not in reviewed
        }
        self.assertEqual(
            unreviewed,
            set(),
            "a record() call writes a row with no tenant under a library subject type, and every tenant reads it.\n"
            "Check that its actor is the system, an agent or platform staff and that its title is not a tenant's\n"
            "words, then add its line to REVIEWED_LIBRARY_RECORD_CALLS with the reason:\n  "
            + "\n  ".join(sorted(unreviewed)),
        )

    def test_the_reviewed_list_holds_no_call_that_has_gone(self) -> None:
        stale = {_quotes_normalised(call) for call in REVIEWED_LIBRARY_RECORD_CALLS} - set(_library_record_calls())
        self.assertEqual(stale, set(), "these reviewed calls no longer exist; drop them:\n  " + "\n  ".join(sorted(stale)))

    def test_the_guard_sees_the_calls_it_is_meant_to_see(self) -> None:
        # The applier and the reference seed are the writers of library rows today; a guard
        # that found nothing would pass for the wrong reason.
        modules = {where.split(":")[0] for where in _library_record_calls().values()}
        self.assertIn("apps/proposals/apply.py", modules)
        self.assertIn("apps/library/seeds/library.py", modules)
        # And the calls whose tenant id is decided at runtime, which the guard used to walk
        # past: these are the shape of the call it exists for (review 2026-09-20).
        self.assertIn("apps/taxonomy/tenant_lists_logic.py", modules)
