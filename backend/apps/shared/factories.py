"""Test factories (playbook 2.2). Plain functions, no factory library: each takes the
fields a test cares about and fills the rest deterministically. Values come from
arguments or counters, never from `random` (a seed must reproduce).

Every factory that writes a tenant row activates that tenant first, because the test
runner's own connection is the table owner and FORCE ROW LEVEL SECURITY applies to it
too: a tenant row is invisible and unwritable until `tenancy.activate()` has run in the
transaction (playbook 14). The activation lasts until the test's savepoint is rolled
back, or until the next factory activates another tenant.

**No factory here writes or names a library model.** The library fence
(apps/shared/tests_library_fence.py) treats this file as a production module, so it may
neither open `library_write()` or `watch_write()` nor name a `LibraryModel` beside a
write call — that is what keeps a fixture from being a way round the fence. Builders that
need one live in the app's own `testing.py`, which the fence exempts:

| What you want | Where it is |
|---|---|
| An instrument, a provision, an obligation | `apps/library/testing.py` |
| A source, a source check, a change with its timeline, pages, flags, scope terms and obligation links | `apps/watch/testing.py` |
| An agent, a platform key bound to it, a platform run | `apps/agents/testing.py` |
| A bank's case, its obligation-link decision, two banks with different footprints | `apps/cases/testing.py` |
"""

from __future__ import annotations

import itertools
import uuid
from datetime import timedelta
from collections.abc import Iterable
from types import SimpleNamespace
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.taxonomy.models import ApprovalStatus, ComplianceStatus, FootprintChangeRequest, Team, TeamLabel, VocabularySuggestion
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies
from apps.identity import roles_logic, tokens
from apps.identity.models import (
    ApiKey,
    Invitation,
    InvitationKind,
    InvitationRole,
    Membership,
    MembershipRole,
    PasskeyDeviceType,
    PlatformRole,
    PlatformRoleAssignment,
    TenantRole,
    User,
    UserStatus,
    WebAuthnCredential,
)
from apps.library.models import Language
from apps.library import testing as library_testing
from apps.library.seeds import LANGUAGES, seed_jurisdictions, seed_languages
from apps.register.logic import ensure_register_entry
from apps.register.models import Applicability, DutyOccurrence, SoaUnit, TenantObligationScope
from apps.shared import tenancy
from apps.shared.audit import Actor, ActorType
from apps.shared.models import Tenant, TenantContentLanguage
from apps.tenants.models import Licence, OrgUnit, OrgUnitKind, SupportAccess, TeamMember, TenantProduct
from apps.tenants.testing import licence_type_term

_counter = itertools.count(1)


def language(key: str = "en") -> Language:
    name, config = LANGUAGES[key]
    row, _ = Language.objects.get_or_create(key=key, defaults={"name": name, "text_search_config": config})
    return row


def tenant(*, name: str | None = None, slug: str | None = None, timezone: str = "Europe/Stockholm") -> Tenant:
    """A tenant with its system roles and English as its language. Leaves it activated."""
    n = next(_counter)
    english = language("en")
    row = Tenant.objects.create(name=name or f"Test Tenant {n}", slug=slug or f"test-tenant-{n}", timezone=timezone, default_language=english)
    with transaction.atomic():
        tenancy.activate(row.id)
        TenantContentLanguage.objects.create(tenant=row, language=english, sort_order=0)
        roles_logic.ensure_system_roles(row)
        # The tenant's own lists (chunk 2, apps/taxonomy/tenant_hooks.py), as a new tenant has them.
        ensure_tenant_vocabularies(row, actor=Actor.system("test_factory"))
    return row


def user(*, email: str | None = None, name: str | None = None, status: UserStatus = UserStatus.ACTIVE) -> User:
    n = next(_counter)
    return User.objects.create(email=email or f"person-{n}@test.example", name=name or f"Person {n}", status=status.value)


def member(tenant: Tenant, *, roles: Iterable[str] = ("reader",), user_row: User | None = None, title: str = "") -> Membership:
    """A membership in `tenant` holding the given system role keys. Activates the tenant."""
    person = user_row or user()
    with transaction.atomic():
        tenancy.activate(tenant.id)
        membership = Membership.objects.create(tenant=tenant, user=person, title=title)
        for role in roles_logic.roles_by_keys(tenant.id, list(roles)):
            MembershipRole.objects.create(tenant=tenant, membership=membership, role=role)
    return membership


def member_user(tenant: Tenant, *, roles: Iterable[str] = ("reader",)) -> User:
    """The tenant-isolation guard's record for member routes: the user whose id is the path parameter."""
    return member(tenant, roles=roles).user


def platform_user(*, roles: Iterable[str] = ("platform_admin",), email: str | None = None) -> User:
    roles_logic.ensure_platform_roles()
    person = user(email=email)
    for key in roles:
        PlatformRoleAssignment.objects.create(user=person, role=PlatformRole.objects.get(key=key))
    return person


def passkey(user_row: User, *, nickname: str = "Laptop", public_key: str = "", credential_id: str | None = None) -> WebAuthnCredential:
    n = next(_counter)
    return WebAuthnCredential.objects.create(
        user=user_row,
        credential_id=credential_id or tokens.b64url(f"cred-{n}".encode()),
        public_key=public_key or tokens.b64url(b"\x00" * 77),
        sign_count=0,
        transports=["internal"],
        aaguid="00000000-0000-0000-0000-000000000000",
        device_type=PasskeyDeviceType.MULTI_DEVICE.value,
        backup_eligible=True,  # what registration stores for a multi-device passkey
        backed_up=True,
        nickname=nickname,
    )


def invitation(tenant: Tenant, *, email: str | None = None, roles: Iterable[str] = ("reader",), kind: InvitationKind = InvitationKind.INVITE) -> Invitation:
    """An open invitation in `tenant`. Returns the row; the plain token is `row.plain_token`."""
    n = next(_counter)
    token = tokens.new_token(16)
    with transaction.atomic():
        tenancy.activate(tenant.id)
        row = Invitation.objects.create(
            tenant=tenant,
            email=email or f"invitee-{n}@test.example",
            token_hash=tokens.hash_token(token),
            kind=kind.value,
            expires_at=timezone.now() + timedelta(hours=72),
        )
        for role in roles_logic.roles_by_keys(tenant.id, list(roles)):
            InvitationRole.objects.create(tenant=tenant, invitation=row, role=role)
    row.plain_token = token  # type: ignore[attr-defined]
    return row


def api_key(tenant: Tenant, *, name: str = "Agent key", scopes: Iterable[str] = ("library:read",)) -> SimpleNamespace:
    """A live key in `tenant`: `.id`, `.row` (the ApiKey) and `.plain_key` (shown once).

    `scopes` are written as given, so a test can stand up a key a bank could only hold from
    before the watch writes became platform-only (PLATFORM_ONLY_SCOPES): such a key works
    without them (apps/identity/api_keys_logic.py:resolve_api_key). The default is one a
    bank's key may hold today."""
    plain, prefix, key_hash = tokens.new_api_key()
    with transaction.atomic():
        tenancy.activate(tenant.id)
        row = ApiKey.objects.create(tenant=tenant, name=name, key_prefix=prefix, key_hash=key_hash, scopes=list(scopes))
    return SimpleNamespace(id=row.id, row=row, plain_key=plain)


def tenant_role_key(tenant: Tenant) -> SimpleNamespace:
    """The tenant-isolation guard's record for role routes, addressed by key: a custom
    role of `tenant` whose `.id` is its key."""
    n = next(_counter)
    with transaction.atomic():
        tenancy.activate(tenant.id)
        role = TenantRole.objects.create(tenant=tenant, key=f"custom-role-{n}", permissions=["cases.read"])
    return SimpleNamespace(id=role.key, role=role)


def footprint_request(tenant: Tenant) -> FootprintChangeRequest:
    """The tenant-isolation guard's record for footprint request routes: the tenant's
    pending request, reused when one waits, because a second cannot (FP-S6)."""
    with transaction.atomic():
        tenancy.activate(tenant.id)
        waiting = FootprintChangeRequest.objects.filter(tenant=tenant, status=ApprovalStatus.PENDING.value).first()  # ordering: at most one pending row per tenant, by constraint
    if waiting is not None:
        return waiting
    requester = member_user(tenant, roles=("compliance_officer",))
    with transaction.atomic():
        tenancy.activate(tenant.id)
        return FootprintChangeRequest.objects.create(tenant=tenant, requested_by=requester)


def vocabulary_suggestion(tenant: Tenant) -> SimpleNamespace:
    """The tenant-isolation guard's record for suggestion routes. Its path carries the list
    as well as the id, so it names both: a list that exists means the only thing between
    another tenant and the record is tenancy, not an "unknown list" 404."""
    suggester = member_user(tenant)
    with transaction.atomic():
        tenancy.activate(tenant.id)
        row = VocabularySuggestion.objects.create(
            tenant=tenant, list_name="tenant_tag", key=f"suggested-{next(_counter)}", suggested_by=suggester
        )
    return SimpleNamespace(id=row.id, params={"list_name": "tenant_tag"})


def obligation_participant(tenant: Tenant) -> SimpleNamespace:
    """The tenant-isolation guard's record for the register-entry participant routes: a
    person taking part in `tenant`'s register entry for an obligation private to `tenant`.
    The obligation is built by `apps/collab/testing.py`, which the library fence exempts."""
    from apps.collab import testing as collab_testing

    return collab_testing.participant_on_private_obligation(tenant)


def user_actor(*, label: str = "Test Person", user_id: uuid.UUID | None = None) -> Actor:
    return Actor(kind=ActorType.USER, id=user_id or uuid.uuid4(), label=label)


def agent_actor(*, label: str = "Test Agent", agent_id: uuid.UUID | None = None) -> Actor:
    return Actor(kind=ActorType.AGENT, id=agent_id or uuid.uuid4(), label=label)


# ---------------------------------------------------------------------------------------
# c9-case-contract: the tenant-isolation guard's records for the case workflow routes.
# A case names a library change, so the case itself is built by `apps/cases/testing.py`
# (the fence exempts it); the children are this bank's own rows and are built here.
# ---------------------------------------------------------------------------------------
def case_change(tenant: Tenant) -> SimpleNamespace:
    """A change with a case of `tenant`, addressed by the change's id as every workflow
    route addresses it. Another bank has no case for it, so tenancy alone answers 404."""
    from apps.cases import testing as case_build

    row = case_build.case_on_a_new_change(tenant)
    return SimpleNamespace(id=row.change_id, case=row)


def case_action(tenant: Tenant) -> SimpleNamespace:
    """A live action on a case of `tenant`, addressed by its own id."""
    from apps.cases.models import Action

    row = case_change(tenant).case
    owner = member_user(tenant, roles=("compliance_officer",))
    with transaction.atomic():
        tenancy.activate(tenant.id)
        action = Action.objects.create(
            tenant=tenant,
            case=row,
            title="Document the research criteria",
            owner=owner,
            due_date=timezone.localdate(),
            created_by=owner,
        )
    return SimpleNamespace(id=action.id, case=row)


def case_evidence(tenant: Tenant) -> SimpleNamespace:
    """A live piece of evidence (a link, so no bytes) on a case of `tenant`, by its own id."""
    from apps.cases.models import Evidence, EvidenceKind

    row = case_change(tenant).case
    uploader = member_user(tenant, roles=("compliance_officer",))
    with transaction.atomic():
        tenancy.activate(tenant.id)
        evidence = Evidence.objects.create(
            tenant=tenant,
            case=row,
            kind=EvidenceKind.LINK.value,
            name="FI decision memo",
            url="https://intranet.example.com/memo/42",
            uploaded_by=uploader,
            # A link has no bytes to scan, so it is recorded clean (CasesEvidence.scanState).
            scan_state="clean",
            scanned_at=timezone.now(),
        )
    return SimpleNamespace(id=evidence.id, case=row)
# c8-tenants-contract: the tenant-isolation guard's records for the chunk 8 tenants routes
# (TEN-02, TEN-03, TEN-06). A licence's type is a library term this file may not write;
# apps/tenants/testing.py, which the library fence exempts, writes it.
# ---------------------------------------------------------------------------------------
def org_unit(tenant: Tenant, *, name: str | None = None) -> OrgUnit:
    """A department of `tenant` (a business area), which needs no legal-entity term."""
    with transaction.atomic():
        tenancy.activate(tenant.id)
        return OrgUnit.objects.create(
            tenant=tenant, kind=OrgUnitKind.BUSINESS_AREA.value, name=name or f"Business area {next(_counter)}"
        )


def licence(tenant: Tenant) -> Licence:
    """A licence held by a department of `tenant`; its type is the one test term."""
    unit = org_unit(tenant=tenant)
    term = licence_type_term()
    with transaction.atomic():
        tenancy.activate(tenant.id)
        return Licence.objects.create(tenant=tenant, org_unit=unit, licence_type=term)


def tenant_product(tenant: Tenant, *, name: str | None = None) -> TenantProduct:
    with transaction.atomic():
        tenancy.activate(tenant.id)
        return TenantProduct.objects.create(tenant=tenant, name=name or f"Product {next(_counter)}")


def team_key(tenant: Tenant) -> SimpleNamespace:
    """A team of `tenant`, addressed by key: `.id` is its key, which no other bank's team
    shares, so the only thing between another bank and the team is tenancy."""
    with transaction.atomic():
        tenancy.activate(tenant.id)
        team = Team.objects.create(tenant=tenant, key=f"team-{next(_counter)}")
    return SimpleNamespace(id=team.key, team=team)


def support_access(tenant: Tenant) -> SupportAccess:
    """A support-access row of `tenant`, as chunk 1's recovery writes one."""
    requester = platform_user()
    with transaction.atomic():
        tenancy.activate(tenant.id)
        return SupportAccess.objects.create(
            tenant=tenant, platform_user=requester, reason="The bank's watch feed stopped updating.", started_at=timezone.now()
        )


# c8-ten-teams-people (TEN-02, TEN-03): a named team with its English label and department,
# the people in it, and a department with a head.
def team(tenant: Tenant, *, key: str, label: str, org_unit: OrgUnit | None = None, members: Iterable[User] = ()) -> Team:
    with transaction.atomic():
        tenancy.activate(tenant.id)
        row = Team.objects.create(tenant=tenant, key=key, org_unit=org_unit)
        TeamLabel.objects.create(tenant=tenant, vocabulary=row, language="en", text=label, is_original=True)
        for person in members:
            TeamMember.objects.create(tenant=tenant, team=row, user=person)
    return row


def department(tenant: Tenant, *, name: str, head: User | None, kind: OrgUnitKind = OrgUnitKind.BUSINESS_AREA) -> OrgUnit:
    with transaction.atomic():
        tenancy.activate(tenant.id)
        return OrgUnit.objects.create(tenant=tenant, kind=kind.value, name=name, head_user=head)
# c8-reg-status: the tenant-isolation guard's record for a legal entity's register row.
def register_entity(tenant: Tenant) -> SimpleNamespace:
    """A legal entity of `tenant`. The route reads the entity under row-level security before
    it looks at the obligation, so another bank asking for it is refused as if it never
    existed; apps/register/tests_status.py proves the same under a real shared obligation."""
    from apps.tenants.models import OrgUnit, OrgUnitKind

    with transaction.atomic():
        tenancy.activate(tenant.id)
        entity = OrgUnit.objects.create(tenant=tenant, kind=OrgUnitKind.LEGAL_ENTITY.value, name=f"Example Entity {next(_counter)} AB")
    return SimpleNamespace(id=entity.id, params={"obligation_id": uuid.uuid4()})
# --- c8-reg-gaps-risk (REG-03) ----------------------------------------------------------
def gap(tenant: Tenant) -> Any:
    """The tenant-isolation guard's record for gap routes: an open gap of `tenant`, with a
    waiting risk acceptance so the approval has something to decide, on a library obligation
    built for it by the library's own builders (this file writes no library model)."""
    from apps.library import testing as library_testing
    from apps.library.seeds import seed_jurisdictions, seed_languages
    from apps.register.models import Gap
    from apps.register.logic import ensure_register_entry
    from apps.taxonomy.models import GapSource, GapStatus, RiskAcceptanceReason, RiskRating
    from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms

    n = next(_counter)
    with transaction.atomic():
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()
        act = library_testing.instrument(key=f"gap-act-{n}", regime="regime:securities")
        duty = library_testing.obligation(act, key=f"gap-duty-{n}")
    person = member_user(tenant, roles=("compliance_officer",))
    with transaction.atomic():
        tenancy.activate(tenant.id)
        entry = ensure_register_entry(tenant_id=tenant.id, obligation_id=duty.id, actor=user_actor(user_id=person.id))
        return Gap.objects.create(
            tenant=tenant,
            tenant_obligation=entry,
            title=f"Gap {n}",
            severity=RiskRating.objects.get(key="high"),
            source=GapSource.objects.get(key="audit"),
            status=GapStatus.objects.get(key="open"),
            identified_by=person,
            acceptance_reason=RiskAcceptanceReason.objects.get(key="other"),
            acceptance_requested_by=person,
            acceptance_requested_at=timezone.now(),
        )


# c8-reg-links-history (REG-05): the tenant-isolation guard's record for DELETE /internal-links/{id}.
def internal_link(tenant: Tenant) -> SimpleNamespace:
    """A live link of `tenant` to a fresh library obligation, with the item it points at.
    The obligation comes from apps/library/testing.py, the one place a test writes the
    library; the reference rows it needs are seeded idempotently first."""
    from apps.library import testing as library_testing
    from apps.library.seeds import seed_jurisdictions, seed_languages
    from apps.register.logic import ensure_register_entry
    from apps.register.models import InternalLink
    from apps.taxonomy.models import LinkKind
    from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms
    from apps.tenants.models import InternalItem

    n = next(_counter)
    with transaction.atomic():
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()
    act = library_testing.instrument(key=f"factory-act-{n}", regime="regime:securities")
    duty = library_testing.obligation(act, key=f"factory-act-{n}/1")
    person = member_user(tenant, roles=("compliance_officer",))
    actor = Actor(kind=ActorType.USER, id=person.id, label=person.name)
    with transaction.atomic():
        tenancy.activate(tenant.id)
        entry = ensure_register_entry(tenant_id=tenant.id, obligation_id=duty.id, actor=actor)
        item = InternalItem.objects.create(tenant=tenant, kind=LinkKind.objects.get(key="policy"), name=f"Policy {n}")
        link = InternalLink.objects.create(
            tenant=tenant, tenant_obligation=entry, internal_item=item, label=item.name, created_by=person
        )
    return SimpleNamespace(id=link.id, link=link)


# --- c8-reg-applicability ---------------------------------------------------------------
def legal_entity(tenant: Tenant, *, name: str = "Example Bank AB", entity_term_id: uuid.UUID | None = None, active: bool = True) -> OrgUnit:
    """An org unit of the legal-entity kind in `tenant`, carrying the entity term whose id is
    given (a `legal_entity` dimension term, by id so this file names no library model)."""
    with transaction.atomic():
        tenancy.activate(tenant.id)
        return OrgUnit.objects.create(
            tenant=tenant, kind=OrgUnitKind.LEGAL_ENTITY.value, name=name, entity_term_id=entity_term_id, active=active
        )


# c8-reg-units (REG-08, D-41): the tenant-isolation guard's record for unit routes.
def soa_unit(tenant: Tenant) -> SoaUnit:
    """A live Statement of Applicability unit of `tenant`: under a fresh standard's
    conformance duty (built by apps/library/testing.py), for a legal entity whose
    conformance row applies, so the only thing between another tenant and it is tenancy."""
    n = next(_counter)
    with transaction.atomic():
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()
        edition = library_testing.instrument(
            key=f"unit-standard-{n}", jurisdiction="intl", regime="regime:ai_ict", level="standard", binding=False
        )
        duty = library_testing.obligation(edition, key=f"unit-standard-{n}-conformance", duty_type="governance")
    officer = member_user(tenant, roles=("compliance_officer",))
    with transaction.atomic():
        tenancy.activate(tenant.id)
        entry = ensure_register_entry(tenant_id=tenant.id, obligation_id=duty.id, actor=user_actor(user_id=officer.id))
        status = ComplianceStatus.objects.get(is_default=True, active=True)
        entity = OrgUnit.objects.create(tenant=tenant, kind=OrgUnitKind.LEGAL_ENTITY.value, name=f"Entity {n} AB")
        scope = TenantObligationScope.objects.create(
            tenant=tenant,
            tenant_obligation=entry,
            org_unit=entity,
            applicability=Applicability.APPLIES.value,
            applicability_reason="Certified",
            applicability_decided_at=timezone.now(),
            applicability_decided_by=officer,
            compliance_status=status,
        )
        return SoaUnit.objects.create(tenant=tenant, scope=scope, reference=f"X.{n}", title="Our own words", compliance_status=status)


# c8-duty-occurrences (REG-07): the tenant-isolation guard's record for the completion route.
def duty_occurrence(tenant: Tenant) -> DutyOccurrence:
    """An upcoming occurrence of a fresh obligation's quarterly duty (both built by
    apps/library/testing.py) on `tenant`'s register entry, so the only thing between another
    tenant and it is tenancy."""
    n = next(_counter)
    with transaction.atomic():
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()
        law = library_testing.instrument(key=f"duty-law-{n}", regime="regime:securities")
        duty = library_testing.recurring_duty(library_testing.obligation(law, key=f"duty-law-{n}-report"))
    officer = member_user(tenant, roles=("compliance_officer",))
    with transaction.atomic():
        tenancy.activate(tenant.id)
        entry = ensure_register_entry(tenant_id=tenant.id, obligation_id=duty.obligation_id, actor=user_actor(user_id=officer.id))
        return DutyOccurrence.objects.create(tenant=tenant, recurring_duty=duty, tenant_obligation=entry, due_date=timezone.localdate())


def case_participant(tenant: Tenant) -> SimpleNamespace:
    """c9-case-participants: a member of `tenant` taking part in a case of `tenant`, for a
    change no other bank has a case for. `.id` is the participation, `.params` names the
    change, as the case participant routes address it."""
    from apps.collab.models import Participant

    row = case_change(tenant).case
    officer = member_user(tenant, roles=("compliance_officer",))
    person = member_user(tenant)
    with transaction.atomic():
        tenancy.activate(tenant.id)
        participation = Participant.objects.create(tenant=tenant, case=row, user=person, added_by=officer)
    return SimpleNamespace(id=participation.id, params={"change_id": row.change_id})


# ---------------------------------------------------------------------------------------
# c9-case-file-export: a case worked from triage to sign-off, for the case file (CAS-07).
# ---------------------------------------------------------------------------------------
def closed_case(tenant: Tenant, *, actions: int = 2, evidence: int = 3, so_what_confirmed: bool = True) -> SimpleNamespace:
    """A case of `tenant` signed off by a second person, with everything its file prints: a
    "So what?", a saved assessment, `actions` actions (the first done, the second removed,
    the rest open) and `evidence` pieces (a scanned file, a link, then removed files), the
    whole transition ledger and the sign-off's audit row carrying its step-up. An
    unconfirmed "So what?" stays the AI's draft."""
    from apps.cases.models import Action, CaseTransition, ChangeCase, Evidence, EvidenceKind, ImpactAssessment
    from apps.shared.audit import record
    from apps.taxonomy.models import CaseStatusCategory, ClosureReason, EffortSize

    row = case_change(tenant).case
    owner = member_user(tenant, roles=("compliance_officer",))
    approver = member_user(tenant, roles=("approver",))
    now = timezone.now()
    step_up = uuid.uuid4()
    with transaction.atomic():
        tenancy.activate(tenant.id)
        confirmation = {"so_what_confirmed_by": owner, "so_what_confirmed_at": now} if so_what_confirmed else {}
        ChangeCase.objects.filter(pk=row.pk).update(
            status=CaseStatusCategory.CLOSED.value,
            owner=owner,
            urgency_confirmed=True,
            so_what_text="Our research payment model must be documented before the rules apply.",
            so_what_confirmed=so_what_confirmed,
            triaged_by=owner,
            triaged_at=now,
            signoff_requested_by=owner,
            signoff_requested_at=now,
            signed_off_by=approver,
            close_reason=ClosureReason.objects.get(key="signed_off"),
            closed_at=now,
            closed_note="Signed off after the board meeting.",
            **confirmation,
        )
        ImpactAssessment.objects.create(
            tenant=tenant,
            case=row,
            applies="partly",
            why="The equity desk buys research from three brokers.",
            what_must_change="Written criteria for research budgets.",
            internal_deadline=timezone.localdate() + timedelta(days=30),
            effort=EffortSize.objects.get(key="m"),
            saved=True,
            saved_by=owner,
            saved_at=now,
        )
        for index in range(actions):
            Action.objects.create(
                tenant=tenant,
                case=row,
                title=f"Action {index + 1}: document the research criteria",
                owner=owner,
                due_date=timezone.localdate() + timedelta(days=index),
                created_by=owner,
                done_at=now if index == 0 else None,
                done_by=owner if index == 0 else None,
                removed_at=now if index == 1 else None,
                removed_by=owner if index == 1 else None,
            )
        for index in range(evidence):
            is_link = index == 1
            Evidence.objects.create(
                tenant=tenant,
                case=row,
                kind=EvidenceKind.LINK.value if is_link else EvidenceKind.FILE.value,
                name=f"Evidence {index + 1}: board minutes",
                url="https://intranet.example.com/minutes/7" if is_link else "",
                storage_key="" if is_link else f"tenants/{tenant.id}/evidence/{uuid.uuid4()}",
                content_hash="" if is_link else f"{index:064x}",
                size_bytes=None if is_link else 1024,
                mime_type="" if is_link else "application/pdf",
                uploaded_by=owner,
                removed_at=now if index >= 2 else None,
                scan_state="clean",
                scanned_at=now,
            )
        path = ["", "new", "assigned", "assessing", "implementing", "signoff", "closed"]
        for before, after in itertools.pairwise(path):
            CaseTransition.objects.create(
                tenant=tenant,
                case=row,
                from_status=before,
                to_status=after,
                by_user=approver if after == "closed" else owner,
                note="Checked against the minutes." if after == "closed" else "",
            )
        record(
            action="case.moved",
            actor=Actor(kind=ActorType.USER, id=approver.id, label=approver.name),
            subject_type="change_case",
            subject_id=row.id,
            subject_title=row.change.title,
            summary=f"{approver.name} signed off a case.",
            tenant_id=tenant.id,
            after={"status": "closed"},
            step_up_assertion_id=step_up,
        )
    row.refresh_from_db()
    return SimpleNamespace(case=row, change_id=row.change_id, owner=owner, approver=approver, step_up=step_up)
