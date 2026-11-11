"""The malware scan of a piece of evidence (CAS-05, D-101).

`scan_evidence` is a `@tenant_task` queued after the storing request commits: it reads the
bytes, asks the configured scanner and writes the verdict and one audit row in one
transaction. A failed scan is retried up to `EVIDENCE_SCAN_RETRIES` times, then stays
`error`; an infected file's bytes are deleted once the verdict commits, its row and hash
kept. A decided file is left alone. Nothing logs a filename or a byte.
"""

from __future__ import annotations

import uuid

from celery import shared_task
from django.conf import settings
from django.db import transaction

from apps.cases.models import Evidence
from apps.shared import tenancy
from apps.shared.adapters.scanner import ScanState, get_scanner
from apps.shared.audit import Actor, record
from apps.shared.storage import get_storage

SCANNED = "case.evidence_scanned"


@shared_task
@tenancy.tenant_task
def scan_evidence(tenant_id: uuid.UUID, evidence_id: str) -> None:
    pending = Evidence.objects.filter(tenant_id=tenant_id, pk=evidence_id, scan_state=ScanState.PENDING.value)
    evidence = pending.first()  # ordering: pk lookup, at most one row
    if evidence is None:
        return
    # The scan runs before the row is locked, so a removal never waits on the scanner.
    storage = get_storage()
    content = storage.read(evidence.storage_key)
    scanner = get_scanner()
    for _attempt in range(settings.EVIDENCE_SCAN_RETRIES + 1):
        result = scanner.scan(content, filename=evidence.name)
        if result.state is not ScanState.ERROR:
            break
    # Another delivery of this task may have decided the file meanwhile: the first one wins.
    evidence = pending.select_related("case__change").select_for_update(of=("self",)).first()  # ordering: pk lookup
    if evidence is None:
        return
    evidence.scan_state, evidence.scanned_at = result.state.value, result.scanned_at
    evidence.save(update_fields=["scan_state", "scanned_at"])
    record(
        action=SCANNED,
        actor=Actor.system("malware scan"),
        subject_type="evidence",
        subject_id=evidence.id,
        subject_title=evidence.case.change.title,
        summary=f"The malware scan of a file attached to a case answered {result.state.value}.",
        tenant_id=tenant_id,
        after={"evidenceId": str(evidence.id), "scanState": result.state.value, "signature": result.signature},
    )
    if result.state is ScanState.INFECTED:
        # Once the verdict is committed, so a rolled-back verdict never leaves a pending row
        # without its bytes.
        key = evidence.storage_key
        transaction.on_commit(lambda: storage.delete(key))
