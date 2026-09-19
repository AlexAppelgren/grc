"""The tier-one allowlist: enums that are kinds (playbook 15, INPUT_DELTAS §1).

An enum in code is a kind: a thing the rules branch on, owned by engineering through a
PRD bump. Everything an admin might add, rename or retire is a vocabulary row. The
"kinds only" guard (apps/shared/tests_kinds_only.py) and scripts/compliance_check.py
both read this file: every `TextChoices`, `IntegerChoices`, `Enum` or Postgres enum
under apps/ must have its class name here, with the delta name it implements and a
reason. Adding a name here is a code review question, not a formality.

This module is plain Python on purpose: the compliance lint imports it without Django.
"""

from __future__ import annotations

# class name -> (INPUT_DELTAS §1 name, why it is a kind and not a row)
TIER_ONE_KINDS: dict[str, tuple[str, str]] = {
    "ActorType": (
        "actor_type",
        "AUD-01: the audit log branches on user, agent or system; an admin never adds one",
    ),
    "OriginType": ("origin_type", "Where a record came from; the rules branch on it"),
    "RunStatus": ("run_status", "Agent run lifecycle; the scheduler branches on it"),
    "JobStatus": ("job_status", "Background job lifecycle"),
    "CheckStatus": ("check_status", "Source check outcome; coverage reports branch on it"),
    "ProposalKind": ("proposal_kind", "PRO-01: what a proposal changes; apply() branches on it"),
    "ProposalStatus": ("proposal_status", "PRO-02: the queue's state machine"),
    "ApprovalStatus": ("approval_status", "Four-eyes request lifecycle"),
    "Applicability": ("applicability", "REG-01: applies / does not apply / unknown"),
    "AssessmentApplies": ("assessment_applies", "CAS-03: the assessment's verdict"),
    "CloseReason": ("close_reason", "CAS-02: dismissal vs completion; restorable or not"),
    "EvidenceKind": ("evidence_kind", "CAS-05: file, link or reference; storage branches"),
    "SubjectType": ("subject_type", "What an audit event or comment points at"),
    "SearchSource": ("search_source", "SRC-02: keyword, vector or fused match kind"),
    "AiPurpose": ("ai_purpose", "AUD-02: what a model call was for"),
    "AiStatus": ("ai_status", "AUD-02: review state of AI output"),
    "ReportStatus": ("report_status", "AUD-03: problem report lifecycle"),
    "ExportKind": ("export_kind", "REP-02: what an export contains"),
    "ImportKind": ("import_kind", "REP-03: what an import contains"),
    "DatePrecision": ("date_precision", "Legal dates carry day, month, quarter or year"),
    "RecordStatus": ("record_status", "Library record lifecycle"),
    "ChangeStatus": ("change_status", "WAT-02: a reform's lifecycle stage"),
    "FeedFilter": ("feed_filter", "FP-03: inside or outside the footprint"),
    "TicketProvider": ("ticket_provider", "INT-02: the integration branches per provider"),
    "AgentKind": ("agent_kind", "AGT-03: what an agent definition does"),
    "CaseStatusCategory": (
        "case_status",
        "CAS-02..08: the fixed categories the state machine and its guards read (D-13)",
    ),
    "PillTone": ("pill_tone", "NFR-03: six tones, chosen by slot or kind, never by a person"),
    "PrincipalKind": (
        "principal_kind",
        "Playbook 4.2: user, agent or enrolment session; the auth classes branch on it",
    ),
    "UngatedReason": (
        "ungated_reason",
        "Playbook 5: the five shapes a route may give for having no permission gate",
    ),
}
