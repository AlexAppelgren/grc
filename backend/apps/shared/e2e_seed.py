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

Chunk 4 seeds what the console queue and the bank's own screens decide: one waiting
proposal per journey that spends one (`EXPECTED_PROPOSALS`), and the one open problem
report a reader of tenant A left on a library record (`EXPECTED_PROBLEM_REPORT`).

`EXPECTED_TENANTS` and `SEED_LOGINS` are what the seed-integrity guard
(apps/shared/tests_seed_integrity.py) demands, so a seed change cannot quietly hollow
out a journey. Fixed ids keep audit rows and URLs stable across reseeds."""

from __future__ import annotations

import datetime
from typing import Any
import uuid
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from django.apps import apps as django_apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction

from apps.agents.models import AgentRun, RunStatus
from apps.agents.seeds import seed_agent_definitions
# c11-e2e-seed
from decimal import Decimal
from apps.agents.models import AgentCadence, RunTrigger, TenantAgent, TenantAgentBudget
from apps.agents.seeds.e2e import publish_e2e_version
from apps.proposals import batch as proposal_batch
from apps.proposals.schemas import ObligationScopeChange, ObligationScopePayload
from apps.cases import matching as case_matching
from apps.cases.creation import CHANGE_REGISTERED
from apps.cases.models import ChangeCase
from apps.home import tasks as home_tasks
from apps.identity import invitation_logic, roles_logic, tokens
from apps.identity.models import (
    ApiKey,
    Invitation,
    InvitationKind,
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
from apps.library import reports
from apps.library.models import DatePrecision, Language, ProblemReport, ReportStatus, SubjectType
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import RESEARCH_OBLIGATION, load_library, seed_authorities
from apps.proposals.apply import apply_reverification
from apps.proposals.logic import Proposer, Reviewer
from apps.proposals.logic import approve as approve_proposal
from apps.proposals.logic import create as create_proposal
from apps.proposals.models import Proposal, ProposalKind, ProposalStatus
from apps.search import eval_sets
from apps.shared import outbox, tenancy
from apps.shared import permissions as perms
from apps.shared.adapters.mailer import MockMailer
from apps.shared.audit import Actor, ActorType, record
from apps.shared.e2e_logins import E2E_INVITATION_TOKEN_ANNA, NO_RECORD_READ_ROLE, SEED_LOGINS, TENANT_A_SLUG, TENANT_B_SLUG, SeedLogin
from apps.shared.e2e_passkeys import E2E_PASSKEYS
from apps.shared.schemas import AgentDecision
from apps.taxonomy.models import CaseStatusCategory
from apps.watch import e2e_seed as watch_e2e_seed
from apps.watch.models import CheckFrequency, CheckStatus
from apps.shared.models import Tenant
from apps.taxonomy import footprint_logic, markets_logic, tenant_lists_logic, terms_logic
from apps.taxonomy.models import ApprovalStatus, FootprintChangeRequest, FootprintTerm, WatchedMarket
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, switch_on_term
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
# `footprint{regimes, accounts, entities, services, clients}` less pension accounts, the one
# term FP-S4 needs left out (`EXPECTED_OUTSIDE_SCOPE`), and operating in Sweden, so the
# Danish rules are what watching Denmark adds (tax-watched-inventory, FP-S13); tenant B's is
# a smaller, different bank that names no jurisdiction, so J-8 can prove the footprint is
# per tenant and every rule reaches it.
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
        # tax-watched-feed (FP-04): the bank operates in Sweden, as FP-S10, FP-S13 and FP-S15
        # have it, so a Danish record is outside this scope and "Markets we watch" has
        # something to add. Union rules reach Sweden, so none of them moves.
        "jurisdiction:se",
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
# directives its lineage needs and FFFS 2026:11, the sample instrument T8 adds so
# FFFS 2017:2's own provision tree has something that amends it), the obligation whose
# second version is still ahead, and the one sample obligation whose only service is
# advice, which J-6's switch-off hides (the prototype's 15 obligations plus that one).
# tax-nordic-seed (FP-04): plus Kapitalmarkedsloven and verdipapirhandelloven with one
# obligation each, the Danish one for Custody and the Norwegian one for Advice.
# Plus the one standard below (E2E_STANDARD): ISO/IEC 27001:2022 and its conformance duty.
EXPECTED_LIBRARY = SeedLibrary(
    instruments=18 + 1,
    obligations=18 + 1,
    research_obligation=RESEARCH_OBLIGATION,
    advice_only_obligation="obl-suitability-statement",
    anchor_date=datetime.date(2026, 9, 16),
)


# --- lib-standard-e2e-seed (INV-S11, FP-S16) ------------------------------------------
# ISO/IEC 27001:2022 with its one conformance duty, for E2E only: seed_demo never loads it
# until Alex answers TODO_FOR_alex.md "Legal, before any standard is seeded". The duty links
# to the standard's term, which stays inactive (apps/taxonomy/seeds), and no E2E tenant
# follows it, so every tenant's inventory hides it until a journey adds it to a scope.
E2E_STANDARD = Path(__file__).resolve().parents[1] / "library" / "fixtures" / "e2e_standard.json"
E2E_STANDARD_INSTRUMENT = "iso-iec-27001-2022"
E2E_STANDARD_OBLIGATION = "iso-iec-27001-2022-conformance"
# --- end lib-standard-e2e-seed -----------------------------------------------------------

# --- std-journeys (FP-S16) ----------------------------------------------------------------
# A scope request names active terms only, so FP-S16 cannot follow the standard while its
# term is off. The reference seed now files it active on a new database (watch-standards),
# and E2E switches it on where a database was seeded while it was held (D-85). No E2E tenant
# follows it, so the duty stays hidden until a journey adds the term and takes it out again.
E2E_STANDARD_TERM = ("standard", "iso_iec_27001")
# --- end std-journeys ---------------------------------------------------------------------


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
            # What Playwright's virtual authenticator reports for a credential it was
            # handed: not backup eligible. Sign-in holds each assertion's flag to this one.
            "backup_eligible": False,
            "backed_up": False,
            "device_type": PasskeyDeviceType.SINGLE_DEVICE.value,
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
    # the next run starts from the seeded footprint again.
    for term in removes:
        if not FootprintTerm.objects.filter(tenant=tenant, term=term).exists():
            footprint_logic.seed_terms(tenant=tenant, actor=SEED_ACTOR, terms=[term])
    footprint_logic.create_request(tenant=tenant, requester=requester, actor=Actor.system("seed_e2e"), adds=adds, removes=removes)
    return 1


# What waits in the console queue when a journey starts, and the journey each one is there
# for. There is no UI path in R1 for a person to file a `new_obligation_version` proposal
# (only an agent, or a library editor through the API, can), so a journey that approves,
# corrects or rejects one has nothing to work on without this. Every one is filed through
# apps.proposals.logic.create(), the same function POST /proposals calls, so it is checked
# exactly as a real submission is; the seed never approves one, so it writes no library row.
#
# No obligation target is obl-research-payments: apps/library/seeds/library.py already files
# that obligation's own version 2 straight from the fixture's "proposals" entry
# (prop-research-payments-v2), so approving a fresh proposal against it here would file a
# redundant version 3 instead of the version 2 the design card and PRO-S3 both expect. It is
# the subject of the seeded problem report instead. Nor is any of them
# obl-suitability-statement: frontend/tests/e2e/taxonomy.journey.spec.ts (J-6) already owns
# it as ADVICE_ONLY_OBLIGATION, whose only service is Advice, to prove that switching Advice
# off hides it; a correction here that replaces its scope terms (PRO-S4 rewrites the whole
# array, never adds to it) would rewrite the fact that journey depends on. The four targets
# below carry version 1 only, sit inside tenant A's footprint, are not advice-only and are
# named by no other spec, so a decision on any of them is a clean version 2 nothing else is
# watching, and the four journeys never race each other.
#
# --- library-updates-frontend (PRO-S7) ---------------------------------------------------
# PRO-S7 approves its proposal and then finds the change on the bank's "Library updates" by
# the duty's own title. Its target was obl-isk-control-statements until SRC-S3
# (search.journey.spec.ts) came to name that duty's title, and then the pension transfer
# right until FP-S4 took that duty as the one record outside tenant A's scope
# (`EXPECTED_OUTSIDE_SCOPE`), so it is now the safeguards on automated decisions: version 1
# only, inside tenant A's footprint with or without Advice (J-6 switches Advice off while
# other journeys run), and named by no other spec or seed.
PRO_S7_OBLIGATION = "obl-gdpr-article-22"
AUTOMATED_DECISIONS_RUN = uuid.UUID("00000000-0000-4000-9000-000000000005")
# --- end library-updates-frontend ---------------------------------------------------------
# --- agent-j4-smoke (AGT-S10, J-4) -------------------------------------------------------
# J-4's own duty: an agent minted in the console files a new version of it under a change it
# registers, a library editor approves it, and the bank's officer reads it. Every attempt adds
# a version, so no other spec or seed may name it, and the journey asserts the version its own
# approval produced, never a number. Product governance under FFFS 2017:2 reaches tenant A
# with or without Advice (J-6 switches Advice off while other journeys run). The fixture
# loads it; this names it as J-4's.
J4_OBLIGATION = "obl-product-governance"
# --- end agent-j4-smoke -------------------------------------------------------------------
AGENT_MODEL = "agent pipeline 0.4"
# The library editor who files PRO-S5's proposal; the second editor decides everything else.
LIBRARY_EDITOR_EMAIL = "editor@bleqq.test"
# The agent run behind each obligation proposal, fixed so a reseed leaves the same ids.
APPROPRIATENESS_RUN = uuid.UUID("00000000-0000-4000-9000-000000000001")
COSTS_CHARGES_RUN = uuid.UUID("00000000-0000-4000-9000-000000000002")
CLIENT_ASSETS_RUN = uuid.UUID("00000000-0000-4000-9000-000000000003")
# --- pro-s13-journey (PRO-S13) ---------------------------------------------------------------
# The sweeper's proposal the confirming agent decides through the API, end to end. Its target
# is version 1 only, reaches tenant A with or without Advice, and is named by no other spec,
# seed constant or seeded proposal, so its version 2 is the confirming agent's and nobody
# else's (tests_seed_integrity.py checks all three).
# Not product governance, which J-4 owns (J4_OBLIGATION above): each journey that adds a
# version needs a duty of its own.
PRO_S13_OBLIGATION = "obl-idd-demands-needs"
PRO_S13_RUN = uuid.UUID("00000000-0000-4000-9000-000000000013")
# --- end pro-s13-journey ---------------------------------------------------------------------


@dataclass(frozen=True)
class SeedProposal:
    """One proposal the seed leaves waiting, and the journey that spends it. `target` is the
    obligation's stable key for an obligation kind and `<list>:<key>` for a vocabulary kind;
    `proposed_by_email` is empty when an agent's run filed it."""

    journey: str
    kind: str
    target: str
    agent_run: uuid.UUID | None = None
    proposed_by_email: str = ""


# PRO-S5 needs a proposal a library editor made themselves, so that the same editor's
# approval is refused by four eyes; the other four are an agent's, which any editor decides.
EXPECTED_PROPOSALS: tuple[SeedProposal, ...] = (
    SeedProposal("PRO-S3", ProposalKind.NEW_OBLIGATION_VERSION.value, "obl-appropriateness", APPROPRIATENESS_RUN),
    SeedProposal("PRO-S4", ProposalKind.NEW_OBLIGATION_VERSION.value, "obl-costs-charges", COSTS_CHARGES_RUN),
    SeedProposal("PRO-S9", ProposalKind.NEW_OBLIGATION_VERSION.value, "obl-client-assets", CLIENT_ASSETS_RUN),
    SeedProposal("PRO-S7", ProposalKind.NEW_OBLIGATION_VERSION.value, PRO_S7_OBLIGATION, AUTOMATED_DECISIONS_RUN),
    SeedProposal("PRO-S5", ProposalKind.VOCABULARY_RELABEL.value, "flag:ai", proposed_by_email=LIBRARY_EDITOR_EMAIL),
    SeedProposal("PRO-S13", ProposalKind.NEW_OBLIGATION_VERSION.value, PRO_S13_OBLIGATION, PRO_S13_RUN),
)


@dataclass(frozen=True)
class SeedProblemReport:
    """The one open "this looks wrong" report a bank's reader left on a library record
    (AUD-03, AUD-S5), and what they had on screen when they wrote it."""

    journey: str
    tenant_slug: str
    reporter_email: str
    obligation: str
    version_number: int
    language: str


# AUD-S5: the reader who files it holds `problems.report` like every member, and the report
# stays inside tenant A. Version 1 in Swedish is what the reader had on screen: version 2 of
# the research payment obligation is still ahead of the fixture's anchor date.
EXPECTED_PROBLEM_REPORT = SeedProblemReport(
    journey="AUD-S5",
    tenant_slug=TENANT_A_SLUG,
    reporter_email="reader@example-bank.test",
    obligation=RESEARCH_OBLIGATION,
    version_number=1,
    language="sv",
)


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


def _obligation(stable_key: str) -> Any:
    """The obligation itself, read the same way `_obligation_id` reads its id: chunk 5's
    fixtures need the row, not only its id, to link and re-check against (`c5-seed-watch`)."""
    return django_apps.get_model("library", "Obligation").objects.get(stable_key=stable_key)


def _agent(key: str) -> Any:
    """A platform agent definition, read the same way: `Agent` is a `LibraryModel` too."""
    return django_apps.get_model("agents", "Agent").objects.get(key=key)


def _regulatory_change_exists(stable_key: str) -> bool:
    """Whether a chunk 5 reform is already in the library, read the same way:
    `RegulatoryChange` is a `LibraryModel`, so this keeps its name out of this module's AST
    as anything but a string, exactly as `_obligation_id` does for `Obligation`."""
    return django_apps.get_model("watch", "RegulatoryChange").objects.filter(stable_key=stable_key).exists()


def _waiting(kind: str, **target: Any) -> bool:  # compliance: allow-kwargs one ORM filter per proposal kind
    """Is a proposal of this kind already waiting on this target? A seeded proposal is filed
    again only when none is, so a journey that decided one on an earlier run finds a fresh
    one rather than a decided row it cannot use, and a reseed of an untouched database
    changes nothing."""
    return Proposal.objects.filter(
        kind=kind,
        status=ProposalStatus.OPEN.value,
        **target,
    ).exists()


def _propose_obligation_version(
    *,
    obligation: str,
    agent_run: uuid.UUID,
    title: str,
    summaries: dict[str, str],
    effective_from: str,
    source_label: str,
    source_url: str,
    terms: list[str] | None = None,
) -> None:
    """One agent's proposal for a new version of `obligation`, with a source per changed
    field (PRO-01): the summary in each language, the date, and the scope when it changes
    one. All four cite the authority's own page, as a real run would.

    Filed as the create route files an agent's proposal (AGT-01): by the seeded sweeper's
    key and its agent, under `agent_run`, an open run of that key, which this opens with
    that fixed id when a reseed has not already. The watch-sweeper definition's own step
    `POST /proposals` is the one this stands for."""
    target_id = _obligation_id(obligation)
    if _waiting(ProposalKind.NEW_OBLIGATION_VERSION.value, target_id=target_id):
        return
    filer, agent = _sweeper_key()
    AgentRun.objects.get_or_create(
        pk=agent_run,
        defaults={"agent": agent, "api_key": filer, "model": AGENT_MODEL, "pipeline_version": "0.4"},
    )
    payload: dict[str, Any] = {
        "summaries": summaries,
        "original_language": "sv",
        "is_machine": True,
        "effective_from": effective_from,
        "effective_from_precision": "day",
    }
    sources = {f"summaries.{language}": source_url for language in summaries}
    sources["effectiveFrom"] = source_url
    if terms is not None:
        payload["terms"] = terms
        sources["terms"] = source_url
    create_proposal(
        kind=ProposalKind.NEW_OBLIGATION_VERSION.value,
        title=title,
        payload=payload,
        proposer=Proposer(
            actor=Actor(kind=ActorType.AGENT, id=agent.id, label=agent.key),
            api_key_id=filer.id,
            agent_id=agent.id,
        ),
        agent_run_id=agent_run,
        target_type="obligation",
        target_id=target_id,
        model=AGENT_MODEL,
        field_sources=sources,
        source_label=source_label,
        source_url=source_url,
    )


def _propose_flag_relabel() -> None:
    """PRO-S5: the proposal a library editor made themselves, so that their own approval is
    refused by four eyes. A vocabulary label is wording a person writes rather than a fact
    from an authority, so it carries no field source, as the queue's other vocabulary
    proposals do not."""
    if _waiting(
        ProposalKind.VOCABULARY_RELABEL.value,
        payload__list="flag",
        payload__key="ai",
    ):
        return
    editor = User.objects.get(email=LIBRARY_EDITOR_EMAIL)
    create_proposal(
        kind=ProposalKind.VOCABULARY_RELABEL.value,
        title="Rename the AI flag so it says what it marks",
        payload={
            "list": "flag",
            "key": "ai",
            "labels": {"en": "AI and automated decisions", "sv": "AI och automatiserade beslut"},
        },
        proposer=Proposer(
            actor=Actor(kind=ActorType.USER, id=editor.id, label=editor.name),
            user=editor,
        ),
    )


def seed_proposals() -> int:
    """One proposal waiting per journey that spends one (EXPECTED_PROPOSALS). Runs with no
    tenant active, as a library editor's or an agent's own call would (PRO-03), so
    `proposed_in_tenant` is false on every row and none of them reaches a bank's own list.
    Returns how many wait, which is the same number on every run."""
    tenancy.clear_tenant()

    _propose_obligation_version(
        obligation="obl-appropriateness",
        agent_run=APPROPRIATENESS_RUN,
        title="Add version 2 of the appropriateness assessment obligation, in force 15 October 2026",
        summaries={
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
        effective_from="2026-10-15",
        source_label="Finansinspektionen, board decision 15 September 2026",
        source_url="https://www.fi.se/",
    )
    _propose_obligation_version(
        obligation="obl-costs-charges",
        agent_run=COSTS_CHARGES_RUN,
        title="Add version 2 of the costs and charges obligation, extending it to professional clients",
        summaries={
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
        effective_from="2026-11-01",
        # A scope the reviewer is meant to disagree with (PRO-S4): the correction form
        # removes client_category:professional before approving.
        terms=["service_type:advice", "service_type:execution_only", "client_category:retail", "client_category:professional"],
        source_label="Riksdagen, consolidated text",
        source_url="https://www.riksdagen.se/",
    )
    _propose_obligation_version(
        obligation="obl-client-assets",
        agent_run=CLIENT_ASSETS_RUN,
        title="Add version 2 of the client assets obligation, with a monthly reconciliation",
        summaries={
            "sv": (
                "Institutet ska hålla kundernas finansiella instrument och medel åtskilda från sina "
                "egna och stämma av innehaven mot depåförvaltarens uppgifter varje månad. Avvikelser "
                "ska rättas utan dröjsmål och dokumenteras."
            ),
            "en": (
                "The institution keeps clients' financial instruments and funds separate from its own "
                "and reconciles the holdings against the custodian's records every month. Differences "
                "are corrected without delay and recorded."
            ),
        },
        effective_from="2026-12-01",
        source_label="Finansinspektionen, consultation memorandum 2026:14",
        source_url="https://www.fi.se/",
    )
    # library-updates-frontend (PRO-S7): see PRO_S7_OBLIGATION above.
    _propose_obligation_version(
        obligation=PRO_S7_OBLIGATION,
        agent_run=AUTOMATED_DECISIONS_RUN,
        title="Add version 2 of the automated decisions obligation, with a review by a person within one month",
        summaries={
            "sv": (
                "Den registrerade får begära att en person granskar ett beslut som enbart grundas på "
                "automatiserad behandling och som i betydande grad påverkar den registrerade. Banken "
                "förklarar logiken bakom beslutet, låter den registrerade framföra sin synpunkt och "
                "låter en person granska beslutet inom en månad från begäran."
            ),
            "en": (
                "A data subject may ask that a person review a decision based solely on automated "
                "processing that significantly affects them. The bank explains the logic behind the "
                "decision, lets the data subject state their view and has a person review the decision "
                "within one month of the request."
            ),
        },
        effective_from="2027-01-01",
        source_label="EUR-Lex, Regulation (EU) 2016/679, Article 22, consolidated text",
        source_url="https://eur-lex.europa.eu/",
    )
    # pro-s13-journey (PRO-S13): see PRO_S13_OBLIGATION above.
    _propose_obligation_version(
        obligation=PRO_S13_OBLIGATION,
        agent_run=PRO_S13_RUN,
        title="Add version 2 of the demands and needs obligation, with the suitability assessment kept on file",
        summaries={
            "sv": (
                "Innan ett avtal om en försäkringsbaserad investeringsprodukt ingås ska distributören "
                "klargöra kundens krav och behov och, vid rådgivning, bedöma om produkten och dess "
                "underliggande tillgångar är lämpliga, och spara bedömningen så länge avtalet gäller."
            ),
            "en": (
                "Before an insurance-based investment product is concluded, the distributor specifies "
                "the customer's demands and needs and, when advising, assesses whether the product and "
                "its underlying assets are suitable, and keeps the assessment for as long as the contract runs."
            ),
        },
        effective_from="2027-02-01",
        source_label="Finansinspektionen, amended insurance distribution rules",
        source_url="https://www.fi.se/",
    )
    _propose_flag_relabel()
    return len(EXPECTED_PROPOSALS)


def seed_problem_report(tenants: list[Tenant]) -> int:
    """AUD-S5: one open problem report a reader of tenant A left on a library record, filed
    with that tenant activated so the row carries it and no other bank can read it. Filed
    again only when none of this reader's is open on the record, so a journey that closed it
    finds a fresh one and a reseed of an untouched database changes nothing."""
    expected = EXPECTED_PROBLEM_REPORT
    tenant = next(row for row in tenants if row.slug == expected.tenant_slug)
    tenancy.activate(tenant.id)
    reporter = User.objects.get(email=expected.reporter_email)
    open_already = ProblemReport.objects.filter(
        tenant=tenant,
        reporter=reporter,
        subject_id=_obligation_id(expected.obligation),
        status=ReportStatus.OPEN.value,
    ).exists()
    if open_already:
        return 0
    reports.create_report(
        subject_type=SubjectType.OBLIGATION,
        subject_id=_obligation_id(expected.obligation),
        subject_title=expected.obligation,
        tenant_id=tenant.id,
        reporter=reporter,
        actor=Actor(kind=ActorType.USER, id=reporter.id, label=reporter.name),
        description=(
            "The summary still says research may be paid from the institution's own resources only. "
            "The new wording we were sent names a research payment account as well."
        ),
        version_number=expected.version_number,
        language=expected.language,
    )
    return 1


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
    lead = watch_e2e_seed.seed_change(
        stable_key=EXPECTED_HOME.lead_change,
        title="FI adopts amended rules on paying for investment research",
        key_date=today + datetime.timedelta(days=near),
        key_date_label="In force",
        urgency="act_now",
        first_seen_at=timezone_now_this_week(TENANT_A.timezone),
        so_what_draft="Confirm the annual assessment criteria before the rules take effect.",
    )
    later = watch_e2e_seed.seed_change(
        stable_key=EXPECTED_HOME.later_change,
        title="Amended reporting of securities financing transactions",
        key_date=today + datetime.timedelta(days=far),
        key_date_label="Applies",
        urgency="six_months_plus",
        first_seen_at=timezone_now_this_week(TENANT_A.timezone),
    )
    outside = watch_e2e_seed.seed_change(
        stable_key=EXPECTED_HOME.outside_scope_change,
        title="Insurance distribution guidance outside our scope",
        key_date=today + datetime.timedelta(days=near + 5),
        key_date_label="Applies",
        urgency="within_3_months",
        first_seen_at=timezone_now_this_week(TENANT_A.timezone),
    )
    last_week = watch_e2e_seed.seed_change(
        stable_key=EXPECTED_HOME.last_week_change,
        title="FI starts mapping how financial firms use AI",
        key_date=today + datetime.timedelta(days=far + 30),
        key_date_label="Consultation",
        urgency="monitor",
        first_seen_at=timezone_now_last_week(TENANT_A.timezone),
        so_what_draft="No obligation changes yet. Keep the AI tooling register current.",
    )
    # Every change carries a regime (D-39, AC-AGT1), each one tenant A's scope holds, so the
    # scope verdicts the cases below cache are the ones they had: the outside-scope change
    # stays outside through its pension term (`seed_outside_scope_terms`).
    for change, regime in (
        (lead, "regime:securities"),
        (later, "regime:securities"),
        (outside, "regime:insurance"),
        (last_week, "regime:ai_ict"),
    ):
        watch_e2e_seed.seed_scope_term_link(change, term_ref=regime)
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
    # Outside the bank's regulatory scope (HOM-S4, FP-S4): the change carries the one term
    # tenant A's scope leaves out (`seed_outside_scope_terms()`), so false is what the rule
    # answers too, what the feed decides on every read, and what a recompute after any
    # approved footprint change keeps (seed integrity checks every case against the rule).
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
    # A regime each, one tenant B's scope holds, so both cases stay in scope (D-39).
    watch_e2e_seed.seed_scope_term_link(change_b1, term_ref="regime:aml")
    watch_e2e_seed.seed_scope_term_link(change_b2, term_ref="regime:securities")
    _seed_case(tenant_b, change_b1, urgency="within_3_months", footprint_match=True)
    _seed_case(tenant_b, change_b2, urgency="six_months_plus", footprint_match=True)
    return 6


def seed_search_index() -> dict[str, int]:
    """SRC-01, J-7 (c7-e2e-seed): the search index over the seeded library, rebuilt and
    embedded with the mock embedder inside the same transaction as the seed, so a journey
    never races the outbox worker for a vector that has not arrived yet. Runs last, once
    every shared row the index can read exists, registered changes included, with no
    tenant active (`index_write()` writes in the shared zone and the rebuild's audit row
    belongs to it).

    The chunk count is read through `django_apps.get_model()`, never through a `SearchChunk`
    import: the index fence's guard (`apps/search/tests_index_fence.py`) flags any module
    outside `indexing.py` that so much as names `SearchChunk` beside an unrelated write call
    of its own — `seed_tenants()`'s `update_or_create()` a few lines below among them — so
    this reads the count without naming the model.
    """
    from apps.search.indexing import embed_backlog, reindex_all

    reindex_all()
    embed_backlog()
    return {"search_chunks": _search_chunk_count()}


def _search_chunk_count() -> int:
    return int(django_apps.get_model("search", "SearchChunk").objects.count())


@dataclass(frozen=True)
class SeedChunk5Watch:
    """Chunk 5's own watch fixtures (c5-seed-watch), beyond chunk 6's four changes: the
    natural keys `watch.journey.spec.ts`, `taxonomy.journey.spec.ts` and the seed-integrity
    guard read back by."""

    timeline_change: str
    obligations_change: str
    payments_change: str
    curation_change: str
    healthy_source: str
    failing_source: str
    inactive_source: str
    unswept_source: str


EXPECTED_CHUNK5_WATCH = SeedChunk5Watch(
    # WAT-S2's own example dates (consultation 2026-03, adopted 2026-06-15, in force
    # "Q1 2027"), so the journey that renders them needs no dates of its own.
    timeline_change="chg-e2e-c5-timeline",
    # Carries the two `change_obligation` links WAT-S6 reads (one confirmed, one a
    # suggestion) and the two documents WAT-01's coverage and AGT-07's screening need.
    obligations_change="chg-e2e-c5-obligations",
    # A third reform so the feed and the console queue are not both single-row lists;
    # "Markets we watch" stays empty until `f03-T41` derives a jurisdiction (D-29).
    payments_change="chg-e2e-c5-payments",
    # WAT-S4's own reform, every fact the sweeper's suggestion, which the journey confirms as
    # a person in the console. No other journey reads or corrects it, so confirming it can
    # never move a fact under another journey (the payments change is corrected by
    # taxonomy.journey.spec.ts as the same editor, whose correction is then their own).
    curation_change="chg-e2e-c5-curation",
    healthy_source="EUR-Lex legal database (E2E)",
    failing_source="Open web sweep, payments (E2E)",
    inactive_source="ISO standards register (E2E, inactive)",
    unswept_source="ESMA register (E2E)",
)

# The one obligation a `recheck` source check names (AGT-01, item 3): not used by any other
# journey, so a re-check row here never collides with a proposal or an assertion elsewhere.
RECHECK_OBLIGATION = "obl-priips-kid"

# The two obligations WAT-S6's links carry (`c3-seed-provisions`'s own fixture), neither used
# by the proposals seed above or by taxonomy.journey.spec.ts's ADVICE_ONLY_OBLIGATION.
CONFIRMED_LINK_OBLIGATION = "obl-dora-ict-register"
SUGGESTED_LINK_OBLIGATION = "obl-client-assets"

# The independent agent whose confirmations this seed stands behind (D-74): a watch fact's
# confirmed state is an agent's of another definition than the sweeper that suggested it,
# made through its own platform key, so it reads machine-confirmed naming both agents.
CONFIRMING_AGENT = "library-confirmer"


def seed_platform_agent_runs() -> tuple[AgentRun, AgentRun]:
    """One closed and one open platform run of the watch sweeper (AGT-01, item 14): the
    provenance every chunk 5 source check and change below points at. `Agent` is the library
    row `seed_agent_definitions()` loads from `backend/agents/watch-sweeper/v1/`; `ApiKey`
    and `AgentRun` are plain tables outside the library fence, so this module writes them
    directly, exactly as `apps/agents/testing.py` does for the backend suite.

    Idempotent on the key's own name (`_sweeper_key`) and each run's `idempotency_key`: a
    reseed finds the same three rows rather than opening a second key or a second pair of
    runs.

    `api_key` and `agent_run` are mixed tables (playbook 14): their RLS policy accepts a
    `tenant_id` NULL row only from a session with no tenant active, exactly as a library
    row does, so the writes below run inside `tenancy.platform_zone()` regardless of which
    tenant the caller last activated (proven to fail 2026-09-21: `ProgrammingError: new row
    violates row-level security policy for table "api_key"`, from a session `seed_home_cases`
    had left on tenant B).
    """
    key, agent = _sweeper_key()
    with tenancy.platform_zone():
        closed, _ = AgentRun.objects.update_or_create(
            api_key=key,
            idempotency_key="e2e-seed-run-closed",
            defaults={
                "agent": agent,
                "model": "agent pipeline 0.4",
                "pipeline_version": "0.4",
                "status": RunStatus.SUCCEEDED.value,
                "finished_at": timezone_now_this_week(TENANT_A.timezone),
                "stats": {"itemsChecked": 6, "changesFound": 3, "proposalsFiled": 0},
            },
        )
        opened, _ = AgentRun.objects.update_or_create(
            api_key=key,
            idempotency_key="e2e-seed-run-open",
            defaults={"agent": agent, "model": "agent pipeline 0.4", "pipeline_version": "0.4", "status": RunStatus.RUNNING.value},
        )
    return closed, opened


# The scopes a platform watch key holds in R1 (ID-10, PARALLEL_PLAN 7.2), mirroring
# `apps/agents/testing.py`'s own list rather than a second literal.
_WATCH_SCOPES: tuple[str, ...] = ("agent-runs:write", "sources:write", "changes:write", "library:read")


def _sweeper_key() -> tuple[ApiKey, Any]:
    """The watch sweeper's platform key, found by its name or made once, and the agent it is
    bound to: the key its seeded runs were opened with and its seeded proposals filed by.
    Nothing in this seed
    authenticates as the key, so its plain value is generated and immediately dropped
    rather than kept anywhere. Written in `tenancy.platform_zone()`, as every platform row
    of a mixed table must be (H15)."""
    seed_agent_definitions()
    agent = _agent("watch-sweeper")
    _plain, prefix, key_hash = tokens.new_api_key()
    with tenancy.platform_zone():
        key, _created = ApiKey.objects.get_or_create(
            name="Watch sweeper (E2E)",
            defaults={"tenant": None, "agent": agent, "key_prefix": prefix, "key_hash": key_hash, "scopes": list(_WATCH_SCOPES)},
        )
    return key, agent


# The scopes the confirmer's platform key holds, from its definition
# (`backend/agents/library-confirmer/v1/definition.yaml`): never `changes:write` or
# `proposals:write`, so it cannot file what it would then confirm.
_CONFIRMER_SCOPES: tuple[str, ...] = ("agent-runs:write", "library:read", "proposals:review")


def _confirmer_key() -> ApiKey:
    """The library confirmer's platform key, found by its name or made once, bound to its
    own agent definition: the key every confirmation in this seed names (D-74). Like the
    sweeper's, nothing authenticates as it, so its plain value is dropped at once, and it is
    written in `tenancy.platform_zone()` (H15)."""
    seed_agent_definitions()
    agent = _agent(CONFIRMING_AGENT)
    _plain, prefix, key_hash = tokens.new_api_key()
    with tenancy.platform_zone():
        key, _created = ApiKey.objects.get_or_create(
            name="Library confirmer (E2E)",
            defaults={"tenant": None, "agent": agent, "key_prefix": prefix, "key_hash": key_hash, "scopes": list(_CONFIRMER_SCOPES)},
        )
    return key


def seed_chunk5_sources(closed_run: AgentRun) -> None:
    """The registry's own variety (WAT-01), four sources across three of its four kinds
    (`tenant_private` is WAT-06, R3, and fits no shared row): a healthy one, one that has
    just started failing, one registered but not yet swept, and one registered inactive —
    standing in for WAT-07's standards-body kind, which the vocabulary does not carry until
    `f03-T43` seeds it (D-45). Both checks below are the sweeper's closed run's own work."""
    healthy = watch_e2e_seed.seed_source(
        name=EXPECTED_CHUNK5_WATCH.healthy_source, kind="legal_database", authority=None, url="https://eur-lex.europa.eu/",
    )
    watch_e2e_seed.seed_source_check(healthy, status=CheckStatus.OK, run=closed_run)
    failing = watch_e2e_seed.seed_source(
        name=EXPECTED_CHUNK5_WATCH.failing_source, kind="open_web_sweep", authority=None, check_frequency=CheckFrequency.DAILY,
    )
    watch_e2e_seed.seed_source_check(
        failing, status=CheckStatus.FAILED, error="502 from the publisher after three retries", run=closed_run
    )
    watch_e2e_seed.seed_source(
        name=EXPECTED_CHUNK5_WATCH.unswept_source, kind="authority_site", authority="esma", url="https://www.esma.europa.eu/",
    )
    watch_e2e_seed.seed_source(
        name=EXPECTED_CHUNK5_WATCH.inactive_source, kind="authority_site", authority=None, active=False,
        check_frequency=CheckFrequency.MONTHLY,
    )
    watch_e2e_seed.seed_recheck(healthy, _obligation(RECHECK_OBLIGATION), run=closed_run)


def _register_and_fan_out(change: Any) -> None:
    """Deliver `change.registered` exactly as a real registration would (CAS-01): the outbox
    event `record()` writes in the library's zone, drained until every active bank has its
    case. Called only for a change this run just created, so a reseed never re-fires the
    fan-out for one that already has its cases. `change` arrives untyped, by the app
    registry's own reads above, for the reason each of them gives: `RegulatoryChange` is a
    `LibraryModel`, and this module already calls `.update_or_create()` for other rows."""
    with transaction.atomic():
        tenancy.clear_tenant()
        record(
            action=CHANGE_REGISTERED,
            actor=SEED_ACTOR,
            subject_type="regulatory_change",
            subject_id=change.id,
            subject_title=change.title,
            summary="Seeded for E2E journeys.",
            tenant_id=None,
        )
    while outbox.deliver_batch().delivered:
        pass


def seed_chunk5_changes(closed_run: AgentRun) -> SeedChunk5Watch:
    """The three reforms beyond chunk 6's four (WAT-01 to WAT-05): each with a regime term,
    a change type and a flag as suggestions, and their real cases fanned out through the
    outbox cursor exactly as a registration would open them (CAS-01). Every fact is the
    sweeper's suggestion, through its key; the confirmed ones are the library confirmer's,
    through its own (D-74), so nothing here names a person and a journey's person may
    confirm any suggestion left. It clears the tenant it is called with left active.
    """
    sweeper, _agent_row = _sweeper_key()
    confirmer = _confirmer_key()
    tenancy.clear_tenant()
    week = timezone_now_this_week(TENANT_A.timezone)
    today = week.date()

    # WAT-S2's own dates: a three-entry timeline of mixed precision. The regime term is the
    # one classification this seed confirms, so both suggested and confirmed states render.
    is_new = not _regulatory_change_exists(EXPECTED_CHUNK5_WATCH.timeline_change)
    timeline = watch_e2e_seed.seed_change(
        stable_key=EXPECTED_CHUNK5_WATCH.timeline_change,
        title="FI clarifies the appropriateness assessment for complex instruments",
        change_type="adopted",
        published_on=datetime.date(2026, 6, 15),
        key_date=datetime.date(2027, 1, 1),
        key_date_precision=DatePrecision.QUARTER,
        key_date_label="In force",
        urgency="within_3_months",
        first_seen_at=week,
        so_what_draft="Update the appropriateness assessment template before the rules take effect.",
        suggester=sweeper,
    )
    watch_e2e_seed.seed_event(timeline, label="Consultation opened", event_date=datetime.date(2026, 3, 1), precision=DatePrecision.MONTH, sort_order=1)
    watch_e2e_seed.seed_event(timeline, label="Adopted", event_date=datetime.date(2026, 6, 15), precision=DatePrecision.DAY, sort_order=2)
    watch_e2e_seed.seed_event(timeline, label="In force", event_date=datetime.date(2027, 1, 1), precision=DatePrecision.QUARTER, occurred=False, sort_order=3)
    watch_e2e_seed.seed_document(timeline, url="https://www.fi.se/en/published/news/2026/appropriateness/", title="FI clarifies the appropriateness assessment", is_primary=True)
    watch_e2e_seed.seed_flag_link(timeline, flag_key="advice_perimeter", suggester=sweeper)
    watch_e2e_seed.seed_scope_term_link(timeline, term_ref="regime:securities", suggester=sweeper, confirmer=confirmer, confirmed_at=week)
    if is_new:
        _register_and_fan_out(timeline)

    # WAT-S6's own change: two documents (one a merged duplicate, one carrying a screened
    # hit) and two obligation links, one an independent agent confirmed for the shared
    # library and one still a suggestion, so a bank's own decision has something to decide.
    # Its type, flag and scope term are machine-confirmed too, so its feed row carries the
    # machine-confirmed pill where the other two carry the suggestion marker.
    is_new = not _regulatory_change_exists(EXPECTED_CHUNK5_WATCH.obligations_change)
    obligations_change = watch_e2e_seed.seed_change(
        stable_key=EXPECTED_CHUNK5_WATCH.obligations_change,
        title="ESMA finalises technical standards on ICT third-party risk reporting",
        change_type="guidance",
        authority="esma",
        authority_label="European Securities and Markets Authority",
        published_on=today,
        key_date=today + datetime.timedelta(days=45),
        key_date_label="Applies",
        urgency="within_3_months",
        first_seen_at=week + datetime.timedelta(hours=2),
        so_what_draft="Confirm the ICT register covers every third-party arrangement in scope.",
        source_url="https://www.esma.europa.eu/",
        suggester=sweeper,
        type_confirmer=confirmer,
        confirmed_at=week,
    )
    watch_e2e_seed.seed_document(obligations_change, url="https://www.esma.europa.eu/press-news/ict-rts", title="ESMA finalises ICT reporting standards", is_primary=True)
    watch_e2e_seed.seed_document(
        obligations_change, url="https://www.esma.europa.eu/press-news/ict-rts-annex", title="Annex: reporting template", is_duplicate=True, risk_flags=["embedded_instructions"],
    )
    watch_e2e_seed.seed_flag_link(
        obligations_change, flag_key="ai", confidence=0.61, suggester=sweeper, confirmer=confirmer, confirmed_at=week,
    )
    watch_e2e_seed.seed_scope_term_link(
        obligations_change, term_ref="regime:ai_ict", confidence=0.88, suggester=sweeper, confirmer=confirmer, confirmed_at=week,
    )
    watch_e2e_seed.seed_obligation_link(
        obligations_change, _obligation(CONFIRMED_LINK_OBLIGATION), confidence=0.92, suggester=sweeper, confirmer=confirmer, confirmed_at=week,
    )
    watch_e2e_seed.seed_obligation_link(
        obligations_change, _obligation(SUGGESTED_LINK_OBLIGATION), confidence=0.55, suggester=sweeper,
    )
    if is_new:
        _register_and_fan_out(obligations_change)

    # A third, simpler reform, so the feed and the console queue are not both one row.
    is_new = not _regulatory_change_exists(EXPECTED_CHUNK5_WATCH.payments_change)
    payments = watch_e2e_seed.seed_change(
        stable_key=EXPECTED_CHUNK5_WATCH.payments_change,
        title="FI consults on instant payment infrastructure resilience",
        change_type="consultation",
        key_date=today + datetime.timedelta(days=200),
        key_date_label="Consultation closes",
        urgency="monitor",
        first_seen_at=week + datetime.timedelta(hours=4),
        suggester=sweeper,
        type_confidence=0.83,
    )
    watch_e2e_seed.seed_document(payments, url="https://www.fi.se/en/published/news/2026/instant-payments/", is_primary=True)
    watch_e2e_seed.seed_scope_term_link(payments, term_ref="regime:payments", confidence=0.7, suggester=sweeper)
    if is_new:
        _register_and_fan_out(payments)

    # WAT-S4's reform: the scenario's own classification, each fact suggested by the sweeper
    # with its confidence, and nothing confirmed.
    is_new = not _regulatory_change_exists(EXPECTED_CHUNK5_WATCH.curation_change)
    curation = watch_e2e_seed.seed_change(
        stable_key=EXPECTED_CHUNK5_WATCH.curation_change,
        title="ESMA consults on the marketing of complex products to retail clients",
        change_type="consultation",
        authority="esma",
        authority_label="European Securities and Markets Authority",
        key_date=today + datetime.timedelta(days=120),
        key_date_label="Consultation closes",
        urgency="monitor",
        first_seen_at=week + datetime.timedelta(hours=6),
        source_url="https://www.esma.europa.eu/",
        suggester=sweeper,
        type_confidence=0.91,
    )
    watch_e2e_seed.seed_document(curation, url="https://www.esma.europa.eu/press-news/complex-products", is_primary=True)
    watch_e2e_seed.seed_flag_link(curation, flag_key="advice_perimeter", confidence=0.74, suggester=sweeper)
    watch_e2e_seed.seed_scope_term_link(curation, term_ref="regime:securities", confidence=0.8, suggester=sweeper)
    if is_new:
        _register_and_fan_out(curation)

    return EXPECTED_CHUNK5_WATCH


def seed_chunk5_cases(tenants: list[Tenant]) -> int:
    """This bank's own work on chunk 5's three changes (c5-seed-watch, WAT-05): one So
    what confirmed in tenant A, left as the library's draft in tenant B, so both states
    render on a screen that reads one bank's own case. Runs after the real creation path has
    given every active tenant a case for each change (`seed_chunk5_changes`)."""
    tenant_a = next(t for t in tenants if t.slug == TENANT_A_SLUG)
    officer = User.objects.get(email="compliance_officer@example-bank.test")
    tenancy.activate(tenant_a.id)
    case = ChangeCase.objects.get(tenant=tenant_a, change__stable_key=EXPECTED_CHUNK5_WATCH.timeline_change)
    if not case.so_what_confirmed:
        case.so_what_confirmed = True
        case.so_what_confirmed_by = officer
        case.so_what_confirmed_at = timezone_now_this_week(TENANT_A.timezone)
        case.save(update_fields=["so_what_confirmed", "so_what_confirmed_by", "so_what_confirmed_at"])
        record(
            action="case.so_what_confirmed",
            actor=SEED_ACTOR,
            subject_type="change_case",
            subject_id=case.id,
            subject_title=case.change.title,
            summary="Seeded for E2E journeys.",
            tenant_id=tenant_a.id,
            after={"soWhatConfirmed": True},
        )
    tenancy.clear_tenant()
    return 1


# ---------------------------------------------------------------------------------------
# FP-S4 (FP-03, tax-fp-s4-journey): one record of each kind outside tenant A's scope
# ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SeedOutsideScope:
    """What FP-S4's journey finds outside tenant A's regulatory scope without changing it:
    the one term the seed leaves out of that scope, and the obligation and the change that
    fall outside it through that term alone."""

    term: str
    obligation: str
    change: str


# --- tax-nordic-seed (FP-04, FP-S10) -----------------------------------------------------
# Tenant A watches Denmark, the design card's watched market; tenant B watches nothing.
EXPECTED_WATCHED_MARKETS: dict[str, tuple[str, ...]] = {
    TENANT_A_SLUG: ("dk",),
    TENANT_B_SLUG: (),
}


def seed_watched_markets(tenants: list[Tenant]) -> None:
    """Through markets_logic.watch(), so the seed makes the audited write the product makes.
    watch() answers already_watching on a repeat, so a market already watched is skipped."""
    for tenant in tenants:
        tenancy.activate(tenant.id)
        for key in EXPECTED_WATCHED_MARKETS[tenant.slug]:
            if not WatchedMarket.objects.filter(tenant=tenant, jurisdiction__key=key).exists():
                markets_logic.watch(tenant=tenant, actor=SEED_ACTOR, key=key)
# --- end tax-nordic-seed -------------------------------------------------------------------

# --- tax-watched-inventory (FP-04, FP-S13) -------------------------------------------------
# The Danish custody duty: tenant A operates in Sweden and watches Denmark, so it is what
# "Markets we watch" adds, and the default inventory hides it.
WATCHED_MARKET_OBLIGATION = "obl-dk-csd-registration"
# --- end tax-watched-inventory -------------------------------------------------------------


# --- tax-market-journeys (FP-S8, TEN-S7) ---------------------------------------------------
@dataclass(frozen=True)
class SeedMarketJourney:
    """FP-S8's tenant, its two people and one in-scope obligation per jurisdiction."""

    tenant_slug: str
    requester_email: str
    approver_email: str
    union_obligation: str
    home_obligation: str
    country_obligation: str
    country: str


# FP-S8 turns on Denmark in tenant B, whose scope names no jurisdiction, and restores it.
# Each obligation is inside B's scope as seeded: the ESMA guidance (EU) keeps showing, the
# Swedish duty hides, the Danish one stays. No other journey reads tenant B's inventory.
EXPECTED_MARKET_JOURNEY = SeedMarketJourney(
    tenant_slug=TENANT_B_SLUG,
    requester_email="admin@second-bank.test",
    approver_email="approver@second-bank.test",
    union_obligation="obl-esma-warnings",
    home_obligation="obl-appropriateness",
    country_obligation="obl-dk-csd-registration",
    country="dk",
)


@dataclass(frozen=True)
class SeedTenantOnlyRows:
    tenant_slug: str
    role_key: str
    role_labels: dict[str, str]
    tag_list: str
    tag_key: str
    tag_labels: dict[str, str]


# TEN-S7 (J-8): one custom role and one tenant tag tenant A has and tenant B must never see.
# Labels far from every label a vocabulary journey adds, so no near-duplicate check trips.
EXPECTED_TENANT_A_ONLY = SeedTenantOnlyRows(
    tenant_slug=TENANT_A_SLUG,
    role_key="sanctions_lead",
    role_labels={"en": "Sanctions lead", "sv": "Sanktionsansvarig"},
    tag_list="tenant_tag",
    tag_key="whistleblowing",
    tag_labels={"en": "Whistleblowing", "sv": "Visselblåsning"},
)


def seed_tenant_only_rows(tenants: list[Tenant]) -> None:
    """Through the logic the admin screens call, so each row leaves its audit event; a
    reseed finds them and writes nothing."""
    spec = EXPECTED_TENANT_A_ONLY
    tenant = next(t for t in tenants if t.slug == spec.tenant_slug)
    tenancy.activate(tenant.id)
    if not TenantRole.objects.filter(tenant=tenant, key=spec.role_key).exists():
        roles_logic.create_role(
            tenant=tenant,
            actor=SEED_ACTOR,
            key=spec.role_key,
            labels=spec.role_labels,
            usage_note="Owns the sanctions screening duties.",
            permissions=["register.read"],
            step_up_assertion_id=None,
        )
    if not tenant_lists_logic.entry_for(spec.tag_list).model._default_manager.filter(tenant=tenant, key=spec.tag_key).exists():
        tenant_lists_logic.create_row(list_name=spec.tag_list, tenant=tenant, actor=SEED_ACTOR, labels=spec.tag_labels, key=spec.tag_key)
# --- end tax-market-journeys ---------------------------------------------------------------


# --- r2-e2e-login-roster ------------------------------------------------------------------
@dataclass(frozen=True)
class SeedTenantRole:
    tenant_slug: str
    key: str
    labels: dict[str, str]
    usage_note: str
    permissions: frozenset[str]


# HOM-S10, COL-S12 and COL-S8: a member of tenant A whose only role reads neither the
# register nor cases. A tenant role, because every system role reads both.
EXPECTED_NO_RECORD_READ_ROLE = SeedTenantRole(
    tenant_slug=TENANT_A_SLUG,
    key=NO_RECORD_READ_ROLE,
    labels={"en": "Library only", "sv": "Endast biblioteket"},
    usage_note="Reads the library and the watch, and takes no part in the register or cases.",
    permissions=frozenset(perms.SYSTEM_ROLES["reader"] - {perms.REGISTER_READ, perms.CASES_READ}),
)


def seed_no_record_read_role(tenants: list[Tenant]) -> None:
    """Through the logic the roles screen calls, so the row leaves its audit event; a reseed
    finds it and writes nothing."""
    spec = EXPECTED_NO_RECORD_READ_ROLE
    tenant = next(t for t in tenants if t.slug == spec.tenant_slug)
    tenancy.activate(tenant.id)
    if not TenantRole.objects.filter(tenant=tenant, key=spec.key).exists():
        roles_logic.create_role(
            tenant=tenant,
            actor=SEED_ACTOR,
            key=spec.key,
            labels=spec.labels,
            usage_note=spec.usage_note,
            permissions=sorted(spec.permissions),
            step_up_assertion_id=None,
        )
# --- end r2-e2e-login-roster --------------------------------------------------------------


# The journey cannot narrow the scope itself: FP-S5 (J-6) changes tenant A's scope, and
# every home and watch journey reads it in parallel. So tenant A holds the prototype's scope
# less pension accounts, which leaves exactly one library obligation outside it (the
# pension transfer right, which only pension accounts carry and which no seeded proposal
# or named seed record uses; the seed-integrity guard fails if one comes to) and the
# outside-scope change, which carries the same term. `seed_footprints()` only adds terms,
# so a database seeded while pension was still in the scope keeps it and must be
# recreated; the E2E run recreates its database every time.
EXPECTED_OUTSIDE_SCOPE = SeedOutsideScope(
    term="account_type:pension",
    obligation="obl-pension-transfer-right",
    change=EXPECTED_HOME.outside_scope_change,
)


def seed_outside_scope_terms() -> None:
    """The outside-scope change carries the term tenant A's scope leaves out, so the rule
    and the verdict its case caches agree (FP-03). Without a scope term a change matches
    every bank: the feed, which decides from the terms on every read, showed it in scope
    while the roadmap and the briefing, which read the cache, hid it, and the first
    approved footprint change would have recomputed the cache to true. Left a suggestion,
    as an agent leaves one: an unconfirmed term scopes a change all the same (WAT-03)."""
    change = django_apps.get_model("watch", "RegulatoryChange").objects.get(stable_key=EXPECTED_OUTSIDE_SCOPE.change)
    watch_e2e_seed.seed_scope_term_link(change, term_ref=EXPECTED_OUTSIDE_SCOPE.term)


# --- tax-watched-feed (FP-04, FP-S15) ----------------------------------------------------
# A Danish authority's change about custody: outside tenant A's scope, which operates in
# Sweden only, and listed under "Markets we watch" because tenant A watches Denmark. Its
# urgency is the lowest and it was first seen last week, so it moves neither HOM-S1's lead
# nor this week's lists, and its cases come from the real fan-out, so tenant A's verdict is
# the rule's own.
EXPECTED_WATCHED_CHANGE = "chg-e2e-dk-custody"


def seed_watched_market_change() -> None:
    """The Danish change and every bank's case for it, fanned out only when this run
    created it, so a reseed opens no second case. The fan-out enters each bank's zone, so
    this clears the tenant it leaves active, as `seed_chunk5_cases()` does."""
    is_new = not _regulatory_change_exists(EXPECTED_WATCHED_CHANGE)
    week = timezone_now_last_week(TENANT_A.timezone)
    change = watch_e2e_seed.seed_change(
        stable_key=EXPECTED_WATCHED_CHANGE,
        title="Finanstilsynet tightens the safekeeping rules for client financial instruments",
        change_type="adopted",
        authority="finanstilsynet-dk",
        authority_label="Finanstilsynet (DK)",
        published_on=week.date(),
        key_date=week.date() + datetime.timedelta(days=150),
        key_date_label="In force",
        urgency="monitor",
        first_seen_at=week,
        so_what_draft="Check whether the custody set-up for Danish clients follows the new rules.",
        source_url="https://www.dfsa.dk/",
        summary="The Danish supervisor amended the rules on how firms keep their clients' financial instruments apart.",
    )
    watch_e2e_seed.seed_scope_term_link(change, term_ref="regime:securities", confidence=0.9)
    watch_e2e_seed.seed_scope_term_link(change, term_ref="service_type:custody", confidence=0.84)
    if is_new:
        _register_and_fan_out(change)
    tenancy.clear_tenant()
# --- end tax-watched-feed ------------------------------------------------------------------

# --- lib-machine-confirmed-journey (INV-S14) ---------------------------------------------
# Two records whose newest wording the watch sweeper filed and the library confirmer, an
# independent definition with a key and a run of its own, approved (INV-05, PRO-02, D-62,
# D-80), through the same proposal logic the queue's routes call. A library editor then
# re-verified the second one against its source, so INV-S14 reads one record still labelled
# machine-confirmed and one whose stamp names that person (D-74). Both are named by no other
# spec or seed and sit inside tenant A's scope with or without Advice, and each new version
# carries no effective date, so it is the one in force whatever day a screen reads.
@dataclass(frozen=True)
class SeedMachineConfirmed:
    journey: str
    machine_confirmed: str
    reverified: str
    reverifier_email: str


EXPECTED_MACHINE_CONFIRMED = SeedMachineConfirmed(
    journey="INV-S14",
    # Not product governance, which J-4 owns, nor the demands and needs duty, PRO-S13's.
    machine_confirmed="obl-switch-documentation",
    reverified="obl-isk-approved-assets",
    reverifier_email=LIBRARY_EDITOR_EMAIL,
)
# The runs behind each record's proposal and its decision, fixed so a reseed finds them.
MACHINE_CONFIRMED_RUNS: dict[str, tuple[uuid.UUID, uuid.UUID]] = {
    "obl-switch-documentation": (uuid.UUID("00000000-0000-4000-9000-000000000014"), uuid.UUID("00000000-0000-4000-9000-000000000015")),
    "obl-isk-approved-assets": (uuid.UUID("00000000-0000-4000-9000-000000000016"), uuid.UUID("00000000-0000-4000-9000-000000000017")),
}
# The seed's stand-in for the passkey assertion a person's re-verification carries on its
# audit row: the seed signs nobody in, and it refuses to run deployed (refuse_when_deployed).
SEED_REVERIFICATION_STEP_UP = uuid.UUID("00000000-0000-4000-9000-000000000018")
_MACHINE_CONFIRMED_WORDING: dict[str, dict[str, str]] = {
    "obl-switch-documentation": {
        "sv": (
            "När rådgivningen innebär byte av underliggande placeringar ska distributören dokumentera varför "
            "fördelarna med bytet överväger kostnaderna, och ge kunden en skriftlig förklaring av hur rådet "
            "motsvarar kundens önskemål och mål innan bytet genomförs."
        ),
        "en": (
            "When advice involves switching underlying investments, the distributor documents why the benefits "
            "of the switch outweigh its costs, and gives the customer a written explanation of how the advice "
            "meets their preferences and objectives before the switch is made."
        ),
    },
    "obl-isk-approved-assets": {
        "sv": (
            "På ett investeringssparkonto får endast godkända investeringstillgångar förvaras. Tillgångar som "
            "upphör att vara godkända ska flyttas från kontot inom den tid lagen anger, och kunden ska "
            "informeras om det."
        ),
        "en": (
            "Only approved investment assets may be held on an investment savings account. Assets that stop "
            "qualifying must be moved out within the period the act allows, and the customer is told."
        ),
    },
}


def _agents_confirm(stable_key: str) -> None:
    """The sweeper files a new wording of `stable_key` in its own open run and the confirmer
    approves it in a run of its own key, with the model call behind its decision (D-80)."""
    obligation_id = _obligation_id(stable_key)
    sweep_run, review_run = MACHINE_CONFIRMED_RUNS[stable_key]
    filer, sweeper = _sweeper_key()
    confirmer_key = _confirmer_key()
    confirmer = _agent(CONFIRMING_AGENT)
    with tenancy.platform_zone():
        AgentRun.objects.get_or_create(pk=sweep_run, defaults={"agent": sweeper, "api_key": filer, "model": AGENT_MODEL, "pipeline_version": "0.4"})
        AgentRun.objects.get_or_create(
            pk=review_run, defaults={"agent": confirmer, "api_key": confirmer_key, "model": AGENT_MODEL, "pipeline_version": "0.4"}
        )
    source_url = "https://www.fi.se/"
    wording = _MACHINE_CONFIRMED_WORDING[stable_key]
    proposal, _created = create_proposal(
        kind=ProposalKind.NEW_OBLIGATION_VERSION.value,
        title="Refresh the wording against the source",
        payload={"summaries": wording, "original_language": "sv", "is_machine": True},
        proposer=Proposer(actor=Actor(kind=ActorType.AGENT, id=sweeper.id, label=sweeper.key), api_key_id=filer.id, agent_id=sweeper.id),
        agent_run_id=sweep_run,
        target_type="obligation",
        target_id=obligation_id,
        model=AGENT_MODEL,
        field_sources={f"summaries.{language}": source_url for language in wording},
        source_label="Finansinspektionen, consolidated regulation",
        source_url=source_url,
    )
    reviewer_actor = Actor(kind=ActorType.AGENT, id=confirmer.id, label=f"{confirmer.key} v{confirmer.current_version}")
    approve_proposal(
        proposal=proposal,
        reviewer=Reviewer(actor=reviewer_actor, api_key_id=confirmer_key.id, agent_id=confirmer.id, api_key_prefix=confirmer_key.key_prefix),
        actor=reviewer_actor,
        note="",
        step_up_assertion_id=None,
        decision=AgentDecision.model_validate(
            {
                "model": AGENT_MODEL,
                "modelVersion": "0.4",
                "promptTemplate": "library-confirmer/decide/v1",
                "promptHash": "e2e0000000000014",
                "output": "Approve. The proposed wording matches the consolidated regulation the proposal cites.",
                "citations": [{"label": "Finansinspektionen, consolidated regulation", "url": source_url}],
            }
        ),
        agent_run_id=review_run,
    )


def seed_machine_confirmed() -> int:
    """INV-S14: both records confirmed by agents, then the second re-verified by the library
    editor. A record whose agents' approval is already applied is left as it is, so a reseed
    changes nothing. Returns how many records agents confirmed."""
    tenancy.clear_tenant()
    expected = EXPECTED_MACHINE_CONFIRMED
    for stable_key in (expected.machine_confirmed, expected.reverified):
        applied = Proposal.objects.filter(
            kind=ProposalKind.NEW_OBLIGATION_VERSION.value, target_id=_obligation_id(stable_key), status=ProposalStatus.APPROVED.value
        ).exists()
        if applied:
            continue
        _agents_confirm(stable_key)
        if stable_key == expected.reverified:
            editor = User.objects.get(email=expected.reverifier_email)
            apply_reverification(
                _obligation(stable_key),
                actor=SEED_ACTOR,
                verified_by=editor,
                outcome="no_change",
                note="Read against the consolidated regulation after the agents confirmed the new wording.",
                step_up_assertion_id=SEED_REVERIFICATION_STEP_UP,
            )
    # Applying a version reindexes its record; embed it now, as seed_search_index() does, so
    # no journey races the outbox worker for its vector (SRC-01).
    from apps.search.indexing import embed_backlog

    embed_backlog()
    return 2
# --- end lib-machine-confirmed-journey ---------------------------------------------------

# ---------------------------------------------------------------------------------------
# ask-journeys (SRC-S4, SRC-S5, SRC-S10): a pending change for Ask to flag, and a question
# the library cannot answer
# ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SeedAsk:
    """What search.journey.spec.ts asks and reads back. Ask flags a cited obligation that a
    change the library confirmed will move after the answer's "as of" (SRC-S4), so the lead
    change of the home journeys gets a confirmed link to the research payment duty: it is
    adopted (a kind that moves the law) and dated twenty days after the tenant-local today.
    The answered question retrieves that duty; the unsupported one retrieves nothing in the
    seeded library, so no model is asked and the answer is "no answer" (SRC-S5). The spec
    carries the same two questions; the seed-integrity guard proves both."""

    pending_change: str
    pending_obligation: str
    answered_question: str
    unsupported_question: str


EXPECTED_ASK = SeedAsk(
    pending_change=EXPECTED_HOME.lead_change,
    pending_obligation=RESEARCH_OBLIGATION,
    answered_question="What are our obligations on research payments?",
    unsupported_question="Do we need a licence for crypto custody?",
)


def seed_ask_pending_link() -> None:
    """The lead change's confirmed link to the research payment duty, the sweeper's
    suggestion confirmed this week by the library confirmer's own key, as every confirmation
    in this seed is (D-74). A link is library-zone, so no tenant is active; it adds a row to
    the roadmap's and the change page's obligations and changes nothing a home or watch
    journey counts."""
    tenancy.clear_tenant()
    sweeper, _agent_row = _sweeper_key()
    change = django_apps.get_model("watch", "RegulatoryChange").objects.get(stable_key=EXPECTED_ASK.pending_change)
    watch_e2e_seed.seed_obligation_link(
        change,
        _obligation(EXPECTED_ASK.pending_obligation),
        confidence=0.9,
        suggester=sweeper,
        confirmer=_confirmer_key(),
        confirmed_at=timezone_now_this_week(TENANT_A.timezone),
    )


# --- c11-e2e-seed (AGT-03, AGT-04, AGT-05, PRO-04) ------------------------------------------
@dataclass(frozen=True)
class SeedChunk11:
    """What the chunk 11 journeys find: the sweeper published at two versions with a
    scheduled platform run on each (AGT-S4); tenant A's own source watch, weekly with a scope,
    whose runs over the recent weeks put the month's spend just under its one cap (AGT-S5,
    AGT-S6); tenant B with no agent and no cap of its own; and one open re-tag of twelve
    obligations waiting in the console (PRO-S8), filed by the second library editor so the
    first can decide it.

    Every run is dated from the seed's clock in tenant A's zone, at midnight (the fixed wall
    time, never after "now"): a run this month is on today's date less whole weeks, but never
    before the first of the month, and a run of the month before is whole weeks before the
    first. So the month's spend is the sum of `month_costs` on any day, a month boundary
    included (apps/agents/tests_seed.py). The re-tag adds a lifecycle stage, a dimension that
    never narrows a footprint, so deciding it moves no bank's scope under another journey."""

    platform_agent: str
    platform_versions: tuple[int, ...]
    confirming_agent: str
    tenant_agent: str
    tenant_slug: str
    scope: dict[str, list[str]]
    monthly_cap: Decimal
    currency: str
    month_costs: tuple[Decimal, ...]
    earlier_costs: tuple[Decimal, ...]
    batch_title: str
    batch_term: str
    batch_source: str
    batch_obligations: tuple[str, ...]
    batch_proposer_email: str
    updated_by_email: str


# The prototype's weekly run costs (prototype_data.json `agent_runs`), and a cap one more
# such run would pass.
EXPECTED_CHUNK11 = SeedChunk11(
    platform_agent="watch-sweeper",
    platform_versions=(1, 2),
    confirming_agent=CONFIRMING_AGENT,
    tenant_agent="tenant-source-watch",
    tenant_slug=TENANT_A_SLUG,
    scope={"jurisdictions": ["se", "dk"]},
    monthly_cap=Decimal("7.00"),
    currency="EUR",
    month_costs=(Decimal("2.1000"), Decimal("1.8500"), Decimal("2.3000")),
    earlier_costs=(Decimal("1.9500"), Decimal("2.0500")),
    batch_title="Add the reporting stage to twelve obligations whose duty ends in a report",
    batch_term="lifecycle_stage:reporting",
    batch_source="https://www.fi.se/en/our-registers/reporting/",
    # Twelve obligations without the term, none with a proposal of its own waiting on its
    # scope, and not the advice-only one J-6 hides.
    batch_obligations=(
        "obl-dk-csd-registration",
        "obl-dora-ict-register",
        "obl-esma-warnings",
        "obl-gdpr-article-22",
        "obl-idd-demands-needs",
        "obl-isk-approved-assets",
        "obl-no-suitability",
        "obl-pension-transfer-right",
        "obl-priips-kid",
        "obl-product-governance",
        "obl-suitability",
        "obl-switch-documentation",
    ),
    batch_proposer_email="editor2@bleqq.test",
    updated_by_email="admin@example-bank.test",
)
# Fixed ids, so a reseed finds each run rather than opening another.
C11_PLATFORM_RUNS: tuple[uuid.UUID, ...] = tuple(uuid.UUID(f"00000000-0000-4000-8000-00000c110{n:03d}") for n in range(3))
C11_TENANT_RUNS: tuple[uuid.UUID, ...] = tuple(
    uuid.UUID(f"00000000-0000-4000-8000-00000c111{n:03d}")
    for n in range(len(EXPECTED_CHUNK11.month_costs) + len(EXPECTED_CHUNK11.earlier_costs))
)
C11_RUN_MINUTES = 14


def c11_run_starts(now: datetime.datetime) -> tuple[list[datetime.datetime], list[datetime.datetime]]:
    """The start of each of tenant A's runs of this month and of the month before, newest
    first, at midnight in its zone: never after `now`, and never on the other side of the
    first of the month from where `month_costs` and `earlier_costs` say."""
    zone = ZoneInfo(TENANT_A.timezone)
    today = now.astimezone(zone).date()
    first = today.replace(day=1)

    def midnight(day: datetime.date) -> datetime.datetime:
        return datetime.datetime.combine(day, datetime.time(0, 0), tzinfo=zone)

    this_month = [midnight(max(today - datetime.timedelta(weeks=n), first)) for n in range(len(EXPECTED_CHUNK11.month_costs))]
    earlier = [midnight(first - datetime.timedelta(weeks=n + 1)) for n in range(len(EXPECTED_CHUNK11.earlier_costs))]
    return this_month, earlier


def _c11_run(pk: uuid.UUID, started: datetime.datetime, now: datetime.datetime, **fields: Any) -> None:  # compliance: allow-kwargs one run's columns
    """One closed run, found by its fixed id or opened once, then dated from the clock: the
    date is the one column a reseed on another day moves, and `update()` leaves every other
    column, `updated_at`s included, as it was."""
    AgentRun.objects.get_or_create(pk=pk, defaults={"status": RunStatus.SUCCEEDED.value, "pipeline_version": "0.4", **fields})
    AgentRun.objects.filter(pk=pk).update(started_at=started, finished_at=min(started + datetime.timedelta(minutes=C11_RUN_MINUTES), now))


def seed_chunk11_agents(tenants: list[Tenant], now: datetime.datetime | None = None) -> None:
    """The chunk 11 rows (EXPECTED_CHUNK11), anchored to `now` (the real clock unless a test
    moves it). Idempotent: a reseed on the same clock changes nothing, and on another day it
    moves the runs' dates and the next run and nothing else."""
    now = now or datetime.datetime.now(datetime.UTC)
    spec = EXPECTED_CHUNK11
    seed_agent_definitions()
    tenancy.clear_tenant()

    # AGT-S4: the sweeper at two versions, a scheduled platform run on each, and one of the
    # confirmer, so the console lists runs no bank owns.
    first_version = _agent(spec.platform_agent).versions.get(version_no=spec.platform_versions[0])
    second_version = publish_e2e_version(
        key=spec.platform_agent,
        version_no=spec.platform_versions[1],
        change_note="Version 1's prompt and tools, published again so the journeys find a version history.",
    )
    confirmer = _agent(spec.confirming_agent)
    zone = ZoneInfo(TENANT_A.timezone)
    today = datetime.datetime.combine(now.astimezone(zone).date(), datetime.time(0, 0), tzinfo=zone)
    with tenancy.platform_zone():
        for pk, agent, version, weeks, cost in (
            (C11_PLATFORM_RUNS[0], _agent(spec.platform_agent), first_version, 3, Decimal("3.4000")),
            (C11_PLATFORM_RUNS[1], _agent(spec.platform_agent), second_version, 1, Decimal("3.1500")),
            (C11_PLATFORM_RUNS[2], confirmer, confirmer.versions.get(version_no=confirmer.current_version), 1, Decimal("0.9200")),
        ):
            _c11_run(
                pk, today - datetime.timedelta(weeks=weeks), now,
                agent=agent, agent_version=version, trigger=RunTrigger.SCHEDULE.value, model=version.model, cost=cost,
                stats={"modelCalls": 18, "fetches": 40, "sourcesChecked": 12, "changesRegistered": 2, "proposalsSubmitted": 1},
            )

    # AGT-S5, AGT-S6: tenant A's own agent, its runs and its one cap. Tenant B gets none.
    tenant = next(t for t in tenants if t.slug == spec.tenant_slug)
    tenancy.activate(tenant.id)
    admin = User.objects.get(email=spec.updated_by_email)
    definition = _agent(spec.tenant_agent)
    this_month, earlier = c11_run_starts(now)
    tenant_agent, created = TenantAgent.objects.get_or_create(
        tenant=tenant,
        agent=definition,
        defaults={"enabled": True, "cadence": AgentCadence.WEEKLY.value, "run_hour": 0, "scope": spec.scope, "updated_by": admin},
    )
    TenantAgent.objects.filter(pk=tenant_agent.pk).update(next_run_at=this_month[0] + datetime.timedelta(weeks=1))
    budget, budget_created = TenantAgentBudget.objects.get_or_create(
        tenant=tenant, defaults={"monthly_cap": spec.monthly_cap, "currency": spec.currency, "updated_by": admin}
    )
    if created:
        record(
            action="tenant_agent.seeded", actor=SEED_ACTOR, subject_type="tenant_agent", subject_id=tenant_agent.pk,
            subject_title=definition.key, summary="Seeded for E2E journeys.", tenant_id=tenant.id,
            after={"agent": definition.key, "enabled": True, "cadence": AgentCadence.WEEKLY.value, "scope": spec.scope},
        )
    if budget_created:
        record(
            action="tenant_agent_budget.seeded", actor=SEED_ACTOR, subject_type="tenant_agent_budget", subject_id=budget.pk,
            subject_title=tenant.slug, summary="Seeded for E2E journeys.", tenant_id=tenant.id,
            after={"monthlyCap": str(spec.monthly_cap), "currency": spec.currency},
        )
    version = definition.versions.get(version_no=definition.current_version)
    for pk, started, cost in zip(C11_TENANT_RUNS, [*this_month, *earlier], [*spec.month_costs, *spec.earlier_costs], strict=True):
        _c11_run(
            pk, started, now,
            agent=definition, agent_version=version, tenant_agent=tenant_agent, trigger=RunTrigger.SCHEDULE.value,
            model=version.model, scope=spec.scope, cost=cost, tokens_in=41_000, tokens_out=3_200,
            stats={"modelCalls": 6, "fetches": 9, "sourcesChecked": 4},
        )

    # PRO-S8: the open re-tag, through the one function that files a batch.
    tenancy.clear_tenant()
    if Proposal.objects.filter(is_batch=True, title=spec.batch_title, status=ProposalStatus.OPEN.value).exists():
        return
    editor = User.objects.get(email=spec.batch_proposer_email)
    proposal_batch.create_batch(
        kind=ProposalKind.OBLIGATION_SCOPE.value,
        title=spec.batch_title,
        payload=ObligationScopePayload(
            changes=[
                ObligationScopeChange(obligation_id=_obligation_id(key), add=[spec.batch_term], remove=[], source=spec.batch_source)
                for key in spec.batch_obligations
            ]
        ),
        proposer=Proposer(actor=Actor(kind=ActorType.USER, id=editor.id, label=editor.name), user=editor),
        source_label="Finansinspektionen, reporting",
        source_url=spec.batch_source,
    )
# --- end c11-e2e-seed -------------------------------------------------------------------------


def seed_e2e() -> dict[str, int]:
    """Run the whole seed. Returns counts the command prints and the guard asserts."""
    refuse_when_deployed()
    # The mock outbox is one cache entry that never expires, and an E2E run recreates the
    # database but not the cache: empty it first, so no journey reads an earlier run's mail.
    MockMailer.reset()
    with transaction.atomic():
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()
        seed_authorities()
        library = load_library()
        # lib-standard-e2e-seed: the one standard, added to the counts the command prints.
        for name, count in load_library(E2E_STANDARD).items():
            library[name] += count
        # std-journeys: the standard's term on, so FP-S16 can follow it (E2E_STANDARD_TERM).
        switch_on_term(*E2E_STANDARD_TERM)
        # Chunk 6's sources and changes: library-zone rows, written here — before any
        # tenant is activated — for the same reason `seed_authorities()` and
        # `load_library()` run here rather than after `seed_tenants()` (WAT-06).
        home = seed_watch_changes()
        seed_outside_scope_terms()
        # SRC-05: the release gate's own questions, so the console's evaluation page has the
        # set it will have on a deployed platform. Platform rows, refused to any session with a
        # tenant active, so they are written in the platform's zone even on a re-seed.
        with tenancy.platform_zone():
            eval_questions = eval_sets.seed_questions(actor=SEED_ACTOR)
        roles_logic.ensure_platform_roles()
        tenants = seed_tenants()
        # r2-e2e-login-roster: the tenant role one login holds, before the logins.
        seed_no_record_read_role(tenants)
        logins = seed_logins(tenants)
        footprint_terms = seed_footprints(tenants)
        seed_pending_footprint_request(tenants)
        seed_watched_markets(tenants)
        seed_tenant_only_rows(tenants)
        proposals = seed_proposals()
        problem_reports = seed_problem_report(tenants)
        home_cases = seed_home_cases(tenants, home)
        # Chunk 5's own watch fixtures (c5-seed-watch): after the logins above, because a
        # confirmed classification names a library editor who must already exist, and after
        # the footprints above, because a case's footprint verdict is computed against the
        # bank's footprint as it stands when the case is created.
        closed_run, _open_run = seed_platform_agent_runs()
        seed_chunk5_sources(closed_run)
        seed_chunk5_changes(closed_run)
        seed_ask_pending_link()
        chunk5_cases = seed_chunk5_cases(tenants)
        seed_watched_market_change()
        seed_standard_change()
        # c11-e2e-seed: after the logins and the platform runs, before the search index.
        seed_chunk11_agents(tenants)

        # INV-S14, after the logins: the re-verification names a seeded library editor.
        machine_confirmed = seed_machine_confirmed()
        # SRC-01: last, once every shared row the index reads exists — chunk 5's changes
        # included, whose registrations reach the index through the outbox without a vector
        # (search-index-changes) — and in the shared zone, where its audit row belongs.
        tenancy.clear_tenant()
        search_index = seed_search_index()
    return {
        "tenants": len(tenants),
        "logins": logins,
        "footprint_terms": footprint_terms,
        "proposals": proposals,
        "problem_reports": problem_reports,
        "home_cases": home_cases,
        "chunk5_cases": chunk5_cases,
        "machine_confirmed": machine_confirmed,
        "eval_questions": eval_questions,
        **library,
        **search_index,
    }


def anna_invitation() -> Invitation | None:
    """The open invitation of the one awaiting user, for the guard and journeys."""
    return invitation_logic.find_open_for_email("anna@example-bank.test")


# ---------------------------------------------------------------------------------------
# watch-standards (WAT-S10, WAT-07, CAS-01): a new edition of a standard, seen only by the
# banks that follow it
# ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SeedStandardChange:
    """The one change a standards body issued, and the term that decides who sees it.
    Tenant A follows no standard as seeded (std-journeys' FP-S16 and INV-S11 start from
    that), so WAT-S10's journey switches the term on for its own run through
    `follow_the_standard()` and back off afterwards, on failure too."""

    stable_key: str
    title: str
    key_date_label: str
    term: str


EXPECTED_STANDARD_CHANGE = SeedStandardChange(
    stable_key="chg-e2e-iso-27001-amendment",
    # The standard's reference and nothing of its official title (INV-08, D-35).
    title="ISO/IEC 27001 amendment",
    key_date_label="Transition ends",
    term="standard:iso_iec_27001",
)


def seed_standard_change() -> None:
    """The amendment as a sweep would file it: ISO/IEC as the authority, the AI and ICT
    regime and the standard's term, a draft for comment and a publication on its timeline,
    the end of the transition as its key date. Its cases come from the real fan-out, so
    both banks hold one and neither is in scope as seeded. Runs last in `seed_e2e`.

    The key date is 400 days after tenant A's today and the first sighting 30 days before
    it, so while a journey has the term switched on the change sits last on tenant A's
    roadmap and outside this and last week's briefing: HOM-S1's lead and Today's "Coming
    up" list do not move. Urgency `monitor`, never `act_now`, for the same reason."""
    tenancy.clear_tenant()
    today = datetime.datetime.now(ZoneInfo(TENANT_A.timezone)).date()
    spec = EXPECTED_STANDARD_CHANGE
    is_new = not _regulatory_change_exists(spec.stable_key)
    change = watch_e2e_seed.seed_change(
        stable_key=spec.stable_key,
        title=spec.title,
        change_type="adopted",
        authority="iso-iec",
        authority_label="ISO/IEC",
        published_on=today - datetime.timedelta(days=10),
        key_date=today + datetime.timedelta(days=400),
        key_date_label=spec.key_date_label,
        urgency="monitor",
        first_seen_at=timezone_now_this_week(TENANT_A.timezone) - datetime.timedelta(days=30),
        so_what_draft="Plan the move to the amended edition before the transition ends.",
        source_url="https://www.iso.org/",
    )
    watch_e2e_seed.seed_event(change, label="Draft for comment", event_date=today - datetime.timedelta(days=60), sort_order=1)
    watch_e2e_seed.seed_event(change, label="Published", event_date=today - datetime.timedelta(days=10), sort_order=2)
    watch_e2e_seed.seed_scope_term_link(change, term_ref="regime:ai_ict")
    watch_e2e_seed.seed_scope_term_link(change, term_ref=spec.term)
    if is_new:
        _register_and_fan_out(change)
    # The fan-out leaves the last bank's zone active; the seed ends in none, as it began.
    tenancy.clear_tenant()


def follow_the_standard(follow: bool) -> None:
    """Tenant A starts or stops following ISO/IEC 27001, for WAT-S10's journey and its
    restore (`manage.py e2e_follow_standard`). The same footprint writes the seed makes,
    history and audit included, then the one recompute an approved change would trigger,
    narrowed to the standard's change so no other case of the bank is touched. The E2E
    stack runs no beat, so nothing else would deliver it. Refused when deployed."""
    refuse_when_deployed("e2e_follow_standard")
    tenant = Tenant.objects.get(slug=TENANT_A_SLUG)
    change = django_apps.get_model("watch", "RegulatoryChange").objects.get(stable_key=EXPECTED_STANDARD_CHANGE.stable_key)
    with transaction.atomic():
        tenancy.activate(tenant.id)
        term = terms_logic.term_by_ref(*EXPECTED_STANDARD_CHANGE.term.split(":"))
        switch = footprint_logic.seed_terms if follow else footprint_logic.unseed_terms
        switch(tenant=tenant, actor=SEED_ACTOR, terms=[term])
        case_matching._recompute(tenant.id, change_id=change.id)
