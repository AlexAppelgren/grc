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
from zoneinfo import ZoneInfo

from django.apps import apps as django_apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction

from apps.agents.models import AgentRun, RunStatus
from apps.agents.seeds import seed_agent_definitions
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
    User,
    UserStatus,
    WebAuthnCredential,
)
from apps.library import reports
from apps.library.models import DatePrecision, Language, ProblemReport, ReportStatus, SubjectType
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import RESEARCH_OBLIGATION, load_library, seed_authorities
from apps.proposals.logic import Proposer
from apps.proposals.logic import create as create_proposal
from apps.proposals.models import Proposal, ProposalKind, ProposalStatus
from apps.shared import outbox, tenancy
from apps.shared.audit import Actor, ActorType, record
from apps.shared.e2e_logins import E2E_INVITATION_TOKEN_ANNA, SEED_LOGINS, TENANT_A_SLUG, TENANT_B_SLUG, SeedLogin
from apps.shared.e2e_passkeys import E2E_PASSKEYS
from apps.taxonomy.models import CaseStatusCategory
from apps.watch import e2e_seed as watch_e2e_seed
from apps.watch.models import CheckFrequency, CheckStatus
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
AGENT_LABEL = "Research agent 0.4"
AGENT_MODEL = "agent pipeline 0.4"
# The library editor who files PRO-S5's proposal; the second editor decides everything else.
LIBRARY_EDITOR_EMAIL = "editor@bleqq.test"
# The agent run behind each obligation proposal, fixed so a reseed leaves the same ids.
APPROPRIATENESS_RUN = uuid.UUID("00000000-0000-4000-9000-000000000001")
COSTS_CHARGES_RUN = uuid.UUID("00000000-0000-4000-9000-000000000002")
CLIENT_ASSETS_RUN = uuid.UUID("00000000-0000-4000-9000-000000000003")
ISK_STATEMENTS_RUN = uuid.UUID("00000000-0000-4000-9000-000000000004")


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
    SeedProposal("PRO-S7", ProposalKind.NEW_OBLIGATION_VERSION.value, "obl-isk-control-statements", ISK_STATEMENTS_RUN),
    SeedProposal("PRO-S5", ProposalKind.VOCABULARY_RELABEL.value, "flag:ai", proposed_by_email=LIBRARY_EDITOR_EMAIL),
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
    one. All four cite the authority's own page, as a real run would."""
    target_id = _obligation_id(obligation)
    if _waiting(ProposalKind.NEW_OBLIGATION_VERSION.value, target_id=target_id):
        return
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
            actor=Actor(kind=ActorType.AGENT, id=agent_run, label=AGENT_LABEL),
            agent_run_id=agent_run,
        ),
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
    _propose_obligation_version(
        obligation="obl-isk-control-statements",
        agent_run=ISK_STATEMENTS_RUN,
        title="Add version 2 of the ISK control statement obligation, moving the deadline to 31 January",
        summaries={
            "sv": (
                "Kontrolluppgift för ett investeringssparkonto ska lämnas till Skatteverket senast den "
                "31 januari året efter beskattningsåret, med kapitalunderlaget per kvartal och de "
                "insättningar som räknas in i underlaget."
            ),
            "en": (
                "The control statement for an investment savings account is filed with the Swedish Tax "
                "Agency by 31 January of the year after the tax year, with the capital base per quarter "
                "and the deposits counted into it."
            ),
        },
        effective_from="2027-01-01",
        source_label="Skatteverket, statement of practice 2026-09-10",
        source_url="https://www.skatteverket.se/",
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


def seed_search_index() -> dict[str, int]:
    """SRC-01, J-7 (c7-e2e-seed): the search index over the seeded library, rebuilt and
    embedded with the mock embedder inside the same transaction as the seed, so a journey
    never races the outbox worker for a vector that has not arrived yet. Runs after
    `load_library()` and `seed_watch_changes()`, once every shared row the index can read
    exists, and before any tenant is activated (`index_write()` writes in the shared zone,
    the same reason `seed_authorities()` and `load_library()` run there too).

    The chunk count is read through `django_apps.get_model()`, never through a `SearchChunk`
    import: the index fence's guard (`apps/search/tests_index_fence.py`) flags any module
    outside `indexing.py` that so much as names `SearchChunk` beside an unrelated write call
    of its own — `seed_tenants()`'s `update_or_create()` a few lines below among them — so
    this reads the count without naming the model.
    """
    from apps.search.indexing import embed_backlog, reindex_all

    reindex_all()
    embed_backlog()
    chunk_model = django_apps.get_model("search", "SearchChunk")
    return {"search_chunks": chunk_model.objects.count()}


@dataclass(frozen=True)
class SeedChunk5Watch:
    """Chunk 5's own watch fixtures (c5-seed-watch), beyond chunk 6's four changes: the
    natural keys `watch.journey.spec.ts`, `taxonomy.journey.spec.ts` and the seed-integrity
    guard read back by."""

    timeline_change: str
    obligations_change: str
    payments_change: str
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

# The one library editor whose confirmations this seed stands behind: the same account
# `proposals.journey.spec.ts` signs in as, so a journey that confirms something here and
# something in the console queue is confirming as one person.
CONFIRMING_EDITOR_EMAIL = "editor@bleqq.test"


def seed_platform_agent_runs() -> tuple[AgentRun, AgentRun]:
    """One closed and one open platform run of the watch sweeper (AGT-01, item 14): the
    provenance every chunk 5 source check and change below points at. `Agent` is the library
    row `seed_agent_definitions()` loads from `backend/agents/watch-sweeper/v1/`; `ApiKey`
    and `AgentRun` are plain tables outside the library fence, so this module writes them
    directly, exactly as `apps/agents/testing.py` does for the backend suite.

    Idempotent on the key's own name and each run's `idempotency_key`: a reseed finds the
    same three rows rather than opening a second key or a second pair of runs.

    `api_key` and `agent_run` are mixed tables (playbook 14): their RLS policy accepts a
    `tenant_id` NULL row only from a session with no tenant active, exactly as a library
    row does, so the writes below run inside `tenancy.platform_zone()` regardless of which
    tenant the caller last activated (proven to fail 2026-09-21: `ProgrammingError: new row
    violates row-level security policy for table "api_key"`, from a session `seed_home_cases`
    had left on tenant B).
    """
    seed_agent_definitions()
    agent = _agent("watch-sweeper")
    # Nothing in this seed authenticates as the key; it exists for the runs' FK alone, so
    # its plain value is generated and immediately dropped rather than kept anywhere.
    _plain, prefix, key_hash = tokens.new_api_key()
    with tenancy.platform_zone():
        key, _created = ApiKey.objects.get_or_create(
            name="Watch sweeper (E2E)",
            defaults={"tenant": None, "agent": agent, "key_prefix": prefix, "key_hash": key_hash, "scopes": list(_WATCH_SCOPES)},
        )
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
    outbox cursor exactly as a registration would open them (CAS-01). Runs after
    `seed_logins()`, because a confirmed classification names a library editor who must
    already exist, and it clears the tenant it is called with left active.
    """
    editor = User.objects.get(email=CONFIRMING_EDITOR_EMAIL)
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
    )
    watch_e2e_seed.seed_event(timeline, label="Consultation opened", event_date=datetime.date(2026, 3, 1), precision=DatePrecision.MONTH, sort_order=1)
    watch_e2e_seed.seed_event(timeline, label="Adopted", event_date=datetime.date(2026, 6, 15), precision=DatePrecision.DAY, sort_order=2)
    watch_e2e_seed.seed_event(timeline, label="In force", event_date=datetime.date(2027, 1, 1), precision=DatePrecision.QUARTER, occurred=False, sort_order=3)
    watch_e2e_seed.seed_document(timeline, url="https://www.fi.se/en/published/news/2026/appropriateness/", title="FI clarifies the appropriateness assessment", is_primary=True)
    watch_e2e_seed.seed_flag_link(timeline, flag_key="advice_perimeter")
    watch_e2e_seed.seed_scope_term_link(timeline, term_ref="regime:securities", confirmed_by_id=editor.id, confirmed_at=week)
    if is_new:
        _register_and_fan_out(timeline)

    # WAT-S6's own change: two documents (one a merged duplicate, one carrying a screened
    # hit) and two obligation links, one confirmed for the shared library and one still a
    # suggestion, so a bank's own decision has something to decide.
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
    )
    watch_e2e_seed.seed_document(obligations_change, url="https://www.esma.europa.eu/press-news/ict-rts", title="ESMA finalises ICT reporting standards", is_primary=True)
    watch_e2e_seed.seed_document(
        obligations_change, url="https://www.esma.europa.eu/press-news/ict-rts-annex", title="Annex: reporting template", is_duplicate=True, risk_flags=["embedded_instructions"],
    )
    watch_e2e_seed.seed_flag_link(obligations_change, flag_key="ai", confidence=0.61)
    watch_e2e_seed.seed_scope_term_link(obligations_change, term_ref="regime:ai_ict", confidence=0.88)
    watch_e2e_seed.seed_obligation_link(
        obligations_change, _obligation(CONFIRMED_LINK_OBLIGATION), confidence=0.92, confirmed_by_id=editor.id, confirmed_at=week,
    )
    watch_e2e_seed.seed_obligation_link(
        obligations_change, _obligation(SUGGESTED_LINK_OBLIGATION), confidence=0.55,
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
    )
    watch_e2e_seed.seed_document(payments, url="https://www.fi.se/en/published/news/2026/instant-payments/", is_primary=True)
    watch_e2e_seed.seed_scope_term_link(payments, term_ref="regime:payments", confidence=0.7)
    if is_new:
        _register_and_fan_out(payments)

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
        # SRC-01: the index reads every shared row load_library() and seed_watch_changes()
        # just wrote, and is itself a shared-zone write, so it runs here too.
        search_index = seed_search_index()
        roles_logic.ensure_platform_roles()
        tenants = seed_tenants()
        logins = seed_logins(tenants)
        footprint_terms = seed_footprints(tenants)
        seed_pending_footprint_request(tenants)
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
        chunk5_cases = seed_chunk5_cases(tenants)
    return {
        "tenants": len(tenants),
        "logins": logins,
        "footprint_terms": footprint_terms,
        "proposals": proposals,
        "problem_reports": problem_reports,
        "home_cases": home_cases,
        "chunk5_cases": chunk5_cases,
        **library,
        **search_index,
    }


def anna_invitation() -> Invitation | None:
    """The open invitation of the one awaiting user, for the guard and journeys."""
    return invitation_logic.find_open_for_email("anna@example-bank.test")
