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
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.test import RequestFactory
from django.utils import timezone

from apps.agents.models import Agent, AgentRun
from apps.cases.models import ChangeCase
from apps.home import feed
from apps.home.models import Briefing
from apps.identity import api_keys_logic, code_logic, invitation_logic, session_logic
from apps.identity.models import ApiKey, AuthChallenge, ChallengeKind, SessionKind, User, UserSession, WebAuthnCredential
from apps.identity.tests_webauthn_support import SoftwareAuthenticator
from apps.identity.tokens import b64url
from apps.library.models import Instrument, Obligation, ProblemReport, Provision
from apps.proposals.models import Proposal, ProposalStatus
from apps.search import ask
from apps.search.schemas import AskRequest, AskStartEvent
from apps.shared import factories, tenancy
from apps.shared.e2e_logins import E2E_INVITATION_TOKEN_ANNA, TENANT_A_SLUG
from apps.shared.e2e_passkeys import E2E_PASSKEYS
from apps.shared.e2e_seed import EXPECTED_ASK, EXPECTED_CHUNK5_WATCH, anna_invitation
from apps.shared.models import Tenant
from apps.shared.testing import sign_in
from apps.taxonomy import footprint_logic, tenant_lists_logic
from apps.taxonomy.models import TaxonomyTerm
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
    PerfRoute("deactivateMember", admin, _member("contributor@example-bank.test"), status=204),
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
]
