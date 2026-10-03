"""The public page's demo data (design/public/README.md "The demo", D-120): the real library
baseline, and Example Bank AB's own work made up on top of it.

Alex, 2026-10-03: "I would like it to use the actual library and then the rest can be
mocked". So the library is the whole of `apps/library/baseline/`, filed through the proposal
door by the platform agent `library-baseline` exactly as a deploy files it
(`apps/proposals/baseline.py`) and approved, pass after pass until nothing is due, by
`library-confirmer`: an agent of another definition and key holding `proposals:review`
(D-62), so every record reads machine-confirmed and names both agents, the product's steady
state. No library row is written through the seed door (CLAUDE.md section 5, ADR 0058,
ADR 0065); the reference seeds are the deploy's own.

The bank is the E2E seed's Example Bank AB, made up as it is there, built only on stable keys
the library holds:

- its organisation and register, through the E2E seed's own builders, on the real duties that
  sort first in its inventory, because the demo's recorder follows at most twenty records a
  route and a list sorts by stable key;
- its regulatory changes, each a fact of the baseline itself: the day an instrument's duties
  start to apply, with the instrument's own authority, source and duties. Nothing says an
  authority published anything on a day it did not; when a change was first seen and how the
  bank worked its case are the bank's own story, and are made up;
- its cases, worked to every category with actions, evidence, comments and people on them;
- last week's briefing, sent for real, and the markets it watches.

Every made-up date is the bank's local today plus an offset. Only the reader signs in, with
the E2E seed's fixed passkey, so the recorder walks the app as that person.

Separate from `seed_e2e` and `seed_demo` on purpose: every journey and the search evaluation
keep their fixtures. The seed-integrity guard is apps/shared/tests_demo_seed.py."""

from __future__ import annotations

import datetime
import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test.utils import override_settings
from django.utils import timezone

from apps.agents import runner_events
from apps.agents.models import AgentRun, RunStatus
from apps.cases import matching as case_matching
from apps.cases.models import Action, AssessmentApplies, CaseTransition, ChangeCase, Evidence, EvidenceKind, ImpactAssessment
from apps.collab.models import Participant
from apps.home import tasks as home_tasks
from apps.identity import roles_logic, tokens
from apps.identity.models import ApiKey, User
from apps.proposals import baseline
from apps.proposals.logic import Proposer, Reviewer
from apps.proposals.logic import approve as approve_proposal
from apps.proposals.logic import create as create_proposal
from apps.proposals.models import Proposal, ProposalKind, ProposalStatus
from apps.shared import e2e_seed, tenancy
from apps.shared.adapters.agent_runner import RunnerEvent
from apps.shared.adapters.mailer import MockMailer
from apps.shared.audit import Actor, ActorType, record
from apps.shared.e2e_logins import SEED_LOGINS, TENANT_A_SLUG
from apps.shared.e2e_seed import (
    SeedComment,
    SeedEntityScope,
    SeedEntry,
    SeedGap,
    SeedInternalItem,
    SeedLicence,
    SeedOrgRegister,
    SeedOrgUnit,
    SeedProduct,
    SeedReading,
    SeedTeam,
    SeedAssessment,
)
from apps.shared.models import Tenant
from apps.shared.schemas import AgentDecision
from apps.shared.storage import get_storage
from apps.taxonomy import footprint_logic, markets_logic, terms_logic
from apps.taxonomy.models import CaseStatusCategory, FootprintTerm, WatchedMarket
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies
from apps.tenants.logic import set_content_languages
from apps.watch import e2e_seed as watch_seed
from apps.watch.models import CheckStatus

SEED_ACTOR = Actor.system("seed_public_demo")
TENANT = e2e_seed.TENANT_A
CONFIRMING_AGENT = "library-confirmer"
SWEEPING_AGENT = "watch-sweeper"
AGENT_MODEL = "agent pipeline 0.4"

# The people of Example Bank AB the demo names, every one a login of the E2E roster. Only the
# reader signs in: the demo person reads everything and changes nothing.
DEMO_READER = "reader@example-bank.test"
_SARA = "compliance_officer@example-bank.test"
_JOHAN = "owner@example-bank.test"
_MARIA = "approver@example-bank.test"
_KARIN = "contributor@example-bank.test"
_EMMA = "owner-approver@example-bank.test"
_HEAD = "head@example-bank.test"
DEMO_PEOPLE: tuple[str, ...] = ("admin@example-bank.test", _SARA, _JOHAN, _MARIA, _KARIN, DEMO_READER, _HEAD, _EMMA)

# The bank's regulatory scope: operating in Sweden, so what applies EU-wide reaches it too,
# and watching Denmark. No fund company, whose duties would crowd the inventory's first page.
DEMO_FOOTPRINT: tuple[str, ...] = (
    "jurisdiction:se",
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
    "service_type:advice",
    "service_type:non_advised",
    "service_type:execution_only",
    "service_type:portfolio_management",
    "service_type:custody",
    "service_type:insurance_distribution",
    "client_category:retail",
    "client_category:professional",
)
DEMO_WATCHED_MARKETS: tuple[str, ...] = ("dk",)
DEMO_REGIMES = frozenset(ref.partition(":")[2] for ref in DEMO_FOOTPRINT if ref.startswith("regime:"))

# The duties the bank's register holds. They sort first among the duties in its scope, so the
# inventory's first page, which the recorder follows, opens on the records with most to show.
ALGO_KILL = "obl-eu-algo-rts-kill-functionality"
ALGO_PRE_TRADE = "obl-eu-algo-rts-pre-trade-controls"
ALGO_SELF_ASSESSMENT = "obl-eu-algo-rts-annual-self-assessment"
AI_LITERACY = "obl-eu-aiact-ai-literacy"
AI_PROHIBITED = "obl-eu-aiact-prohibited-practices"
AI_DISCLOSURE = "obl-eu-aiact-interaction-disclosure"
AI_FRIA = "obl-eu-aiact-fundamental-rights-impact-assessment"
AI_PROVIDER = "obl-eu-aiact-high-risk-provider"
SANCTIONS_FREEZE = "obl-eu-af753-asset-freeze"
SANCTIONS_REPORTING = "obl-eu-af753-reporting"
THIRD_COUNTRY_RISK = "obl-eu-2019-758-third-country-risk"
AMLA_COOPERATION = "obl-eu-amla-direct-supervision-cooperation"

# A Swedish summary beside the baseline's English, as a machine translation the sweeper filed
# and the confirmer approved: a second version of a real duty that changes none of its facts,
# so the inventory has a version to compare in the bank's first content language.
SWEDISH_WORDING: dict[str, str] = {
    AI_LITERACY: (
        "Som leverantör eller tillhandahållare av AI-system ska företaget vidta åtgärder för att stödja "
        "AI-kunnigheten hos sin personal och andra som driver eller använder AI-system för dess räkning, med "
        "hänsyn till deras kunskaper, erfarenhet och utbildning, sammanhanget där systemen används och de "
        "personer de används på. Det krävs inte att någon enskild person har en viss nivå av AI-kunnighet."
    ),
    ALGO_KILL: (
        "Som en nödåtgärd ska ett företag som bedriver algoritmisk handel omedelbart kunna annullera alla eller "
        "vissa av sina ej utförda order på alla eller vissa av de handelsplatser det är anslutet till, och kunna "
        "se vilken algoritm, handlare, handelsavdelning eller kund varje order kommer från."
    ),
}

DEMO_REGISTER = SeedOrgRegister(
    tenant_slug=TENANT_A_SLUG,
    units=(
        SeedOrgUnit("Example Group", "group"),
        SeedOrgUnit("Example Bank AB", "legal_entity", "Example Group", "556000-0001", "legal_entity:bank"),
        SeedOrgUnit("Example Liv Försäkring AB", "legal_entity", "Example Group", "516000-0002", "legal_entity:insurer"),
        SeedOrgUnit("Retail Banking", "business_area", "Example Bank AB", head=_HEAD),
        SeedOrgUnit("Trading", "business_area", "Example Bank AB"),
        SeedOrgUnit("Risk control", "function", "Example Group", head=_SARA),
    ),
    licences=(
        SeedLicence("Example Bank AB", "legal_entity:bank", "Banking business", ("service_type:custody",)),
        SeedLicence(
            "Example Bank AB",
            "legal_entity:investment_firm",
            "Securities business",
            ("service_type:advice", "service_type:non_advised", "service_type:execution_only", "service_type:portfolio_management"),
        ),
        SeedLicence("Example Liv Försäkring AB", "legal_entity:insurer", "Life insurance business"),
        SeedLicence("Example Liv Försäkring AB", "legal_entity:insurer", "Insurance distribution", ("service_type:insurance_distribution",)),
        e2e_seed.CERTIFICATE,
    ),
    products=(
        SeedProduct(
            "Self-directed trading",
            "Example Bank AB",
            "live",
            _JOHAN,
            ("account_type:isk", "account_type:af", "account_type:depa", "service_type:non_advised", "service_type:execution_only", "service_type:custody"),
        ),
        SeedProduct("Guided investing", "Example Bank AB", "planned", _JOHAN, ("account_type:isk", "service_type:advice", "service_type:portfolio_management")),
        SeedProduct("Kapitalförsäkring", "Example Liv Försäkring AB", "live", _JOHAN, ("account_type:kf", "service_type:insurance_distribution", "service_type:advice")),
    ),
    teams=(
        SeedTeam("retail_compliance", {"en": "Retail compliance", "sv": "Compliance privatmarknad"}, "Retail Banking", (_JOHAN, _KARIN, _SARA)),
        SeedTeam("legal", {"en": "Legal", "sv": "Juridik"}, "Risk control", (DEMO_READER, _MARIA)),
        SeedTeam("trading", {"en": "Trading", "sv": "Handel"}, "Trading", (_JOHAN, _EMMA)),
    ),
    entries=(
        SeedEntry(
            ALGO_KILL, "applies", "Our trading desk runs algorithms that send orders to trading venues.", "compliant", "high",
            _JOHAN, _MARIA, "Algorithmic trading", "Pre-trade risk gateway", "Quarterly kill switch tests", 76,
        ),
        SeedEntry(
            ALGO_PRE_TRADE, "applies", "Every algorithmic order passes the pre-trade risk gateway.", "partly_compliant", "medium",
            None, _MARIA, "Algorithmic trading", "Pre-trade risk gateway", "Limit configuration log", 40,
            status_note="Maximum message limits are not yet set for the newest venue.", owner_team="trading",
        ),
        SeedEntry(
            ALGO_SELF_ASSESSMENT, "applies", "We trade algorithmically on our own account and for clients.", "compliant", "medium",
            _SARA, _MARIA, "Algorithmic trading", "", "Self-assessment report", 150,
        ),
        SeedEntry(
            AI_LITERACY, "applies", "Staff in customer service, fraud and credit use AI systems every day.", "partly_compliant", "medium",
            _SARA, _MARIA, "Training", "Learning platform", "Course completion records", 19,
            status_note="Customer service staff who use the chat assistant have not yet taken the AI course.",
        ),
        SeedEntry(
            AI_PROHIBITED, "applies", "We use AI systems in customer service, fraud detection and credit scoring.", "compliant", "high",
            _SARA, _MARIA, "Model approval", "Model inventory", "Model approval decisions", 120,
        ),
        SeedEntry(
            AI_DISCLOSURE, "applies", "The chat assistant in the app talks to customers.", "gap", "medium",
            _JOHAN, _MARIA, "Digital channels", "Chat assistant", "Release notes", 30,
            status_note="The chat assistant does not yet say that it is an AI system.",
        ),
        SeedEntry(
            AI_FRIA, "applies", "Our credit scoring model for consumer loans is an AI system that assesses creditworthiness.", "not_assessed", "high",
            _JOHAN, _MARIA, "Credit decisions", "Credit scoring model", "", -5,
            status_note="To be assessed before the scoring model is next updated.",
        ),
        SeedEntry(
            AI_PROVIDER, "does_not_apply", "We buy and use AI systems but develop no high-risk AI system ourselves.", "partly_compliant", "low",
            _SARA, _MARIA, "Model approval", "Model inventory", "Make-or-buy decisions", 200,
        ),
        SeedEntry(
            SANCTIONS_FREEZE, "applies", "Every customer and payment is screened against the EU sanctions lists.", "compliant", "high",
            _SARA, _MARIA, "Sanctions screening", "Screening engine", "Daily screening log", 60,
        ),
        SeedEntry(
            SANCTIONS_REPORTING, "applies", "Frozen funds are reported by the sanctions desk.", "compliant", "low",
            _SARA, _MARIA, "Sanctions screening", "Case manager", "Reports filed", 90,
        ),
        SeedEntry(
            THIRD_COUNTRY_RISK, "applies", "The group has a branch outside the EEA.", "partly_compliant", "medium",
            _SARA, _MARIA, "Group AML risk assessment", "Risk register", "Group risk assessment", 127,
        ),
        SeedEntry(
            AMLA_COOPERATION, "applies", "We answer to AMLA's requests through Finansinspektionen today.", "not_assessed", "low",
            _SARA, _MARIA, "Regulatory contacts", "", "", 45, status_note="Not yet assessed.",
        ),
    ),
    entity_scopes=(
        SeedEntityScope(
            THIRD_COUNTRY_RISK, "Example Bank AB", "compliant", "medium", _SARA,
            "Group AML risk assessment", "Risk register", "Branch risk assessment", 127,
        ),
        SeedEntityScope(
            THIRD_COUNTRY_RISK, "Example Liv Försäkring AB", "partly_compliant", "medium", _JOHAN,
            "Group AML risk assessment", "Risk register", "Insurance risk assessment", 35,
            status_note="The insurance company's distributors outside the EEA are not yet in the assessment.",
        ),
    ),
    assessments=(
        SeedAssessment(
            ALGO_KILL, 330, "self_assessment", "partly_compliant", "high",
            "The kill switch cancelled open orders on the main venue only; the two newest venues were not connected to it.", _JOHAN,
        ),
        SeedAssessment(
            ALGO_KILL, 30, "second_line_review", "compliant", "high",
            "A test cancelled every open order on every connected venue within seconds, and each order named its algorithm.", _SARA,
        ),
        SeedAssessment(
            AI_PROVIDER, 200, "self_assessment", "partly_compliant", "low",
            "Our model inventory did not say which systems we built and which we bought.", _SARA,
        ),
    ),
    readings=(
        SeedReading(ALGO_KILL, 1, 330, "Kill means every unexecuted order on every venue, whichever algorithm sent it.", _JOHAN),
        SeedReading(
            ALGO_KILL, 2, 30,
            "Kill also covers orders the order router has passed to other brokers, which we cancel through each broker's own kill function.", _SARA,
        ),
        SeedReading(AI_FRIA, 1, 60, "Our credit scoring model is used to evaluate creditworthiness, so the assessment applies to it.", _SARA),
    ),
    gaps=(
        SeedGap(
            AI_DISCLOSURE, "The chat assistant does not say it is an AI system",
            "Customers who open the chat in the app are not told that they are talking to an AI system.",
            "high", "assessment", "open", _JOHAN, _SARA, 20, 45,
        ),
        SeedGap(
            AI_LITERACY, "Customer service staff have not taken the AI course",
            "The course on using AI systems is done in fraud and credit, but not yet by the customer service staff who use the chat assistant.",
            "medium", "assessment", "remediating", _SARA, _SARA, 36, 60,
            remediation="Add the course to customer service onboarding and book the current team before the end of the quarter.",
        ),
        SeedGap(
            ALGO_PRE_TRADE, "Message limits are missing for the newest venue",
            "The pre-trade risk gateway sets price, value and volume limits for every venue, but no maximum message limit for the venue added this year.",
            "medium", "audit", "open", _JOHAN, _SARA, 15, 35,
        ),
        SeedGap(
            THIRD_COUNTRY_RISK, "Distributors outside the EEA are missing from the group risk assessment",
            "The insurance company sells through two distributors outside the EEA that the group risk assessment does not name.",
            "low", "audit", "open", _SARA, _SARA, 40, 120,
        ),
    ),
    items=(
        SeedInternalItem("procedure", "Kill switch test", "PRO-052", _JOHAN, (ALGO_KILL,)),
        SeedInternalItem("control", "Pre-trade limit checks", "CTL-310", _JOHAN, (ALGO_PRE_TRADE,)),
        SeedInternalItem("policy", "AI policy", "POL-031", _SARA, (AI_PROHIBITED, AI_LITERACY)),
        SeedInternalItem("procedure", "Model approval", "PRO-061", _SARA, (AI_FRIA,)),
        SeedInternalItem("control", "Daily sanctions screening", "CTL-118", _SARA, (SANCTIONS_FREEZE,)),
        SeedInternalItem("policy", "Group AML policy", "POL-002", _SARA, (THIRD_COUNTRY_RISK,)),
    ),
)


# --- the library: the baseline, through the proposal door -------------------------------------
def _agent(key: str) -> Any:
    """A platform agent definition, by the app registry: `Agent` is a library row."""
    return django_apps.get_model("agents", "Agent").objects.get(key=key)


def _platform_key(agent_key: str, name: str, scopes: tuple[str, ...]) -> ApiKey:
    """An agent's platform key, found by its name or made once. Nothing authenticates as it,
    so its plain value is dropped at once; written in the platform's zone (H15)."""
    _plain, prefix, key_hash = tokens.new_api_key()
    with tenancy.platform_zone():
        key, _created = ApiKey.objects.get_or_create(
            name=name,
            defaults={"tenant": None, "agent": _agent(agent_key), "key_prefix": prefix, "key_hash": key_hash, "scopes": list(scopes)},
        )
    return key


def _bound(key: ApiKey) -> Any:
    """The agent a key here is bound to: `_platform_key` makes every one bound."""
    return key.agent


def confirmer_key() -> ApiKey:
    # The confirmer's scopes, from its definition: never one that files what it confirms.
    return _platform_key(CONFIRMING_AGENT, "Library confirmer", ("agent-runs:write", "library:read", "proposals:review"))


def sweeper_key() -> ApiKey:
    return _platform_key(SWEEPING_AGENT, "Watch sweeper", ("agent-runs:write", "sources:write", "changes:write", "library:read"))


def _open_run(key: ApiKey) -> AgentRun:
    with tenancy.platform_zone():
        return AgentRun.objects.create(
            agent=_bound(key), api_key=key, model=AGENT_MODEL, pipeline_version="0.4", idempotency_key=f"demo-{uuid.uuid4()}"
        )


def _close_run(run: AgentRun, stats: dict[str, int]) -> None:
    runner_events.apply_event(RunnerEvent(run_id=run.id, status=RunStatus.SUCCEEDED, stats=stats))


def _decision(proposal: Proposal) -> AgentDecision:
    """What the confirmer reports of its review: the page the proposal cites, read against it."""
    source = proposal.source_url
    return AgentDecision.model_validate(
        {
            "model": AGENT_MODEL,
            "modelVersion": "0.4",
            "promptTemplate": "library-confirmer/decide/v1",
            "promptHash": hashlib.sha256(source.encode()).hexdigest()[:16],
            "output": "Approve. The proposal matches the page it cites.",
            "citations": [{"label": proposal.source_label or source, "url": source}],
        }
    )


def _confirm(proposals: list[Proposal]) -> list[str]:
    """The confirmer approves each proposal in one run of its own key. Returns the stable keys
    the door refused it, which the caller stops on: a person has to read those."""
    if not proposals:
        return []
    key = confirmer_key()
    run = _open_run(key)
    actor = Actor(kind=ActorType.AGENT, id=key.agent_id, label=f"{_bound(key).key} v{_bound(key).current_version}")
    reviewer = Reviewer(actor=actor, api_key_id=key.id, agent_id=key.agent_id, api_key_prefix=key.key_prefix)
    refused: list[str] = []
    approved = 0
    for proposal in proposals:
        try:
            approve_proposal(
                proposal=proposal, reviewer=reviewer, actor=actor, note="", step_up_assertion_id=None,
                decision=_decision(proposal), agent_run_id=run.id,
            )
        except ValidationError as error:
            refused.append(f"{proposal.payload.get('key', proposal.id)}: {' '.join(error.messages)}")
            continue
        approved += 1
    _close_run(run, {"modelCalls": approved})
    return refused


class DemoSeedStopped(Exception):
    """The baseline could not be filed and confirmed whole: what it names needs a person."""


def seed_library() -> dict[str, int]:
    """File the baseline and let the confirmer approve it, pass after pass, until nothing is
    due: instruments on the first pass, their duties on the second (ADR 0065). A reseed files
    and approves nothing. Then the two Swedish versions."""
    tenancy.clear_tenant()
    baseline.register_sources()
    passes = 0
    while True:
        report = baseline.file()
        if report.refused:
            raise DemoSeedStopped("The proposal door refused baseline entries: " + "; ".join(f"{key}: {detail}" for key, _code, detail in report.refused))
        waiting = list(
            Proposal.objects.filter(status=ProposalStatus.OPEN.value, proposed_by_agent__key=baseline.AGENT_KEY).order_by("created_at", "id")
        )
        refused = _confirm(waiting)
        if refused:
            raise DemoSeedStopped("The confirmer may not approve: " + "; ".join(refused))
        if not waiting:
            break
        passes += 1
    for stable_key, wording in SWEDISH_WORDING.items():
        _add_swedish_wording(stable_key, wording)
    return {"baseline_passes": passes}


def _obligation(stable_key: str) -> Any:
    return django_apps.get_model("library", "Obligation").objects.get(stable_key=stable_key)


def _add_swedish_wording(stable_key: str, swedish: str) -> None:
    """The sweeper files the duty's summary with a Swedish machine translation beside its
    English, and the confirmer approves it. Done once: a reseed finds the version applied."""
    obligation = _obligation(stable_key)
    kind = ProposalKind.NEW_OBLIGATION_VERSION.value
    if Proposal.objects.filter(kind=kind, target_id=obligation.id).exclude(status=ProposalStatus.REJECTED.value).exists():
        return
    entry = next(entry for entry in baseline.load() if entry.key == stable_key)
    key = sweeper_key()
    run = _open_run(key)
    wording = {"en": entry.payload["summaries"]["en"], "sv": swedish}
    proposal, _created = create_proposal(
        kind=kind,
        title="Add a Swedish summary",
        payload={"summaries": wording, "original_language": "en", "is_machine": True},
        proposer=Proposer(actor=Actor(kind=ActorType.AGENT, id=key.agent_id, label=_bound(key).key), api_key_id=key.id, agent_id=key.agent_id),
        agent_run_id=run.id,
        target_type="obligation",
        target_id=obligation.id,
        model=AGENT_MODEL,
        field_sources={f"summaries.{language}": entry.source_url for language in wording},
        source_label=entry.source_label,
        source_url=entry.source_url,
    )
    _close_run(run, {"modelCalls": 1})
    refused = _confirm([proposal])
    if refused:
        raise DemoSeedStopped("The confirmer may not approve: " + "; ".join(refused))


# --- the bank ---------------------------------------------------------------------------------
def seed_tenant() -> Tenant:
    languages = {row.key: row for row in django_apps.get_model("library", "Language").objects.all()}
    tenant, created = Tenant.objects.update_or_create(
        slug=TENANT.slug,
        defaults={"id": TENANT.id, "name": TENANT.name, "timezone": TENANT.timezone, "default_language": languages[TENANT.content_languages[0]]},
    )
    tenancy.activate(tenant.id)
    set_content_languages(tenant, [languages[key] for key in TENANT.content_languages])
    roles_logic.ensure_system_roles(tenant)
    ensure_tenant_vocabularies(tenant, actor=SEED_ACTOR)
    if created:
        record(
            action="tenant.seeded",
            actor=SEED_ACTOR,
            subject_type="tenant",
            subject_id=tenant.id,
            subject_title=tenant.name,
            summary="Seeded for the public demo.",
            tenant_id=None,
            after={"slug": tenant.slug, "timezone": tenant.timezone},
        )
    return tenant


def seed_people(tenant: Tenant) -> dict[str, User]:
    """The bank's members the demo names, with the reader's fixed passkey and no other."""
    people: dict[str, User] = {}
    for login in SEED_LOGINS:
        if login.email not in DEMO_PEOPLE:
            continue
        user = e2e_seed._seed_user(login)
        e2e_seed._seed_membership(tenant, user, login)
        if login.email == DEMO_READER:
            e2e_seed._seed_passkey(user, login)
        people[login.email] = user
    return people


def seed_scope(tenant: Tenant) -> None:
    wanted = [terms_logic.term_by_ref(*ref.split(":")) for ref in DEMO_FOOTPRINT]
    present = set(FootprintTerm.objects.filter(tenant=tenant).values_list("term_id", flat=True))
    missing = [term for term in wanted if term.id not in present]
    if missing:
        footprint_logic.seed_terms(tenant=tenant, actor=SEED_ACTOR, terms=missing)
    for key in DEMO_WATCHED_MARKETS:
        if not WatchedMarket.objects.filter(tenant=tenant, jurisdiction__key=key).exists():
            markets_logic.watch(tenant=tenant, actor=SEED_ACTOR, key=key)


# --- the bank's regulatory changes: facts of the baseline ----------------------------------------
@dataclass(frozen=True)
class Fact:
    """The day some of an instrument's duties start to apply, as the baseline has it."""

    instrument: baseline.Entry
    day: datetime.date
    duties: tuple[str, ...]

    @property
    def stable_key(self) -> str:
        return f"chg-{self.instrument.key}-applies-{self.day.isoformat()}"


def facts() -> list[Fact]:
    """Every (instrument, day) on which baseline duties start to apply, in day order."""
    entries = baseline.load()
    instruments = {entry.key: entry for entry in entries if entry.kind == baseline.INSTRUMENT}
    grouped: dict[tuple[str, datetime.date], list[str]] = {}
    for entry in entries:
        effective = entry.payload.get("effectiveFrom")
        if entry.kind == baseline.OBLIGATION and effective:
            grouped.setdefault((entry.instrument, datetime.date.fromisoformat(effective)), []).append(entry.key)
    return sorted(
        (Fact(instruments[instrument], day, tuple(sorted(duties))) for (instrument, day), duties in grouped.items()),
        key=lambda fact: (fact.day, fact.instrument.key),
    )


def _in(fact: Fact, jurisdictions: tuple[str, ...]) -> bool:
    payload = fact.instrument.payload
    return payload["jurisdiction"] in jurisdictions and payload["regime"].partition(":")[2] in DEMO_REGIMES


def _pick(candidates: list[Fact], taken: set[str], count: int) -> list[Fact]:
    """The first `count` facts of `candidates`, one per instrument, none already taken."""
    picked: list[Fact] = []
    for fact in candidates:
        if len(picked) == count:
            break
        if fact.instrument.key in taken:
            continue
        taken.add(fact.instrument.key)
        picked.append(fact)
    return picked


@dataclass(frozen=True)
class CaseAction:
    title: str
    owner: str
    done: bool
    due_in_days: int = 0


@dataclass(frozen=True)
class CasePlan:
    """How the bank worked its case for one fact: the category it reached, when it first saw
    the change (weeks before this one; 0 is this week), and what it did on the way."""

    status: CaseStatusCategory
    urgency: str
    weeks_ago: int
    owner: str | None = None
    requested_by: str | None = None
    so_what_confirmed: bool = False
    actions: tuple[CaseAction, ...] = ()
    evidence: tuple[tuple[str, str], ...] = ()  # (name, scan state), or (name, url) for a link
    participants: tuple[str, ...] = ()  # emails, or "team:<key>"
    comments: tuple[tuple[str, str, int, tuple[str, ...]], ...] = ()  # (author, body, hours before now, mentions)


_DONE = (
    CaseAction("Map the duties to our processes", _JOHAN, done=True),
    CaseAction("Brief the teams who run them", _KARIN, done=True),
)
# Upcoming facts, nearest first: the week's lead, then the work further along.
UPCOMING_PLANS: tuple[CasePlan, ...] = (
    CasePlan(CaseStatusCategory.NEW, "act_now", 0, so_what_confirmed=True),
    CasePlan(
        CaseStatusCategory.ASSESSING, "within_3_months", 2, owner=_JOHAN,
        participants=("team:legal", _SARA, DEMO_READER),
        comments=(
            (_JOHAN, "The duties are mapped to our processes. The open questions are listed in the assessment, and the teams are briefed next week.", 50, ()),
            (_SARA, "Oskar, can you confirm whether this changes what we tell customers before they sign?", 26, (DEMO_READER,)),
        ),
    ),
    CasePlan(
        CaseStatusCategory.IMPLEMENTING, "act_now", 4, owner=_JOHAN,
        actions=(
            CaseAction("Map the duties to our processes", _JOHAN, done=True),
            CaseAction("Update the procedure and the customer documents", _KARIN, done=False, due_in_days=40),
            CaseAction("Sample test the first month after the date", _JOHAN, done=False, due_in_days=-1),
        ),
        evidence=(("Gap analysis.pdf", "clean"), ("Updated procedure, draft.pdf", "pending")),
    ),
    CasePlan(
        CaseStatusCategory.SIGNOFF, "within_3_months", 6, owner=_EMMA, requested_by=_EMMA, actions=_DONE,
        evidence=(("Impact assessment.pdf", "clean"),),
    ),
    CasePlan(CaseStatusCategory.ASSIGNED, "six_months_plus", 0, owner=_JOHAN, so_what_confirmed=True),
    CasePlan(CaseStatusCategory.NEW, "monitor", 1),
)
# Facts already past: the work the bank finished, and one it set aside.
PAST_PLANS: tuple[CasePlan, ...] = (
    CasePlan(
        CaseStatusCategory.CLOSED, "within_3_months", 10, owner=_JOHAN, requested_by=_JOHAN, actions=_DONE,
        evidence=(("Implementation report.pdf", "clean"), ("Board decision memo", "https://intranet.example-bank.test/memo/42")),
    ),
    CasePlan(CaseStatusCategory.DISMISSED, "monitor", 8),
)
# A Danish fact the bank watches, and a Norwegian one outside its scope.
WATCHED_PLAN = CasePlan(CaseStatusCategory.NEW, "monitor", 1)
OUTSIDE_PLAN = CasePlan(CaseStatusCategory.NEW, "monitor", 0)

# The moves of a worked case, as a share of the time between its first sighting and now.
_PATH = (
    CaseStatusCategory.NEW,
    CaseStatusCategory.ASSIGNED,
    CaseStatusCategory.ASSESSING,
    CaseStatusCategory.IMPLEMENTING,
    CaseStatusCategory.SIGNOFF,
    CaseStatusCategory.CLOSED,
)
_MOVE_ACTION = {
    CaseStatusCategory.ASSIGNED: "case.triaged",
    CaseStatusCategory.ASSESSING: "case.assessment_started",
    CaseStatusCategory.IMPLEMENTING: "case.implementation_started",
    CaseStatusCategory.SIGNOFF: "case.signoff_requested",
    CaseStatusCategory.CLOSED: "case.signed_off",
    CaseStatusCategory.DISMISSED: "case.dismissed",
}
_STEP = {status: index for index, status in enumerate(_PATH)} | {CaseStatusCategory.DISMISSED: 1}


@dataclass
class Clock:
    """The bank's own now and today, which every made-up moment is an offset of."""

    now: datetime.datetime
    zone: ZoneInfo
    today: datetime.date = field(init=False)

    def __post_init__(self) -> None:
        self.today = self.now.astimezone(self.zone).date()

    def first_seen(self, weeks_ago: int) -> datetime.datetime:
        """Tuesday 09:00 of the week `weeks_ago` weeks back, and never later than an hour ago."""
        monday = datetime.datetime.combine(self.today - datetime.timedelta(days=self.today.weekday()), datetime.time(0), self.zone)
        tuesday = monday + datetime.timedelta(days=1, hours=9) - datetime.timedelta(weeks=weeks_ago)
        return max(monday - datetime.timedelta(weeks=weeks_ago), min(tuesday, self.now - datetime.timedelta(hours=1)))

    def at(self, days: int) -> datetime.datetime:
        return datetime.datetime.combine(self.today + datetime.timedelta(days=days), e2e_seed.SEED_WALL_TIME, self.zone)


def _short(fact: Fact) -> str:
    return str(fact.instrument.payload["shortName"])


def _day(day: datetime.date) -> str:
    return f"{day.day} {day:%B %Y}"


def _title(fact: Fact, all_duties: int) -> str:
    if len(fact.duties) == all_duties:
        return f"{_short(fact)}: its duties apply from {_day(fact.day)}"
    if len(fact.duties) == 1:
        return f"{_short(fact)}: one duty applies from {_day(fact.day)}"
    return f"{_short(fact)}: {len(fact.duties)} duties apply from {_day(fact.day)}"


def _summary(fact: Fact) -> str:
    payload = fact.instrument.payload
    name = f"{payload['titles']['en']} ({payload['officialRef']})"
    in_force = payload.get("inForceFrom")
    said = f"{name} entered into force on {_day(datetime.date.fromisoformat(in_force))}. " if in_force else f"{name}. "
    duties = "One of its duties applies" if len(fact.duties) == 1 else f"{len(fact.duties)} of its duties apply"
    return f"{said}{duties} from {_day(fact.day)}."


def _so_what(fact: Fact, clock: Clock) -> str:
    if fact.day <= clock.today:
        return "These duties already apply. Confirm that our processes meet them."
    return "Check which of our products and processes these duties reach, and plan the changes before they apply."


def seed_change(fact: Fact, plan: CasePlan, clock: Clock, all_duties: int) -> Any:
    """The fact as a regulatory change: the instrument's own authority and page, its date
    with the duties it brings, its regime, and the agents' confirmed links to those duties.
    Merged on its stable key, so a reseed finds it."""
    tenancy.clear_tenant()
    payload = fact.instrument.payload
    authority = django_apps.get_model("library", "Authority").objects.get(key=payload["authority"])
    sweeper, confirmer = sweeper_key(), confirmer_key()
    seen = clock.first_seen(plan.weeks_ago)
    change = watch_seed.seed_change(
        stable_key=fact.stable_key,
        title=_title(fact, all_duties),
        key_date=fact.day,
        key_date_label="Applies",
        urgency=plan.urgency,
        first_seen_at=seen,
        so_what_draft=_so_what(fact, clock),
        change_type="adopted",
        authority=authority.key,
        authority_label=authority.name,
        published_unknown=True,
        source_url=fact.instrument.source_url,
        summary=_summary(fact),
        suggester=sweeper,
        type_confirmer=confirmer,
        confirmed_at=seen,
    )
    watch_seed.seed_document(change, url=fact.instrument.source_url, title=fact.instrument.source_label, publisher=authority.name, is_primary=True)
    in_force = payload.get("inForceFrom")
    if in_force:
        entered = datetime.date.fromisoformat(in_force)
        watch_seed.seed_event(change, label="Entered into force", event_date=entered, occurred=entered <= clock.today, sort_order=1)
    watch_seed.seed_event(change, label="Applies", event_date=fact.day, occurred=fact.day <= clock.today, sort_order=2)
    watch_seed.seed_scope_term_link(change, term_ref=payload["regime"], confidence=0.95, suggester=sweeper, confirmer=confirmer, confirmed_at=seen)
    for duty in fact.duties[:6]:
        watch_seed.seed_obligation_link(change, _obligation(duty), confidence=0.9, suggester=sweeper, confirmer=confirmer, confirmed_at=seen)
    return change


def _record(case: ChangeCase, action: str, after: dict[str, Any], before: dict[str, Any] | None = None) -> None:
    record(
        action=action,
        actor=SEED_ACTOR,
        subject_type="change_case",
        subject_id=case.id,
        subject_title=case.change.title,
        summary="Seeded for the public demo.",
        tenant_id=case.tenant_id,
        before=before,
        after=after,
    )


def seed_case(tenant: Tenant, change: Any, plan: CasePlan, clock: Clock, people: dict[str, User]) -> ChangeCase:
    """The bank's case walked to the plan's category, every move a transition and an audit
    row, as the E2E seed walks its journeys' cases. Written once: a case that exists is left
    as it is, because its ledger cannot be rewound."""
    tenancy.activate(tenant.id)
    existing = ChangeCase.objects.filter(change=change).first()  # ordering: one per (tenant, change)
    if existing is not None:
        return existing
    seen = change.first_seen_at
    span = clock.now - seen

    def moment(status: CaseStatusCategory) -> datetime.datetime:
        return seen + span * _STEP[status] / (len(_PATH) + 1)

    officer = people[_SARA]
    owner = people[plan.owner] if plan.owner else None
    path = [CaseStatusCategory.NEW, CaseStatusCategory.DISMISSED] if plan.status == CaseStatusCategory.DISMISSED else list(_PATH[: _PATH.index(plan.status) + 1])
    triaged = CaseStatusCategory.ASSIGNED in path
    closed = plan.status == CaseStatusCategory.CLOSED
    dismissed = plan.status == CaseStatusCategory.DISMISSED
    vocab = django_apps.get_model
    confirmed_at = moment(CaseStatusCategory.ASSIGNED) if (triaged or plan.so_what_confirmed) else None
    case = ChangeCase.objects.create(
        tenant=tenant,
        change=change,
        status=plan.status.value,
        urgency=vocab("taxonomy", "Urgency").objects.get(key=plan.urgency),
        urgency_confirmed=triaged,
        footprint_match=True,
        owner=owner,
        so_what_text=change.so_what_draft,
        so_what_confirmed=confirmed_at is not None,
        so_what_confirmed_by=officer if confirmed_at is not None else None,
        so_what_confirmed_at=confirmed_at,
        triaged_by=officer if triaged else None,
        triaged_at=moment(CaseStatusCategory.ASSIGNED) if triaged else None,
        dismissed_reason=vocab("taxonomy", "DismissalReason").objects.get(key="already_covered") if dismissed else None,
        dismissed_by=officer if dismissed else None,
        dismissed_at=moment(CaseStatusCategory.DISMISSED) if dismissed else None,
        signoff_requested_by=people[plan.requested_by] if plan.requested_by else None,
        signoff_requested_at=moment(CaseStatusCategory.SIGNOFF) if plan.requested_by else None,
        signed_off_by=people[_MARIA] if closed else None,
        close_reason=vocab("taxonomy", "ClosureReason").objects.get(key="signed_off") if closed else None,
        closed_at=moment(CaseStatusCategory.CLOSED) if closed else None,
    )
    _record(case, "case.created", {"status": CaseStatusCategory.NEW.value})
    for previous, status in zip(path, path[1:], strict=False):
        by = {
            CaseStatusCategory.ASSIGNED: officer,
            CaseStatusCategory.DISMISSED: officer,
            CaseStatusCategory.CLOSED: people[_MARIA],
            CaseStatusCategory.SIGNOFF: people[plan.requested_by] if plan.requested_by else None,
        }.get(status, owner)
        at = moment(status)
        # The fixture path (a raw save) keeps the made-up moment in the append-only ledger.
        CaseTransition(tenant=tenant, case=case, from_status=previous.value, to_status=status.value, at=at, by_user=by).save_base(raw=True)
        _record(case, _MOVE_ACTION[status], {"status": status.value, "at": at.isoformat()}, before={"status": previous.value})
    if CaseStatusCategory.ASSESSING in path:
        _seed_assessment(case, plan, clock, owner, moment(CaseStatusCategory.ASSESSING))
    for action in plan.actions:
        _seed_action(case, action, clock, owner, people, moment(CaseStatusCategory.ASSESSING), moment(CaseStatusCategory.IMPLEMENTING))
    case_matching._recompute(tenant.id, change_id=change.id)
    case.refresh_from_db()
    return case


def _seed_assessment(case: ChangeCase, plan: CasePlan, clock: Clock, owner: User | None, saved_at: datetime.datetime) -> None:
    deadline = case.change.key_date if plan.status == CaseStatusCategory.CLOSED else clock.today + datetime.timedelta(days=30)
    ImpactAssessment.objects.create(
        tenant=case.tenant,
        case=case,
        applies=AssessmentApplies.YES.value,
        why="We offer the affected services to retail and professional clients from the Swedish bank.",
        what_must_change="Update the process and the customer documents, and brief the teams who run them.",
        internal_deadline=deadline,
        effort=django_apps.get_model("taxonomy", "EffortSize").objects.get(key="m"),
        saved=True,
        saved_by=owner,
        saved_at=saved_at,
    )
    _record(case, "case.assessment_saved", {"applies": AssessmentApplies.YES.value, "effort": "m", "internalDeadline": deadline.isoformat() if deadline else None})


def _seed_action(
    case: ChangeCase, plan: CaseAction, clock: Clock, owner: User | None, people: dict[str, User], added_at: datetime.datetime, done_at: datetime.datetime
) -> None:
    due = done_at.date() if plan.done else clock.today + datetime.timedelta(days=plan.due_in_days)
    action = Action(
        tenant=case.tenant,
        case=case,
        title=plan.title,
        owner=people[plan.owner],
        due_date=due,
        done_at=done_at if plan.done else None,
        done_by=people[plan.owner] if plan.done else None,
        created_by=owner,
        created_at=added_at,
    )
    action.save_base(raw=True)
    _record(case, "case.action_added", {"actionId": str(action.id), "ownerId": str(action.owner_id), "dueDate": due.isoformat()})
    if plan.done:
        _record(case, "case.action_completed", {"actionId": str(action.id), "at": done_at.isoformat()})


def seed_case_extras(tenant: Tenant, case: ChangeCase, plan: CasePlan, clock: Clock, people: dict[str, User]) -> None:
    """The case's evidence, people and comments, each once."""
    tenancy.activate(tenant.id)
    storage = get_storage()
    for name, state in plan.evidence:
        url = state if state.startswith("https://") else ""
        content = e2e_seed.seed_evidence_pdf(name)
        row = Evidence.objects.filter(case=case, name=name).first()  # ordering: one per (case, name)
        if row is None:
            at = case.change.first_seen_at + (clock.now - case.change.first_seen_at) / 2
            kind = EvidenceKind.LINK if url else EvidenceKind.FILE
            scan = "clean" if url else state
            row = Evidence(
                tenant=tenant, case=case, kind=kind.value, name=name, url=url, uploaded_by=people[plan.owner or _JOHAN],
                uploaded_at=at, scan_state=scan, scanned_at=None if scan == "pending" else at,
            )
            if kind is EvidenceKind.FILE:
                row.storage_key = f"{tenant.id}/cases/{case.id}/evidence/{uuid.uuid4().hex}"
                row.content_hash = "sha256:" + hashlib.sha256(content).hexdigest()
                row.size_bytes = len(content)
                row.mime_type = "application/pdf"
            row.save_base(raw=True)
            record(
                action="case.evidence_attached", actor=SEED_ACTOR, subject_type="evidence", subject_id=row.id,
                subject_title=case.change.title, summary="Seeded for the public demo.", tenant_id=tenant.id,
                after={"evidenceId": str(row.id), "caseId": str(case.id), "kind": row.kind, "scanState": row.scan_state},
            )
        if row.storage_key and row.scan_state != "infected" and not storage.exists(row.storage_key):
            storage.write(row.storage_key, content, row.mime_type)
    live = Participant.objects.filter(case=case, removed_at__isnull=True)
    for who in plan.participants:
        team = django_apps.get_model("taxonomy", "Team").objects.get(key=who.removeprefix("team:")) if who.startswith("team:") else None
        person = None if team is not None else people[who]
        if live.filter(team=team, user=person).exists():
            continue
        joined = Participant.objects.create(tenant=tenant, case=case, team=team, user=person, added_by=people[_SARA], added_at=clock.at(-2))
        e2e_seed._seeded(tenant, "participant", joined, case.change.stable_key, {"caseId": str(case.id)})
    for index, (author, body, hours, mentions) in enumerate(plan.comments):
        spec = SeedComment(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"demo-comment:{case.change.stable_key}:{index}"),
            tenant_slug=tenant.slug,
            subject_type="change_case",
            subject_key=case.change.stable_key,
            author=author,
            body=body,
            # `_seed_comment` dates a comment from the bank's 09:00 today.
            before_anchor=datetime.timedelta(hours=hours) + (e2e_seed.case_anchor(tenant.timezone) - clock.now),
            mentions=mentions,
        )
        if not django_apps.get_model("collab", "Comment").objects.filter(pk=spec.id).exists():
            e2e_seed._seed_comment(tenant, spec, people)


def seed_changes(tenant: Tenant, people: dict[str, User], clock: Clock) -> int:
    """The facts the bank's feed carries and its case for each. Which facts depends on the day
    it runs: the nearest dates still ahead, and the most recent already past."""
    every = facts()
    all_duties: dict[str, int] = {}
    for entry in baseline.load():
        if entry.kind == baseline.OBLIGATION:
            all_duties[entry.instrument] = all_duties.get(entry.instrument, 0) + 1
    taken: set[str] = set()
    ahead = [fact for fact in every if fact.day > clock.today]
    past = [fact for fact in reversed(every) if fact.day <= clock.today]
    plans: list[tuple[Fact, CasePlan]] = []
    plans += zip(_pick([f for f in ahead if _in(f, ("eu", "se"))], taken, len(UPCOMING_PLANS)), UPCOMING_PLANS, strict=False)
    plans += zip(_pick([f for f in past if _in(f, ("eu", "se"))], taken, len(PAST_PLANS)), PAST_PLANS, strict=False)
    plans += zip(_pick([f for f in ahead + past if _in(f, DEMO_WATCHED_MARKETS)], taken, 1), (WATCHED_PLAN,), strict=False)
    plans += zip(_pick([f for f in ahead + past if _in(f, ("no",))], taken, 1), (OUTSIDE_PLAN,), strict=False)
    for fact, plan in plans:
        change = seed_change(fact, plan, clock, all_duties[fact.instrument.key])
        case = seed_case(tenant, change, plan, clock, people)
        seed_case_extras(tenant, case, plan, clock, people)
    tenancy.clear_tenant()
    return len(plans)


def seed_sources() -> None:
    """A sweep check on each source the baseline registered, every one of them healthy."""
    tenancy.clear_tenant()
    for source in django_apps.get_model("watch", "Source").objects.filter(active=True):
        watch_seed.seed_source_check(source, status=CheckStatus.OK)


def seed_public_demo(now: datetime.datetime | None = None) -> dict[str, int]:
    """The whole demo dataset, in one transaction as `seed_e2e` is. Idempotent: a second run
    files, approves and writes nothing new."""
    from apps.shared.management.commands.seed_reference import REFERENCE_SEEDS

    e2e_seed.refuse_when_deployed("seed_public_demo")
    MockMailer.reset()
    clock = Clock(now or timezone.now(), ZoneInfo(TENANT.timezone))
    with transaction.atomic():
        for _name, seed, _breaks in REFERENCE_SEEDS:
            seed()
        counts = seed_library()
        tenant = seed_tenant()
        people = seed_people(tenant)
        seed_scope(tenant)
        org = e2e_seed._seed_organisation(tenant, DEMO_REGISTER, people)
        e2e_seed._seed_register(tenant, DEMO_REGISTER, people, org)
        counts["changes"] = seed_changes(tenant, people, clock)
        seed_sources()
        # Last week's briefing, sent by the production job, its mail delivered at once (H21).
        tenancy.activate(tenant.id)
        with override_settings(CELERY_TASK_ALWAYS_EAGER=True):
            home_tasks.send_weekly_briefing(tenant.id)
        # The search index over the whole library, embedded now so nothing waits on the worker.
        tenancy.clear_tenant()
        counts.update(e2e_seed.seed_search_index())
    return counts
