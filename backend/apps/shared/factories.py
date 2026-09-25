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

from django.db import transaction
from django.utils import timezone

from apps.taxonomy.models import ApprovalStatus, FootprintChangeRequest, Team, VocabularySuggestion
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
from apps.library.seeds import LANGUAGES
from apps.shared import tenancy
from apps.shared.audit import Actor, ActorType
from apps.shared.models import Tenant, TenantContentLanguage
from apps.tenants.models import Licence, OrgUnit, OrgUnitKind, SupportAccess, TenantProduct
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


def user_actor(*, label: str = "Test Person", user_id: uuid.UUID | None = None) -> Actor:
    return Actor(kind=ActorType.USER, id=user_id or uuid.uuid4(), label=label)


def agent_actor(*, label: str = "Test Agent", agent_id: uuid.UUID | None = None) -> Actor:
    return Actor(kind=ActorType.AGENT, id=agent_id or uuid.uuid4(), label=label)


# ---------------------------------------------------------------------------------------
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
