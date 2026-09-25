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
    "FeedFilter": (
        "feed_filter",
        "HOM-03: which kinds of dated item the roadmap read includes - all, regulatory or "
        "internal - and the roadmap query branches on it. Corrected twice on 2026-09-21: it "
        "was recorded as FP-03's inside-or-outside-the-footprint, which it never was "
        "(schema.sql line 61), and then as the calendar subscription's scope as well, which "
        "D-52 and ADR 0045 removed - a calendar feed carries the dates the outside world set "
        "and never the bank's own, so it has nothing left to choose between",
    ),
    "TicketProvider": ("ticket_provider", "INT-02: the integration branches per provider"),
    "AgentKind": (
        "agent_kind",
        "AGT-03: what an agent definition does. `watch` sweeps sources and proposes; "
        "`review` (D-62, D-80) proposes nothing and decides what another definition "
        "proposed, so a definition's kind says which side of four eyes it works on",
    ),
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
        "FP-01, D-36: a scope dimension may restrict the footprint, a classification never does, and an "
        "opt-in dimension (standards) matches only the terms the footprint names; matching branches on it",
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
        "I18N-01, INV-01, INV-08, D-38: supranational, country or international (a standards "
        "body); instrument relations (implements) branch on it, and only supranational and "
        "country rows are mirrored into the footprint's jurisdiction dimension",
    ),
    "InstrumentLevelKind": (
        "instrument_level_kind",
        "INV-01, INV-08, D-37: the one optional value, standard, is what tells a pill to "
        "read Standard rather than Binding or Guidance, comply or explain, and what the "
        "provision triggers refuse a provision under; the five other levels stay kindless "
        "and no admin may add a second value",
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
    "EvalVia": (
        "eval_via",
        "SRC-05, SRC-S12: an evaluation question is scored on search's hits or on Ask's passages; "
        "the gate's scorer branches on it, and the file names it in `via`",
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
    # Chunk 6 (home, the briefing, the roadmap and the calendar feed). Both live as literals
    # in apps/home/schemas.py, because the roadmap is computed and has no table of its own;
    # they are declared here because they are kinds the code branches on, and an engineer
    # looking for the list of kinds must find them where every other one is written down.
    "RoadmapItemKind": (
        "roadmap_item_kind",
        "HOM-03: a roadmap item is about a date the outside world set or one this bank set; "
        "the card picks an urgency pill for the first and 'Our deadline' for the second",
    ),
    "RoadmapItemType": (
        "roadmap_item_type",
        "HOM-03, HOM-04: what produced the date - a change's key date, an internal deadline, "
        "an action due or a review due; the card and the calendar builder branch on it",
    ),
    # Chunk 8 organisation and chunk 11 security policy (c8-org-models, tenants 0002).
    "OrgUnitKind": (
        "org_unit_kind",
        "TEN-02, D-21: a group, legal entity, business area, business unit or function; only a legal "
        "entity holds licences and the legal-entity term, and a department is a unit of the last three kinds",
    ),
    "ProductStatusKind": (
        "product_status",
        "TEN-02: planned, live or retired; retired is how a product is withdrawn, never deleted, and "
        "scope and agent-access narrowing (D-70) branch on it, so it is a kind and not a tenant list",
    ),
    "CredentialPolicyKind": (
        "credential_policy",
        "ID-07, ADR 0048: any passkey or device-bound only; sign-in and enrolment branch on it",
    ),
    # Chunk 8's register lists (c8-vocab-lists-rules). Categories the rules read off a
    # tenant row's fixed `kind`; the tenant's labels, order and extra rows stay its own.
    "GapCategory": (
        "gap_category",
        "REG-03, VOC-04: open, remediating, risk accepted or closed; the gap workflow, the reports and the pill tone read the category, never the tenant's label",
    ),
    "RiskLevel": (
        "risk_level",
        "VOC-05: low, medium or high; the pill tone reads the level a risk rating maps to, never its editable ordinal or its label",
    ),
    # Chunk 8's register (c8-register-models, register 0001). `Applicability` is listed above.
    "AssessmentMethod": (
        "assessment_method",
        "REG-04: self-assessment, second-line review, internal audit, external audit or regulator "
        "(schema.sql); an audit result is an assessment of the two audit methods, which the standards "
        "reporting branches on",
    ),
    # c8-duty-occurrences (register 0004, REG-07).
    "DutyStatus": (
        "duty_status",
        "REG-07: where a dated duty occurrence stands; completion, the roadmap and Today branch on it",
    ),
}
