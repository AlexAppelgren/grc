"""Assessment history and "How we read this rule" (REG-04).

Assessments are append-only; an interpretation is a new version on every save, the previous
one stamped superseded and kept readable, with no approval step and no four-eyes check (plan
7.2). The text of a version is never rewritten, and it never reaches an audit value, a log
or the outbox (R2_CROSS_CUTTING (m)): the audit row names the obligation and the version.
"""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.identity.models import User
from apps.library.reading import obligation_headings
from apps.register.links import person_id
from apps.register.logic import ensure_register_entry
from apps.register.models import ComplianceAssessment, Interpretation, TenantObligation
from apps.register.schemas import (
    RegisterAssessment,
    RegisterAssessmentPage,
    RegisterInterpretation,
    RegisterInterpretationBody,
    RegisterInterpretationVersion,
    RegisterPersonRef,
    RegisterVocabRef,
)
from apps.shared.audit import Actor, record
from apps.shared.models import Tenant
from apps.shared.vocabulary import Vocabulary, label_for

INTERPRETATION_SAVED = "register.interpretation_saved"


def list_assessments(
    *, tenant: Tenant, order: list[str], obligation_id: uuid.UUID, limit: int, offset: int
) -> RegisterAssessmentPage:
    """The bank's assessments of one obligation, newest first, in a constant number of
    queries. An obligation the bank cannot see is 404; one never assessed is an empty page."""
    _visible(obligation_id)
    assessments = ComplianceAssessment.objects.filter(tenant_obligation__obligation_id=obligation_id)
    rows = (
        assessments.select_related("status", "risk_rating", "assessed_by", "scope__org_unit")
        .prefetch_related("status__labels", "risk_rating__labels")
        .order_by("-assessed_at", "-id")[offset : offset + limit]
    )
    return RegisterAssessmentPage(
        items=[
            RegisterAssessment(
                id=row.id,
                org_unit_id=None if row.scope is None else row.scope.org_unit_id,
                org_unit_name=None if row.scope is None else row.scope.org_unit.name,
                assessed_at=row.assessed_at,
                assessed_by=_person(row.assessed_by),
                method=row.method,  # type: ignore[arg-type]  # the AssessmentMethod kind's values
                status=_vocab(row.status, order),
                risk_rating=None if row.risk_rating is None else _vocab(row.risk_rating, order),
                rationale=row.rationale,
                next_review_date=row.next_review_date,
            )
            for row in rows
        ],
        total=assessments.count(),
    )


def read_interpretation(*, tenant: Tenant, obligation_id: uuid.UUID) -> RegisterInterpretation:
    """The reading in force and every earlier one, newest first. An obligation the bank
    cannot see is 404; one without a reading has `current` null."""
    _visible(obligation_id)
    return _interpretation_out(obligation_id)


def save_interpretation(
    *,
    tenant: Tenant,
    actor: Actor,
    obligation_id: uuid.UUID,
    body: RegisterInterpretationBody,
    expected_version: int | None,
) -> RegisterInterpretation:
    """Write the next version and stamp the one before it superseded. The entry row is
    locked first, so two saves at once are ordered and the second one's `If-Match` is stale."""
    entry = ensure_register_entry(tenant_id=tenant.id, obligation_id=obligation_id, actor=actor)
    TenantObligation.objects.select_for_update().filter(pk=entry.pk).first()  # ordering: pk lookup, the lock only
    current = Interpretation.objects.filter(tenant_obligation=entry, superseded_at__isnull=True).first()  # ordering: at most one version in force
    current_no = 0 if current is None else current.version_number
    if expected_version is not None and expected_version != current_no:
        raise ValidationError("Somebody wrote a newer reading in between. Reload it first.", code="stale_write")
    now = timezone.now()
    if current is not None:
        current.superseded_at = now
        current.save(update_fields=["superseded_at"])
    version = Interpretation.objects.create(
        tenant_id=tenant.id,
        tenant_obligation=entry,
        version_number=current_no + 1,
        body=body.text,
        author_id=person_id(actor),
        created_at=now,
    )
    heading = obligation_headings([obligation_id], []).get(obligation_id)
    record(
        action=INTERPRETATION_SAVED,
        actor=actor,
        subject_type="interpretation",
        subject_id=version.id,
        subject_title="" if heading is None else f"{heading.instrument_short_name}, {heading.reference_label}",
        summary=f"How we read this rule, version {version.version_number}.",
        tenant_id=tenant.id,
        before={"versionNo": current_no},
        after={"obligationId": str(obligation_id), "versionNo": version.version_number},
    )
    return _interpretation_out(obligation_id)


def _visible(obligation_id: uuid.UUID) -> None:
    if not obligation_headings([obligation_id], []):
        raise ValidationError("That obligation is not here.", code="not_found")


def _interpretation_out(obligation_id: uuid.UUID) -> RegisterInterpretation:
    versions = [
        RegisterInterpretationVersion(
            version_no=row.version_number, text=row.body, author=_person(row.author), written_at=row.created_at
        )
        for row in Interpretation.objects.filter(tenant_obligation__obligation_id=obligation_id)
        .select_related("author")
        .order_by("-version_number")
    ]
    return RegisterInterpretation(obligation_id=obligation_id, current=versions[0] if versions else None, earlier=versions[1:])


def _person(user: User) -> RegisterPersonRef:
    return RegisterPersonRef(id=user.id, name=user.name)


def _vocab(row: Vocabulary, order: list[str]) -> RegisterVocabRef:
    return RegisterVocabRef(key=row.key, kind=row.kind, label=label_for(row, order))
