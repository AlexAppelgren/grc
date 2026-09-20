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
    "SearchSource": (
        "search_source",
        "SRC-01: which library record a search chunk was built from; the rebuild and the "
        "retrieval query both branch on it",
    ),
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
    "CaseLinkDecision": (
        "case_link_decision",
        "WAT-04: what a bank said about a suggested obligation link on its own case; the "
        "change page branches on accepted or removed and there is no third answer",
    ),
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
    # Chunk 1 (identity and tenant admin basics). Each is something the rules branch on.
    "TenantStatus": ("tenant_status", "TEN-01: active or deactivated; every request branches on it"),
    "UserStatus": ("user_status", "ID-02, ID-03: invited, active or deactivated; sign-in branches on it"),
    "InvitationKind": ("invitation_kind", "ID-01, ID-05: invite or re-enrolment; acceptance branches on it"),
    "ChallengeKind": ("challenge_kind", "ID-02, ID-06: registration, authentication or step-up ceremony"),
    "PasskeyDeviceType": ("credential_device_type", "ID-07: single-device or multi-device (synced); policy branches on it"),
    "SessionKind": ("session_kind", "ID-02, AC-ID2: enrolment or full; the auth classes branch on it"),
    "LoginMethod": ("login_method", "ID-11, INPUT_DELTAS §2: email_code, passkey, api_key (later oidc, saml)"),
    "LoginEventKind": ("login_event", "ID-11: what the security log records; the log is a ledger, not a picker"),
    "SupportAccessLevel": ("support_access_level", "ID-05, TEN-06: read or write support access"),
    # Chunk 2 (vocabularies, taxonomy and footprint). Each is a category the rules read
    # off a vocabulary row's fixed `kind`; the row's label, translations and usage note
    # stay an admin's to change (playbook 15, INPUT_DELTAS §1).
    "TermDimensionKind": (
        "term_dimension_kind",
        "FP-01: a scope dimension may restrict the footprint, a classification never does; matching branches on it",
    ),
    "ChangeLifecycleKind": (
        "change_lifecycle_kind",
        "WAT-02, HOM-03: pre-adoption, adopted, in force, supervisory or recurring; the feed and roadmap branch on it",
    ),
    "ProvisionStructuralKind": (
        "provision_structural_kind",
        "INV-02: a division groups provisions, a unit carries legal text, an annex hangs off the instrument; the tree and search chunks branch on it",
    ),
    "ComplianceCategory": (
        "compliance_category",
        "REG-02, VOC-05: compliant, partly, gap or not assessed; reports and the pill tone read the category, never the tenant's label",
    ),
    "JurisdictionKind": (
        "jurisdiction_kind",
        "I18N-01, INV-01: supranational or country; instrument relations (implements) branch on it",
    ),
    "FootprintAction": (
        "footprint_action",
        "FP-02: a history row records a term added or removed; the as-of reconstruction branches on it",
    ),
    "SuggestionStatus": (
        "suggestion_status",
        "VOC-03: a member's suggestion is pending, accepted (the row was created) or declined; the admin's inbox branches on it",
    ),
    # Chunk 7 (search and ask). The API's own kinds: what a hit points at, how it was
    # matched, and what a reader said about an answer. Each has its own delta name;
    # `search_source` above stays the chunk table's own column, which the index owns.
    "SearchHitType": (
        "search_hit_type",
        "SRC-01: a hit is an obligation, a provision or a change; the screen and the ranking branch on it",
    ),
    "SearchMatchKind": (
        "search_match_kind",
        "SRC-02: keyword, concept or both; every hit says how it was won and the pill's tone follows it",
    ),
    "AnswerFeedbackKind": (
        "answer_feedback",
        "SRC-03, SRC-05: helpful or wrong; the evaluation set reads the verdict back",
    ),
    # Chunk 3 (library and inventory).
    "VerificationOutcome": (
        "verification_outcome",
        "INV-06: a re-verification found no change, found a change (a proposal follows) or could not reach the source; the re-verify queue branches on it",
    ),
    # Chunk 5 (watch). `check_status`, `change_status` and `feed_filter` were already
    # allowlisted above; these two are the build's own, recorded in INPUT_DELTAS §1.
    "SourceCheckKind": (
        "source_check_kind",
        "WAT-01, AGT-01: a sweep for new documents or a re-check of one library record; the check names a subject only when it is a re-check",
    ),
    "CheckFrequency": (
        "check_frequency",
        "WAT-01: how often a source is checked; the scheduler and the stale rule branch on it, and no admin adds a cadence",
    ),
}
