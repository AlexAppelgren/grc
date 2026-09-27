"""Evidence: attached, scanned, hashed and streamed (CAS-05; D-11, D-101).

Published ahead of its logic: every function loads the caller's case or evidence, so
another bank's answers 404 exactly as it will, and then answers 501 `not_built` until
`c9-evidence` builds it here. A file arrives in the request itself as multipart form
data (CHUNK9 ruling 4) and leaves only through the streaming download (ruling 5).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.http import HttpResponse
from ninja import UploadedFile

from apps.cases import logic
from apps.cases.schemas import CasesEvidenceCreated, CasesEvidenceForm, CasesEvidencePage
from apps.shared.audit import Actor
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.shared.schemas import PageQuery

NOT_BUILT = "This part of the case workflow is not available yet."


def list_evidence(*, tenant: Tenant, change_id: uuid.UUID, page: PageQuery) -> CasesEvidencePage:
    """One page of the case's live evidence, each with its scan state."""
    logic.load_case(tenant, change_id)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)


def add_evidence(
    *, tenant: Tenant, actor: Actor, user: Any, change_id: uuid.UUID, form: CasesEvidenceForm, file: UploadedFile | None
) -> CasesEvidenceCreated:
    """A file, a link or a reference on the case. A file is checked, hashed, stored and
    queued for the scan before this answers."""
    logic.load_case(tenant, change_id)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)


def download_evidence(*, tenant: Tenant, actor: Actor, user: Any, evidence_id: uuid.UUID) -> HttpResponse:
    """The bytes of a clean file, streamed, with one audit row per download."""
    logic.load_evidence(tenant, evidence_id)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)


def remove_evidence(*, tenant: Tenant, actor: Actor, user: Any, evidence_id: uuid.UUID) -> None:
    """Remove a piece of evidence: `removed_at` is set, and the row and its hash stay."""
    logic.load_evidence(tenant, evidence_id)
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)
