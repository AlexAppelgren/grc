"""The tenant-creation hook of chunk 2: `ensure_tenant_vocabularies(tenant, actor=...)` seeds the
system rows of every tier-3 list for one tenant (VOC-01, VOC-04, VOC-05, VOC-06),
idempotently, matched on the immutable key. Everything a tenant can change is written
once, when the hook creates the row: its labels, usage note, sort order, active flag,
default and extra columns. `seed_reference` runs this for every tenant on every deploy, so
re-applying those would silently undo a tenant's reorder, retire or default change. The
`kind` is the exception: no route lets a tenant change it, the case state machine needs a
system row per category, so the code's kind is put back on every run. Every row created
and every kind put back leaves one audit row, and the caller says whose work it is.

A key the tenant already used for a value of its own stops the seed rather than being
adopted: the row would keep the tenant's meaning while the list lost its system value.

Call it, with the tenant activated, wherever a tenant comes into being: the E2E seed
(apps/shared/e2e_seed.py), `seed_reference` for every existing tenant, the test factory
(apps/shared/factories.py) and the console's tenant creation when it lands (TEN-02).
The vocabulary-integrity guard demands a default and a system row per kind for every
list; a tenant without these rows has empty pickers and a case state machine with no
status to start in."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError

from apps.shared.audit import Actor, record
from apps.shared.models import Tenant
from apps.taxonomy.models import CaseStatusCategory, CloseReason, ComplianceCategory, GapCategory, RiskLevel
from apps.taxonomy.registry import REGISTRY, TENANT_LISTS
from apps.taxonomy.seeds import fixture

ORIGINAL_LANGUAGE = "en"
SUBJECT_TYPE = "vocabulary"


@dataclass(frozen=True)
class SystemRow:
    key: str
    labels: dict[str, str]
    usage_note: str = ""
    kind: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _fixture_rows(list_name: str, *, kinds: dict[str, str] | None = None, extra_fields: tuple[str, ...] = ()) -> list[SystemRow]:
    rows = []
    for key, row in fixture.vocabulary(list_name).items():
        rows.append(
            SystemRow(
                key=key,
                labels=fixture.labels_of(row),
                usage_note=row.get("usage_note", ""),
                kind=(kinds or {}).get(key, row.get("kind")),
                extra={name: row[name] for name in extra_fields if name in row},
            )
        )
    return rows


# The fixture's compliance keys carry their category as the kind (VOC-05); its labels
# are the prototype's. `partly_compliant` maps to the category `partly`.
_COMPLIANCE_KINDS = {
    "compliant": ComplianceCategory.COMPLIANT.value,
    "partly_compliant": ComplianceCategory.PARTLY.value,
    "gap": ComplianceCategory.GAP.value,
    "not_assessed": ComplianceCategory.NOT_ASSESSED.value,
}

# The fixture's risk ratings carry no kind; each maps to the level of its own key (VOC-05).
_RISK_LEVELS = {level.value: level.value for level in RiskLevel}

# list name -> (default key, system rows). Prototype lists come from the fixture; the
# lists the prototype has no screen for are authored here with the pills card's phrases.
TENANT_SYSTEM_ROWS: dict[str, tuple[str, list[SystemRow]]] = {
    "tenant_tag": (
        "follow_up",
        [SystemRow("follow_up", {"en": "Follow up", "sv": "Följ upp"}, "A marker for records someone must come back to. Relabel it; it is the list's default.")],
    ),
    "link_kind": ("policy", _fixture_rows("link_kind")),
    "effort_size": (
        "m",
        [
            SystemRow("s", {"en": "S", "sv": "S"}, "Days of work."),
            SystemRow("m", {"en": "M", "sv": "M"}, "Weeks of work."),
            SystemRow("l", {"en": "L", "sv": "L"}, "Months of work, or a project."),
        ],
    ),
    "compliance_status": ("not_assessed", _fixture_rows("compliance_status", kinds=_COMPLIANCE_KINDS, extra_fields=("ordinal",))),
    "risk_rating": ("low", _fixture_rows("risk_rating", kinds=_RISK_LEVELS, extra_fields=("ordinal",))),
    "case_sub_status": (
        CaseStatusCategory.NEW.value,
        [
            SystemRow("new", {"en": "Needs triage", "sv": "Behöver prioriteras"}, "Registered by an agent, nobody has looked yet.", CaseStatusCategory.NEW.value),
            SystemRow("assigned", {"en": "Assigned", "sv": "Tilldelad"}, "Triaged with an urgency and an owner.", CaseStatusCategory.ASSIGNED.value),
            SystemRow("assessing", {"en": "Assessing", "sv": "Bedöms"}, "The owner is working out what it means for us.", CaseStatusCategory.ASSESSING.value),
            SystemRow("implementing", {"en": "Implementing", "sv": "Genomförs"}, "Actions are open.", CaseStatusCategory.IMPLEMENTING.value),
            SystemRow("signoff", {"en": "Waiting for sign-off", "sv": "Väntar på godkännande"}, "Every action done, evidence attached, a second person asked.", CaseStatusCategory.SIGNOFF.value),
            SystemRow("closed", {"en": "Closed", "sv": "Stängd"}, "Signed off, or closed without action with a reason.", CaseStatusCategory.CLOSED.value),
            SystemRow("dismissed", {"en": "Dismissed", "sv": "Avfärdad"}, "Not for us, with a reason. Can be restored.", CaseStatusCategory.DISMISSED.value),
        ],
    ),
    "dismissal_reason": (
        "out_of_scope",
        [
            SystemRow("out_of_scope", {"en": "Out of scope", "sv": "Utanför vår verksamhet"}, "The change does not touch anything we do."),
            SystemRow("duplicate", {"en": "Duplicate", "sv": "Dubblett"}, "Already handled in another case."),
            SystemRow("already_covered", {"en": "Already covered", "sv": "Redan hanterat"}, "Our existing controls already meet it."),
        ],
    ),
    "close_reason": (
        CloseReason.SIGNED_OFF.value,
        [
            SystemRow("signed_off", {"en": "Signed off", "sv": "Godkänd"}, "The work was done and a second person confirmed it.", CloseReason.SIGNED_OFF.value),
            SystemRow("not_applicable", {"en": "Not applicable", "sv": "Ej tillämplig"}, "Assessed and found not to apply to us.", CloseReason.NOT_APPLICABLE.value),
            SystemRow("no_action", {"en": "No action needed", "sv": "Ingen åtgärd"}, "Applies, but nothing has to change.", CloseReason.NO_ACTION.value),
        ],
    ),
    "gap_status": (
        GapCategory.OPEN.value,
        [
            SystemRow("open", {"en": "Open", "sv": "Öppen"}, "Found and not yet being fixed.", GapCategory.OPEN.value),
            SystemRow("remediating", {"en": "Remediating", "sv": "Åtgärdas"}, "Someone is closing it to a plan and a date.", GapCategory.REMEDIATING.value),
            SystemRow("risk_accepted", {"en": "Risk accepted", "sv": "Risk accepterad"}, "Left open on purpose, with a reason and a person who decided.", GapCategory.RISK_ACCEPTED.value),
            SystemRow("closed", {"en": "Closed", "sv": "Stängd"}, "Fixed, and the fix is shown.", GapCategory.CLOSED.value),
        ],
    ),
    "gap_source": (
        "assessment",
        [
            SystemRow("assessment", {"en": "Assessment", "sv": "Bedömning"}, "Found when the obligation's compliance was assessed."),
            SystemRow("change_case", {"en": "Change case", "sv": "Ändringsärende"}, "Found while working a regulatory change."),
            SystemRow("audit", {"en": "Audit", "sv": "Revision"}, "Raised by an internal or external audit."),
            SystemRow("incident", {"en": "Incident", "sv": "Incident"}, "Revealed by something that went wrong."),
            SystemRow("regulator", {"en": "Regulator", "sv": "Tillsynsmyndighet"}, "Pointed out by a supervisory authority."),
        ],
    ),
    "risk_acceptance_reason": (
        "accepted_by_management",
        [
            SystemRow("accepted_by_management", {"en": "Accepted by management", "sv": "Accepterad av ledningen"}, "Management decided to carry the risk."),
            SystemRow("cost_disproportionate", {"en": "Cost disproportionate", "sv": "Oproportionerlig kostnad"}, "Closing the gap would cost more than the risk it removes."),
            SystemRow("compensating_control", {"en": "Compensating control", "sv": "Kompenserande kontroll"}, "Another control covers the risk."),
            SystemRow("time_limited", {"en": "Time limited", "sv": "Tidsbegränsad"}, "Accepted until a set date, then looked at again."),
            SystemRow("other", {"en": "Other", "sv": "Annat"}, "Say why in the note."),
        ],
    ),
    "team": (
        "compliance",
        [SystemRow("compliance", {"en": "Compliance", "sv": "Compliance"}, "The compliance function. Relabel it and add the organisation's own teams beside it.")],
    ),
}


def ensure_tenant_vocabularies(tenant: Tenant, *, actor: Actor) -> int:
    """Create the system rows of every tenant list this tenant does not have yet, and put
    back a system row's kind. `actor` is whoever is seeding: the deploy's `seed_reference`,
    the E2E seed, the test factory or, later, the console creating the tenant. Must run
    with the tenant activated, inside a transaction. Returns the number of rows ensured."""
    count = 0
    for list_name in TENANT_LISTS:
        entry = REGISTRY[list_name]
        default_key, rows = TENANT_SYSTEM_ROWS[list_name]
        for sort_order, spec in enumerate(rows):
            defaults: dict[str, Any] = {
                "kind": spec.kind,
                "is_system": True,
                "active": True,
                "sort_order": sort_order,
                "is_default": spec.key == default_key,
                "usage_note": spec.usage_note,
                **spec.extra,
            }
            row, created = entry.model._default_manager.get_or_create(tenant=tenant, key=spec.key, defaults=defaults)
            if created:
                for language, text in spec.labels.items():
                    entry.label_model._default_manager.create(
                        tenant=tenant, vocabulary=row, language=language, text=text, is_original=language == ORIGINAL_LANGUAGE
                    )
                record(
                    action="vocabulary.created",
                    actor=actor,
                    subject_type=SUBJECT_TYPE,
                    subject_id=row.id,
                    subject_title=f"{list_name}:{spec.key}",
                    summary=f"Added {spec.key} to {list_name} from the reference seed.",
                    tenant_id=tenant.id,
                    after={"list": list_name, "key": spec.key, "labels": spec.labels, "kind": spec.kind},
                )
            elif not row.is_system:
                raise ValidationError(
                    f"{list_name}:{spec.key} is already one of this organisation's own values, so the "
                    f"system value cannot be added. Give that value another key first (tenant {tenant.id}).",
                    code="system_key_taken",
                )
            elif row.kind != spec.kind:
                before = row.kind
                row.kind = spec.kind
                row.version += 1
                row.save(update_fields=["kind", "version"])
                record(
                    action="vocabulary.updated",
                    actor=actor,
                    subject_type=SUBJECT_TYPE,
                    subject_id=row.id,
                    subject_title=f"{list_name}:{spec.key}",
                    summary=f"Put the kind of {spec.key} on {list_name} back.",
                    tenant_id=tenant.id,
                    before={"kind": before},
                    after={"kind": spec.kind},
                )
            count += 1
    return count
