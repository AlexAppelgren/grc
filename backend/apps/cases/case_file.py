"""The case file: one case's whole story as text that stands alone (CAS-07).

An auditor reads it without the product beside it, so it says everything in words: the
change and where it came from, the bank's "So what?", the assessment, every action and
what became of it, every piece of evidence with its hash and scan, the sign-off with both
people and the step-up that confirmed it, the dismissal or the close, and every move. A
removed action or piece of evidence is printed and marked, never left out: nothing is
overwritten (playbook 4.3). An unconfirmed "So what?" is the AI's draft and is labelled
as one, never presented as the bank's text (WAT-05).

The text is written from the catalog below in the reader's language, in the manner of
`apps/home/mail.py`: English and Swedish, and English for a language this module does not
hold. It names no requirement, column or permission. Dates and times are in the bank's
own time zone with the offset spelled out.

One builder serves both the screen and the export (`apps/reports/exporters/case_file.py`),
so the two cannot drift. It reads a fixed number of queries whatever the case holds — the
case with its people and reasons, one label query per reason it carries, the assessment,
the actions, the evidence, the moves and the sign-off's step-up — so a case at its caps
stays inside the request budget. It reads and never writes.
"""

from __future__ import annotations

import datetime
import uuid
import zoneinfo
from typing import Any

from apps.cases import logic
from apps.cases.models import Action, CaseTransition, ChangeCase, Evidence, EvidenceKind, ImpactAssessment
from apps.shared.audit import Actor
from apps.shared.kinds import CaseStatusCategory
from apps.shared.models import AuditEvent, Tenant
from apps.shared.vocabulary import label_for

FALLBACK_LANGUAGE = "en"

# What the file joins beside the case, so naming every person costs no query of its own.
JOINS = (*logic.CASE_JOINS, "so_what_confirmed_by")

_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "heading": "Case file: {title}",
        "identifier": "Identifier: {value}",
        "authority": "Authority: {value}",
        "published": "Published: {value}",
        "key_date": "{label}: {value}",
        "key_date_default": "Key date",
        "source": "Source: {label} ({url})",
        "stage": "Stage: {value}",
        "stage_detail": "Stage: {value} ({detail})",
        "urgency": "Urgency: {value}",
        "urgency_suggested": "Urgency: {value}, suggested and not yet confirmed by a person",
        "owner": "Owner: {name}",
        "triaged": "Triaged by {name} on {at}",
        "so_what": "So what?",
        "so_what_confirmed": "Confirmed by {name} on {at}.",
        "so_what_draft": "Draft written by an AI agent. Nobody at the bank has confirmed it.",
        "so_what_none": "Nobody has written what this change means for the bank.",
        "assessment": "Assessment",
        "applies": "Does it apply: {value}",
        "why": "Why: {value}",
        "what_must_change": "What must change: {value}",
        "deadline": "Internal deadline: {value}",
        "effort": "Effort: {value}",
        "assessment_saved": "Saved by {name} on {at}.",
        "assessment_none": "No assessment has been saved.",
        "actions": "Actions",
        "action_line": "- {title}",
        "action_owner": "  Owner: {name}. Due: {due}.",
        "action_done": "  Done by {name} on {at}.",
        "action_open": "  Not done yet.",
        "action_removed": "  Removed by {name} on {at}. It is no longer part of the plan.",
        "actions_none": "No actions were planned.",
        "evidence": "Evidence",
        "evidence_line": "- {name} ({kind})",
        "evidence_added": "  Added by {name} on {at}.",
        "evidence_hash": "  Content hash (SHA-256): {value}",
        "evidence_url": "  Address: {value}",
        "evidence_scan": "  Malware scan: {value}",
        "evidence_scan_at": "  Malware scan: {value}, {at}",
        "evidence_removed": "  Removed on {at}. It no longer counts as evidence.",
        "evidence_none": "No evidence was added.",
        "signoff": "Sign-off",
        "signoff_requested": "Requested by {name} on {at}.",
        "signoff_by": "Signed off by {name} on {at}.",
        "signoff_step_up": "Confirmed with a passkey, reference {value}.",
        "signoff_none": "Sign-off has not been requested.",
        "outcome": "Outcome",
        "closed": "Closed on {at}. Reason: {reason}.",
        "closed_note": "Note: {value}",
        "dismissed": "Dismissed by {name} on {at}. Reason: {reason}.",
        "open": "The case is still open.",
        "history": "History",
        "move": "- {at}: {from_stage} to {to_stage}, by {name}",
        "move_first": "- {at}: opened in {to_stage}",
        "move_note": "  Note: {value}",
        "nobody": "the system",
        "none": "not set",
        # The fixed categories, the verdicts, the kinds of evidence and the scan states.
        "new": "Needs triage",
        "assigned": "Assigned",
        "assessing": "Assessing",
        "implementing": "Implementing",
        "signoff_stage": "Waiting for sign-off",
        "closed_stage": "Closed",
        "dismissed_stage": "Dismissed",
        "yes": "Yes",
        "partly": "Partly",
        "no": "No",
        "file": "file",
        "link": "link",
        "reference": "reference to an internal document",
        "pending": "not scanned yet",
        "clean": "passed",
        "infected": "malware found",
        "error": "could not be scanned",
    },
    "sv": {
        "heading": "Ärendeakt: {title}",
        "identifier": "Identitet: {value}",
        "authority": "Myndighet: {value}",
        "published": "Publicerad: {value}",
        "key_date": "{label}: {value}",
        "key_date_default": "Viktigt datum",
        "source": "Källa: {label} ({url})",
        "stage": "Steg: {value}",
        "stage_detail": "Steg: {value} ({detail})",
        "urgency": "Brådska: {value}",
        "urgency_suggested": "Brådska: {value}, föreslagen och ännu inte bekräftad av en person",
        "owner": "Ansvarig: {name}",
        "triaged": "Triagerad av {name} {at}",
        "so_what": "Vad betyder det för oss?",
        "so_what_confirmed": "Bekräftad av {name} {at}.",
        "so_what_draft": "Utkast skrivet av en AI-agent. Ingen på banken har bekräftat det.",
        "so_what_none": "Ingen har skrivit vad ändringen betyder för banken.",
        "assessment": "Bedömning",
        "applies": "Gäller det oss: {value}",
        "why": "Varför: {value}",
        "what_must_change": "Vad som måste ändras: {value}",
        "deadline": "Intern tidsgräns: {value}",
        "effort": "Arbetsinsats: {value}",
        "assessment_saved": "Sparad av {name} {at}.",
        "assessment_none": "Ingen bedömning har sparats.",
        "actions": "Åtgärder",
        "action_line": "- {title}",
        "action_owner": "  Ansvarig: {name}. Klar senast: {due}.",
        "action_done": "  Klar, markerad av {name} {at}.",
        "action_open": "  Inte klar ännu.",
        "action_removed": "  Borttagen av {name} {at}. Den ingår inte längre i planen.",
        "actions_none": "Inga åtgärder planerades.",
        "evidence": "Underlag",
        "evidence_line": "- {name} ({kind})",
        "evidence_added": "  Tillagt av {name} {at}.",
        "evidence_hash": "  Kontrollsumma (SHA-256): {value}",
        "evidence_url": "  Adress: {value}",
        "evidence_scan": "  Skanning mot skadlig kod: {value}",
        "evidence_scan_at": "  Skanning mot skadlig kod: {value}, {at}",
        "evidence_removed": "  Borttaget {at}. Det räknas inte längre som underlag.",
        "evidence_none": "Inget underlag lades till.",
        "signoff": "Godkännande",
        "signoff_requested": "Begärt av {name} {at}.",
        "signoff_by": "Godkänt av {name} {at}.",
        "signoff_step_up": "Bekräftat med passkey, referens {value}.",
        "signoff_none": "Godkännande har inte begärts.",
        "outcome": "Utfall",
        "closed": "Stängt {at}. Skäl: {reason}.",
        "closed_note": "Anteckning: {value}",
        "dismissed": "Avfärdat av {name} {at}. Skäl: {reason}.",
        "open": "Ärendet är fortfarande öppet.",
        "history": "Historik",
        "move": "- {at}: {from_stage} till {to_stage}, av {name}",
        "move_first": "- {at}: öppnat i {to_stage}",
        "move_note": "  Anteckning: {value}",
        "nobody": "systemet",
        "none": "inte angivet",
        "new": "Behöver triageras",
        "assigned": "Tilldelat",
        "assessing": "Bedöms",
        "implementing": "Genomförs",
        "signoff_stage": "Väntar på godkännande",
        "closed_stage": "Stängt",
        "dismissed_stage": "Avfärdat",
        "yes": "Ja",
        "partly": "Delvis",
        "no": "Nej",
        "file": "fil",
        "link": "länk",
        "reference": "hänvisning till ett internt dokument",
        "pending": "inte skannat ännu",
        "clean": "godkänd",
        "infected": "skadlig kod hittad",
        "error": "kunde inte skannas",
    },
}

# A category's catalog key: three of them share a word with a heading or an outcome.
_STAGE = {"signoff": "signoff_stage", "closed": "closed_stage", "dismissed": "dismissed_stage"}


def case_file(*, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID) -> str:
    """The caller's case for this change as its file. Another bank's case, and a change
    the bank has no case for, answer the same 404 before anything else is read."""
    return compose(tenant=tenant, case_id=logic.load_case(tenant, change_id).id, order=order)


def compose(*, tenant: Tenant, case_id: uuid.UUID, order: list[str]) -> str:
    """The file of this bank's case with this id, in the first language of `order` the
    catalog holds."""
    texts = next((_TEXTS[code] for code in order if code in _TEXTS), _TEXTS[FALLBACK_LANGUAGE])
    zone = zoneinfo.ZoneInfo(tenant.timezone)
    case = ChangeCase.objects.select_related(*JOINS).get(tenant=tenant, pk=case_id)
    writer = _Writer(texts, zone)
    _change(writer, case, order)
    _so_what(writer, case)
    _assessment(writer, case, order)
    _actions(writer, case)
    _evidence(writer, case)
    _signoff(writer, case, tenant)
    _outcome(writer, case, order)
    _history(writer, case)
    return "\n".join(writer.lines) + "\n"


class _Writer:
    """The lines of one file, the catalog and the bank's clock."""

    def __init__(self, texts: dict[str, str], zone: zoneinfo.ZoneInfo) -> None:
        self.texts = texts
        self.zone = zone
        self.lines: list[str] = []

    def say(self, key: str, **values: str) -> None:  # compliance: allow-kwargs the catalog's named placeholders
        self.lines.append(self.texts[key].format(**values))

    def section(self, key: str) -> None:
        self.lines.extend(["", self.texts[key], "=" * len(self.texts[key])])

    def word(self, key: str) -> str:
        return self.texts[_STAGE.get(key, key)]

    def at(self, moment: datetime.datetime) -> str:
        return moment.astimezone(self.zone).strftime("%Y-%m-%d %H:%M UTC%:z")

    def name(self, user: Any) -> str:
        return self.texts["nobody"] if user is None else str(user.name)


def _day(value: datetime.date | None, writer: _Writer) -> str:
    return writer.texts["none"] if value is None else value.isoformat()


def _change(writer: _Writer, case: ChangeCase, order: list[str]) -> None:
    change = case.change
    writer.say("heading", title=change.title)
    writer.say("identifier", value=change.stable_key)
    writer.say("authority", value=change.authority_label)
    writer.say("published", value=_day(change.published_on, writer))
    if change.key_date is not None:
        writer.say("key_date", label=change.key_date_label or writer.texts["key_date_default"], value=change.key_date.isoformat())
    writer.say("source", label=change.source_label, url=change.source_url)
    stage = writer.word(case.status)
    if case.sub_status is None:
        writer.say("stage", value=stage)
    else:
        writer.say("stage_detail", value=stage, detail=label_for(case.sub_status, order))
    urgency = label_for(case.urgency, order)
    writer.say("urgency" if case.urgency_confirmed else "urgency_suggested", value=urgency)
    if case.owner is not None:
        writer.say("owner", name=case.owner.name)
    if case.triaged_at is not None:
        writer.say("triaged", name=writer.name(case.triaged_by), at=writer.at(case.triaged_at))


def _so_what(writer: _Writer, case: ChangeCase) -> None:
    writer.section("so_what")
    if not case.so_what_text:
        writer.say("so_what_none")
        return
    writer.lines.append(case.so_what_text)
    if case.so_what_confirmed and case.so_what_confirmed_at is not None:
        writer.say("so_what_confirmed", name=writer.name(case.so_what_confirmed_by), at=writer.at(case.so_what_confirmed_at))
    else:
        writer.say("so_what_draft")


def _assessment(writer: _Writer, case: ChangeCase, order: list[str]) -> None:
    writer.section("assessment")
    assessment = (
        ImpactAssessment.objects.select_related("saved_by", "effort")
        .filter(case=case, saved=True)
        .first()  # ordering: one per case
    )
    if assessment is None or assessment.saved_at is None:
        writer.say("assessment_none")
        return
    writer.say("applies", value=writer.word(assessment.applies))
    writer.say("why", value=assessment.why)
    writer.say("what_must_change", value=assessment.what_must_change or writer.texts["none"])
    writer.say("deadline", value=_day(assessment.internal_deadline, writer))
    writer.say("effort", value=writer.texts["none"] if assessment.effort is None else label_for(assessment.effort, order))
    writer.say("assessment_saved", name=writer.name(assessment.saved_by), at=writer.at(assessment.saved_at))


def _actions(writer: _Writer, case: ChangeCase) -> None:
    writer.section("actions")
    actions = list(Action.objects.select_related("owner", "done_by", "removed_by").filter(case=case))
    if not actions:
        writer.say("actions_none")
    for action in actions:
        writer.say("action_line", title=action.title)
        writer.say("action_owner", name=action.owner.name, due=action.due_date.isoformat())
        if action.done_at is not None:
            writer.say("action_done", name=writer.name(action.done_by), at=writer.at(action.done_at))
        else:
            writer.say("action_open")
        if action.removed_at is not None:
            writer.say("action_removed", name=writer.name(action.removed_by), at=writer.at(action.removed_at))


def _evidence(writer: _Writer, case: ChangeCase) -> None:
    writer.section("evidence")
    pieces = list(Evidence.objects.select_related("uploaded_by").filter(case=case).order_by("uploaded_at", "id"))
    if not pieces:
        writer.say("evidence_none")
    for piece in pieces:
        writer.say("evidence_line", name=piece.name, kind=writer.word(piece.kind))
        writer.say("evidence_added", name=writer.name(piece.uploaded_by), at=writer.at(piece.uploaded_at))
        if piece.content_hash:
            writer.say("evidence_hash", value=piece.content_hash)
        if piece.url:
            writer.say("evidence_url", value=piece.url)
        if piece.kind == EvidenceKind.FILE.value:
            scan = writer.word(piece.scan_state)
            if piece.scanned_at is None:
                writer.say("evidence_scan", value=scan)
            else:
                writer.say("evidence_scan_at", value=scan, at=writer.at(piece.scanned_at))
        if piece.removed_at is not None:
            writer.say("evidence_removed", at=writer.at(piece.removed_at))


def _signoff(writer: _Writer, case: ChangeCase, tenant: Tenant) -> None:
    writer.section("signoff")
    if case.signoff_requested_at is None:
        writer.say("signoff_none")
        return
    writer.say("signoff_requested", name=writer.name(case.signoff_requested_by), at=writer.at(case.signoff_requested_at))
    if case.signed_off_by is None or case.closed_at is None:
        return
    writer.say("signoff_by", name=case.signed_off_by.name, at=writer.at(case.closed_at))
    # The approval's audit row names the passkey assertion that confirmed it (ID-06).
    step_up = (
        AuditEvent.objects.filter(
            tenant=tenant, subject_type=logic.SUBJECT_TYPE, subject_id=case.id, step_up_assertion_id__isnull=False
        )
        .order_by("-created", "-id")
        .values_list("step_up_assertion_id", flat=True)
        .first()
    )
    if step_up is not None:
        writer.say("signoff_step_up", value=str(step_up))


def _outcome(writer: _Writer, case: ChangeCase, order: list[str]) -> None:
    writer.section("outcome")
    if case.dismissed_reason is not None and case.dismissed_at is not None and case.status == CaseStatusCategory.DISMISSED.value:
        writer.say(
            "dismissed",
            name=writer.name(case.dismissed_by),
            at=writer.at(case.dismissed_at),
            reason=label_for(case.dismissed_reason, order),
        )
    elif case.closed_at is not None and case.status == CaseStatusCategory.CLOSED.value:
        reason = writer.texts["none"] if case.close_reason is None else label_for(case.close_reason, order)
        writer.say("closed", at=writer.at(case.closed_at), reason=reason)
        if case.closed_note:
            writer.say("closed_note", value=case.closed_note)
    else:
        writer.say("open")


def _history(writer: _Writer, case: ChangeCase) -> None:
    writer.section("history")
    for move in CaseTransition.objects.select_related("by_user").filter(case=case):
        if move.from_status:
            writer.say(
                "move",
                at=writer.at(move.at),
                from_stage=writer.word(move.from_status),
                to_stage=writer.word(move.to_status),
                name=writer.name(move.by_user),
            )
        else:
            writer.say("move_first", at=writer.at(move.at), to_stage=writer.word(move.to_status))
        if move.note:
            writer.say("move_note", value=move.note)
