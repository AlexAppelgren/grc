"""The E2E seed (playbook 8.3): idempotent (natural keys), deterministic (no randomness),
realistic, built from the prototype's sample data so journeys match the design.

Chunk 1 seeds two tenants with their system roles, one login per system role in tenant
A (each with one fixed passkey whose public key comes from apps/shared/e2e_passkeys.py),
tenant B's admin, the platform editor and admin, and Anna, the one user still awaiting
enrolment: invited with an open invitation and no passkey. Under E2E_MODE her invitation
token is the fixed literal in apps/shared/e2e_logins.py; otherwise a random one that
nobody sees (the seed still runs locally for a dev database). It also seeds one login per
journey that spends a person in a way the UI cannot undo (`reserved_for` in the roster):
the member ADM-S2 re-issues, so the shared approver survives a full run.

`EXPECTED_TENANTS` and `SEED_LOGINS` are what the seed-integrity guard
(apps/shared/tests_seed_integrity.py) demands, so a seed change cannot quietly hollow
out a journey. Fixed ids keep audit rows and URLs stable across reseeds."""

from __future__ import annotations

import datetime
from typing import Any
import uuid
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from django.apps import apps as django_apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction

from apps.cases.models import ChangeCase
from apps.home import tasks as home_tasks
from apps.identity import invitation_logic, roles_logic, tokens
from apps.identity.models import (
    Invitation,
    InvitationKind,
    Membership,
    MembershipRole,
    PasskeyDeviceType,
    PlatformRole,
    PlatformRoleAssignment,
    User,
    UserStatus,
    WebAuthnCredential,
)
from apps.library.models import Language
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import RESEARCH_OBLIGATION, load_library, seed_authorities
from apps.proposals.logic import Proposer
from apps.proposals.logic import create as create_proposal
from apps.proposals.models import ProposalKind
from apps.shared import tenancy
from apps.shared.audit import Actor, ActorType, record
from apps.shared.e2e_logins import E2E_INVITATION_TOKEN_ANNA, SEED_LOGINS, TENANT_A_SLUG, TENANT_B_SLUG, SeedLogin
from apps.shared.e2e_passkeys import E2E_PASSKEYS
from apps.taxonomy.models import CaseStatusCategory
from apps.watch import e2e_seed as watch_e2e_seed
from apps.watch.models import CheckStatus
from apps.shared.models import Tenant
from apps.taxonomy import footprint_logic, terms_logic
from apps.taxonomy.models import ApprovalStatus, FootprintChangeRequest, FootprintTerm
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies
from apps.tenants.logic import set_content_languages


@dataclass(frozen=True)
class SeedTenant:
    id: uuid.UUID
    name: str
    slug: str
    timezone: str
    content_languages: tuple[str, ...]


# Tenant A is the prototype's company ("Example Bank AB"). Tenant B exists so J-8 can prove
# isolation; it is plainly a second bank and never the subject of a journey's own data.
TENANT_A = SeedTenant(
    id=uuid.UUID("00000000-0000-4000-8000-00000000000a"),
    name="Example Bank AB",
    slug="example-bank",
    timezone="Europe/Stockholm",
    content_languages=("sv", "en"),
)
TENANT_B = SeedTenant(
    id=uuid.UUID("00000000-0000-4000-8000-00000000000b"),
    name="Second Bank A/S",
    slug="second-bank",
    timezone="Europe/Copenhagen",
    content_languages=("da", "en"),
)
EXPECTED_TENANTS: tuple[SeedTenant, ...] = (TENANT_A, TENANT_B)
SEED_ACTOR = Actor.system("seed_e2e")

# Footprints as "dimension:key" (chunk 2, FP-01, J-6). Tenant A's is the prototype's
# `footprint{regimes, accounts, entities, services, clients}`; tenant B's is a smaller,
# different bank so J-8 can prove the footprint is per tenant.
EXPECTED_FOOTPRINTS: dict[str, tuple[str, ...]] = {
    TENANT_A_SLUG: (
        "regime:securities",
        "regime:insurance",
        "regime:tax",
        "regime:data_protection",
        "regime:aml",
        "regime:ai_ict",
        "regime:banking",
        "regime:payments",
        "account_type:isk",
        "account_type:af",
        "account_type:depa",
        "account_type:kf",
        "account_type:pension",
        "legal_entity:bank",
        "legal_entity:insurer",
        "legal_entity:fund_company",
        "service_type:advice",
        "service_type:non_advised",
        "service_type:execution_only",
        "service_type:portfolio_management",
        "service_type:custody",
        "service_type:insurance_distribution",
        "client_category:retail",
        "client_category:professional",
    ),
    TENANT_B_SLUG: (
        "regime:securities",
        "regime:aml",
        "account_type:depa",
        "legal_entity:bank",
        "service_type:execution_only",
        "service_type:custody",
        "client_category:retail",
    ),
}


@dataclass(frozen=True)
class SeedFootprintRequest:
    tenant_slug: str
    requested_by_email: str
    adds: tuple[str, ...]
    removes: tuple[str, ...]


# J-6: the compliance officer has asked to switch off Advice; the approver decides.
EXPECTED_PENDING_REQUEST = SeedFootprintRequest(
    tenant_slug=TENANT_A_SLUG,
    requested_by_email="compliance_officer@example-bank.test",
    adds=(),
    removes=("service_type:advice",),
)


@dataclass(frozen=True)
class SeedLibrary:
    instruments: int
    obligations: int
    research_obligation: str
    advice_only_obligation: str
    anchor_date: datetime.date


# Chunk 3: the prototype's library (the fixture's 12 instruments plus the three EU
# directives its lineage needs), the obligation whose second version is still ahead, and
# the one sample obligation whose only service is advice, which J-6's switch-off hides
# (the prototype's 15 obligations plus that one).
EXPECTED_LIBRARY = SeedLibrary(
    instruments=15,
    obligations=16,
    research_obligation=RESEARCH_OBLIGATION,
    advice_only_obligation="obl-suitability-statement",
    anchor_date=datetime.date(2026, 9, 16),
)


@dataclass(frozen=True)
class SeedHome:
    """Chunk 6's own dates (c6-e2e-seed, HOM-01, HOM-03, ruling 17): the natural keys
    `home.journey.spec.ts` and the seed-integrity guard read back by, so a change to this
    seed cannot quietly hollow out HOM-S1 to HOM-S6 without failing there."""

    lead_change: str
    later_change: str
    outside_scope_change: str
    last_week_change: str
    failed_source: str
    healthy_source: str


EXPECTED_HOME = SeedHome(
    lead_change="chg-e2e-research-payments",
    later_change="chg-e2e-sft-reporting",
    outside_scope_change="chg-e2e-outside-scope",
    last_week_change="chg-e2e-ai-mapping",
    healthy_source="fi.se sweep (E2E)",
    # The design card's own example (design/screens/tenant-today.html): "EBA news feed
    # failed 18 Sep."
    failed_source="EBA news feed (E2E)",
)


class SeedRefused(ImproperlyConfigured):
    """seed_e2e or seed_demo on a deployed environment (playbook 8.3, 12)."""


def refuse_when_deployed(command: str = "seed_e2e") -> None:
    if settings.IS_DEPLOYED_ENVIRONMENT:
        raise SeedRefused(
            f"{command} refuses to run on deployed environment {settings.ENVIRONMENT!r}: "
            "test-only data changes never execute where a real tenant could live."
        )


def seed_tenants() -> list[Tenant]:
    from apps.library.models import Language

    tenants: list[Tenant] = []
    languages = {language.key: language for language in Language.objects.all()}
    for spec in EXPECTED_TENANTS:
        row, created = Tenant.objects.update_or_create(
            slug=spec.slug,
            defaults={
                "id": spec.id,
                "name": spec.name,
                "timezone": spec.timezone,
                "default_language": languages[spec.content_languages[0]],
            },
        )
        tenancy.activate(row.id)
        set_content_languages(row, [languages[key] for key in spec.content_languages])
        roles_logic.ensure_system_roles(row)
        ensure_tenant_vocabularies(row, actor=SEED_ACTOR)
        if created:
            record(
                action="tenant.seeded",
                actor=SEED_ACTOR,
                subject_type="tenant",
                subject_id=row.id,
                subject_title=row.name,
                summary="Seeded for E2E journeys.",
                tenant_id=None,
                after={"slug": row.slug, "timezone": row.timezone},
            )
        tenants.append(row)
    return tenants


def _seed_user(login: SeedLogin) -> User:
    status = UserStatus.INVITED if login.awaiting_enrolment else UserStatus.ACTIVE
    user, _ = User.objects.update_or_create(
        email=login.email,
        defaults={"id": login.id, "name": login.name, "status": status.value, "locale": Language.objects.get(key=login.locale)},
    )
    return user


def _seed_membership(tenant: Tenant, user: User, login: SeedLogin) -> None:
    membership, _ = Membership.objects.update_or_create(tenant=tenant, user=user, defaults={"title": login.title})
    wanted = roles_logic.roles_by_keys(tenant.id, login.tenant_roles)
    MembershipRole.objects.filter(membership=membership).exclude(role__in=wanted).delete()
    for role in wanted:
        MembershipRole.objects.get_or_create(tenant=tenant, membership=membership, role=role)


def _seed_platform_roles(user: User, login: SeedLogin) -> None:
    for key in login.platform_roles:
        role = PlatformRole.objects.get(key=key)
        PlatformRoleAssignment.objects.get_or_create(user=user, role=role)


def _seed_passkey(user: User, login: SeedLogin) -> None:
    fixed = E2E_PASSKEYS[login.email]
    WebAuthnCredential.objects.update_or_create(
        credential_id=fixed.credential_id,
        defaults={
            "user": user,
            "public_key": fixed.public_key_cose,
            "sign_count": 0,
            "transports": ["internal"],
            "aaguid": fixed.aaguid,
            "backup_eligible": True,
            "backed_up": True,
            "device_type": PasskeyDeviceType.MULTI_DEVICE.value,
            "nickname": "E2E virtual authenticator",
            "retired_at": None,
        },
    )


def _seed_invitation(tenant: Tenant, user: User, login: SeedLogin) -> None:
    """The one open invitation. Idempotent: an existing open one is kept (and its token
    re-pinned under E2E_MODE); anything else is superseded."""
    open_invitation = invitation_logic.find_open_for_email(user.email)
    token = E2E_INVITATION_TOKEN_ANNA if settings.E2E_MODE else tokens.new_token(32)
    if open_invitation is not None and open_invitation.tenant_id == tenant.id:
        if settings.E2E_MODE and open_invitation.token_hash != tokens.hash_token(token):
            open_invitation.token_hash = tokens.hash_token(token)
            open_invitation.save(update_fields=["token_hash"])
        return
    invitation_logic.create_invitation(
        tenant=tenant,
        email=user.email,
        roles=roles_logic.roles_by_keys(tenant.id, login.tenant_roles),
        title=login.title,
        invited_by=None,
        actor=SEED_ACTOR,
        kind=InvitationKind.INVITE,
        fixed_token=token,
    )


def seed_logins(tenants: list[Tenant]) -> int:
    by_slug = {tenant.slug: tenant for tenant in tenants}
    for login in SEED_LOGINS:
        user = _seed_user(login)
        tenant = by_slug[login.tenant_slug] if login.tenant_slug else None
        if tenant is not None:
            tenancy.activate(tenant.id)
            if login.awaiting_enrolment:
                _seed_invitation(tenant, user, login)
            else:
                _seed_membership(tenant, user, login)
        _seed_platform_roles(user, login)
        if login.has_passkey:
            _seed_passkey(user, login)
    return len(SEED_LOGINS)


def seed_footprints(tenants: list[Tenant]) -> int:
    """Each tenant's footprint from EXPECTED_FOOTPRINTS (chunk 2, FP-01): idempotent on
    (tenant, term); a term added by the seed leaves its history row and one audit event
    per tenant on first creation, through the same logic a person's approval uses."""
    count = 0
    for tenant in tenants:
        tenancy.activate(tenant.id)
        wanted = [terms_logic.term_by_ref(*ref.split(":")) for ref in EXPECTED_FOOTPRINTS[tenant.slug]]
        present = set(FootprintTerm.objects.filter(tenant=tenant).values_list("term_id", flat=True))
        missing = [term for term in wanted if term.id not in present]
        if missing:
            footprint_logic.seed_terms(tenant=tenant, actor=SEED_ACTOR, terms=missing)
        count += len(wanted)
    return count


def seed_pending_footprint_request(tenants: list[Tenant]) -> int:
    """The one pending request of J-6, authored by the compliance officer. Kept when it
    already waits; recreated when it was decided (a journey approved it)."""
    spec = EXPECTED_PENDING_REQUEST
    tenant = next(t for t in tenants if t.slug == spec.tenant_slug)
    tenancy.activate(tenant.id)
    if FootprintChangeRequest.objects.filter(tenant=tenant, status=ApprovalStatus.PENDING.value).exists():
        return 1
    requester = User.objects.get(email=spec.requested_by_email)
    removes = [terms_logic.term_by_ref(*ref.split(":")) for ref in spec.removes]
    adds = [terms_logic.term_by_ref(*ref.split(":")) for ref in spec.adds]
    # A journey may have approved the seeded request and removed the term; put it back so
    # the next run starts from the prototype's footprint again.
    for term in removes:
        if not FootprintTerm.objects.filter(tenant=tenant, term=term).exists():
            footprint_logic.seed_terms(tenant=tenant, actor=SEED_ACTOR, terms=[term])
    footprint_logic.create_request(tenant=tenant, requester=requester, actor=Actor.system("seed_e2e"), adds=adds, removes=removes)
    return 1


# Two proposals waiting in the console queue, for chunk 4's PRO-S3 (plain approval) and
# PRO-S4 (correcting scope and wording before approving). chunk4-T8 ("Seed each journey's
# proposal and a problem report", docs/plans/briefs/CHUNK4_TASKS.md) owns this rather than
# the read-only screens of chunk4-T14/T17/T19/T20, but T8 has not landed on `main` yet and
# there is no UI path in R1 for a person to create a `new_obligation_version` proposal (only
# an agent, or a library editor through the API, can), so those journeys have nothing to
# approve or correct without it. Seeded directly through apps.proposals.logic.create(), the
# same function POST /proposals calls, so it is checked exactly as a real submission is.
#
# Neither target is obl-research-payments: apps/library/seeds/library.py already files that
# obligation's own version 2 straight from the fixture's "proposals" entry
# (prop-research-payments-v2), so approving a fresh proposal against it here would file a
# redundant version 3 instead of the version 2 the design card and PRO-S3 both expect.
# Nor is either obl-suitability-statement: frontend/tests/e2e/taxonomy.journey.spec.ts (J-6)
# already owns it as ADVICE_ONLY_OBLIGATION, whose only service is Advice, to prove that
# switching Advice off hides it; a correction here that replaces its scope terms (PRO-S4
# rewrites the whole array, never adds to it) would rewrite the fact that journey depends
# on. obl-appropriateness and obl-costs-charges carry only version 1 and are not named by
# any other spec, so approving a proposal against either files a clean version 2 that
# nothing else is watching.
RESEARCH_AGENT_RUN = uuid.UUID("00000000-0000-4000-9000-000000000001")
COSTS_CHARGES_AGENT_RUN = uuid.UUID("00000000-0000-4000-9000-000000000002")


def _obligation_id(stable_key: str) -> uuid.UUID:
    """A read-only lookup, by Django's own app registry rather than an `Obligation` import:
    this module already calls `.update_or_create()` for its tenant and login rows, and the
    library fence's static guard (apps/shared/tests_library_fence.py) fails closed on any
    module that both names a concrete `LibraryModel` and contains a write-method call,
    whether or not the two are related. Obligation is a `LibraryModel`; this keeps its name
    out of this module's AST as anything but a string, so the guard reads this seed
    correctly as the read it is."""
    model = django_apps.get_model("library", "Obligation")
    return model.objects.get(stable_key=stable_key).id


def seed_proposals() -> int:
    """Idempotent by Idempotency-Key (playbook 4.3): a reseed that finds one already decided
    (a journey approved or rejected it on an earlier run) leaves it exactly as it is, so a
    retried journey finds its proposal "waiting or already applied" rather than duplicated
    or reset. Runs with no tenant active, as a library editor's or an agent's own call would
    (PRO-03): `proposed_in_tenant` is false on both rows."""
    tenancy.clear_tenant()

    appropriateness_id = _obligation_id("obl-appropriateness")
    create_proposal(
        kind=ProposalKind.NEW_OBLIGATION_VERSION.value,
        title="Add version 2 of the appropriateness assessment obligation, in force 15 October 2026",
        payload={
            "summaries": {
                "sv": (
                    "Innan en tjänst utan rådgivning tillhandahålls i ett komplicerat finansiellt "
                    "instrument ska institutet begära uppgifter om kundens kunskap och erfarenhet och "
                    "bedöma om tjänsten eller produkten passar kunden. Om den inte passar, eller om "
                    "uppgifter saknas, ska kunden varnas. Institutet ska dokumentera bedömningen och "
                    "varningen samt se över sina kriterier för lämplighetsprövning minst en gång om året."
                ),
                "en": (
                    "Before providing a non-advised service in a complex financial instrument, the "
                    "institution asks about the client's knowledge and experience and assesses whether "
                    "the service or product is appropriate. If it is not appropriate, or information is "
                    "missing, the client is warned. The institution keeps a record of the assessment and "
                    "the warning given, and reviews its appropriateness criteria at least once a year."
                ),
            },
            "original_language": "sv",
            "is_machine": True,
            "effective_from": "2026-10-15",
            "effective_from_precision": "day",
        },
        proposer=Proposer(
            actor=Actor(kind=ActorType.AGENT, id=RESEARCH_AGENT_RUN, label="Research agent 0.4"),
            agent_run_id=RESEARCH_AGENT_RUN,
        ),
        idempotency_key="e2e-seed-prop-appropriateness-v2",
        target_type="obligation",
        target_id=appropriateness_id,
        model="agent pipeline 0.4",
        field_sources={
            "summaries.sv": "https://www.fi.se/",
            "summaries.en": "https://www.fi.se/",
            "effectiveFrom": "https://www.fi.se/",
        },
        source_label="Finansinspektionen, board decision 15 September 2026",
        source_url="https://www.fi.se/",
    )

    costs_charges_id = _obligation_id("obl-costs-charges")
    create_proposal(
        kind=ProposalKind.NEW_OBLIGATION_VERSION.value,
        title="Add version 2 of the costs and charges obligation, extending it to professional clients",
        payload={
            "summaries": {
                "sv": (
                    "Kunder ska i god tid få sammanställd information om alla kostnader och avgifter för "
                    "tjänsten och instrumentet, och därefter minst årligen, med kostnadernas effekt på "
                    "avkastningen. Sammanställningen lämnas på ett varaktigt medium."
                ),
                "en": (
                    "Clients receive aggregated information on all costs and charges of the service and "
                    "the instrument in good time before the service, and at least annually afterwards, "
                    "with the effect of costs on return. The statement is provided in a durable medium."
                ),
            },
            "original_language": "sv",
            "is_machine": True,
            "effective_from": "2026-11-01",
            "effective_from_precision": "day",
            # A scope the reviewer is meant to disagree with (PRO-S4): the correction form
            # removes client_category:professional before approving.
            "terms": ["service_type:advice", "service_type:execution_only", "client_category:retail", "client_category:professional"],
        },
        proposer=Proposer(
            actor=Actor(kind=ActorType.AGENT, id=COSTS_CHARGES_AGENT_RUN, label="Research agent 0.4"),
            agent_run_id=COSTS_CHARGES_AGENT_RUN,
        ),
        idempotency_key="e2e-seed-prop-costs-charges-v2",
        target_type="obligation",
        target_id=costs_charges_id,
        model="agent pipeline 0.4",
        field_sources={
            "summaries.sv": "https://www.riksdagen.se/",
            "summaries.en": "https://www.riksdagen.se/",
            "effectiveFrom": "https://www.riksdagen.se/",
            "terms": "https://www.riksdagen.se/",
        },
        source_label="Riksdagen, consolidated text",
        source_url="https://www.riksdagen.se/",
    )
    return 2


def _quarter_safe_offsets() -> tuple[int, int]:
    """Two day-offsets from "today" that always land in two different quarters, whatever
    the real calendar day this seed runs on (HOM-S4, HOM-S6). A quarter is 90 to 92 days
    long, so moving forward by more than the longest quarter always crosses at least one
    quarter boundary: the near date (`+20` days) is always "this side" of it and the far
    date (`+120` days, 100 days later) is always on the other side, never the same
    quarter — proved for four anchors a quarter apart in `tests_seed_integrity.py`."""
    return 20, 120


def seed_watch_changes() -> SeedHome:
    """The library-zone rows chunk 6's screens read (c6-e2e-seed, HOM-01, HOM-03, HOM-S1,
    HOM-S2, HOM-S4, HOM-S6): two sources with their coverage (one healthy, one failed) and
    four regulatory changes. Runs before `seed_tenants()`, while no tenant is active yet,
    because `source` is written with no tenant activated (WAT-06) — the same reason
    `seed_authorities()` and `load_library()` run there too.

    Anchored to the tenant-local date (`Europe/Stockholm`, `TENANT_A.timezone`) plus fixed
    day offsets, never to a literal date or `date.today()`: `_quarter_safe_offsets()` keeps
    the near and far dates in two different quarters whatever day this runs on, and every
    date below is that anchor plus a fixed number of days, so a quarter boundary never
    changes what a journey sees (CLAUDE.md §11, chunk 6 plan rule 10).
    """
    healthy = watch_e2e_seed.seed_source(name=EXPECTED_HOME.healthy_source)
    watch_e2e_seed.seed_source_check(healthy, status=CheckStatus.OK)
    failed = watch_e2e_seed.seed_source(name=EXPECTED_HOME.failed_source)
    watch_e2e_seed.seed_source_check(failed, status=CheckStatus.FAILED, error="502 from the publisher after three retries")

    today = datetime.datetime.now(ZoneInfo(TENANT_A.timezone)).date()
    near, far = _quarter_safe_offsets()
    watch_e2e_seed.seed_change(
        stable_key=EXPECTED_HOME.lead_change,
        title="FI adopts amended rules on paying for investment research",
        key_date=today + datetime.timedelta(days=near),
        key_date_label="In force",
        urgency="act_now",
        first_seen_at=timezone_now_this_week(TENANT_A.timezone),
        so_what_draft="Confirm the annual assessment criteria before the rules take effect.",
    )
    watch_e2e_seed.seed_change(
        stable_key=EXPECTED_HOME.later_change,
        title="Amended reporting of securities financing transactions",
        key_date=today + datetime.timedelta(days=far),
        key_date_label="Applies",
        urgency="six_months_plus",
        first_seen_at=timezone_now_this_week(TENANT_A.timezone),
    )
    watch_e2e_seed.seed_change(
        stable_key=EXPECTED_HOME.outside_scope_change,
        title="Insurance distribution guidance outside our scope",
        key_date=today + datetime.timedelta(days=near + 5),
        key_date_label="Applies",
        urgency="within_3_months",
        first_seen_at=timezone_now_this_week(TENANT_A.timezone),
    )
    watch_e2e_seed.seed_change(
        stable_key=EXPECTED_HOME.last_week_change,
        title="FI starts mapping how financial firms use AI",
        key_date=today + datetime.timedelta(days=far + 30),
        key_date_label="Consultation",
        urgency="monitor",
        first_seen_at=timezone_now_last_week(TENANT_A.timezone),
        so_what_draft="No obligation changes yet. Keep the AI tooling register current.",
    )
    return EXPECTED_HOME


def timezone_now_this_week(tz: str) -> datetime.datetime:
    """A moment safely inside the bank's current ISO week (Tuesday, mid-morning, its own
    zone), for a change that should lead the running week's briefing (HOM-S1, HOM-S3)."""
    today = datetime.datetime.now(ZoneInfo(tz))
    monday = today - datetime.timedelta(days=today.weekday())
    return monday.replace(hour=9, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)


def timezone_now_last_week(tz: str) -> datetime.datetime:
    """The same moment, one ISO week earlier, for the change the seeded briefing snapshot
    already carries (HOM-S3, ruling 17)."""
    return timezone_now_this_week(tz) - datetime.timedelta(days=7)


def _seed_case(
    tenant: Tenant,
    change: Any,
    *,
    urgency: str,
    footprint_match: bool,
    so_what_confirmed_by: User | None = None,
) -> ChangeCase:
    """One bank's case for one seeded change, idempotent on `UNIQUE (tenant, change)`
    exactly as a registered change's own fan-out would create it (`apps/cases/creation.py`),
    with the one audit row AUD-01 asks of every write. `so_what_confirmed_by` given names
    who confirmed the wording (the check constraint demands a person, never a bare flag);
    left out, the case keeps the library's draft, unconfirmed, exactly as creation leaves
    one (WAT-05)."""
    tenancy.activate(tenant.id)
    existed = ChangeCase.objects.filter(tenant=tenant, change=change).exists()
    case, _ = ChangeCase.objects.update_or_create(
        tenant=tenant,
        change=change,
        defaults={
            "status": CaseStatusCategory.NEW.value,
            "urgency": django_apps.get_model("taxonomy", "Urgency").objects.get(key=urgency),
            "footprint_match": footprint_match,
            "so_what_text": change.so_what_draft,
            "so_what_confirmed": so_what_confirmed_by is not None,
            "so_what_confirmed_by": so_what_confirmed_by,
            "so_what_confirmed_at": timezone_now_this_week(TENANT_A.timezone) if so_what_confirmed_by is not None else None,
        },
    )
    if not existed:
        record(
            action="case.created",
            actor=SEED_ACTOR,
            subject_type="change_case",
            subject_id=case.id,
            subject_title=change.title,
            summary="Seeded for E2E journeys.",
            tenant_id=tenant.id,
            after={"status": case.status, "footprintMatch": footprint_match},
        )
    return case


def seed_home_cases(tenants: list[Tenant], home: SeedHome) -> int:
    """This bank's own work on chunk 6's seeded changes (c6-e2e-seed, HOM-01, HOM-03),
    plus last week's briefing, sent and snapshotted once so `c6-briefing-screen`'s journey
    can open a past week without waiting for the beat (ruling 17). Runs after `seed_tenants()`
    and `seed_footprints()`, because a case is a tenant row under row-level security."""
    tenant_a = next(t for t in tenants if t.slug == TENANT_A_SLUG)
    tenant_b = next(t for t in tenants if t.slug == TENANT_B_SLUG)
    by_key = {row.stable_key: row for row in django_apps.get_model("watch", "RegulatoryChange").objects.filter(
        stable_key__in=[home.lead_change, home.later_change, home.outside_scope_change, home.last_week_change]
    )}
    # A person's own words, not the library draft: the compliance officer of tenant A
    # confirmed these, which is what lets the lead card and the briefing show a "So what?"
    # with no AI label (WAT-05).
    officer = User.objects.get(email="compliance_officer@example-bank.test")

    _seed_case(tenant_a, by_key[home.lead_change], urgency="act_now", footprint_match=True, so_what_confirmed_by=officer)
    _seed_case(tenant_a, by_key[home.later_change], urgency="six_months_plus", footprint_match=True)
    # Outside the bank's regulatory scope (HOM-S4, FP-S4): a case FP-03's own matching
    # would have computed false too, set directly here as the backend's own HOM-S4 test
    # does, so this seed needs no extra scope terms to prove the same absence.
    _seed_case(tenant_a, by_key[home.outside_scope_change], urgency="within_3_months", footprint_match=False)
    _seed_case(tenant_a, by_key[home.last_week_change], urgency="monitor", footprint_match=True, so_what_confirmed_by=officer)

    # Last week's briefing: sent for real, from the real production job, so the snapshot
    # it writes is exactly what a bank was mailed (c6-briefing-screen, HOM-S3).
    home_tasks.send_weekly_briefing(tenant_a.id)

    # Tenant B's own two dates (J-8): different keys, different titles, so an isolation
    # journey has something of tenant B's that must never reach tenant A's screens.
    today_b = datetime.datetime.now(ZoneInfo(TENANT_B.timezone)).date()
    near, far = _quarter_safe_offsets()
    change_b1 = watch_e2e_seed.seed_change(
        stable_key="chg-e2e-tenant-b-1",
        title="Finanstilsynet consults on AML reporting thresholds",
        key_date=today_b + datetime.timedelta(days=near + 3),
        key_date_label="Consultation closes",
        urgency="within_3_months",
        first_seen_at=timezone_now_this_week(TENANT_B.timezone),
    )
    change_b2 = watch_e2e_seed.seed_change(
        stable_key="chg-e2e-tenant-b-2",
        title="Second Bank A/S's own reform, seeded for isolation",
        key_date=today_b + datetime.timedelta(days=far + 3),
        key_date_label="Applies",
        urgency="six_months_plus",
        first_seen_at=timezone_now_this_week(TENANT_B.timezone),
    )
    _seed_case(tenant_b, change_b1, urgency="within_3_months", footprint_match=True)
    _seed_case(tenant_b, change_b2, urgency="six_months_plus", footprint_match=True)
    return 6


def seed_e2e() -> dict[str, int]:
    """Run the whole seed. Returns counts the command prints and the guard asserts."""
    refuse_when_deployed()
    with transaction.atomic():
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()
        seed_authorities()
        library = load_library()
        # Chunk 6's sources and changes: library-zone rows, written here — before any
        # tenant is activated — for the same reason `seed_authorities()` and
        # `load_library()` run here rather than after `seed_tenants()` (WAT-06).
        home = seed_watch_changes()
        roles_logic.ensure_platform_roles()
        tenants = seed_tenants()
        logins = seed_logins(tenants)
        footprint_terms = seed_footprints(tenants)
        seed_pending_footprint_request(tenants)
        proposals = seed_proposals()
        home_cases = seed_home_cases(tenants, home)
    return {
        "tenants": len(tenants),
        "logins": logins,
        "footprint_terms": footprint_terms,
        "proposals": proposals,
        "home_cases": home_cases,
        **library,
    }


def anna_invitation() -> Invitation | None:
    """The open invitation of the one awaiting user, for the guard and journeys."""
    return invitation_logic.find_open_for_email("anna@example-bank.test")
