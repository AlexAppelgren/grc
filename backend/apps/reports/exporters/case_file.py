"""The case file as an export (CAS-07): the same text `GET /changes/{changeId}/case-file`
answers, built by `apps/cases/case_file.py`, plain UTF-8 (no PDF library).

`subjectId` names the case. `check` runs on create and on every download: the person must be
able to read cases and the case must be their bank's (404 otherwise). The builder re-reads the
case under the job's tenant, so a job naming another bank's case fails. The file is in the
asker's language.
"""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError

from apps.cases import case_file
from apps.cases.models import ChangeCase
from apps.identity.roles_logic import language_order
from apps.reports.models import ExportJob
from apps.shared import permissions as perms
from apps.shared.errors import ProblemError, not_found
from apps.shared.models import Tenant


def check(*, tenant: Tenant, permissions: frozenset[str], subject_id: uuid.UUID | None) -> None:
    """Refuse a person who may not read cases, and a case that is not this bank's."""
    if perms.CASES_READ not in permissions:
        raise ProblemError(
            status=403, code="permission_denied", detail="You do not have access to this.", required_permission=perms.CASES_READ
        )
    if subject_id is None or not ChangeCase.objects.filter(tenant=tenant, pk=subject_id).exists():
        raise not_found()


def build(job: ExportJob) -> bytes:
    tenant = Tenant.objects.select_related("default_language").get(pk=job.tenant_id)
    if job.subject_id is None or not ChangeCase.objects.filter(tenant=tenant, pk=job.subject_id).exists():
        raise ValidationError("The case this export names is not in your bank.")
    requester = job.requested_by
    order = language_order(requester, tenant)
    return case_file.compose(tenant=tenant, case_id=job.subject_id, order=order).encode("utf-8")
