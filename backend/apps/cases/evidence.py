"""Evidence: attached, scanned, hashed and streamed (CAS-05; D-11, D-101).

A file arrives in the request itself as multipart form data (CHUNK9 ruling 4) and is
untrusted from its first byte. The server says what it is: the header, the name's
extension and the bytes must all agree on one type of `EVIDENCE_ALLOWED_TYPES`, the size
is the bytes received, and the SHA-256 is computed here. A file outside the list or over
`EVIDENCE_MAX_BYTES` is refused before a byte reaches storage. The bytes are stored under
a key made of the tenant, the case and a random part, never the name, and the row starts
`pending`: `tasks.scan_evidence` decides, and a download serves only `clean`.

A file leaves only through the streaming download (ruling 5), one permission check and one
audit row per download (D-11). A link stores an https address and nothing fetches it; a
reference stores a name. Removal sets `removed_at` and nothing else.

A name is tenant content: it never reaches a log, an audit value or a storage key.
"""

from __future__ import annotations

import hashlib
import io
import unicodedata
import uuid
import zipfile
from collections.abc import Callable
from pathlib import PurePath
from typing import Any, cast
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.http import content_disposition_header
from ninja import UploadedFile

from apps.cases import logic, schemas, tasks
from apps.cases.models import ChangeCase, Evidence, EvidenceKind
from apps.cases.schemas import CasesEvidence, CasesEvidenceCreated, CasesEvidenceForm, CasesEvidencePage
from apps.shared.adapters.scanner import ScanState, get_scanner
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.kinds import CaseStatusCategory
from apps.shared.models import Tenant
from apps.shared.schemas import PageQuery
from apps.shared.storage import get_storage
from apps.taxonomy.schemas import PersonRef

SUBJECT_TYPE = "evidence"
ATTACHED = "case.evidence_attached"
DOWNLOADED = "case.evidence_downloaded"
REMOVED = "case.evidence_removed"

CLOSED_CATEGORIES = (CaseStatusCategory.CLOSED.value, CaseStatusCategory.DISMISSED.value)
# What a browser sends when it does not know the type; the extension and the bytes decide.
GENERIC_TYPES = ("", "application/octet-stream")
_OOXML = "application/vnd.openxmlformats-officedocument."


def _pdf(content: bytes) -> bool:
    return content.startswith(b"%PDF-")


def _ooxml(folder: str) -> Callable[[bytes], bool]:
    """An Office Open XML package with its content types and a part in `folder`. Only the
    zip's directory is read; nothing is extracted."""

    def looks_like(content: bytes) -> bool:
        try:
            names = zipfile.ZipFile(io.BytesIO(content)).namelist()
        except (zipfile.BadZipFile, zipfile.LargeZipFile, ValueError, EOFError, OSError):
            return False
        return "[Content_Types].xml" in names and any(name.startswith(folder) for name in names)

    return looks_like


def _text(content: bytes) -> bool:
    """UTF-8 text without a NUL and not starting as markup, so no page, SVG or XML passes
    as plain text."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    return "\0" not in text and not text.lstrip().startswith("<")


# Each type the server can recognise: the extensions a name may carry and the test the
# bytes must pass. A type in the setting but not here is refused.
RECOGNISED: dict[str, tuple[tuple[str, ...], Callable[[bytes], bool]]] = {
    "application/pdf": ((".pdf",), _pdf),
    _OOXML + "wordprocessingml.document": ((".docx",), _ooxml("word/")),
    _OOXML + "spreadsheetml.sheet": ((".xlsx",), _ooxml("xl/")),
    _OOXML + "presentationml.presentation": ((".pptx",), _ooxml("ppt/")),
    "image/png": ((".png",), lambda content: content.startswith(b"\x89PNG\r\n\x1a\n")),
    "image/jpeg": ((".jpg", ".jpeg"), lambda content: content.startswith(b"\xff\xd8\xff")),
    "text/plain": ((".txt",), _text),
    "text/csv": ((".csv",), _text),
}


def _refused_file() -> ProblemError:
    megabytes = settings.EVIDENCE_MAX_BYTES / (1024 * 1024)
    return ProblemError(
        status=422,
        code="validation_error",
        detail=(
            "This file cannot be attached. Attach a PDF, Word, Excel, PowerPoint, PNG, JPEG, "
            f"text or CSV file of at most {megabytes:g} MB whose name ends in its type."
        ),
    )


def identify(filename: str, declared: str, content: bytes) -> str | None:
    """The one allowed type the header, the extension and the bytes agree on, or None."""
    extension = PurePath(filename).suffix.lower()
    declared = declared.split(";")[0].strip().lower()
    for mime, (extensions, looks_like) in RECOGNISED.items():
        if (
            mime in settings.EVIDENCE_ALLOWED_TYPES
            and declared in (mime, *GENERIC_TYPES)
            and extension in extensions
            and looks_like(content)
        ):
            return mime
    return None


def _view(evidence: Evidence) -> CasesEvidence:
    is_file = evidence.kind == EvidenceKind.FILE.value
    return CasesEvidence(
        id=evidence.id,
        kind=cast(schemas.EvidenceKind, evidence.kind),
        name=evidence.name,
        url=evidence.url if evidence.kind == EvidenceKind.LINK.value else None,
        size_bytes=evidence.size_bytes if is_file else None,
        mime_type=evidence.mime_type if is_file else None,
        content_hash=evidence.content_hash if is_file else None,
        scan_state=cast(schemas.ScanState, evidence.scan_state),
        uploaded_by=PersonRef(id=evidence.uploaded_by.id, name=evidence.uploaded_by.name),
        uploaded_at=evidence.uploaded_at,
    )


def _refuse_when_closed(case: ChangeCase) -> None:
    """A closed or dismissed case's evidence is what was signed off or set aside: it stays."""
    if case.status in CLOSED_CATEGORIES:
        raise ProblemError(status=409, code="case_closed", detail="This case is closed, so its evidence cannot change.")


def _invalid(detail: str) -> ProblemError:
    return ProblemError(status=422, code="validation_error", detail=detail)


def list_evidence(*, tenant: Tenant, change_id: uuid.UUID, page: PageQuery) -> CasesEvidencePage:
    """One page of the case's live evidence, each with its scan state."""
    case = logic.load_case(tenant, change_id)
    live = Evidence.objects.select_related("uploaded_by").filter(tenant=tenant, case=case, removed_at__isnull=True)
    return CasesEvidencePage(
        items=[_view(row) for row in live[page.offset : page.offset + page.limit]],
        total=live.count(),
    )


def add_evidence(
    *, tenant: Tenant, actor: Actor, user: Any, change_id: uuid.UUID, form: CasesEvidenceForm, file: UploadedFile | None
) -> CasesEvidenceCreated:
    """A file, a link or a reference on the case. A file is checked, hashed, stored and
    queued for the scan before this answers."""
    case = logic.load_case(tenant, change_id, for_update=True)
    _refuse_when_closed(case)
    kind = EvidenceKind(form.kind)
    if (kind is EvidenceKind.FILE) != (file is not None):
        raise _invalid("Send the file part with a file, and only with a file.")
    if kind is EvidenceKind.LINK:
        address = urlsplit(form.url)
        if address.scheme != "https" or not address.hostname or any(c.isspace() or not c.isprintable() for c in form.url):
            raise _invalid("A link must be a full https address.")
    elif form.url:
        raise _invalid("Only a link has an address.")
    if Evidence.objects.filter(case=case, removed_at__isnull=True).count() >= settings.CASE_EVIDENCE_MAX:
        raise ProblemError(
            status=409,
            code="evidence_limit_reached",
            detail=f"A case holds at most {settings.CASE_EVIDENCE_MAX} pieces of evidence. Remove one to add another.",
        )

    evidence = Evidence(tenant=tenant, case=case, kind=kind.value, name=form.name, uploaded_by=user)
    if file is None:
        # Nothing to scan: a link's address is never fetched and a reference is a name.
        evidence.url = form.url
        evidence.scan_state, evidence.scanned_at = ScanState.CLEAN.value, timezone.now()
    else:
        _store(evidence, file)
    evidence.save()
    after: dict[str, Any] = {"evidenceId": str(evidence.id), "caseId": str(case.id), "kind": kind.value}
    if file is not None:
        after |= {"contentHash": evidence.content_hash, "sizeBytes": evidence.size_bytes, "mimeType": evidence.mime_type}
        transaction.on_commit(lambda: tasks.scan_evidence.delay(str(tenant.id), str(evidence.id)))
    record(
        action=ATTACHED,
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=evidence.id,
        subject_title=case.change.title,
        summary=f"{actor.label} attached a {kind.value} to a case as evidence.",
        tenant_id=tenant.id,
        after=after,
    )
    return CasesEvidenceCreated(evidence=_view(evidence))


def _store(evidence: Evidence, file: UploadedFile) -> None:
    """Refuse the file, or measure it, identify it and write it to storage. Django counted
    `file.size` from the bytes it received, so the cap is checked before they are read."""
    try:
        get_scanner()
    except ImproperlyConfigured as refused:
        raise ProblemError(
            status=503, code="scanner_unavailable", detail="Files cannot be attached right now. Try again later."
        ) from refused
    if not file.size or file.size > settings.EVIDENCE_MAX_BYTES:
        raise _refused_file()
    content = file.read()
    mime = identify(file.name or "", file.content_type or "", content)
    if mime is None:
        raise _refused_file()
    evidence.storage_key = f"{evidence.tenant_id}/cases/{evidence.case_id}/evidence/{uuid.uuid4().hex}"
    evidence.content_hash = "sha256:" + hashlib.sha256(content).hexdigest()
    evidence.size_bytes = len(content)
    evidence.mime_type = mime
    get_storage().write(evidence.storage_key, content, mime)


def download_name(name: str, mime: str) -> str:
    """The name a download is saved under: the evidence's name without control or
    direction-changing characters, ending in its checked type's extension, so a name typed as
    `controls.ps1` or `report\u202etxt.exe` never lands on a disk as something to run."""
    visible = "".join(c for c in name if unicodedata.category(c) not in ("Cc", "Cf")).strip() or "evidence"
    extensions = RECOGNISED[mime][0] if mime in RECOGNISED else (".bin",)
    return visible if PurePath(visible).suffix.lower() in extensions else visible + extensions[0]


def download_evidence(*, tenant: Tenant, actor: Actor, user: Any, evidence_id: uuid.UUID) -> HttpResponse:
    """The bytes of a clean file, with one audit row per download."""
    evidence = logic.load_evidence(tenant, evidence_id)
    if evidence.kind != EvidenceKind.FILE.value:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    if evidence.scan_state == ScanState.PENDING.value:
        raise ProblemError(status=409, code="scan_pending", detail="This file is still being checked for malware. Try again shortly.")
    if evidence.scan_state != ScanState.CLEAN.value:
        raise ProblemError(status=422, code="scan_failed", detail="This file did not pass the malware check and cannot be downloaded.")
    content = get_storage().read(evidence.storage_key)
    record(
        action=DOWNLOADED,
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=evidence.id,
        subject_title=evidence.case.change.title,
        summary=f"{actor.label} downloaded a file attached to a case as evidence.",
        tenant_id=tenant.id,
        after={"evidenceId": str(evidence.id), "caseId": str(evidence.case_id), "contentHash": evidence.content_hash},
    )
    # Never served as a type the allow-list does not know, so a row can never become a page.
    mime = evidence.mime_type if evidence.mime_type in RECOGNISED else "application/octet-stream"
    response = HttpResponse(content, content_type=mime)
    response["Content-Disposition"] = content_disposition_header(as_attachment=True, filename=download_name(evidence.name, mime))
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def remove_evidence(*, tenant: Tenant, actor: Actor, user: Any, evidence_id: uuid.UUID) -> None:
    """Remove a piece of evidence: `removed_at` is set, and the row and its hash stay."""
    evidence = logic.load_evidence(tenant, evidence_id)
    _refuse_when_closed(evidence.case)
    evidence.removed_at = timezone.now()
    evidence.save(update_fields=["removed_at"])
    record(
        action=REMOVED,
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=evidence.id,
        subject_title=evidence.case.change.title,
        summary=f"{actor.label} removed a piece of evidence from a case.",
        tenant_id=tenant.id,
        after={"evidenceId": str(evidence.id), "caseId": str(evidence.case_id), "removedAt": evidence.removed_at.isoformat()},
    )
