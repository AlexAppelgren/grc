"""Research requests (AGT-05, D-98, ADR 0053): a bank asks its own agents to run now, check a
registered source or a web address, or research a topic; re-tagging library records is
asked in the console and answered by one batch proposal, never a direct edit.

Every request opens a run with the trigger `request` and the request on it
(`tasks.open_request_run`, through the one opener), so the request is a job and its status
is its run's. A bank's request is checked in this order, each refusal writing nothing:
an agent of its own at all (409 `no_tenant_agent`, since no bank commands one of bleqq's),
the agent named (404 another bank's, 403 one it may not steer), the fields its kind takes,
the source or the address, the plan's monthly number (429 `plan_limit_reached`), the AI
switch (422 `feature_off`) and the cap (422 `budget_cap_reached`, read as `budget.at_cap`: a
request inherits the cap the bank set).

**What a bank writes stays in the bank (D-98).** The topic is the bank's own text: length
capped by the schema, screened as untrusted (`risk_flags`), stored on the bank's request
and nowhere else, never logged and never in an audit, outbox or run row. A bank's request
can only open a run of the bank's own agent, so the text never reaches a platform run; the
runner that works it reaches a model only through the logged wrapper, which the bank's
switch stops.

**A web address is untrusted input (AGT-07).** `check_url` takes https on port 443 to a
host every address of which is public, never a standards publisher (D-45), and follows no
redirect it would not have accepted as the first address. The connection goes to the
address that was checked, so the name cannot move between the check and the connect. What
comes back is screened and stored as text: never executed, never rendered as HTML.

The console's re-tag opens a run of bleqq's `RETAG_AGENT` in no tenant's zone and reads no
bank's row; what that run finds is filed by `file_retag` through `batch.create_batch()`,
the one writer of a batch (PRO-04).
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.agents import budget, tasks
from apps.agents.models import AgentRun, ResearchRequest, ResearchRequestKind, ResearchRequestStatus, RunStatus, TenantAgent
from apps.agents.schemas import ResearchRequestInput, ResearchRequestOut, ResearchRequestPage, RetagRequestInput
from apps.agents.screen import screen_all
from apps.agents.tenant_agents import lock_tenant, own_agent
from apps.identity.models import User
from apps.proposals import batch
from apps.proposals.logic import Proposer
from apps.proposals.models import Proposal, ProposalKind
from apps.proposals.schemas import ObligationScopePayload
from apps.shared import ai
from apps.shared.audit import Actor, ActorType, record
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.taxonomy.schemas import PersonRef
from apps.watch.keys import source_for_write

SUBJECT_TYPE = "research_request"
# The one of bleqq's agents that answers a re-tag: it proposes to the library, never edits it.
RETAG_AGENT = "watch-sweeper"
# The field each kind a bank asks for takes; every other field must be left out.
_FIELD = {
    ResearchRequestKind.RUN_NOW.value: None,
    ResearchRequestKind.CHECK_SOURCE.value: "source_id",
    ResearchRequestKind.CHECK_URL.value: "url",
    ResearchRequestKind.RESEARCH_TOPIC.value: "topic",
}
_REDIRECTS = (301, 302, 303, 307, 308)
# What a request reads as while its run is in each state.
_STATUS_OF_RUN = {
    RunStatus.RUNNING.value: ResearchRequestStatus.RUNNING.value,
    RunStatus.SUCCEEDED.value: ResearchRequestStatus.DONE.value,
    RunStatus.FAILED.value: ResearchRequestStatus.FAILED.value,
    RunStatus.INTERRUPTED.value: ResearchRequestStatus.FAILED.value,
}


# ---------------------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------------------
def _run(request: ResearchRequest) -> AgentRun | None:
    runs = list(request.runs.all())
    return max(runs, key=lambda run: (run.started_at, str(run.id))) if runs else None


def _out(request: ResearchRequest) -> ResearchRequestOut:
    run = _run(request)
    return ResearchRequestOut.model_validate(
        {
            "id": request.id,
            "kind": request.kind,
            "tenant_agent_id": request.tenant_agent_id,
            "topic": request.topic or None,
            "source_id": request.source_id,
            "url": request.url or None,
            "status": request.status if run is None else _STATUS_OF_RUN[run.status],
            "requested_by": PersonRef(id=request.requested_by.id, name=request.requested_by.name),
            "created_at": request.created_at,
            "completed_at": None if run is None else run.finished_at,
            "batch_proposal_id": request.batch_proposal_id,
        }
    )


def _requests() -> Any:
    return ResearchRequest.objects.select_related("requested_by").prefetch_related("runs")


def list_requests(*, tenant: Tenant, limit: int, offset: int) -> ResearchRequestPage:
    """`GET /research-requests`: the bank's own, newest first. The table is mixed (a console
    re-tag has no tenant), so the bank's rows are asked for by name as well as under
    row-level security."""
    queryset = _requests().filter(tenant=tenant).order_by("-created_at", "id")
    return ResearchRequestPage(items=[_out(row) for row in queryset[offset : offset + limit]], total=queryset.count())


def get_request(*, tenant: Tenant, request_id: uuid.UUID) -> ResearchRequestOut:
    """`GET /research-requests/{requestId}`: one of the bank's own, or 404."""
    row = _requests().filter(pk=request_id, tenant=tenant).first()  # ordering: pk lookup, at most one row
    if row is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return _out(row)


def get_retag(*, request_id: uuid.UUID) -> ResearchRequestOut:
    """`GET /console/research-requests/{requestId}`: a re-tag, or 404 for anything else."""
    row = (
        _requests().filter(pk=request_id, kind=ResearchRequestKind.RETAG.value, tenant__isnull=True).first()  # ordering: pk lookup, at most one row
    )
    if row is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return _out(row)


# ---------------------------------------------------------------------------------------
# A bank asks its own agent
# ---------------------------------------------------------------------------------------
def _checked_fields(body: ResearchRequestInput) -> None:
    wanted = _FIELD[body.kind]
    for field in ("source_id", "url", "topic"):
        given = getattr(body, field) is not None
        if field == wanted and not given:
            raise ValidationError(f"A {body.kind} request needs `{_camel(field)}`.", code="validation_error")
        if field != wanted and given:
            raise ValidationError(f"A {body.kind} request takes no `{_camel(field)}`.", code="validation_error")


def _camel(field: str) -> str:
    head, *rest = field.split("_")
    return head + "".join(part.title() for part in rest)


def _checked_source(source_id: uuid.UUID) -> None:
    """A source the bank can see (404 otherwise) that the agents check: one registered with
    its checks off, such as a standards publisher's (D-45), is 422 `source_not_checked`."""
    if not source_for_write(source_id).active:
        raise ValidationError("The agents do not check that source, so an agent cannot check it now.", code="source_not_checked")


def _person(who: Principal) -> tuple[User, Actor]:
    user = User.objects.get(pk=who.subject_id)
    return user, Actor(kind=ActorType.USER, id=user.id, label=user.name)


def create_request(*, who: Principal, tenant: Tenant, body: ResearchRequestInput) -> ResearchRequestOut:
    """`POST /research-requests`: record the request and open its run, or refuse and write
    nothing."""
    if not TenantAgent.objects.filter(tenant=tenant).exists():
        raise ProblemError(
            status=409,
            code="no_tenant_agent",
            detail="Your organisation has no agent of its own to ask. Add one first: bleqq's agents take no requests.",
        )
    tenant_agent = own_agent(body.tenant_agent_id)
    _checked_fields(body)
    if body.source_id is not None:
        _checked_source(body.source_id)
    user, actor = _person(who)
    # Fetched before the bank's requests are serialized below, so a slow page holds no lock.
    fetched_text = _fetch(body.url) if body.url is not None else ""
    with transaction.atomic():
        lock_tenant(tenant, "research_requests")
        start, end = budget.month(tenant)
        made = ResearchRequest.objects.filter(tenant=tenant, created_at__gte=start, created_at__lt=end).count()
        if made >= settings.RESEARCH_REQUESTS_PER_MONTH:
            raise ProblemError(
                status=429,
                code="plan_limit_reached",
                detail=f"Your organisation has made its {settings.RESEARCH_REQUESTS_PER_MONTH} research requests for this month.",
            )
        try:
            ai.ensure_enabled()
        except ProblemError as off:
            raise ValidationError(off.detail, code="feature_off") from None
        if budget.at_cap(tenant):
            raise ValidationError(
                "Your organisation's agents have reached this month's cap, or no cap is set.", code="budget_cap_reached"
            )
        request = ResearchRequest.objects.create(
            tenant=tenant,
            tenant_agent=tenant_agent,
            requested_by=user,
            kind=body.kind,
            topic=body.topic or "",
            source_id=body.source_id,
            url=body.url or "",
            fetched_text=fetched_text,
            risk_flags=screen_all([body.topic or "", fetched_text]),
        )
        _opened(request, user, actor, tenant_id=tenant.id, subject_title=tenant_agent.agent.key)
    return get_request(tenant=tenant, request_id=request.id)


def _opened(request: ResearchRequest, user: User, actor: Actor, *, tenant_id: uuid.UUID | None, subject_title: str, agent_key: str = "") -> None:
    """Open the request's run and record the request: its kind, agent and flags, and never
    its text."""
    run = tasks.open_request_run(request, requested_by=user, agent_key=agent_key)
    request.status = ResearchRequestStatus.RUNNING.value if run.status == RunStatus.RUNNING.value else ResearchRequestStatus.FAILED.value
    request.save(update_fields=["status"])
    record(
        action="research_request.created",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=request.id,
        subject_title=subject_title,
        summary=f"{actor.label} asked {subject_title} for a {request.kind} request.",
        tenant_id=tenant_id,
        after={
            "kind": request.kind,
            "tenantAgent": None if request.tenant_agent_id is None else str(request.tenant_agent_id),
            "source": None if request.source_id is None else str(request.source_id),
            "run": str(run.id),
            "riskFlags": request.risk_flags,
        },
    )


# ---------------------------------------------------------------------------------------
# check_url: the one place a bank's address is fetched
# ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Fetched:
    """One https answer: its status, where a redirect points, the first bytes of its body
    and the charset it declared."""

    status: int
    location: str
    body: bytes
    charset: str


class Unreachable(Exception):
    """The address answered nothing usable: no connection, no TLS, a timeout."""


def _not_allowed(reason: str) -> ValidationError:
    return ValidationError(f"That address cannot be checked: {reason}", code="url_not_allowed")


def _public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def _resolve(host: str) -> list[str]:
    """Every address the name resolves to (the network's door, replaced in tests)."""
    try:
        return sorted({str(info[4][0]) for info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)})
    except (socket.gaierror, UnicodeError):
        return []


def _allowed(url: str) -> tuple[str, str, str]:
    """The host, the checked address and the path an address may be fetched at, or
    `url_not_allowed`."""
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        raise _not_allowed("its port is not a number.") from None
    host = (parts.hostname or "").rstrip(".").lower()
    if parts.scheme != "https" or not host or port not in (None, 443) or parts.username or parts.password:
        raise _not_allowed("only an https address on the standard port, with no user name, is checked.")
    if any(host == listed or host.endswith(f".{listed}") for listed in settings.STANDARDS_PUBLISHER_HOSTS):
        raise _not_allowed("a standards publisher's pages are not fetched.")
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        addresses = _resolve(host)
    if not addresses:
        raise ValidationError("That address could not be reached.", code="url_unreachable")
    if not all(_public(address) for address in addresses):
        raise _not_allowed("it is not on the public internet.")
    target = parts.path or "/"
    return host, addresses[0], f"{target}?{parts.query}" if parts.query else target


class _CheckedConnection(http.client.HTTPSConnection):
    """An https connection to the address that was checked, so the name cannot resolve to
    another one between the check and the connect. The certificate is verified for the
    host all the same."""

    def __init__(self, host: str, address: str) -> None:
        super().__init__(host, 443, timeout=settings.RESEARCH_URL_TIMEOUT_SECONDS)
        self.address = address
        self.tls = ssl.create_default_context()

    def connect(self) -> None:
        raw = socket.create_connection((self.address, self.port), self.timeout)
        self.sock = self.tls.wrap_socket(raw, server_hostname=self.host)


def _get(*, host: str, address: str, target: str) -> Fetched:
    """One GET, following nothing (the network's door, replaced in tests)."""
    connection = _CheckedConnection(host, address)
    try:
        connection.request("GET", target, headers={"User-Agent": "bleqq-research/1", "Accept": "text/html, text/plain"})
        response = connection.getresponse()
        return Fetched(
            status=response.status,
            location=response.getheader("Location") or "",
            body=response.read(settings.RESEARCH_URL_MAX_BYTES),
            charset=response.headers.get_content_charset() or "utf-8",
        )
    except (OSError, http.client.HTTPException) as failure:
        raise Unreachable() from failure
    finally:
        connection.close()


def _fetch(url: str) -> str:
    """The page at `url` as text, each redirect checked as the first address was."""
    for _ in range(settings.RESEARCH_URL_MAX_REDIRECTS + 1):
        host, address, target = _allowed(url)
        try:
            answer = _get(host=host, address=address, target=target)
        except Unreachable:
            raise ValidationError("That address could not be reached.", code="url_unreachable") from None
        if answer.status in _REDIRECTS and answer.location:
            url = urljoin(url, answer.location)
            continue
        if not 200 <= answer.status < 300:
            raise ValidationError("That address did not answer with a page.", code="url_unreachable")
        try:
            text = answer.body.decode(answer.charset, errors="replace")
        except LookupError:
            text = answer.body.decode("utf-8", errors="replace")
        # PostgreSQL text holds no NUL; the rest is kept as it came.
        return text.replace("\x00", "")
    raise ValidationError("That address redirects too many times.", code="url_unreachable")


# ---------------------------------------------------------------------------------------
# The console's re-tag
# ---------------------------------------------------------------------------------------
def create_retag(*, who: Principal, body: RetagRequestInput) -> ResearchRequestOut:
    """`POST /console/research-requests`: record the re-tag and open bleqq's run for it, in
    no tenant's zone."""
    user, actor = _person(who)
    with transaction.atomic():
        request = ResearchRequest.objects.create(
            requested_by=user, kind=ResearchRequestKind.RETAG.value, topic=body.topic, risk_flags=screen_all([body.topic])
        )
        _opened(request, user, actor, tenant_id=None, subject_title=RETAG_AGENT, agent_key=RETAG_AGENT)
    return get_retag(request_id=request.id)


def file_retag(*, run_id: uuid.UUID, payload: ObligationScopePayload, source_label: str, source_url: str) -> Proposal:
    """What a re-tag's run found, filed once as one batch through `batch.create_batch()`: the
    run's agent proposes, naming its run, and the request names the batch. The door the
    runner that works a re-tag files through (AGT-06); nothing in the library changes
    until an independent person approves the batch."""
    with transaction.atomic():
        run = (
            AgentRun.objects.select_related("agent", "research_request")
            .filter(pk=run_id, tenant__isnull=True, research_request__kind=ResearchRequestKind.RETAG.value)
            .first()  # ordering: pk lookup, at most one row
        )
        if run is None or run.research_request is None:
            raise ProblemError(status=404, code="not_found", detail="Not found.")
        request = ResearchRequest.objects.select_for_update().get(pk=run.research_request.pk)
        if request.batch_proposal_id is not None:
            raise ProblemError(status=409, code="already_filed", detail="This re-tag has already filed its batch.")
        actor = Actor(kind=ActorType.AGENT, id=run.agent_id, label=run.agent.key)
        proposal, _ = batch.create_batch(
            kind=ProposalKind.OBLIGATION_SCOPE.value,
            title=request.topic,
            payload=payload,
            proposer=Proposer(actor=actor, agent_id=run.agent_id),
            agent_run_id=run.id,
            model=run.model,
            source_label=source_label,
            source_url=source_url,
        )
        request.batch_proposal_id = proposal.id
        request.completed_at = timezone.now()
        request.save(update_fields=["batch_proposal_id", "completed_at"])
        record(
            action="research_request.batch_filed",
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=request.id,
            subject_title=run.agent.key,
            summary=f"{run.agent.key} filed a batch of {proposal.row_count} for a re-tag.",
            tenant_id=None,
            after={"batchProposal": str(proposal.id), "run": str(run.id), "rowCount": proposal.row_count},
        )
    return proposal
