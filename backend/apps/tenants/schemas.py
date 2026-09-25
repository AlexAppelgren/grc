"""Request and response schemas of the tenants app (TEN-01, ID-05 console): camelCase
through CamelSchema.

Everything here is one bank's own identity and settings. It lives in that bank's zone and
no other bank ever reads it; the platform console reads the tenant row itself — name,
short name, status, language, creation date — and nothing underneath it, which is why the
console has a row schema of its own rather than reusing `TenantOut`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import ConfigDict, Field, JsonValue

from apps.identity.schemas import RoleRef
from apps.shared.models import (
    ESCALATE_AFTER_DAYS_MAX,
    LEAD_DAYS_MAX,
    LEAD_DAYS_MAX_ENTRIES,
    TRIAGE_TARGET_HOURS_MAX,
)
from apps.shared.schemas import CamelSchema, WriteBody

__all__ = ["CamelSchema"]

# The examples are the prototype's bank (`design/prototype/index.html`, seeded as tenant A
# for the journeys) and the second Nordic bank beside it. Never a real customer.
_EXAMPLE_LANGUAGE_SV: dict[str, JsonValue] = {"key": "sv", "kind": None, "label": "Svenska"}
_EXAMPLE_LANGUAGE_EN: dict[str, JsonValue] = {"key": "en", "kind": None, "label": "English"}
_EXAMPLE_LANGUAGE_DA: dict[str, JsonValue] = {"key": "da", "kind": None, "label": "Dansk"}
_EXAMPLE_WORKFLOW: dict[str, JsonValue] = {
    "reminderDaysBefore": [7, 3],
    "reviewReminderDaysBefore": [30],
    "escalateAfterDays": 5,
    "escalateToRole": {"key": "compliance_officer", "kind": None, "label": "Compliance officer"},
    "digestWeekday": "monday",
    "triageTargetHours": 48,
}

_WEEKDAYS_IN_WORDS = (
    "one of the seven days in lower case: `monday`, `tuesday`, `wednesday`, `thursday`, "
    "`friday`, `saturday` or `sunday`"
)


class OnboardingStep(CamelSchema):
    """One line of the bank's first-run checklist: which step, and whether it is done."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"key": "footprint", "done": True}]})

    key: str = Field(
        description=(
            "Which first-run step this line is about. Five, fixed in code and safe to match "
            "on: `profile` (the bank has a name, a timezone and content languages), `members` "
            "(somebody else has been invited, or there is more than one member), `footprint` "
            "(the markets, entities and services the bank operates in have been chosen), "
            "`vocabularies` (the bank's own lists have been reviewed, which reads false for "
            "everyone until the screen that reviews them ships) and `passkey` (an "
            "administrator has enrolled a passkey of their own)."
        )
    )
    done: bool = Field(
        description=(
            "Whether that step is finished. The server works it out from the records "
            "themselves each time the profile is read, so there is no call that marks a step "
            "done and no way to fake one. A finished step can still be revisited: true means "
            "the bank has done the work once, not that the setting is now locked."
        )
    )


class Onboarding(CamelSchema):
    """How far the bank has got through first-run setup, recomputed on every read."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "stepsDone": 3,
                    "steps": [
                        {"key": "profile", "done": True},
                        {"key": "members", "done": True},
                        {"key": "footprint", "done": True},
                        {"key": "vocabularies", "done": False},
                        {"key": "passkey", "done": False},
                    ],
                }
            ]
        }
    )

    steps_done: int = Field(
        description=(
            "How many of the five first-run steps are finished, so a screen can show progress "
            "without counting the list itself. It is a number of steps and not a percentage, "
            "and it never exceeds the length of `steps`. Computed by the server."
        )
    )
    steps: list[OnboardingStep] = Field(
        description=(
            "The five first-run steps in the order the setup screen walks through them, each "
            "with its key and whether it is done. Computed by the server from the bank's own "
            "records on every read, never stored and never sent in. Read it as a to-do list "
            "for the bank's administrator and never as a gate: nothing in the product is "
            "withheld because a step is unfinished."
        )
    )


class TenantWorkflow(CamelSchema):
    """The bank's workflow policy: when its members are reminded, when overdue work
    escalates and to whom, the day the digest goes out and how quickly a new change should
    be triaged. Every bank starts at the platform defaults and changes its own through
    `PATCH /tenant/workflow`."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_WORKFLOW]})

    reminder_days_before: list[int] = Field(
        description=(
            f"How many days before a due date the owner of an open action or case is reminded, "
            f"one reminder per entry, largest first — `[7, 3]` reminds a week ahead and again "
            f"three days ahead. One to {LEAD_DAYS_MAX_ENTRIES} entries, each a whole number of "
            f"days from 1 to {LEAD_DAYS_MAX}, counted in the bank's own timezone. The platform "
            "default is `[3]`."
        )
    )
    review_reminder_days_before: list[int] = Field(
        description=(
            f"How many days before a scheduled review the owner of the record under review is "
            f"reminded, largest first. One to {LEAD_DAYS_MAX_ENTRIES} entries, each a whole "
            f"number of days from 1 to {LEAD_DAYS_MAX}. The platform default is `[30]`."
        )
    )
    escalate_after_days: int = Field(
        description=(
            f"How many whole days a piece of work may be overdue before it escalates, from 1 to "
            f"{ESCALATE_AFTER_DAYS_MAX}. It escalates once, to the members holding "
            "`escalateToRole`. The platform default is 5."
        )
    )
    escalate_to_role: RoleRef = Field(
        description=(
            "The role of this bank whose members are told when overdue work escalates, as key, "
            "kind and label; the key is what `PATCH /tenant/workflow` takes. Roles are rows of "
            "the bank's role vocabulary: the seeded `admin`, `compliance_officer` (the platform "
            "default), `owner`, `approver`, `contributor`, `reader` and `auditor`, plus any role "
            "an admin may extend it with in the role editor (`GET /tenant/roles` lists the live "
            "set), so an unfamiliar key is new data and not an error. It names a role and never "
            "a person, so the escalation survives a member leaving."
        )
    )
    digest_weekday: str = Field(
        description=(
            f"The day of the week the bank's digest goes out, in the bank's own timezone: "
            f"{_WEEKDAYS_IN_WORDS}. A fixed set in code rather than a list a bank extends. The "
            "platform default is `monday`."
        )
    )
    triage_target_hours: int = Field(
        description=(
            f"How many hours a new change may wait before somebody at the bank has triaged it, "
            f"from 1 to {TRIAGE_TARGET_HOURS_MAX} (thirty days). A case's triage due time is "
            "counted from it. The platform default is 48."
        )
    )


class TenantOut(CamelSchema):
    """The bank's own profile, as a member of that bank reads it."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "00000000-0000-4000-8000-00000000000a",
                    "name": "Example Bank AB",
                    "slug": "example-bank",
                    "timezone": "Europe/Stockholm",
                    "status": "active",
                    "defaultLanguage": _EXAMPLE_LANGUAGE_SV,
                    "contentLanguages": [_EXAMPLE_LANGUAGE_SV, _EXAMPLE_LANGUAGE_EN],
                    "aiEnabled": True,
                    "workflow": _EXAMPLE_WORKFLOW,
                    "workflowDefaults": {**_EXAMPLE_WORKFLOW, "reminderDaysBefore": [3], "escalateAfterDays": 5},
                    "onboarding": {
                        "stepsDone": 3,
                        "steps": [
                            {"key": "profile", "done": True},
                            {"key": "members", "done": True},
                            {"key": "footprint", "done": True},
                            {"key": "vocabularies", "done": False},
                            {"key": "passkey", "done": False},
                        ],
                    },
                }
            ]
        }
    )

    id: uuid.UUID = Field(
        description=(
            "The bank's permanent identifier, a UUID issued once when the organisation was "
            "created and never reissued. Key your own records on it: the short name in `slug` "
            "is for people to read, while this is the value every call that names a bank takes."
        )
    )
    name: str = Field(
        description=(
            "The bank's own name for itself, as it appears on its screens and its exports — "
            "'Example Bank AB'. It is the bank's judgement in the bank's own zone, an "
            "administrator may reword it at any time, and it is not a legal-register entry "
            "and not an identifier."
        )
    )
    slug: str = Field(
        description=(
            "The bank's short name — lower-case letters, digits and hyphens, at most 80 "
            "characters, such as `example-bank`. Nobody types it: it was derived from the "
            "organisation's name when the organisation was created, with letters such as ø and "
            "æ spelled out and a numeric suffix when another bank already had it. It is unique "
            "across the platform and fixed from then on, even when the name is reworded. "
            "Support staff use it to name the organisation in a conversation; it never appears "
            "in a URL and no call takes it. This call cannot change it."
        )
    )
    timezone: str = Field(
        description=(
            "The IANA timezone the bank works in, such as `Europe/Stockholm`. It is what "
            "turns a stored UTC instant into the local day a deadline is counted in and a "
            "screen is grouped by. It belongs to the organisation and not to a person: a "
            "member reading from another country still sees the bank's day."
        )
    )
    status: str = Field(
        description=(
            "Whether the organisation is open for business: `active` means its members can "
            "sign in and work, `deactivated` means the platform has closed it and no session "
            "will open. Platform staff set it; the bank cannot. It says nothing about the "
            "data inside — a deactivated organisation still holds everything it ever had "
            "until a tenant exit has been approved by two people and executed."
        )
    )
    default_language: RoleRef | None = Field(
        description=(
            "The language the bank reads and writes in first: it decides which version of a "
            "library record a reader is shown when they have expressed no preference, and "
            "which language a briefing is written in. A reference to a language row by its "
            "key — `sv`, `en`, `da`, `nb` or `fi` — with a label to show. Languages are "
            "library reference rows, not a vocabulary a bank's admin may extend; read "
            "`GET /reference/languages` for the set on offer. Null only while a brand-new "
            "organisation has not chosen one."
        )
    )
    content_languages: list[RoleRef] = Field(
        description=(
            "Every language this bank keeps content in, in the order its administrators put "
            "them, the default usually first. It decides which translations a reader is "
            "offered and which languages an import or an export covers; it does not limit "
            "what the shared library holds, which stays whole whatever a bank picks here. "
            "Each entry points at a language row by key, and those rows are library reference "
            "data rather than a vocabulary an admin may extend."
        )
    )
    ai_enabled: bool = Field(
        description=(
            "Whether this bank's own AI features are on: `true` means its members may use Ask "
            "and have a model draft text for them, `false` means every such call is refused "
            "with `feature_off` before any model is reached. It starts `true`. Only "
            "`PUT /tenant/ai` changes it, with `security.manage` and a passkey step-up; the "
            "profile edit ignores it. It covers this bank's own features only: the research "
            "agents that keep the shared library current run for every bank and are not "
            "switched here."
        )
    )
    workflow: TenantWorkflow = Field(
        description=(
            "The bank's workflow policy: reminder lead days, when overdue work escalates and "
            "to which role, the digest's weekday and the triage target. Every member may read "
            "it; only `PATCH /tenant/workflow`, with `workflow.manage`, changes it, and the "
            "profile edit ignores it."
        )
    )
    workflow_defaults: TenantWorkflow = Field(
        description=(
            "The platform defaults a bank's workflow policy starts at, in the same shape as "
            "`workflow`, so the bank can see what it is changing from and go back to it. They "
            "are the platform's settings, not the bank's: nothing here changes them, and "
            "changing them later moves no bank's own policy."
        )
    )
    onboarding: Onboarding = Field(
        description=(
            "How far the bank has got through first-run setup, computed by the server on "
            "every read. It is progress through a checklist and nothing more: a complete "
            "onboarding says the bank has configured the product, never that it applies any "
            "obligation to itself and never that it complies with one."
        )
    )


class TenantPatch(CamelSchema):
    """What an administrator may change about their own bank's profile. Send only the
    fields you are changing; an omitted field is left exactly as it was."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"name": "Example Bank AB", "timezone": "Europe/Stockholm", "contentLanguages": ["sv", "en"]}]
        }
    )

    name: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "A new name for the organisation, at most 200 characters. Omit the field to leave "
            "the name alone; sending it blank does not clear it, it is refused with a 422, "
            "because an organisation without a name cannot be told apart in an audit trail."
        ),
    )
    timezone: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "A new IANA timezone for the organisation, such as `Europe/Copenhagen`, at most 64 "
            "characters. Omit the field to leave it alone. The name is checked against the "
            "IANA database the server runs on and an unknown one is refused with `unknown_key`. "
            "Changing it moves the local day every deadline is counted in, so dates already on "
            "screen are re-read in the new zone; the stored instants themselves do not move."
        ),
    )
    default_language: str | None = Field(
        default=None,
        max_length=8,
        description=(
            "The key of the language the bank should read and write in first — `sv`, `en`, "
            "`da`, `nb` or `fi` — at most 8 characters. A key, never a label. Omit the field "
            "to leave it alone; a key that is not an active language row is refused with "
            "`unknown_key`. The languages on offer are library reference rows and not a "
            "vocabulary a bank's admin may extend."
        ),
    )
    content_languages: list[str] | None = Field(
        default=None,
        description=(
            "The complete new list of language keys the bank keeps content in, in the order it "
            "wants them shown. It replaces the current list rather than adding to it, so send "
            "every language you mean to keep, including the default. Omit the field to leave "
            "the list alone; an empty list is refused with a 422, and a key that is not an "
            "active language row is refused with `unknown_key` naming the key. Keys such as "
            "`sv` and `en`, never labels."
        ),
    )


class TenantWorkflowPatch(WriteBody):
    """What a holder of `workflow.manage` may change about the bank's workflow policy. Send
    only the fields you are changing; an omitted field, or one sent as null, is left as it
    was, and a field this schema does not name is refused."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"reminderDaysBefore": [7, 3], "escalateAfterDays": 5, "digestWeekday": "monday"}]}
    )

    reminder_days_before: list[Annotated[int, Field(ge=1, le=LEAD_DAYS_MAX)]] | None = Field(
        default=None,
        min_length=1,
        max_length=LEAD_DAYS_MAX_ENTRIES,
        description=(
            f"The complete new list of days before a due date on which the owner is reminded: "
            f"one to {LEAD_DAYS_MAX_ENTRIES} whole numbers, each from 1 to {LEAD_DAYS_MAX}. It "
            "replaces the current list; a repeated day counts once and the list is stored "
            "largest first. Omit the field to leave it alone; an empty list, a longer one or a "
            "day out of range is refused with `validation_error` naming the field."
        ),
    )
    review_reminder_days_before: list[Annotated[int, Field(ge=1, le=LEAD_DAYS_MAX)]] | None = Field(
        default=None,
        min_length=1,
        max_length=LEAD_DAYS_MAX_ENTRIES,
        description=(
            f"The complete new list of days before a scheduled review on which the owner is "
            f"reminded: one to {LEAD_DAYS_MAX_ENTRIES} whole numbers, each from 1 to "
            f"{LEAD_DAYS_MAX}, stored largest first with repeats counted once. Omit the field "
            "to leave it alone; an empty list, a longer one or a day out of range is refused "
            "with `validation_error` naming the field."
        ),
    )
    escalate_after_days: int | None = Field(
        default=None,
        ge=1,
        le=ESCALATE_AFTER_DAYS_MAX,
        description=(
            f"How many whole days work may be overdue before it escalates, from 1 to "
            f"{ESCALATE_AFTER_DAYS_MAX}. Omit the field to leave it alone; a value out of range "
            "is refused with `validation_error` naming the field."
        ),
    )
    escalate_to_role: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        description=(
            "The key of the role whose members are told when work escalates, such as "
            "`compliance_officer`, at most 80 characters. A key, never a label. It must be an "
            "active role of this bank — read `GET /tenant/roles` for the set; a key that is "
            "not, including a role of another bank or a retired one, is refused with "
            "`unknown_key` naming the field. Omit the field to leave it alone."
        ),
    )
    digest_weekday: str | None = Field(
        default=None,
        min_length=1,
        max_length=16,
        description=(
            f"The day the digest goes out: {_WEEKDAYS_IN_WORDS}, at most 16 characters. Any "
            "other value is refused with `unknown_key` naming the field. Omit the field to "
            "leave it alone."
        ),
    )
    triage_target_hours: int | None = Field(
        default=None,
        ge=1,
        le=TRIAGE_TARGET_HOURS_MAX,
        description=(
            f"How many hours a new change may wait before it is triaged, from 1 to "
            f"{TRIAGE_TARGET_HOURS_MAX}. Omit the field to leave it alone; a value out of range "
            "is refused with `validation_error` naming the field."
        ),
    )


class TenantAiBody(WriteBody):
    """Switch this bank's own AI features on or off. The body holds the one field and
    nothing else; any other field is refused."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"enabled": False}]})

    enabled: bool = Field(
        strict=True,
        description=(
            "`false` switches this bank's AI features off: Ask and the drafts a model writes "
            "for the bank's members answer `feature_off` from then on. `true` switches them "
            "back on. A JSON boolean, never a string. Sending the value the bank already has "
            "changes nothing and is still recorded in the audit log."
        )
    )


class ConsoleReissueBody(CamelSchema):
    """Why platform support is entering a bank to re-issue an administrator's enrolment,
    and how that person was proved to be who they claim. Both answers are written where
    the bank itself can read them."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "reason": (
                        "The bank's only administrator lost the phone holding her passkey and no "
                        "second administrator exists to re-invite her."
                    ),
                    "ticketRef": "SUP-2418",
                    "outOfBandCheck": (
                        "Called back on the switchboard number held on file and confirmed her "
                        "identity with the head of compliance, who knows her by sight."
                    ),
                }
            ]
        }
    )

    reason: str = Field(
        max_length=1000,
        description=(
            "Why this recovery is happening, in the support engineer's own words and at most "
            "1000 characters. It is written into a support-access record in the bank's own "
            "zone, which the bank can read afterwards, so write it for the customer and not "
            "for an internal ticket queue. Blank is refused with a 422."
        ),
    )
    ticket_ref: str = Field(
        default="",
        max_length=100,
        description=(
            "The support ticket this work is being done under, at most 100 characters — "
            "`SUP-2418`. Optional: it defaults to the empty string where there is no ticket, "
            "and leaving it empty is never a reason to leave `reason` or `outOfBandCheck` "
            "thin. It is stored on the support-access record the bank can read."
        ),
    )
    out_of_band_check: str = Field(
        max_length=1000,
        description=(
            "How the person asking was proved to be who they claim, away from this system — "
            "the number that was called back, the document that was checked, the colleague who "
            "vouched for them — at most 1000 characters. This is the whole control behind a "
            "last-administrator recovery, which is why it is required and a blank one is "
            "refused with a 422. It is recorded in the audit event and in the support-access "
            "record the bank can read."
        ),
    )


class ConsoleTenantRow(CamelSchema):
    """One bank as the platform console lists it (ADM-02). No member count and no
    tenant-side content: a platform session reads the tenant row and nothing under it."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "00000000-0000-4000-8000-00000000000b",
                    "name": "Second Bank A/S",
                    "slug": "second-bank",
                    "status": "active",
                    "defaultLanguage": _EXAMPLE_LANGUAGE_DA,
                    "createdAt": "2026-09-20T07:41:12Z",
                }
            ]
        }
    )

    id: uuid.UUID = Field(
        description=(
            "The bank's permanent identifier, a UUID issued once at creation and never "
            "reissued. It is the value the console's other calls carry in their path."
        )
    )
    name: str = Field(
        description=(
            "The organisation's own name for itself, as the bank set it. Platform staff read "
            "it here; they never change it, because the name belongs to the bank and is edited "
            "in the bank's own profile."
        )
    )
    slug: str = Field(
        description=(
            "The bank's short name — lower-case letters, digits and hyphens, at most 80 "
            "characters, `example-bank` — derived from the name when the organisation was "
            "created, never typed by a person, unique across the platform and fixed from then "
            "on. Support staff use it to name the organisation in a conversation; it never "
            "appears in a URL and no call takes it. The list is ordered by it."
        )
    )
    status: str = Field(
        description=(
            "Whether the organisation is open for business: `active` means its members can "
            "sign in, `deactivated` means no session will open for it. It says nothing about "
            "the data inside, which stays whole until a tenant exit has been approved by two "
            "people and executed."
        )
    )
    default_language: RoleRef | None = Field(
        description=(
            "The language the bank reads and writes in first, as a reference to a language row "
            "by key — `sv`, `en`, `da`, `nb` or `fi` — with a label to show. Languages are "
            "library reference rows and not a vocabulary a bank's admin may extend. Null until "
            "the bank's own administrator chooses one on its Organisation profile: an "
            "organisation created through this console starts without one."
        )
    )
    created_at: datetime = Field(
        description=(
            "When the organisation was created on the platform, as a UTC timestamp in ISO "
            "8601. It is the platform's own record of onboarding and never changes; it is not "
            "a contract date, a go-live date or a billing start."
        )
    )


class ConsoleTenantPage(CamelSchema):
    """One page of the platform console's list of banks."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "id": "00000000-0000-4000-8000-00000000000a",
                            "name": "Example Bank AB",
                            "slug": "example-bank",
                            "status": "active",
                            "defaultLanguage": _EXAMPLE_LANGUAGE_SV,
                            "createdAt": "2026-01-09T09:12:44Z",
                        },
                        {
                            "id": "00000000-0000-4000-8000-00000000000b",
                            "name": "Second Bank A/S",
                            "slug": "second-bank",
                            "status": "active",
                            "defaultLanguage": _EXAMPLE_LANGUAGE_DA,
                            "createdAt": "2026-09-20T07:41:12Z",
                        },
                    ],
                    "total": 2,
                }
            ]
        }
    )

    items: list[ConsoleTenantRow] = Field(
        description=(
            "The banks on this page, ordered by their short name so two calls for the same "
            "page return the same rows. A platform session sees every organisation here and "
            "nothing inside any of them. An empty list is a 200 and means nothing matched; it "
            "is never an error."
        )
    )
    total: int = Field(
        description=(
            "How many organisations exist in total, not how many are on this page — use it to "
            "size a pager. It is counted at the moment of the call, so an organisation created "
            "between two pages can shift what the second page holds."
        )
    )


class ConsoleTenantCreateBody(CamelSchema):
    """Create a bank and invite its first administrator in one action (ADM-02, ID-01).
    The address must be the administrator's own: platform staff are separate accounts.
    The timezone, default language and content languages are not asked here (D-68): the
    bank sets them itself on its Organisation profile screen, which already carries this
    write under `security.manage`; a short name is derived from the name, never typed."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Second Bank A/S",
                    "firstAdminEmail": "compliance.officer@second-bank.test",
                    "firstAdminTitle": "Head of Compliance",
                }
            ]
        }
    )

    name: str = Field(
        max_length=200,
        description=(
            "The organisation's name as the bank itself will see it, at most 200 characters — "
            "'Example Bank AB'. It is the bank's own from the moment it exists and its "
            "administrators reword it themselves afterwards. Blank is refused with a 422. Its "
            "short name is derived from this and never typed by a person: letters such as ø, æ "
            "and å spelled out, lower-cased, hyphenated, cut to at most 80 characters, and "
            "given a numeric suffix if another tenant already has the same one, even one "
            "created at the same moment, so the call is never refused over it."
        ),
    )
    first_admin_email: str = Field(
        max_length=254,
        description=(
            "The work address of the person who will be the bank's first administrator, at "
            "most 254 characters. Creating the organisation sends that person an enrolment "
            "invitation carrying the system role that can invite everyone else; no password is "
            "created at any point, here or later. It has to be the bank's own person: an "
            "address that already belongs to platform staff is refused with a 422, because a "
            "console account carrying platform permissions into a bank session would collapse "
            "the separation the product rests on."
        ),
    )
    first_admin_title: str = Field(
        default="",
        max_length=200,
        description=(
            "That person's job title at the bank, at most 200 characters — 'Head of "
            "Compliance'. Optional; it defaults to the empty string. It is shown beside their "
            "name in member lists and grants nothing at all: what someone may do comes from "
            "their roles and never from a title."
        ),
    )
