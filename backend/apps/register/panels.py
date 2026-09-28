"""The obligation page's read (perf-obligation-page): the register entry and what every panel
shows on load, in one request instead of one per panel.

Each part is the first page the panel's own route reads, built by that route's own function,
so it holds exactly what the route would answer the same caller. A part behind a permission
the route's gate does not already demand (`register.read`) is read only when the caller holds
that permission, and is null otherwise: the reports need `problems.report`, the changes
`watch.read` and the comments `library.read`. A read writes nothing, and the query count is
fixed however many rows each part holds.
"""

from __future__ import annotations

import uuid

from apps.collab import comments, participants
from apps.collab.schemas import CollabCommentQuery
from apps.governance import problem_reports_logic
from apps.governance.schemas import ProblemReportPage, ProblemReportQuery
from apps.identity.models import User
from apps.library.reading import under_standard
from apps.register import applicability, gaps, history, links, status_logic, units
from apps.register.schemas import RegisterEntry, RegisterEntryWithPanels, RegisterGapPage, RegisterPanels, RegisterPanelUnits
from apps.shared import permissions as perms
from apps.shared.models import Tenant
from apps.shared.permissions import Principal
from apps.shared.schemas import PageQuery
from apps.watch import reading as watch_reading

# The page each panel asks its own route for, so the part here is the page it would read.
FIRST_PAGE = 20
WHOLE_LIST = 100  # gaps, participants and units, which their panels show whole
SUBJECT = "obligation"


def read_with_panels(*, who: Principal, user: User, tenant: Tenant, order: list[str], obligation_id: uuid.UUID) -> RegisterEntryWithPanels:
    """`GET /obligations/{obligationId}/register`: the entry, then its panels' first pages."""
    entry = status_logic.read_register(tenant=tenant, order=order, obligation_id=obligation_id)
    return RegisterEntryWithPanels(
        **dict(entry),
        panels=RegisterPanels(
            # `read_register` answered 404 for a duty the caller cannot see, so these read their
            # page without checking it again.
            spanned_entities=applicability.spanned_of(obligation_id),
            gaps=RegisterGapPage.model_validate(gaps.obligation_gaps_page(order=order, obligation_id=obligation_id, limit=WHOLE_LIST, offset=0)),
            assessments=history.assessments_page(order=order, obligation_id=obligation_id, limit=FIRST_PAGE, offset=0),
            internal_links=links.links_page(order=order, obligation_id=obligation_id, limit=FIRST_PAGE, offset=0),
            units=_units(order=order, obligation_id=obligation_id, entity=_first_applying(entry)),
            participants=participants.list_participants(obligation_id=obligation_id, order=order, limit=WHOLE_LIST, offset=0),
            problem_reports=_problem_reports(who, order, obligation_id) if who.has_permission(perms.PROBLEMS_REPORT) else None,
            changes=(
                watch_reading.list_obligation_changes(tenant, order, obligation_id, PageQuery(limit=FIRST_PAGE, offset=0))
                if who.has_permission(perms.WATCH_READ)
                else None
            ),
            comments=(
                comments.list_comments(
                    who=who, user=user, query=CollabCommentQuery(subject_type=SUBJECT, subject_id=obligation_id, limit=FIRST_PAGE, offset=0)
                )
                if who.has_permission(perms.LIBRARY_READ)
                else None
            ),
        ),
    )


def _first_applying(entry: RegisterEntry) -> uuid.UUID | None:
    """The legal entity the units panel opens on: the first by name the obligation applies to."""
    return next((row.org_unit_id for row in entry.entities if row.applicability == "applies"), None)


def _units(*, order: list[str], obligation_id: uuid.UUID, entity: uuid.UUID | None) -> RegisterPanelUnits | None:
    if entity is None or not under_standard(obligation_id):
        return None
    page = units.units_page(order=order, obligation_id=obligation_id, entity=entity, limit=WHOLE_LIST, offset=0)
    return RegisterPanelUnits(org_unit_id=entity, units=page)


def _problem_reports(who: Principal, order: list[str], obligation_id: uuid.UUID) -> ProblemReportPage:
    rows, total = problem_reports_logic.reports_for(
        who, ProblemReportQuery(subject_type=SUBJECT, subject_id=obligation_id), order, limit=FIRST_PAGE, offset=0
    )
    return ProblemReportPage(items=rows, total=total)
