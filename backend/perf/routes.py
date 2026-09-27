"""The measured route list (NFR-02): one row per API operation, with the principal that
calls it, the fixture that fills its request and the setting that holds its budget
(`API_BUDGET_MS` unless the row names its own, as hybrid search and Ask do).

An append ledger: each performance pass adds its own rows under a comment naming the pass,
and records them with `python scripts/perf_report.py --record`.

A route behind a per-caller rate limit answers 429 once the requests in its window pass the
limit, and the harness fails a 429 rather than timing it. Every row makes PERF_SAMPLES + 1
requests (21 by default). The window is a fixed minute counted in Redis per caller, so it
spans runs: a --record followed at once by a check counts both. It also spans the routes
that share a bucket: POST /search and POST /search/similar spend one allowance of
SEARCH_RATE_PER_USER_PER_MINUTE (60), and Ask allows ASK_RATE_PER_USER_PER_MINUTE (10). A
pass that measures a limited route raises that limit through its env override for both the
record and the check, or waits out the minute between them. The r1-perf pass raises them
all, for the record and the check alike: SEARCH_RATE_PER_USER_PER_MINUTE=1000,
ASK_RATE_PER_USER_PER_MINUTE=1000 and CALENDAR_FEED_RATE_PER_MINUTE=1000 (one address
fetched 21 times, past its 20), and AUTH_RATE_PER_IP_PER_MINUTE=1000 with
ENROLMENT_CODE_RATE_PER_ADDRESS_PER_HOUR and ENROLMENT_CODE_RATE_PER_IP_PER_HOUR at 1000
for the auth ceremonies, which E2E_MODE already exempts where a journey repeats them.

The r2-perf pass adds the R2 operations in three blocks, chunk 8, chunks 9 and 10, and
chunk 11, each row as the principal that calls it in R2. A row with a `variant` measures an
operation a second way, keyed apart in the baseline: My work as a department head, the
inventory filtered by the bank's overlay, what applies, the register reads and MCP with a
personal token beside an entry's key, and search as an entry's key. A versioned write sends
the version it read in `If-Match` through its principal (`_versioned`). Heavy calls are
measured at their caps: applicability and a paste at REGISTER_BULK_MAX, a tagging preview
at BULK_TAGGING_MAX_RECORDS, the Statement of Applicability at Annex A's 93 units and the
inbox at 5,000 rows. An agent access credential is minted per row, so each stays inside
AGENT_ACCESS_RATE_PER_MINUTE. The pass also raises PROBLEM_REPORTS_PER_USER_PER_HOUR to
1000: a record and a check file 42 problem reports as one reader inside an hour, past 30. The slot is seeded and measured with E2E_MODE on, as the
E2E stack seeds it, so Anna's invitation and the emailed code hold their fixed values. The
client talks to the host `testserver`, which ALLOWED_HOSTS must name when the report runs
under config.settings. `publishAgentVersion`
is the one R2 operation left out: it publishes only the next version of a definition from
a folder the build ships, and no seeded definition is one version behind such a folder.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart
from django.utils import timezone

from apps.agents import agent_access, budget
from apps.agents.models import Agent, AgentAccess, AgentRun, ResearchRequest, ResearchRequestKind, RunStatus, RunTrigger, TenantAgent
from apps.agents.schemas import AgentBudgetInput
from apps.agents.tenant_agents import pause
from apps.cases.models import Action, ChangeCase, Evidence
from apps.collab.models import Comment, Notification, NotificationKind, Participant
from apps.governance import reach
from apps.governance.models import AgentAccessCall, TenantReachRequest
from apps.home import feed
from apps.home.models import Briefing
from apps.identity import api_keys_logic, code_logic, invitation_logic, session_logic
from apps.identity.models import ApiKey, AuthChallenge, ChallengeKind, SessionKind, User, UserSession, WebAuthnCredential
from apps.identity.tests_webauthn_support import SoftwareAuthenticator
from apps.identity.tokens import b64url
from apps.library import testing as library_testing
from apps.library.models import Instrument, Obligation, ProblemReport, Provision
from apps.proposals import logic as proposals_logic
from apps.proposals.models import Proposal, ProposalStatus
from apps.register import applicability, gaps
from apps.register.models import DutyOccurrence, Gap, InternalLink, SoaUnit, TenantObligation, TenantObligationScope
from apps.register.schemas import RegisterApplicabilityBody, RegisterApplicabilityManyBody, RegisterGapPatch, RegisterRiskAcceptanceBody
from apps.reports import tasks as export_tasks
from apps.reports.models import ExportJob
from apps.search import ask
from apps.search.schemas import AskRequest, AskStartEvent
from apps.shared import factories, tenancy
from apps.shared.audit import Actor
from apps.shared.e2e_logins import E2E_INVITATION_TOKEN_ANNA, TENANT_A_SLUG, TENANT_B_SLUG
from apps.shared.e2e_passkeys import E2E_PASSKEYS
from apps.shared.e2e_seed import (
    CASE_PARTICIPATION_CHANGE,
    E2E_STANDARD_OBLIGATION,
    E2E_STANDARD_TERM,
    EXPECTED_ASK,
    EXPECTED_BULK_TAGGING,
    EXPECTED_CHUNK5_WATCH,
    EXPECTED_CHUNK11,
    EXPECTED_COMMENTS,
    EXPECTED_J11,
    HISTORY_OBLIGATION,
    LEAVER,
    PARTICIPANT,
    PARTICIPATION_OBLIGATION,
    RETAIL_DEPARTMENT,
    RETAIL_TEAM,
    SPANNING_OBLIGATION,
    anna_invitation,
    seed_evidence_pdf,
)
from apps.shared.models import Tenant
from apps.shared.testing import sign_in, user_principal
from apps.taxonomy import footprint_logic, tenant_lists_logic
from apps.taxonomy.models import ComplianceStatus, TaxonomyTerm
from apps.tenants import reassignment, support_access
from apps.tenants.models import InternalItem, Licence, OrgUnit, OrgUnitKind, SupportAccess, SupportAccessStatus, TenantProduct
from apps.tenants.schemas import ConsoleSupportAccessBody
from apps.watch.models import ChangeEvent, RegulatoryChange, Source
from perf.harness import Call, PerfRoute, PrincipalFactory, RouteFailed, anonymous, person

READER = "reader@example-bank.test"  # tenant A's seeded reader (apps/shared/e2e_logins.py)

# --- r1-perf: who calls what (apps/shared/e2e_logins.py) ----------------------------------
ADMIN = "admin@example-bank.test"
OFFICER = "compliance_officer@example-bank.test"
APPROVER = "approver@example-bank.test"
EDITOR = "editor2@bleqq.test"  # the library editor who decides what editor@ and the agents file
PLATFORM = "platform@bleqq.test"
ANNA = "anna@example-bank.test"  # the one seeded invitee still awaiting enrolment
# The scopes the watch sweeper's platform key holds: the watch writes of R1 (ID-10), the
# proposals it files and the similarity read it checks for a duplicate with.
SWEEPER_SCOPES = ("agent-runs:write", "sources:write", "changes:write", "proposals:write", "library:read", "search:read")
SWEEPER_AGENT = "watch-sweeper"
PERF_KEY = "Performance harness key"
TAG_LIST = "tenant_tag"  # a bank's own list, whose seeded "whistleblowing" is no system row
SOURCE_URL = "https://www.fi.se/en/published/news/2026/research-payments/"


def stepped_up(email: str, tenant: str | None = None) -> PrincipalFactory:
    """`person()` with a fresh passkey assertion on the session, which a step-up route asks
    for (ID-06): the session and the assertion `sign_in(step_up=True)` writes."""

    def headers() -> dict[str, Any]:
        user = User.objects.filter(email=email).first()
        bank = Tenant.objects.filter(slug=tenant).first() if tenant else None
        if user is None or (tenant and bank is None):
            raise RouteFailed(f"{email} in {tenant or 'the platform'} is not in this database: seed it with manage.py seed_e2e")
        return sign_in(user, tenant=bank, step_up=True)

    return headers


def _mint_key() -> tuple[ApiKey, str]:
    """A platform key bound to the watch sweeper's definition, minted the way the console
    mints one (`api_keys_logic.create_agent_key`) inside the harness's transaction; the
    plain value is what the agent sends as `X-API-Key`."""
    creator = User.objects.get(email=PLATFORM)
    return api_keys_logic.create_agent_key(
        actor=session_logic.actor_of(creator),
        created_by=creator,
        agent_id=Agent.objects.get(key=SWEEPER_AGENT).id,
        name=PERF_KEY,
        scopes=SWEEPER_SCOPES,
        expires_at=None,
        step_up_assertion_id=None,
    )


def sweeper() -> dict[str, Any]:
    """The watch sweeper, calling with a real key the real resolver authenticates."""
    return {"HTTP_X_API_KEY": _mint_key()[1]}


def _run() -> AgentRun:
    """A run the harness's key has open, which an agent's write names (AGT-01)."""
    key = ApiKey.objects.get(name=PERF_KEY)
    return AgentRun.objects.create(agent=Agent.objects.get(key=SWEEPER_AGENT), api_key=key, model="agent pipeline 0.4", pipeline_version="0.4")


def _user(email: str) -> User:
    return User.objects.get(email=email)


def _tenant() -> Tenant:
    return Tenant.objects.get(slug=TENANT_A_SLUG)


def _obligation(key: str = EXPECTED_ASK.pending_obligation) -> Obligation:
    return Obligation.objects.get(stable_key=key)


def _change(key: str = EXPECTED_CHUNK5_WATCH.obligations_change) -> RegulatoryChange:
    return RegulatoryChange.objects.get(stable_key=key)


def _term(dimension: str, key: str) -> TaxonomyTerm:
    return TaxonomyTerm.objects.get(dimension__key=dimension, key=key)


def _proposal(obligation: str) -> Proposal:
    return Proposal.objects.get(status=ProposalStatus.OPEN.value, target_id=_obligation(obligation).id)


def _on(**params: object) -> Callable[[], Call]:
    """A fixture that fills only the path, with values that need no lookup."""
    return lambda: Call(params=params)


# The sessions most rows sign in as (r1-perf).
reader = person(READER, TENANT_A_SLUG)
admin = person(ADMIN, TENANT_A_SLUG)
officer = person(OFFICER, TENANT_A_SLUG)
approver = person(APPROVER, TENANT_A_SLUG)
editor = person(EDITOR)
platform = person(PLATFORM)


def _instrument_call() -> Call:
    return Call(params={"instrument_id": Instrument.objects.get(stable_key="fffs-2017-2").id})


def _obligation_call() -> Call:
    return Call(params={"obligation_id": _obligation().id})


def _change_call() -> Call:
    return Call(params={"change_id": _change().id})


def _member(email: str) -> Callable[[], Call]:
    return lambda: Call(params={"user_id": _user(email).id})


def _device(email: str) -> SoftwareAuthenticator:
    """A software passkey of `email`'s, stored as theirs, so a ceremony's verify step runs
    the real signature check (apps/identity/tests_webauthn_support.py)."""
    device = SoftwareAuthenticator()
    user = _user(email)
    device.user_handle = user.id.bytes
    factories.passkey(user, public_key=b64url(device.cose_public_key()), credential_id=device.credential_id_b64)
    return device


def _challenge(kind: ChallengeKind, email: str | None = None) -> str:
    """An open challenge, as the ceremony's options step stores it: a person's is bound to
    their newest session, the one the harness just signed in."""
    user = _user(email) if email else None
    session = UserSession.objects.filter(user=user).order_by("-created_at").first() if user else None
    value = b64url(secrets.token_bytes(32))
    AuthChallenge.objects.create(
        kind=kind.value,
        challenge=value,
        user=user,
        session=session,
        expires_at=timezone.now() + timedelta(seconds=settings.CHALLENGE_TTL_SECONDS),
    )
    return value


def _sign_in_assertion() -> Call:
    device = _device(READER)
    return Call(body={"credential": device.assert_({"challenge": _challenge(ChallengeKind.AUTHENTICATION)})})


def _step_up_assertion() -> Call:
    device = _device(READER)
    return Call(body={"credential": device.assert_({"challenge": _challenge(ChallengeKind.STEP_UP, READER)})})


def _registration() -> Call:
    device = SoftwareAuthenticator()
    options = {"user": {"id": b64url(_user(READER).id.bytes)}, "challenge": _challenge(ChallengeKind.REGISTRATION, READER)}
    return Call(body={"credential": device.register(options), "nickname": "Work laptop"})


def _verify_code() -> Call:
    code_logic.request_code(ANNA, None)
    return Call(body={"email": ANNA, "code": settings.E2E_FIXED_CODE})


def _verify_invitation_code() -> Call:
    invitation_logic.open_invitation(E2E_INVITATION_TOKEN_ANNA, None)
    return Call(body={"token": E2E_INVITATION_TOKEN_ANNA, "code": settings.E2E_FIXED_CODE})


def _my_passkey() -> Call:
    first = WebAuthnCredential.objects.get(credential_id=E2E_PASSKEYS[READER].credential_id)
    return Call(params={"passkey_id": first.id}, body={"nickname": "Work laptop"})


def _second_passkey() -> Call:
    return Call(params={"passkey_id": factories.passkey(_user(READER), nickname="Old phone").id})


def _other_session() -> Call:
    bundle = session_logic.create_session(user=_user(READER), kind=SessionKind.FULL, tenant_id=_tenant().id, request=None)
    return Call(params={"session_id": bundle.session.id})


def _invitation() -> Call:
    invitation = anna_invitation()
    if invitation is None:
        raise RouteFailed("Anna's invitation is not open in this database: reseed it with manage.py seed_e2e")
    return Call(params={"invitation_id": invitation.id})


def _custom_role() -> Call:
    return Call(params={"key": factories.tenant_role_key(_tenant()).id}, body={"labels": {"en": "DORA reviewer"}})


def _footprint_request() -> Call:
    return Call(params={"request_id": factories.footprint_request(_tenant()).id}, body={"note": "Matches the licence."})


def _new_footprint_request() -> Call:
    """The officer takes back the seeded pending request first: one waits at a time."""
    tenant, officer = _tenant(), _user(OFFICER)
    footprint_logic.withdraw(
        tenant=tenant, request=factories.footprint_request(tenant), requester=officer, actor=session_logic.actor_of(officer)
    )
    return Call(body={"adds": [{"dimension": "account_type", "key": "pension"}], "removes": []})


def _suggestion() -> Call:
    suggestion = factories.vocabulary_suggestion(_tenant())
    return Call(params={**suggestion.params, "suggestion_id": suggestion.id})


def _retired_row() -> Call:
    tenant_lists_logic.retire(list_name=TAG_LIST, tenant=_tenant(), actor=session_logic.actor_of(_user(OFFICER)), key="whistleblowing", confirm=True)
    return Call(params={"list_name": TAG_LIST, "key": "whistleblowing"})


def _problem_report() -> Call:
    report = ProblemReport.objects.get(subject_id=_obligation().id)
    return Call(
        params={"report_id": report.id},
        body={"status": "answered", "resolutionNote": "Version 2 says ten years; the screen showed version 1."},
    )


def _answer() -> Call:
    who = _user(READER)
    events = list(ask.answer_events(AskRequest(question=EXPECTED_ASK.answered_question), tenant_id=_tenant().id, user_id=who.id))
    answer_id = next(event.id for event in events if isinstance(event, AskStartEvent))
    return Call(params={"answer_id": answer_id}, body={"feedback": "helpful"})


def _calendar_feed() -> Call:
    tenant, reader = _tenant(), _user(READER)
    tenancy.activate(tenant.id)  # the fetch carries no session, so nothing activated the bank
    created = feed.create_feed(tenant=tenant, user=reader, actor=session_logic.actor_of(reader), request=RequestFactory().get("/"))
    return Call(query={"token": parse_qs(urlsplit(created.url).query)["token"][0]}, params={"feed_id": created.feed.id})


def _briefing() -> Call:
    return Call(params={"week_start": Briefing.objects.filter(tenant=_tenant()).latest("week_start").week_start})


def _run_call(body: object = None) -> Callable[[], Call]:
    return lambda: Call(params={"run_id": _run().id}, body=body)


def _new_change() -> Call:
    return Call(
        body={
            "stableKey": "chg-perf-research-payments",
            "title": "FI adopts amended rules on paying for investment research",
            "changeType": "adopted",
            "authorityCode": "fi",
            "authorityLabel": "Finansinspektionen",
            "summary": "FI's board decided on 15 September 2026 to amend three regulations in the securities area.",
            "sourceLabel": "Finansinspektionen",
            "sourceUrl": SOURCE_URL,
            "termIds": [str(_term("regime", "securities").id)],
            "keyDate": "2026-10-01",
            "keyDatePrecision": "day",
            "agentRunId": str(_run().id),
            "model": "agent pipeline 0.4",
        }
    )


def _new_proposal() -> Call:
    return Call(
        body={
            "kind": "new_obligation_version",
            "title": "Version 2 of the PRIIPs key information duty",
            "targetType": "obligation",
            "targetId": str(_obligation("obl-priips-kid").id),
            "agentRunId": str(_run().id),
            "model": "agent pipeline 0.4",
            "sourceLabel": "Finansinspektionen, board decision 15 September 2026",
            "sourceUrl": SOURCE_URL,
            "fieldSources": {"effectiveFrom": SOURCE_URL, "summaries.en": SOURCE_URL},
            "payload": {
                "effectiveFrom": "2026-10-01",
                "effectiveFromPrecision": "day",
                "isMachine": True,
                "originalLanguage": "en",
                "summaries": {"en": "The key information document is given to a retail investor before the investment is made."},
            },
        }
    )


def _event() -> Call:
    event = ChangeEvent.objects.filter(change=_change(EXPECTED_CHUNK5_WATCH.timeline_change)).earliest("sort_order")
    return Call(
        params={"change_id": event.change_id, "event_id": event.id},
        body={"label": event.label, "eventDate": "2026-06-15", "datePrecision": "day", "occurred": True},
    )


def _links() -> Call:
    change = _change()
    return Call(
        params={"change_id": change.id},
        body=[
            {"obligationId": str(_obligation(key).id), "confidence": 0.8}
            for key in ("obl-dora-ict-register", "obl-client-assets")
        ],
    )


def _case(change: str, body: object = None, obligation: str = "") -> Callable[[], Call]:
    """The change of one of tenant A's cases, found through the case so the case exists."""

    def call() -> Call:
        case = ChangeCase.objects.get(tenant=_tenant(), change__stable_key=change)
        params: dict[str, object] = {"change_id": case.change_id}
        if obligation:
            params["obligation_id"] = _obligation(obligation).id
        return Call(params=params, body=body)

    return call


def _accept_link() -> Call:
    call = _case(EXPECTED_CHUNK5_WATCH.obligations_change)()
    return Call(params=call.params, body={"obligationId": str(_obligation("obl-dora-ict-register").id)})


def _source() -> Call:
    return Call(params={"source_id": Source.objects.get(name=EXPECTED_CHUNK5_WATCH.healthy_source).id}, body={"checkFrequency": "weekly"})


# --- r2-perf: who calls the R2 routes (apps/shared/e2e_logins.py) --------------------------
OWNER = "owner@example-bank.test"  # owns cases and register entries, so My work has rows
HEAD = "head@example-bank.test"  # heads Retail Banking, whose department My work reads
CONTRIBUTOR = "contributor@example-bank.test"
AWAY = "away@example-bank.test"  # TEN-S4's approver, who sets an absence
SECURITY = "security@example-bank.test"  # the second holder of security.manage (ACC-S11)
TOKENS = "tokens@example-bank.test"  # the officer who holds a personal access token (ACC-S3)
REVIEWER = "editor@bleqq.test"  # the second library editor: editor2@ filed the seeded batch
owner = person(OWNER, TENANT_A_SLUG)
security = stepped_up(SECURITY, TENANT_A_SLUG)
steward = stepped_up(ADMIN, TENANT_A_SLUG)  # every write to an agent access entry takes a step-up


def _versioned(principal: PrincipalFactory, build: Callable[[], tuple[Call, int]]) -> tuple[PrincipalFactory, Callable[[], Call]]:
    """A versioned write reads the version it was sent in `If-Match`, a header, which only the
    principal hands the harness: this signs in, builds the call, sends the version it found
    beside the session, and gives the fixture the call it built."""
    built: dict[str, Call] = {}

    def headers() -> dict[str, Any]:
        signed_in = principal()
        built["call"], version = build()
        return {**signed_in, "HTTP_IF_MATCH": str(version)}

    return headers, lambda: built["call"]


def _in_days(days: int) -> str:
    return (timezone.localdate() + timedelta(days=days)).isoformat()


# --- r2-perf, chunk 8: the register, the organisation and My work ---------------------------
ENTITY = "Example Bank AB"  # tenant A's bank, which the ISO/IEC 27001 duty spans
FUND_ENTITY = "Example Fonder AB"  # the second entity SPANNING_OBLIGATION is kept for
ANNEX_A = 93  # the controls of ISO/IEC 27001:2022 Annex A, the statement a bank lists
GAP_OBLIGATION = "obl-costs-charges"  # its seeded gap is open and has no acceptance waiting
AUDIT_GAP_OBLIGATION = "obl-isk-control-statements"  # its seeded audit gap, open likewise


def _entity(name: str = ENTITY) -> OrgUnit:
    return OrgUnit.objects.get(name=name, kind=OrgUnitKind.LEGAL_ENTITY.value)


def _org_unit(name: str = ENTITY) -> OrgUnit:
    return OrgUnit.objects.get(tenant=_tenant(), name=name)


def _gap(obligation: str = GAP_OBLIGATION) -> Gap:
    return Gap.objects.get(tenant_obligation__obligation__stable_key=obligation)


def _officer_actor() -> Actor:
    return session_logic.actor_of(_user(OFFICER))


def _follows_standard() -> Obligation:
    """The bank answers that it follows ISO/IEC 27001, as the officer does before listing a
    unit (REG-08): the conformance duty's scope row for ENTITY applies."""
    duty = _obligation(E2E_STANDARD_OBLIGATION)
    body = RegisterApplicabilityBody.model_validate({"orgUnitId": str(_entity().id), "applicability": "applies", "reason": "Certified"})
    applicability.set_applicability(tenant=_tenant(), actor=_officer_actor(), order=["en"], obligation_id=duty.id, body=body, expected_version=None)
    return duty


def _units(count: int) -> list[SoaUnit]:
    """`count` undecided units of ENTITY's statement under the standard."""
    duty = _follows_standard()
    scope = TenantObligationScope.objects.get(tenant_obligation__obligation=duty, org_unit=_entity(), product__isnull=True)
    status = ComplianceStatus.objects.get(is_default=True, active=True)
    return SoaUnit.objects.bulk_create(
        SoaUnit(tenant_id=scope.tenant_id, scope=scope, reference=f"A.{n + 1}", title=f"Our control {n + 1}", compliance_status=status)
        for n in range(count)
    )


def _unit() -> SoaUnit:
    """The one unit a rename or a removal names, listed on first use, with no history yet."""
    return SoaUnit.objects.filter(reference="A.1").first() or _units(1)[0]  # ordering: at most one live row here


def _statement_call(units: list[SoaUnit]) -> Call:
    return Call(params={"obligation_id": units[0].scope.tenant_obligation.obligation_id}, query={"entity": str(_entity().id)})


def _answered_statement() -> Call:
    """The statement once the bank follows the standard in its regulatory scope (FP-03) and
    has answered every unit, so each carries a history of one decision."""
    footprint_logic.seed_terms(tenant=_tenant(), actor=_officer_actor(), terms=[_term(*E2E_STANDARD_TERM)])
    units = _units(ANNEX_A)
    rows = [
        {"obligationId": str(unit.scope.tenant_obligation.obligation_id), "unitId": str(unit.id), "applicability": "applies", "reason": "Certified"}
        for unit in units
    ]
    applicability.set_applicability_many(tenant=_tenant(), actor=_officer_actor(), order=["en"], body=RegisterApplicabilityManyBody.model_validate({"rows": rows}))
    return _statement_call(units)


def _answers_at_cap() -> Call:
    """A pasted Statement of Applicability's answers, as many as one call takes (AC-REG1)."""
    units = _units(settings.REGISTER_BULK_MAX)
    duty = units[0].scope.tenant_obligation.obligation_id
    return Call(body={"rows": [{"obligationId": str(duty), "unitId": str(unit.id), "applicability": "applies", "reason": "Certified"} for unit in units]})


def _paste_at_cap() -> Call:
    """A paste committed whole, as many lines as one call takes, each answered."""
    lines = [
        {"reference": f"A.{n + 1}", "title": f"Our control {n + 1}", "applicability": "applies", "reason": "Certified"}
        for n in range(settings.REGISTER_BULK_MAX)
    ]
    return Call(params={"obligation_id": _follows_standard().id}, body={"orgUnitId": str(_entity().id), "lines": lines, "dryRun": False})


def _occurrence() -> DutyOccurrence:
    """The ISK control statements' yearly filing, a duty the library carries on a schedule,
    and its occurrence due today on the bank's entry, which applies (REG-07)."""
    duty = library_testing.recurring_duty(
        _obligation(AUDIT_GAP_OBLIGATION), title="Control statements to the Tax Agency", rule="FREQ=YEARLY;BYMONTH=1;BYMONTHDAY=31"
    )
    entry = TenantObligation.objects.get(obligation_id=duty.obligation_id)
    return DutyOccurrence.objects.create(tenant_id=entry.tenant_id, recurring_duty=duty, tenant_obligation=entry, due_date=timezone.localdate())


def _waiting_acceptance() -> Call:
    """The officer asks for the audit gap's risk to be accepted; the approver decides it."""
    gap = _gap(AUDIT_GAP_OBLIGATION)
    body = RegisterRiskAcceptanceBody.model_validate({"reason": "compensating_control"})
    gaps.request_risk_acceptance(tenant=_tenant(), actor=_officer_actor(), order=["en"], gap_id=gap.id, body=body)
    return Call(params={"gap_id": gap.id})


def _closed_gap() -> Call:
    gap = _gap()
    gaps.update_gap(
        tenant=_tenant(), actor=_officer_actor(), order=["en"], gap_id=gap.id, body=RegisterGapPatch.model_validate({"status": "closed"}), expected_version=gap.version
    )
    return Call(params={"gap_id": gap.id})


def _new_gap() -> Call:
    return Call(
        params={"obligation_id": _obligation(GAP_OBLIGATION).id},
        body={
            "title": "Ex post statements leave out third-party payments",
            "severity": "medium",
            "source": "assessment",
            "ownerId": str(_user(OFFICER).id),
            "targetDate": _in_days(90),
            "remediation": "Add received inducements to the annual cost statement.",
        },
    )


def _on_obligation(key: str) -> Callable[[], Call]:
    return lambda: Call(params={"obligation_id": _obligation(key).id})


def _register_update() -> tuple[Call, int]:
    body = {"complianceStatus": "gap", "riskRating": "high", "rationale": "Currency exchange cost is still missing ex ante."}
    entry = TenantObligation.objects.get(obligation__stable_key=GAP_OBLIGATION)
    return Call(params={"obligation_id": entry.obligation_id}, body=body), entry.version


def _entity_update() -> tuple[Call, int]:
    scope = TenantObligationScope.objects.get(tenant_obligation__obligation__stable_key=SPANNING_OBLIGATION, org_unit__name=FUND_ENTITY, product__isnull=True)
    body = {"complianceStatus": "compliant", "rationale": "Negative target markets are now set for every fund."}
    return Call(params={"obligation_id": _obligation(SPANNING_OBLIGATION).id, "org_unit_id": scope.org_unit_id}, body=body), scope.version


def _gap_update() -> tuple[Call, int]:
    gap = _gap()
    return Call(params={"gap_id": gap.id}, body={"status": "remediating", "remediation": "Add the exchange cost to the ex ante view."}), gap.version


def _unit_update(body: object = None) -> Callable[[], tuple[Call, int]]:
    def build() -> tuple[Call, int]:
        unit = _unit()
        return Call(params={"unit_id": unit.id}, body=body), unit.version

    return build


def _grant(active: bool = False) -> SupportAccess:
    """Platform support's request to read tenant A, made the way the console makes it; an
    active one is then approved by the bank's admin, as the approve route leaves it."""
    tenant, requester = _tenant(), _user(PLATFORM)
    out = support_access.request_access(
        tenant_id=tenant.id,
        requester=requester,
        actor=session_logic.actor_of(requester),
        body=ConsoleSupportAccessBody(purpose="The bank's watch feed stopped updating.", ticket_ref="SUP-2419", hours=2),
    )
    grant = SupportAccess.objects.get(pk=out.id)
    if active:
        now = timezone.now()
        grant.status, grant.approved_by, grant.started_at, grant.expires_at = SupportAccessStatus.APPROVED.value, _user(ADMIN), now, now + timedelta(hours=2)
        grant.save(update_fields=["status", "approved_by", "started_at", "expires_at"])
    return grant


def _grant_call(active: bool = False) -> Call:
    return Call(params={"grant_id": _grant(active).id})


def _listed_grant() -> Call:
    _grant()
    return Call()


def _console(fixture: Callable[[], Call]) -> Callable[[], Call]:
    """A fixture that wrote in tenant A, handed back with no bank active, as the platform
    session found it."""

    def call() -> Call:
        made = fixture()
        tenancy.clear_tenant()
        return made

    return call


def _removal() -> Call:
    """The leaver's every kind of work handed to the compliance officer, who may work cases."""
    tenant, leaver = _tenant(), _user(LEAVER)
    owned = reassignment.owned_work(tenant.id, leaver.id)
    kinds = [row["kind"] for row in reassignment.open_work_counts(tenant.id, leaver.id) if row["kind"] in owned]
    return Call(params={"user_id": leaver.id}, body={"owners": [{"kind": kind, "userId": str(_user(OFFICER).id)} for kind in kinds]})


def _department() -> Call:
    """My work for the department the head heads, as the department switch asks for it."""
    return Call(query={"scope": "unit", "unit": str(OrgUnit.objects.get(tenant=_tenant(), head_user__email=HEAD).id)})


# --- r2-perf, chunks 9 and 10: cases, collaboration, tagging and exports --------------------
INBOX_ROWS = 5000  # the inbox a busy member has piled up, for the two inbox rows
EVIDENCE_CASE = "chg-e2e-case-evidence"
FILE_CASE = "chg-e2e-case-file"
CLEAN_FILE = "AMLR gap analysis.pdf"
UPLOADED_FILE = "Research payment criteria signed.pdf"
TAG = EXPECTED_BULK_TAGGING.tag_key


def _case_row(change: str) -> ChangeCase:
    return ChangeCase.objects.get(tenant=_tenant(), change__stable_key=change)


def _move(change: str, body: object = None) -> Callable[[], tuple[Call, int]]:
    def build() -> tuple[Call, int]:
        case = _case_row(change)
        return Call(params={"change_id": case.change_id}, body=body), case.version

    return build


def _open_action() -> Action:
    return Action.objects.get(case=_case_row(EVIDENCE_CASE), done_at__isnull=True)


def _action(body: object = None) -> Callable[[], tuple[Call, int]]:
    def build() -> tuple[Call, int]:
        action = _open_action()
        return Call(params={"action_id": action.id}, body=body), action.version

    return build


def _ready_for_signoff() -> tuple[Call, int]:
    """The evidence case with its one open action done, so the request passes both guards."""
    Action.objects.filter(pk=_open_action().pk).update(done_at=timezone.now(), done_by=_user(OWNER))
    return _move(EVIDENCE_CASE)()


def _evidence(name: str) -> Callable[[], Call]:
    return lambda: Call(params={"evidence_id": Evidence.objects.get(tenant=_tenant(), name=name).id})


def _upload() -> Call:
    """A signed PDF attached to the evidence case, one multipart post through the scanner."""
    body = encode_multipart(
        BOUNDARY, {"kind": "file", "name": UPLOADED_FILE, "file": SimpleUploadedFile(UPLOADED_FILE, seed_evidence_pdf(UPLOADED_FILE), "application/pdf")}
    )
    return Call(params={"change_id": _case_row(EVIDENCE_CASE).change_id}, body=body, content_type=MULTIPART_CONTENT)


def _case_participant(email: str) -> Call:
    case = _case_row(CASE_PARTICIPATION_CHANGE)
    row = Participant.objects.get(case=case, user__email=email, removed_at__isnull=True)
    return Call(params={"change_id": case.change_id, "participant_id": row.id})


def _obligation_participant() -> Call:
    obligation = _obligation(PARTICIPATION_OBLIGATION)
    row = Participant.objects.get(tenant_obligation__obligation=obligation, user__email=PARTICIPANT, removed_at__isnull=True)
    return Call(params={"obligation_id": obligation.id, "participant_id": row.id})


def _comments() -> Call:
    return Call(query={"subjectType": "change_case", "subjectId": str(_case_row(CASE_PARTICIPATION_CHANGE).id)})


def _new_comment() -> Call:
    return Call(
        body={
            "subjectType": "change_case",
            "subjectId": str(_case_row(CASE_PARTICIPATION_CHANGE).id),
            "body": "Oskar, can you check the securities lending fields before Thursday?",
            "mentionUserIds": [str(_user(PARTICIPANT).id)],
        },
    )


def _my_fresh_comment() -> Call:
    """A comment the officer wrote a moment ago, inside the edit window."""
    comment = Comment.objects.create(
        tenant=_tenant(), subject_type="change_case", subject_id=_case_row(CASE_PARTICIPATION_CHANGE).id, author=_user(OFFICER), body="The fields are mapped."
    )
    return Call(params={"comment_id": comment.id}, body={"body": "The reporting fields are mapped."})


def _officers_comment() -> Call:
    return Call(params={"comment_id": next(comment.id for comment in EXPECTED_COMMENTS if comment.author == OFFICER)})


def _notification() -> Notification:
    case = _case_row(CASE_PARTICIPATION_CHANGE)
    return Notification(
        tenant=_tenant(), user=_user(PARTICIPANT), kind=NotificationKind.MENTION.value, subject_type="change_case", subject_id=case.id, title=case.change.title
    )


def _full_inbox() -> Call:
    """The reader's inbox (PARTICIPANT) with INBOX_ROWS unread mentions on top of the seeded ones."""
    Notification.objects.bulk_create(_notification() for _ in range(INBOX_ROWS))
    return Call()


def _one_notification() -> Call:
    row = _notification()
    row.save()
    return Call(params={"notification_id": row.id})


def _export(built: bool) -> Callable[[], Call]:
    """A case file export job of the officer's; `built` runs the worker's task on it in the
    harness's transaction, so the file is ready to download."""

    def call() -> Call:
        job = ExportJob.objects.create(tenant=_tenant(), kind="case_file", subject_id=_case_row(FILE_CASE).id, format="txt", requested_by=_user(OFFICER))
        if built:
            export_tasks.run_export(_tenant().id, str(job.id))
        return Call(params={"export_id": job.id})

    return call


def _tagging(obligation: str) -> Callable[[], Call]:
    return lambda: Call(body={"tagKey": TAG, "subjectType": "obligation", "subjectId": str(_obligation(obligation).id)})


def _tag_batch(ids: list[str]) -> Call:
    return Call(body={"tagKey": TAG, "subjectType": "obligation", "subjectIds": ids})


def _preview_at_cap() -> Call:
    """A selection as large as a batch may be: every seeded obligation, and as many more
    built by the library's own builder as the cap leaves room for."""
    seeded = [str(pk) for pk in Obligation.objects.values_list("pk", flat=True)]
    built = [str(row.id) for row in library_testing.library_of(settings.BULK_TAGGING_MAX_RECORDS - len(seeded))]
    return _tag_batch(seeded + built)


# --- r2-perf, chunk 11: agents, batches, the bank's own queue and agent access --------------
OWN_SOURCE = "https://www.fi.se/sv/vara-register/forfattningssamling/fffs-2026-9/"
ENTRY_SCOPES = ("library:read", "search:read", "tenant:read", "upcoming:read")
MCP_VERSION = "2026-07-28"
WHAT_WE_BUILD = "A new order-routing service for professional clients in shares and derivatives, paid for by debit card."


def _tenant_agent() -> TenantAgent:
    """Tenant A's own agent, the seeded `tenant-source-watch` (EXPECTED_CHUNK11)."""
    tenancy.activate(_tenant().id)
    return TenantAgent.objects.get(tenant=_tenant(), agent__key=EXPECTED_CHUNK11.tenant_agent)


def _agent_call(body: object = None) -> Call:
    return Call(params={"tenant_agent_id": _tenant_agent().id}, body=body)


def _paused_agent() -> Call:
    agent = _tenant_agent()
    pause(agent, "person", by=_user(ADMIN))
    return Call(params={"tenant_agent_id": agent.id})


def _run_now() -> Call:
    """The seeded cap leaves less than one run's most (AGENT_RUN_BUDGET_LIMIT) this month, so
    the admin raises it first, as the budget route does."""
    call = _agent_call()
    budget.put_budget(who=user_principal(subject_id=_user(ADMIN).id), tenant=_tenant(), body=AgentBudgetInput(monthly_cap="20.00"))
    return call


def _open_run() -> Call:
    """A run of tenant A's own agent still going, the kind a person stops."""
    agent = _tenant_agent()
    version = agent.agent.versions.get(version_number=agent.agent.current_version)
    run = AgentRun.objects.create(
        agent=agent.agent,
        agent_version=version,
        tenant_agent=agent,
        tenant=agent.tenant,
        trigger=RunTrigger.MANUAL.value,
        status=RunStatus.RUNNING.value,
        model=version.model,
        pipeline_version="0.4",
        scope=agent.scope,
    )
    return Call(params={"run_id": run.id})


def _research_request() -> Call:
    agent = _tenant_agent()
    request = ResearchRequest.objects.create(tenant=agent.tenant, tenant_agent=agent, requested_by=_user(ADMIN), kind="research_topic", topic="DORA subcontracting")
    return Call(params={"request_id": request.id})


def _retag_request() -> Call:
    tenancy.clear_tenant()
    request = ResearchRequest.objects.create(requested_by=_user(EDITOR), kind=ResearchRequestKind.RETAG.value, topic="Re-tag custody records with Client money.")
    return Call(params={"request_id": request.id})


def _own_proposal(body: object = None) -> Callable[[], Call]:
    """A new instrument of tenant A's own, found by its research agent (D-89): open in the
    bank's queue, for an approver who did not file it."""

    def call() -> Call:
        tenancy.activate(_tenant().id)
        fields = {
            "key": "fffs-2026-9",
            "titles": {"sv": "Finansinspektionens föreskrifter om utkontraktering", "en": "The Swedish FSA's regulations on outsourcing"},
            "originalLanguage": "sv",
            "isMachine": True,
            "shortName": "FFFS 2026:9",
            "officialRef": "FFFS 2026:9",
            "level": "authority_regulation",
            "jurisdiction": "se",
            "authority": "fi",
            "regime": "regime:securities",
            "inForceFrom": _in_days(90),
        }
        sourced = ["titles.sv", "titles.en", "shortName", "officialRef", "level", "jurisdiction", "authority", "regime", "inForceFrom"]
        proposal, _ = proposals_logic.create(
            kind="new_instrument",
            title="New instrument: FFFS 2026:9 on outsourcing",
            payload=fields,
            proposer=proposals_logic.Proposer(actor=factories.agent_actor(label="Scope researcher")),
            field_sources={field: OWN_SOURCE for field in sourced},
            source_label="Finansinspektionen, FFFS 2026:9",
            source_url=OWN_SOURCE,
            private=True,
        )
        return Call(params={"proposal_id": proposal.id}, body=body)

    return call


def _batch(body: object = None) -> Callable[[], Call]:
    def call() -> Call:
        batch = Proposal.objects.get(is_batch=True, title=EXPECTED_CHUNK11.batch_title, status=ProposalStatus.OPEN.value)
        return Call(params={"batch_id": batch.id}, body=body)

    return call


def _new_batch() -> Call:
    changes = [
        {"obligationId": str(_obligation(key).id), "add": ["lifecycle_stage:reporting"], "remove": [], "source": EXPECTED_CHUNK11.batch_source}
        for key in ("obl-costs-charges", "obl-appropriateness")
    ]
    return Call(
        body={
            "kind": "obligation_scope",
            "title": "Add the reporting stage to the costs and appropriateness duties",
            "payload": {"changes": changes},
            "sourceLabel": "Finansinspektionen, reporting",
            "sourceUrl": EXPECTED_CHUNK11.batch_source,
        }
    )


# Agent access (ACC-01 to ACC-09). The seed holds no entry and tenant reach starts off
# (acc-e2e-seed), so each row registers the entry it reads, narrowed to the seeded Trading
# department, through the logic the routes call; the fixture is setup, so no step-up is
# named. A credential is minted fresh per row, so no row shares a rate window
# (AGENT_ACCESS_RATE_PER_MINUTE) with another. No route mints a personal access token yet
# (ACC-S3 is pending), so the token is the one `factories.personal_token` writes.
def _entry(reach_on: bool = False) -> AgentAccess:
    """A live entry narrowed to Trading, registered by the admin; with `reach_on`, the bank's
    switch (admin asks, security approves) and the entry's own toggle are both on."""
    tenant, admin_user = _tenant(), _user(ADMIN)
    tenancy.activate(tenant.id)
    row = agent_access.register(
        tenant=tenant,
        user=admin_user,
        actor=session_logic.actor_of(admin_user),
        name="Trading platform coding agent",
        purpose="Designs and reviews the order-routing service.",
        owner_team="compliance",
        department_ids=[OrgUnit.objects.get(tenant=tenant, name=EXPECTED_J11.department).id],
        product_ids=[],
        step_up_assertion_id=None,
    )
    if reach_on:
        _switch_on()
        agent_access.set_tenant_reach(
            tenant=tenant, entry_id=row.id, actor=session_logic.actor_of(admin_user), enabled=True, expected_version=None, step_up_assertion_id=None
        )
    return row


def _pending() -> TenantReachRequest:
    tenant, admin_user = _tenant(), _user(ADMIN)
    tenancy.activate(tenant.id)
    return reach.request_reach(tenant=tenant, requester=admin_user, actor=session_logic.actor_of(admin_user), step_up_assertion_id=None)


def _switch_on() -> None:
    who = _user(SECURITY)
    reach.approve(tenant=_tenant(), request=_pending(), decider=who, actor=session_logic.actor_of(who), step_up_assertion_id=None)


def _key(entry: AgentAccess) -> tuple[Any, str]:
    admin_user = _user(ADMIN)
    return agent_access.create_key(
        tenant=_tenant(),
        entry_id=entry.id,
        user=admin_user,
        actor=session_logic.actor_of(admin_user),
        name="Order routing CI",
        scopes=ENTRY_SCOPES,
        expires_at=None,
        step_up_assertion_id=None,
    )


def _token(entry: AgentAccess) -> Any:
    return factories.personal_token(_tenant(), _user(TOKENS), scopes=ENTRY_SCOPES, entry=entry)


def entry_key(reach_on: bool = False, **headers: str) -> PrincipalFactory:
    """A fresh service key of a fresh Trading entry, as `X-API-Key`, with any other headers."""
    return lambda: {"HTTP_X_API_KEY": _key(_entry(reach_on))[1], **headers}


def token(reach_on: bool = False, **headers: str) -> PrincipalFactory:
    """A fresh personal access token of tokens@ naming a fresh Trading entry."""
    return lambda: {"HTTP_X_API_KEY": _token(_entry(reach_on)).plain_key, **headers}


def _mcp(credential: Callable[..., PrincipalFactory], method: str) -> PrincipalFactory:
    """The credential, its entry reaching the register so every tool is offered, with the
    headers revision 2026-07-28 mirrors from the body."""
    return credential(True, HTTP_MCP_PROTOCOL_VERSION=MCP_VERSION, HTTP_MCP_METHOD=method)


def _rpc(method: str, params: dict[str, Any] | None = None) -> Callable[[], Call]:
    meta = {"io.modelcontextprotocol/protocolVersion": MCP_VERSION, "io.modelcontextprotocol/clientCapabilities": {}}
    return lambda: Call(body={"jsonrpc": "2.0", "id": 1, "method": method, "params": {**(params or {}), "_meta": meta}})


def _entry_call(body: object = None) -> Callable[[], Call]:
    return lambda: Call(params={"entry_id": _entry().id}, body=body)


def _entry_key_call() -> Call:
    entry = _entry()
    return Call(params={"entry_id": entry.id, "key_id": _key(entry)[0].id})


def _calls() -> Call:
    """A full first page of the entry's access log, its key's calls and its token's."""
    entry = _entry()
    key, person_token = _key(entry)[0], _token(entry)
    AgentAccessCall.objects.bulk_create(
        AgentAccessCall(
            tenant_id=entry.tenant_id,
            api_key_id=key.id if n % 2 else person_token.id,
            agent_access=entry,
            acting_user=None if n % 2 else person_token.row.acts_as_user,
            tool="listObligations",
            filters={},
            record_count=20,
            scopes=list(ENTRY_SCOPES),
            duration_ms=40,
            status=200,
        )
        for n in range(20)
    )
    return Call(params={"entry_id": entry.id})


def _entries() -> Call:
    for _ in range(3):
        _entry()
    return Call()


def _waiting_reach() -> Call:
    _pending()
    return Call()


def _reach_on() -> Call:
    _switch_on()
    return Call()


def _trading_duty() -> Call:
    return Call(params={"obligation_id": _obligation(EXPECTED_J11.trading_obligations[0]).id})


ROUTES: list[PerfRoute] = [
    # perf-harness: three reads every signed-in reader makes, which prove the harness end
    # to end on the seeded data. r1-perf and the chunk 14 passes add the rest.
    PerfRoute("getMe", person(READER, TENANT_A_SLUG)),
    PerfRoute("getHome", person(READER, TENANT_A_SLUG)),
    PerfRoute("listObligations", person(READER, TENANT_A_SLUG)),
    # r1-perf: every other R1 operation, each as the principal that calls it in R1: a bank's
    # member with the permission (a step-up where the route demands one), platform staff for
    # the console and the library editor's routes, the watch sweeper's platform key for what
    # an agent calls, and no one for the ceremonies before a session exists.
    #
    # Not measured, one reason: `e2eMailOutbox` exists only under E2E_MODE, for the journeys
    # to read the mock mailer, and is refused on every deployed environment, so it has no
    # budget a person waits on.
    #
    # --- sign-in, the ceremonies before a session and the session itself ---
    PerfRoute("getProduct", anonymous),
    PerfRoute("openInvitation", anonymous, lambda: Call(body={"token": E2E_INVITATION_TOKEN_ANNA}), status=202),
    PerfRoute("verifyInvitationCode", anonymous, _verify_invitation_code),
    PerfRoute("requestCode", anonymous, lambda: Call(body={"email": ANNA}), status=202),
    PerfRoute("verifyCode", anonymous, _verify_code),
    PerfRoute("passkeyRegisterOptions", reader),
    PerfRoute("passkeyRegisterVerify", reader, _registration, status=201),
    PerfRoute("passkeyAuthenticateOptions", anonymous),
    PerfRoute("passkeyAuthenticateVerify", anonymous, _sign_in_assertion),
    PerfRoute("stepUpOptions", reader),
    PerfRoute("stepUpVerify", reader, _step_up_assertion),
    PerfRoute("refreshSession", reader),
    PerfRoute("signOut", reader, status=204),
    # --- me ---
    PerfRoute("updateMe", reader, lambda: Call(body={"name": "Oskar Lund"})),
    PerfRoute("markVisit", reader, status=204),
    PerfRoute("listMyPasskeys", reader),
    PerfRoute("renameMyPasskey", reader, _my_passkey),
    PerfRoute("removeMyPasskey", reader, _second_passkey, status=204),
    PerfRoute("listMySessions", reader),
    PerfRoute("revokeMySession", reader, _other_session, status=204),
    # --- the bank's administration ---
    PerfRoute("listMembers", admin),
    PerfRoute(
        "inviteMember",
        admin,
        lambda: Call(body={"email": "new.analyst@example-bank.test", "roleKeys": ["reader"], "title": "Compliance analyst"}),
        status=201,
    ),
    PerfRoute(
        "updateMember",
        stepped_up(ADMIN, TENANT_A_SLUG),
        lambda: Call(params={"user_id": _user("contributor@example-bank.test").id}, body={"roleKeys": ["contributor", "owner"]}),
    ),
    # The auditor holds no open work, which a plain removal refuses since chunk 8 (TEN-05).
    PerfRoute("deactivateMember", admin, _member("auditor@example-bank.test"), status=204),
    PerfRoute("listMemberSessions", admin, _member(READER)),
    PerfRoute("revokeMemberSessions", admin, _member(READER), status=204),
    PerfRoute("reissueEnrolment", stepped_up(ADMIN, TENANT_A_SLUG), _member("reissue@example-bank.test"), status=202),
    PerfRoute("listInvitations", admin),
    PerfRoute("resendInvitation", admin, _invitation),
    PerfRoute("revokeInvitation", admin, _invitation, status=204),
    PerfRoute("listRoles", reader),
    PerfRoute(
        "createRole",
        stepped_up(ADMIN, TENANT_A_SLUG),
        lambda: Call(body={"key": "dora_reviewer", "labels": {"en": "DORA reviewer"}, "permissions": ["cases.read", "library.read"]}),
        status=201,
    ),
    PerfRoute("updateRole", admin, _custom_role),
    PerfRoute("retireRole", admin, lambda: Call(params={"key": factories.tenant_role_key(_tenant()).id})),
    PerfRoute("listPermissions", reader),
    PerfRoute("listApiKeys", admin),
    PerfRoute(
        "createApiKey",
        stepped_up(ADMIN, TENANT_A_SLUG),
        lambda: Call(body={"name": "Policy portal sync", "scopes": ["library:read", "search:read"]}),
        status=201,
    ),
    PerfRoute("revokeApiKey", admin, lambda: Call(params={"key_id": factories.api_key(_tenant()).id}), status=204),
    PerfRoute("listSecurityLog", admin),
    PerfRoute("getTenant", reader),
    PerfRoute("updateTenant", admin, lambda: Call(body={"name": "Example Bank AB"})),
    PerfRoute("setTenantAi", stepped_up(ADMIN, TENANT_A_SLUG), lambda: Call(body={"enabled": True})),
    PerfRoute("listLanguages", reader),
    # --- the platform console ---
    PerfRoute("listAgentKeys", platform),
    PerfRoute(
        "createAgentKey",
        stepped_up(PLATFORM),
        lambda: Call(body={"name": "Watch sweeper, nightly", "agentId": str(Agent.objects.get(key=SWEEPER_AGENT).id), "scopes": list(SWEEPER_SCOPES)}),
        status=201,
    ),
    PerfRoute("revokeAgentKey", platform, lambda: Call(params={"key_id": _mint_key()[0].id})),
    PerfRoute("listConsoleTenants", platform),
    PerfRoute(
        "createConsoleTenant",
        platform,
        lambda: Call(body={"name": "Third Bank Oyj", "firstAdminEmail": "admin@third-bank.test", "firstAdminTitle": "Head of Compliance"}),
        status=201,
    ),
    PerfRoute(
        "consoleReissueEnrolment",
        stepped_up(PLATFORM),
        lambda: Call(
            params={"tenant_id": _tenant().id, "user_id": _user("reissue@example-bank.test").id},
            body={"reason": "Lost the phone holding the only passkey.", "outOfBandCheck": "Called back on the number on file.", "ticketRef": "SUP-2418"},
        ),
        status=202,
    ),
    PerfRoute("listAgentDefinitions", platform),
    PerfRoute("listAgentRuns", platform),
    # --- the library ---
    PerfRoute("getObligation", reader, _obligation_call),
    PerfRoute("getObligationDiff", reader, _obligation_call),
    PerfRoute("listInstruments", reader),
    PerfRoute("getInstrument", reader, _instrument_call),
    PerfRoute("listInstrumentProvisions", reader, _instrument_call),
    PerfRoute("getProvisionDiff", reader, lambda: Call(params={"provision_id": Provision.objects.get(stable_key="fffs-2017-2/9-6").id})),
    PerfRoute("listAuthorities", reader),
    PerfRoute("getRecordSources", reader, _obligation_call),
    PerfRoute(
        "reportObligationProblem",
        reader,
        lambda: Call(params={"obligation_id": _obligation().id}, body={"description": "The retention line says five years; the act says ten.", "language": "sv", "versionNumber": 1}),
        status=201,
    ),
    PerfRoute(
        "reportInstrumentProblem",
        reader,
        lambda: Call(params=_instrument_call().params, body={"description": "The title is the old one."}),
        status=201,
    ),
    PerfRoute(
        "reverifyObligation",
        stepped_up(EDITOR),
        lambda: Call(params={"obligation_id": _obligation().id}, body={"outcome": "no_change", "note": "Read against FI's published text."}),
        status=201,
    ),
    PerfRoute("listProblemReports", reader),
    PerfRoute("closeProblemReport", officer, _problem_report),
    # --- vocabularies and the taxonomy ---
    PerfRoute("listVocabularies", reader),
    PerfRoute("reorderVocabulary", officer, lambda: Call(params={"list_name": TAG_LIST}, body={"keys": ["whistleblowing", "follow_up"]})),
    PerfRoute(
        "suggestVocabularyRow",
        reader,
        lambda: Call(params={"list_name": TAG_LIST}, body={"labels": {"en": "Board reporting"}, "usageNote": "Goes into the quarterly board pack."}),
        status=201,
    ),
    PerfRoute("listVocabularySuggestions", officer, _on(list_name=TAG_LIST)),
    PerfRoute("declineVocabularySuggestion", officer, _suggestion),
    PerfRoute("listVocabularyRows", reader, _on(list_name=TAG_LIST)),
    PerfRoute(
        "createVocabularyRow",
        officer,
        lambda: Call(params={"list_name": TAG_LIST}, body={"key": "board_reporting", "labels": {"en": "Board reporting"}, "usageNote": "Goes into the quarterly board pack."}),
        status=201,
    ),
    PerfRoute("getVocabularyRow", reader, _on(list_name=TAG_LIST, key="whistleblowing")),
    PerfRoute(
        "updateVocabularyRow",
        officer,
        lambda: Call(params={"list_name": TAG_LIST, "key": "whistleblowing"}, body={"usageNote": "Reports made through the whistleblowing channel."}),
    ),
    PerfRoute("retireVocabularyRow", officer, lambda: Call(params={"list_name": TAG_LIST, "key": "whistleblowing"}, body={"confirm": True})),
    PerfRoute("restoreVocabularyRow", officer, _retired_row),
    PerfRoute("mergeVocabularyRow", officer, lambda: Call(params={"list_name": TAG_LIST, "key": "whistleblowing"}, body={"into": "follow_up"})),
    PerfRoute("listTaxonomyDimensions", reader),
    PerfRoute("listTerms", reader),
    PerfRoute(
        "createTerm",
        editor,
        lambda: Call(body={"dimension": "service_type", "key": "investment_research", "labels": {"en": "Investment research"}}),
        status=202,
    ),
    PerfRoute(
        "updateTerm",
        editor,
        lambda: Call(params={"term_id": _term("service_type", "advice").id}, body={"usageNote": "Personal recommendations on financial instruments."}),
        status=202,
    ),
    # --- the footprint and the markets we watch ---
    PerfRoute("getFootprint", reader),
    PerfRoute("listFootprintRequests", reader),
    PerfRoute("createFootprintRequest", officer, _new_footprint_request, status=201),
    PerfRoute("approveFootprintRequest", stepped_up(APPROVER, TENANT_A_SLUG), _footprint_request),
    PerfRoute("rejectFootprintRequest", approver, _footprint_request),
    PerfRoute("withdrawFootprintRequest", officer, lambda: Call(params={"request_id": factories.footprint_request(_tenant()).id})),
    PerfRoute("watchMarket", officer, lambda: Call(body={"jurisdiction": "no"})),
    PerfRoute("unwatchMarket", officer, lambda: Call(body={"jurisdiction": "dk"})),
    PerfRoute("listJurisdictions", reader),
    # --- proposals, the audit trail and the AI log ---
    PerfRoute("listProposals", editor),
    PerfRoute("createProposal", sweeper, _new_proposal, status=201),
    PerfRoute("listTenantProposals", officer),
    PerfRoute("listLibraryUpdates", reader),
    PerfRoute("getProposal", editor, lambda: Call(params={"proposal_id": _proposal("obl-appropriateness").id})),
    PerfRoute("approveProposal", stepped_up(EDITOR), lambda: Call(params={"proposal_id": _proposal("obl-costs-charges").id}, body={"note": "Matches the decision."})),
    PerfRoute(
        "rejectProposal",
        editor,
        lambda: Call(params={"proposal_id": _proposal("obl-client-assets").id}, body={"rejectionCode": "duplicate", "note": "Version 1 already says this."}),
    ),
    PerfRoute("listAuditEvents", reader),
    PerfRoute("listAiGenerations", officer),
    # --- search, Ask and the evaluation set ---
    PerfRoute("search", reader, lambda: Call(body={"q": "research payments"}), budget="SEARCH_RERANKED_BUDGET_MS"),
    PerfRoute(
        "findSimilar",
        sweeper,
        lambda: Call(body={"text": "Institutions that receive investment research assess its quality every year."}),
        budget="SEARCH_RERANKED_BUDGET_MS",
    ),
    PerfRoute("ask", reader, lambda: Call(body={"question": EXPECTED_ASK.answered_question}), budget="ASK_FIRST_TOKEN_BUDGET_MS"),
    PerfRoute("rateAnswer", reader, _answer, status=204),
    PerfRoute("listEvalQuestions", editor),
    PerfRoute(
        "createEvalQuestion",
        editor,
        lambda: Call(body={"key": "r-en-perf", "lang": "en", "question": "costs and charges before the service", "matchKind": "concept", "expected": ["obl-costs-charges"]}),
        status=201,
    ),
    PerfRoute("listEvalRuns", editor),
    PerfRoute("getEvalBaseline", editor),
    # --- agent runs, sources and the coverage log ---
    PerfRoute("startAgentRun", sweeper, lambda: Call(body={"agent": SWEEPER_AGENT, "model": "agent pipeline 0.4", "pipelineVersion": "0.4"}), status=201),
    PerfRoute("finishAgentRun", sweeper, _run_call({"status": "succeeded", "stats": {"sourcesChecked": 5}})),
    PerfRoute("listSources", sweeper),
    PerfRoute(
        "createSource",
        editor,
        lambda: Call(body={"name": "Finanstilsynet news", "kind": "authority_site", "checkFrequency": "daily", "url": "https://www.finanstilsynet.dk/nyheder/"}),
        status=201,
    ),
    PerfRoute("getSourceCoverage", editor),
    PerfRoute("updateSource", editor, _source),
    PerfRoute(
        "recordSourceCheck",
        sweeper,
        _run_call({"sourceName": EXPECTED_CHUNK5_WATCH.healthy_source, "status": "ok", "itemsFound": 0}),
        status=204,
    ),
    # --- changes: the feed, the console queue and an agent's filings ---
    PerfRoute("listChanges", reader),
    PerfRoute("createChange", sweeper, _new_change, status=201),
    PerfRoute("listConsoleChanges", editor),
    PerfRoute("getChange", reader, _change_call),
    PerfRoute("updateChange", editor, lambda: Call(params={"change_id": _change().id}, body={"keyDateLabel": "In force"})),
    PerfRoute("listObligationChanges", reader, _obligation_call),
    PerfRoute(
        "addChangeDocument",
        sweeper,
        lambda: Call(params={"change_id": _change().id}, body={"url": "https://www.fi.se/en/published/news/2026/reporting/", "isPrimary": False, "publisher": "Finansinspektionen"}),
        status=201,
    ),
    PerfRoute(
        "addChangeEvent",
        sweeper,
        lambda: Call(params={"change_id": _change().id}, body={"label": "Consultation closed", "eventDate": "2026-06-01", "datePrecision": "day", "occurred": True}),
        status=201,
    ),
    PerfRoute("updateChangeEvent", editor, _event),
    PerfRoute("replaceChangeObligations", stepped_up(EDITOR), _links),
    PerfRoute(
        "confirmChangeCuration",
        stepped_up(EDITOR),
        lambda: Call(params={"change_id": _change().id}, body={"obligationIds": [str(_obligation("obl-client-assets").id)]}),
    ),
    # --- the bank's case on a change ---
    PerfRoute(
        "saveSoWhat",
        officer,
        _case(EXPECTED_CHUNK5_WATCH.payments_change, {"text": "Confirm with the payments desk before 1 October."}),
    ),
    PerfRoute("confirmSoWhat", officer, _case(EXPECTED_CHUNK5_WATCH.payments_change)),
    PerfRoute(
        "acceptCaseObligationLink",
        officer,
        _accept_link,
        status=201,
    ),
    PerfRoute(
        "removeCaseObligationLink",
        officer,
        _case(EXPECTED_CHUNK5_WATCH.obligations_change, obligation="obl-client-assets"),
    ),
    # --- home, the briefing, the roadmap and the calendar ---
    PerfRoute("getCurrentBriefing", reader),
    PerfRoute("getBriefing", reader, _briefing),
    PerfRoute("getRoadmap", reader),
    PerfRoute("listUpcoming", reader),
    PerfRoute("listCalendarFeeds", reader),
    PerfRoute("createCalendarFeed", reader, lambda: Call(body={}), status=201),
    PerfRoute("revokeCalendarFeed", reader, _calendar_feed, status=204),
    PerfRoute("getCalendarIcs", anonymous, _calendar_feed),
    # --- r2-perf: chunk 8 --- the register entry, its legal entities and applicability
    PerfRoute("getRegisterEntry", officer, _on_obligation(SPANNING_OBLIGATION)),
    PerfRoute("updateRegister", *_versioned(officer, _register_update)),
    PerfRoute("updateRegisterEntity", *_versioned(officer, _entity_update)),
    PerfRoute("listSpannedEntities", officer, _on_obligation(SPANNING_OBLIGATION)),
    PerfRoute(
        "setApplicability",
        officer,
        lambda: Call(
            params={"obligation_id": _obligation(SPANNING_OBLIGATION).id},
            body={"orgUnitId": str(_entity("Example Liv Försäkring AB").id), "applicability": "not_applicable", "reason": "Sells no investment products."},
        ),
    ),
    PerfRoute("setApplicabilityMany", officer, _answers_at_cap),  # at REGISTER_BULK_MAX
    # gaps and risk acceptance
    PerfRoute("listRegisterGaps", officer),
    PerfRoute("listObligationGaps", officer, _on_obligation(GAP_OBLIGATION)),
    PerfRoute("createGap", officer, _new_gap, status=201),
    PerfRoute("updateGap", *_versioned(officer, _gap_update)),
    PerfRoute(
        "requestRiskAcceptance",
        officer,
        lambda: Call(params={"gap_id": _gap(AUDIT_GAP_OBLIGATION).id}, body={"reason": "compensating_control", "note": "Every correction is reviewed monthly."}),
    ),
    PerfRoute("approveRiskAcceptance", stepped_up(APPROVER, TENANT_A_SLUG), _waiting_acceptance),
    PerfRoute("reopenGap", officer, _closed_gap),
    # assessment history, how we read the rule and linked internal items
    PerfRoute("listAssessments", officer, _on_obligation(HISTORY_OBLIGATION)),
    PerfRoute("getInterpretation", officer, _on_obligation(HISTORY_OBLIGATION)),
    PerfRoute(
        "saveInterpretation",
        officer,
        lambda: Call(
            params={"obligation_id": _obligation(HISTORY_OBLIGATION).id},
            body={"text": "Every instrument outside the non-complex list is complex for us, structured deposits included."},
        ),
    ),
    PerfRoute("listInternalLinks", officer, _on_obligation(HISTORY_OBLIGATION)),
    PerfRoute(
        "addInternalLink",
        officer,
        lambda: Call(
            params={"obligation_id": _obligation("obl-client-assets").id},
            body={"kind": "policy", "label": "Client asset policy", "internalItemId": str(InternalItem.objects.get(name="Client asset policy").id)},
        ),
        status=201,
    ),
    PerfRoute("listInternalItems", officer),
    PerfRoute(
        "removeInternalLink",
        officer,
        lambda: Call(params={"link_id": InternalLink.objects.get(tenant_obligation__obligation__stable_key=HISTORY_OBLIGATION, removed_at__isnull=True).id}),
        status=204,
    ),
    # the Statement of Applicability, at Annex A's size, and a paste at REGISTER_BULK_MAX
    PerfRoute("listUnits", officer, lambda: _statement_call(_units(ANNEX_A))),
    PerfRoute("getStatementOfApplicability", officer, _answered_statement),
    PerfRoute(
        "createUnit",
        officer,
        lambda: Call(params={"obligation_id": _follows_standard().id}, body={"orgUnitId": str(_entity().id), "reference": "A.5.1", "title": "Our information security policies"}),
        status=201,
    ),
    PerfRoute("pasteUnits", officer, _paste_at_cap),
    PerfRoute("updateUnit", *_versioned(officer, _unit_update({"title": "Our information security policy set"}))),
    PerfRoute("removeUnit", *_versioned(officer, _unit_update()), status=204),
    # recurring duties
    PerfRoute("listDuties", officer, lambda: Call(params={"obligation_id": _occurrence().tenant_obligation.obligation_id})),
    PerfRoute("completeDutyOccurrence", officer, lambda: Call(params={"occurrence_id": _occurrence().id}, body={"note": "Filed with the Tax Agency."})),
    # the inventory as a register reader filters it by the bank's overlay
    PerfRoute("listObligations", officer, lambda: Call(query={"applicability": "applies", "complianceStatus": "partly_compliant"}), variant="overlay"),
    # participants on a register entry
    PerfRoute("listObligationParticipants", reader, _on_obligation(PARTICIPATION_OBLIGATION)),
    PerfRoute(
        "addObligationParticipant",
        officer,
        lambda: Call(params={"obligation_id": _obligation(PARTICIPATION_OBLIGATION).id}, body={"userId": str(_user(CONTRIBUTOR).id)}),
        status=201,
    ),
    PerfRoute("removeObligationParticipant", officer, _obligation_participant, status=204),
    # My work, a member's own and a department head's view of their department
    PerfRoute("getMyWork", owner),
    PerfRoute("getMyWork", person(HEAD, TENANT_A_SLUG), _department, variant="head"),
    # the organisation, its licences, products, teams and people
    PerfRoute("listOrgUnits", reader),
    PerfRoute("createOrgUnit", admin, lambda: Call(body={"kind": "business_unit", "name": "Savings", "parentId": str(_org_unit(RETAIL_DEPARTMENT).id)}), status=201),
    PerfRoute("updateOrgUnit", admin, lambda: Call(params={"org_unit_id": _org_unit(RETAIL_DEPARTMENT).id}, body={"name": "Retail and Private Banking"})),
    PerfRoute("listLicences", reader, lambda: Call(params={"org_unit_id": _org_unit().id})),
    PerfRoute(
        "createLicence",
        admin,
        lambda: Call(params={"org_unit_id": _org_unit().id}, body={"licenceType": "bank", "reference": "FI 2026-1234", "scopeNote": "Deposit taking"}),
        status=201,
    ),
    PerfRoute(
        "updateLicence",
        admin,
        lambda: Call(params={"licence_id": Licence.objects.get(tenant=_tenant(), scope_note="Banking business").id}, body={"reference": "FI 1999-0042"}),
    ),
    PerfRoute("listProducts", reader),
    PerfRoute(
        "createProduct",
        admin,
        lambda: Call(body={"name": "Savings account", "orgUnitId": str(_org_unit().id), "ownerUserId": str(_user(OFFICER).id), "terms": ["isk", "custody"]}),
        status=201,
    ),
    PerfRoute("updateProduct", admin, lambda: Call(params={"product_id": TenantProduct.objects.get(tenant=_tenant(), name="Guided investing").id}, body={"status": "live"})),
    PerfRoute("listTeams", reader),
    PerfRoute("listTeamMembers", reader, _on(key=RETAIL_TEAM)),
    PerfRoute("setMemberTeams", admin, lambda: Call(params={"user_id": _user("teams@example-bank.test").id}, body={"teams": [RETAIL_TEAM]})),
    PerfRoute("listPeople", officer, lambda: Call(query={"permission": "cases.signoff"})),
    PerfRoute("getMemberOpenWork", admin, _member(LEAVER)),
    PerfRoute("removeMember", stepped_up(ADMIN, TENANT_A_SLUG), _removal, status=204),
    # support access: the console asks, the bank decides (TEN-06)
    PerfRoute("listConsoleSupportAccess", platform, _console(_listed_grant)),
    PerfRoute("enterConsoleSupportAccess", stepped_up(PLATFORM), _console(lambda: _grant_call(active=True))),
    PerfRoute(
        "requestConsoleSupportAccess",
        platform,
        lambda: Call(params={"tenant_id": _tenant().id}, body={"purpose": "The bank's watch feed stopped updating.", "ticketRef": "SUP-2419", "hours": 2}),
        status=201,
    ),
    PerfRoute("listTenantSupportAccess", admin, _listed_grant),
    PerfRoute("approveSupportAccess", stepped_up(ADMIN, TENANT_A_SLUG), _grant_call),
    PerfRoute("declineSupportAccess", admin, _grant_call),
    PerfRoute("revokeSupportAccess", admin, lambda: _grant_call(active=True)),
    # --- r2-perf: chunk 9-10 --- the case workflow: triage, dismissal, restore, assessment, close
    PerfRoute("triageChange", *_versioned(officer, lambda: _move("chg-e2e-case-triage", {"urgency": "within_3_months", "ownerId": str(_user(OWNER).id)})())),
    PerfRoute("dismissChange", *_versioned(officer, _move("chg-e2e-case-dismiss", {"reasonKey": "out_of_scope"}))),
    PerfRoute("restoreChange", *_versioned(officer, _move("chg-e2e-case-dismissed"))),
    PerfRoute("startAssessment", *_versioned(owner, _move("chg-e2e-case-assess"))),
    PerfRoute(
        "saveAssessment",
        *_versioned(owner, _move("chg-e2e-case-actions", {"applies": "yes", "why": "Both trading desks settle in T+2 today.", "whatMustChange": "Move the settlement cut-off.", "effort": "m"})),
    ),
    PerfRoute("closeWithoutAction", *_versioned(owner, _move("chg-e2e-case-assigned", {"reasonKey": "no_action", "note": "Covered by the 2025 large exposures review."}))),
    # actions and evidence, the upload through the mock scanner
    PerfRoute("listActions", reader, _case(EVIDENCE_CASE)),
    PerfRoute("addAction", *_versioned(owner, lambda: _move(EVIDENCE_CASE, {"title": "Update the onboarding checklist", "dueDate": _in_days(30)})()), status=201),
    PerfRoute("updateAction", *_versioned(owner, _action({"done": True}))),
    PerfRoute("deleteAction", *_versioned(owner, _action()), status=204),
    PerfRoute("listEvidence", reader, _case(EVIDENCE_CASE)),
    PerfRoute("addEvidence", owner, _upload, status=201),
    PerfRoute("downloadEvidence", reader, _evidence(CLEAN_FILE)),
    PerfRoute("removeEvidence", owner, _evidence(CLEAN_FILE), status=204),
    # sign-off, four eyes, and the case file and its export
    PerfRoute("requestSignoff", *_versioned(owner, _ready_for_signoff)),
    PerfRoute("approveSignoff", *_versioned(stepped_up(APPROVER, TENANT_A_SLUG), _move("chg-e2e-case-signoff", {"note": "Criteria checked against the review."}))),
    PerfRoute("sendBackSignoff", *_versioned(approver, _move("chg-e2e-case-signoff", {"note": "Attach the board minutes."}))),
    PerfRoute("getCaseFile", reader, _case(FILE_CASE)),
    PerfRoute(
        "createExport",
        stepped_up(OFFICER, TENANT_A_SLUG),
        lambda: Call(body={"kind": "case_file", "subjectId": str(_case_row(FILE_CASE).id), "format": "txt"}),
        status=202,
    ),
    PerfRoute("listExports", officer, _export(built=True)),
    PerfRoute("getExport", officer, _export(built=False)),
    PerfRoute("downloadExport", officer, _export(built=True)),
    # participants on a case
    PerfRoute("listCaseParticipants", reader, _case(CASE_PARTICIPATION_CHANGE)),
    PerfRoute("addCaseParticipant", officer, lambda: _case(CASE_PARTICIPATION_CHANGE, {"userId": str(_user(CONTRIBUTOR).id)})(), status=201),
    PerfRoute("removeCaseParticipant", officer, lambda: _case_participant(OWNER), status=204),
    # comments, and the inbox at INBOX_ROWS
    PerfRoute("listComments", reader, _comments),
    PerfRoute("addComment", officer, _new_comment, status=201),
    PerfRoute("editComment", officer, _my_fresh_comment),
    PerfRoute("deleteComment", officer, _officers_comment, status=204),
    PerfRoute("listMyComments", reader, lambda: Call(query={"about": "mentioned"})),
    PerfRoute("listNotifications", reader, _full_inbox),
    PerfRoute("markAllNotificationsRead", reader, _full_inbox, status=204),
    PerfRoute("markNotificationRead", reader, _one_notification, status=204),
    # the bank's own tags, the preview at BULK_TAGGING_MAX_RECORDS
    PerfRoute("tagRecord", officer, _tagging("obl-client-assets")),
    PerfRoute("untagRecord", officer, _tagging(EXPECTED_BULK_TAGGING.already_tagged[0])),
    PerfRoute("tagRecords", officer, lambda: _tag_batch([str(_obligation(key).id) for key in EXPECTED_BULK_TAGGING.obligations])),
    PerfRoute("previewTagging", officer, _preview_at_cap),
    # an absence with a delegate, and the bank's workflow policy
    PerfRoute("getMyOutOfOffice", person(AWAY, TENANT_A_SLUG)),
    PerfRoute("putMyOutOfOffice", person(AWAY, TENANT_A_SLUG), lambda: Call(body={"untilDate": _in_days(7), "delegateId": str(_user(APPROVER).id)})),
    PerfRoute("updateTenantWorkflow", officer, lambda: Call(body={"reminderDaysBefore": [30, 7, 1], "digestWeekday": "monday"})),
    # --- r2-perf: chunk 11 --- bleqq's own agents in the console (D-102)
    PerfRoute("getAgentDefinition", platform, _on(agent_key=SWEEPER_AGENT)),
    PerfRoute("getPlatformAgentSettings", platform, _on(agent_key=SWEEPER_AGENT)),
    PerfRoute(
        "updatePlatformAgentSettings",
        stepped_up(PLATFORM),
        lambda: Call(params={"agent_key": SWEEPER_AGENT}, body={"cadence": "daily", "jurisdictions": ["se", "eu"], "monthlyBudget": "250.00"}),
    ),
    PerfRoute("retireAgentVersion", stepped_up(PLATFORM), _on(agent_key=SWEEPER_AGENT, version_no=2)),
    PerfRoute("listPlatformRuns", platform),
    PerfRoute("createRetagRequest", editor, lambda: Call(body={"topic": "Re-tag custody records with Client money."}), status=202),
    PerfRoute("getRetagRequest", editor, _retag_request),
    # a bank's own agents, their controls, the cap and research requests
    PerfRoute("listPlatformWatch", reader),
    PerfRoute("listTenantAgents", admin),
    PerfRoute(
        "createTenantAgent",
        person("admin@second-bank.test", TENANT_B_SLUG),  # a bank that has added no agent of its own
        lambda: Call(body={"agent": EXPECTED_CHUNK11.tenant_agent, "cadence": "weekly", "runWeekday": 1, "runHour": 6, "scope": {"jurisdictions": ["dk"]}}),
        status=201,
    ),
    PerfRoute("updateTenantAgent", admin, lambda: _agent_call({"cadence": "monthly"})),
    PerfRoute("pauseTenantAgent", admin, _agent_call),
    PerfRoute("resumeTenantAgent", admin, _paused_agent),
    PerfRoute("runTenantAgentNow", admin, _run_now, status=202),
    PerfRoute("interruptAgentRun", admin, _open_run),
    PerfRoute("getAgentBudget", admin),
    PerfRoute("putAgentBudget", admin, lambda: Call(body={"monthlyCap": "20.00"})),
    PerfRoute("listResearchRequests", admin),
    # research_topic fetches nothing: only check_url reaches the network
    PerfRoute(
        "createResearchRequest",
        admin,
        lambda: Call(body={"kind": "research_topic", "tenantAgentId": str(_tenant_agent().id), "topic": "DORA subcontracting"}),
        status=202,
    ),
    PerfRoute("getResearchRequest", admin, _research_request),
    # the bank's own queue (D-89)
    PerfRoute("listPrivateProposals", approver, _own_proposal()),
    PerfRoute("approvePrivateProposal", stepped_up(APPROVER, TENANT_A_SLUG), _own_proposal({"note": "Checked against FFFS 2026:9, 4 kap. 5 §."})),
    PerfRoute("rejectPrivateProposal", approver, _own_proposal({"rejectionCode": "duplicate", "note": "We already hold this duty as our own."})),
    # batch proposals: filed by one library editor, decided by another
    PerfRoute("createProposalBatch", editor, _new_batch, status=201),
    PerfRoute("getProposalBatch", person(REVIEWER), _batch()),
    PerfRoute("decideProposalBatch", stepped_up(REVIEWER), _batch({"rows": [], "rest": "approved"})),
    # the bank's session limits
    PerfRoute("getSecurityPolicy", admin),
    PerfRoute("putSecurityPolicy", stepped_up(ADMIN, TENANT_A_SLUG), lambda: Call(body={"sessionIdleMinutes": 60, "sessionAbsoluteHours": 12})),
    # agent access entries, their keys and their access log (ACC-01, ACC-03, ACC-08)
    PerfRoute("listAgentAccess", admin, _entries),
    PerfRoute(
        "registerAgentAccess",
        steward,
        lambda: Call(
            body={
                "name": "Trading platform coding agent",
                "purpose": "Designs and reviews the order-routing service.",
                "ownerTeam": "compliance",
                "departmentIds": [str(OrgUnit.objects.get(tenant=_tenant(), name=EXPECTED_J11.department).id)],
            }
        ),
        status=201,
    ),
    PerfRoute("getAgentAccess", admin, _entry_call()),
    PerfRoute("updateAgentAccess", steward, _entry_call({"purpose": "Designs, builds and reviews the order-routing service."})),
    PerfRoute("createAgentAccessKey", steward, _entry_call({"name": "Order routing CI", "scopes": list(ENTRY_SCOPES)}), status=201),
    PerfRoute("revokeAgentAccessKey", steward, _entry_key_call),
    PerfRoute("revokeAgentAccess", steward, _entry_call()),
    PerfRoute("setAgentAccessReach", steward, _entry_call({"enabled": True})),
    PerfRoute("listAgentAccessCalls", admin, _calls),
    # the bank's tenant reach, four eyes (ACC-08, D-72)
    PerfRoute("getTenantReach", security, _waiting_reach),
    PerfRoute("switchOffTenantReach", security, _reach_on),
    PerfRoute("requestTenantReach", security, status=201),
    PerfRoute("approveTenantReach", security, lambda: Call(params={"request_id": _pending().id})),
    PerfRoute("rejectTenantReach", security, lambda: Call(params={"request_id": _pending().id})),
    # what applies inside its summary's deadline, with a key and a token (ACC-06, ACC-07)
    PerfRoute("whatApplies", entry_key(reach_on=True), lambda: Call(body={"description": WHAT_WE_BUILD}), budget="WHAT_APPLIES_SUMMARY_DEADLINE_MS"),
    PerfRoute("whatApplies", token(reach_on=True), lambda: Call(body={"description": WHAT_WE_BUILD}), budget="WHAT_APPLIES_SUMMARY_DEADLINE_MS", variant="token"),
    # the register as the bank's own agent reads it (ACC-04)
    PerfRoute("listRegisterEntries", entry_key(reach_on=True)),
    PerfRoute("listRegisterEntries", token(reach_on=True), variant="token"),
    PerfRoute("readRegisterEntry", entry_key(reach_on=True), _trading_duty),
    PerfRoute(
        "search",
        entry_key(),
        lambda: Call(body={"q": "order routing best execution", "filters": {"footprint": "in"}}),
        budget="SEARCH_RERANKED_BUDGET_MS",
        variant="agent key",
    ),
    # the MCP server, with a key and a token (ACC-05)
    PerfRoute("mcpMessage", _mcp(entry_key, "tools/list"), _rpc("tools/list"), variant="tools/list, key"),
    PerfRoute("mcpMessage", _mcp(token, "tools/list"), _rpc("tools/list"), variant="tools/list, token"),
    PerfRoute(
        "mcpMessage",
        _mcp(entry_key, "tools/call"),
        _rpc("tools/call", {"name": "get_obligation", "arguments": {"stableKey": EXPECTED_J11.trading_obligations[0]}}),
        variant="tools/call get_obligation, key",
    ),
    PerfRoute(
        "mcpMessage",
        _mcp(token, "tools/call"),
        _rpc("tools/call", {"name": "search", "arguments": {"query": "order routing best execution"}}),
        variant="tools/call search, token",
    ),
]
