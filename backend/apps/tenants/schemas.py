"""Request and response schemas of the tenants app (TEN-01, ID-05 console): camelCase
through CamelSchema.

Everything here is one bank's own identity and settings. It lives in that bank's zone and
no other bank ever reads it; the platform console reads the tenant row itself — name,
short name, status, language, creation date — and nothing underneath it, which is why the
console has a row schema of its own rather than reusing `TenantOut`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, JsonValue, model_validator

from apps.identity.schemas import RoleRef
from apps.shared.models import (
    ESCALATE_AFTER_DAYS_MAX,
    LEAD_DAYS_MAX,
    LEAD_DAYS_MAX_ENTRIES,
    TRIAGE_TARGET_HOURS_MAX,
)
from apps.shared.schemas import CamelSchema, SingleLineName, WriteBody
from apps.taxonomy.schemas import PersonRef, TermRef

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

    name: SingleLineName | None = Field(
        default=None,
        max_length=200,
        description=(
            "A new name for the organisation, at most 200 characters of one line of visible "
            "text: a line break, a tab or an invisible character is refused with a 422. Omit "
            "the field to leave the name alone; sending it blank does not clear it, it is "
            "refused with a 422, because an organisation without a name cannot be told apart "
            "in an audit trail."
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

    name: SingleLineName = Field(
        max_length=200,
        description=(
            "The organisation's name as the bank itself will see it, at most 200 characters of "
            "one line of visible text — 'Example Bank AB'; a line break, a tab or an invisible "
            "character is refused with a 422. It is the bank's own from the moment it exists and its "
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


# ---------------------------------------------------------------------------------------
# c8-tenants-contract: the bank's organisation, its teams and people, member removal and
# support access (TEN-02, TEN-03, TEN-05, TEN-06, COL-04, HOM-05). Declared ahead of the
# logic that fills them; the examples are the prototype's bank, never a real one.
# ---------------------------------------------------------------------------------------
_EXAMPLE_PERSON: dict[str, JsonValue] = {"id": "8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60", "name": "Karin Holm"}
_EXAMPLE_ENTITY_ID = "3f6a2c1d-8b4e-4d7a-9c5f-0e1d2c3b4a59"
_EXAMPLE_TERM: dict[str, JsonValue] = {"key": "bank", "kind": None, "label": "Bank"}

_EXAMPLE_ORG_UNIT: dict[str, JsonValue] = {
                    "id": _EXAMPLE_ENTITY_ID,
                    "kind": "legal_entity",
                    "name": "Example Bank AB",
                    "parentId": None,
                    "orgNumber": "556000-0000",
                    "lei": "5493000EXAMPLE000000",
                    "countryCode": "SE",
                    "entityTerm": _EXAMPLE_TERM,
                    "head": _EXAMPLE_PERSON,
                    "active": True,
                    "version": 3,
                }

_EXAMPLE_LICENCE: dict[str, JsonValue] = {
                    "id": "5b7d9e1f-3a2c-4e6b-8d0f-2a4c6e8b0d13",
                    "orgUnitId": _EXAMPLE_ENTITY_ID,
                    "licenceType": _EXAMPLE_TERM,
                    "reference": "FI 12-3456",
                    "grantedOn": "2014-03-01",
                    "withdrawnOn": None,
                    "scopeNote": "",
                    "issuer": "",
                    "number": "",
                    "scopeStatement": "",
                    "issuedOn": None,
                    "validUntil": None,
                    "nextAuditOn": None,
                    "owner": _EXAMPLE_PERSON,
                    "serviceTerms": [],
                    "version": 1,
                }

_EXAMPLE_PRODUCT: dict[str, JsonValue] = {
                    "id": "7c9e1a3b-5d2f-4a8c-9e0b-4d6f8a0c2e57",
                    "name": "Custody",
                    "description": "Safekeeping of securities for retail and institutional clients.",
                    "status": "live",
                    "launchDate": "2019-05-01",
                    "orgUnitId": _EXAMPLE_ENTITY_ID,
                    "owner": _EXAMPLE_PERSON,
                    "terms": [{"key": "custody", "kind": None, "label": "Custody"}],
                    "version": 2,
                }

_EXAMPLE_TEAM: dict[str, JsonValue] = {"key": "compliance", "label": "Compliance", "orgUnitId": None, "email": "compliance@example-bank.test", "memberCount": 4, "active": True}

_EXAMPLE_GRANT: dict[str, JsonValue] = {
                    "id": "2e4a6c8e-0b1d-4f3a-8c5e-7a9b1c3d5e71",
                    "state": "active",
                    "purpose": "The bank reports that its watch feed stopped updating on Monday.",
                    "ticketRef": "SUP-2511",
                    "hours": 2,
                    "platformPerson": {"id": "9b1d3f5a-7c2e-4a6b-8d0f-1e3a5c7e9b24", "name": "Jonas Berg"},
                    "requestedAt": "2026-09-24T08:05:00Z",
                    "decidedBy": _EXAMPLE_PERSON,
                    "decidedAt": "2026-09-24T08:20:00Z",
                    "endsAt": "2026-09-24T10:20:00Z",
                }

_EXAMPLE_CONSOLE_GRANT: dict[str, JsonValue] = {
                    "id": "2e4a6c8e-0b1d-4f3a-8c5e-7a9b1c3d5e71",
                    "tenantId": "0c2e4a6c-8e0b-4d1f-9a3c-5e7a9b1c3d52",
                    "tenantName": "Example Bank AB",
                    "state": "active",
                    "purpose": "The bank reports that its watch feed stopped updating on Monday.",
                    "ticketRef": "SUP-2511",
                    "hours": 2,
                    "requestedAt": "2026-09-24T08:05:00Z",
                    "decidedAt": "2026-09-24T08:20:00Z",
                    "endsAt": "2026-09-24T10:20:00Z",
                }

OrgUnitKindValue = Literal["group", "legal_entity", "business_area", "business_unit", "function"]
ProductStatusValue = Literal["planned", "live", "retired"]
# Open work a removal moves to a new owner, and the two kinds it ends instead (TEN-05, TEN-S9).
ReassignableKind = Literal["register_entry", "register_entity", "gap", "duty_occurrence", "internal_item", "case", "action"]
OpenWorkKind = Literal[
    "register_entry",
    "register_entity",
    "gap",
    "duty_occurrence",
    "internal_item",
    "case",
    "action",
    "participation",
    "team_membership",
]
SupportAccessState = Literal["pending", "active", "declined", "revoked", "ended", "lapsed", "recovery"]

_UNIT_KINDS = (
    "`group` (the banking group at the top of the tree), `legal_entity` (a company that holds "
    "licences and carries the legal-entity scope term, so an obligation can be assessed per "
    "entity), `business_area`, `business_unit` and `function` (the last three, with a head, are "
    "what screens call a department). A kind is fixed in code and never added by an administrator"
)
_PRODUCT_STATUSES = (
    "`planned` (not yet offered, already scoped so the work can start), `live` (offered to "
    "customers today) or `retired` (withdrawn; a product is retired and never deleted, and a "
    "retired product scopes nothing)"
)
_OWNER_KINDS = (
    "`register_entry` (an obligation's register entry the person owns), `register_entity` (a "
    "legal entity's row on an entry), `gap`, `duty_occurrence` (a dated recurring duty), "
    "`internal_item` (a policy, procedure, control, process or system), `case` or `action`"
)
_ENDING_KINDS = (
    "`participation` (items the person takes part in without owning them) and "
    "`team_membership` (the teams the person is in); both end with the removal and move to nobody"
)
_SUPPORT_STATES = (
    "`pending` (asked for by platform support and granting nothing yet), `active` (approved by "
    "the bank; the window is open and support may read, never write), `declined` (refused by the "
    "bank), `revoked` (ended by the bank before its window closed), `ended` (its window passed), "
    "`lapsed` (never decided before the request expired) or `recovery` (a one-off last-administrator "
    "recovery platform support carried out, recorded here and granting no reading at all)"
)


class TenantOrgUnit(CamelSchema):
    """One unit of the bank's organisation: a group, a legal entity or a department (TEN-02,
    D-21). The bank's own record, never shared with another bank."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_ORG_UNIT]})

    id: uuid.UUID = Field(description="The unit's identifier, a UUID that never changes; licences and register rows point at it.")
    kind: OrgUnitKindValue = Field(description=f"What the unit is: {_UNIT_KINDS}.")
    name: str = Field(description="The unit's name as the bank wrote it, for display; a person may rename it, so match on the id.")
    parent_id: uuid.UUID | None = Field(
        description="The identifier of the unit this one sits under, a UUID of the same bank, or null at the top of the tree."
    )
    org_number: str = Field(description="The company registration number a legal entity carries, such as `556000-0000`; empty for any other unit.")
    lei: str = Field(description="The legal entity identifier (ISO 17442, 20 characters) a legal entity carries; empty when it has none or for any other unit.")
    country_code: str = Field(description="The two-letter ISO 3166 country a legal entity is registered in, such as `SE`; empty for any other unit.")
    entity_term: TermRef | None = Field(
        description=(
            "The term of the shared library's `legal_entity` dimension a legal entity is scoped "
            "with, the same term obligations are scoped with, so an obligation can be assessed per "
            "entity. The terms are a vocabulary of the shared library, which an administrator may "
            "extend only through an approved proposal; read `GET /taxonomy/terms` for the live set. "
            "Null for every unit that is not a legal entity."
        )
    )
    head: PersonRef | None = Field(
        description="The member who heads the unit, an active member of the same bank, or null when nobody does; a department's head is told about its work."
    )
    active: bool = Field(description="False once the unit is deactivated; a unit is deactivated and never deleted, so its history stays readable.")
    version: int = Field(description="The unit's version; send it back in `If-Match` on a change, and a stale one is refused with `stale_write`.")


class TenantOrgUnitPage(CamelSchema):
    """One page of the bank's organisation, ordered by name."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_ORG_UNIT], "total": 1}]})

    items: list[TenantOrgUnit] = Field(description="The units on this page, by name; an empty list is a 200 and means the bank has recorded none.")
    total: int = Field(description="How many units the bank has in total, active and deactivated, not how many are on this page.")


class TenantOrgUnitBody(WriteBody):
    """A new unit of the bank's organisation. A field the schema does not name is refused."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"kind": "business_area", "name": "Retail Banking", "parentId": _EXAMPLE_ENTITY_ID, "headUserId": _EXAMPLE_PERSON["id"]}]})

    kind: OrgUnitKindValue = Field(description=f"What the unit is, fixed once it exists: {_UNIT_KINDS}. Any other value is refused with a 422.")
    name: SingleLineName = Field(
        min_length=1,
        max_length=200,
        description="The unit's name, at most 200 characters of one line of visible text; blank, a line break, a tab or an invisible character is refused with a 422.",
    )
    parent_id: uuid.UUID | None = Field(
        default=None, description="The identifier of the unit this one sits under, a UUID of the same bank; null by default, at the top of the tree."
    )
    org_number: str = Field(default="", max_length=40, description="A legal entity's company registration number, at most 40 characters; empty by default.")
    lei: str = Field(default="", max_length=20, description="A legal entity's legal entity identifier, at most 20 characters; empty by default.")
    country_code: str = Field(default="", max_length=2, description="A legal entity's two-letter ISO 3166 country, at most 2 characters, such as `SE`; empty by default.")
    entity_term: str | None = Field(
        default=None,
        max_length=80,
        description=(
            "The key of the `legal_entity` dimension term a legal entity is scoped with, at most 80 "
            "characters, such as `bank`; null by default. The terms are a vocabulary of the shared "
            "library, which an administrator may extend only through an approved proposal; read "
            "`GET /taxonomy/terms` for the live set. Only a legal entity may carry one; an unknown "
            "key answers `unknown_key`."
        ),
    )
    head_user_id: uuid.UUID | None = Field(
        default=None, description="The identifier of the member who heads the unit, a UUID of an active member of the same bank; null by default."
    )


class TenantOrgUnitPatch(WriteBody):
    """A change to a unit. Send only the fields you are changing; its kind never changes."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"name": "Retail and Private Banking", "headUserId": _EXAMPLE_PERSON["id"]}]})

    name: SingleLineName | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="A new name, at most 200 characters of one line of visible text; null by default, which leaves it alone. Blank is refused with a 422.",
    )
    parent_id: uuid.UUID | None = Field(default=None, description="A new parent unit, a UUID of the same bank; null by default, which leaves it alone.")
    org_number: str | None = Field(default=None, max_length=40, description="A new registration number, at most 40 characters; null by default, which leaves it alone.")
    lei: str | None = Field(default=None, max_length=20, description="A new legal entity identifier, at most 20 characters; null by default, which leaves it alone.")
    country_code: str | None = Field(default=None, max_length=2, description="A new two-letter country, at most 2 characters; null by default, which leaves it alone.")
    entity_term: str | None = Field(
        default=None,
        max_length=80,
        description=(
            "A new `legal_entity` term key, at most 80 characters; null by default, which leaves it "
            "alone. A vocabulary of the shared library an administrator may extend only through an "
            "approved proposal; read `GET /taxonomy/terms` for the live set."
        ),
    )
    head_user_id: uuid.UUID | None = Field(default=None, description="A new head, a UUID of an active member of the same bank; null by default, which leaves it alone.")
    active: bool | None = Field(default=None, description="False deactivates the unit and true restores it; null by default, which leaves it alone.")


class TenantLicence(CamelSchema):
    """A licence or certificate a legal entity holds (TEN-02, D-43). A certificate's validity
    and next audit are the bank's own deadlines; they carry no term and decide no span."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_LICENCE]})

    id: uuid.UUID = Field(description="The licence's identifier, a UUID that never changes.")
    org_unit_id: uuid.UUID = Field(description="The identifier of the legal entity that holds it, a UUID of the same bank.")
    licence_type: TermRef = Field(
        description=(
            "What the licence or certificate is, as a term of the shared library, the same terms "
            "obligations are scoped with; a vocabulary an administrator may extend only through an "
            "approved proposal (`GET /taxonomy/terms`). A type is a key, never a phrase."
        )
    )
    reference: str = Field(description="The authority's own reference for the licence, such as `FI 12-3456`; empty when there is none.")
    granted_on: date | None = Field(description="The date the licence was granted, a plain date, or null when unknown.")
    withdrawn_on: date | None = Field(
        description="The date it was withdrawn, a plain date, or null while it stands; a withdrawn row reads as withdrawn and stays in the history."
    )
    scope_note: str = Field(description="The bank's own note on what the licence covers, as the bank wrote it; empty when there is none.")
    issuer: str = Field(description="Who issued a certificate, such as `Example Certification AB`; empty for a licence an authority granted.")
    number: str = Field(description="A certificate's number as its issuer prints it; empty when there is none.")
    scope_statement: str = Field(description="A certificate's scope statement as its issuer wrote it; empty when there is none.")
    issued_on: date | None = Field(description="The date a certificate was issued, a plain date, or null.")
    valid_until: date | None = Field(
        description="The last date a certificate is valid, a plain date, or null; it shows on the roadmap as the bank's own deadline and never in the calendar feed."
    )
    next_audit_on: date | None = Field(description="The date of a certificate's next audit, a plain date, or null; the bank's own deadline, like the validity.")
    owner: PersonRef | None = Field(description="The member who owns the licence or certificate and its deadlines, or null.")
    service_terms: list[TermRef] = Field(
        description=(
            "The services the licence covers, as terms of the shared library, a vocabulary an "
            "administrator may extend only through an approved proposal; an empty list when none are recorded."
        )
    )
    version: int = Field(description="The licence's version; send it back in `If-Match` on a change, and a stale one is refused with `stale_write`.")


class TenantLicencePage(CamelSchema):
    """One page of a legal entity's licences and certificates."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_LICENCE], "total": 1}]})

    items: list[TenantLicence] = Field(description="The licences and certificates on this page, withdrawn ones included; an empty list is a 200.")
    total: int = Field(description="How many the legal entity holds in total, not how many are on this page.")


_TERM_KEY = (
    "a term of the shared library, the same terms obligations are scoped with; a vocabulary an "
    "administrator may extend only through an approved proposal, read `GET /taxonomy/terms` for "
    "the live set. An unknown key answers `unknown_key`"
)


class TenantLicenceBody(WriteBody):
    """A licence or certificate a legal entity holds. A field the schema does not name is refused."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"licenceType": "bank", "reference": "FI 12-3456", "grantedOn": "2014-03-01"}]})

    licence_type: str = Field(max_length=80, description=f"What the licence or certificate is, at most 80 characters: the key of {_TERM_KEY}.")
    reference: str = Field(default="", max_length=200, description="The authority's reference, at most 200 characters; empty by default.")
    granted_on: date | None = Field(default=None, description="The date the licence was granted, a plain date; null by default.")
    withdrawn_on: date | None = Field(default=None, description="The date it was withdrawn, a plain date; null by default.")
    scope_note: str = Field(default="", max_length=4000, description="The bank's note on what it covers, at most 4000 characters; empty by default.")
    issuer: SingleLineName = Field(
        default="", max_length=200, description="Who issued a certificate, at most 200 characters of one line of visible text; empty by default."
    )
    number: str = Field(default="", max_length=100, description="A certificate's number, at most 100 characters; empty by default.")
    scope_statement: str = Field(default="", max_length=4000, description="A certificate's scope statement, at most 4000 characters; empty by default.")
    issued_on: date | None = Field(default=None, description="The date a certificate was issued, a plain date; null by default.")
    valid_until: date | None = Field(default=None, description="The last date a certificate is valid, a plain date; null by default.")
    next_audit_on: date | None = Field(default=None, description="The date of a certificate's next audit, a plain date; null by default.")
    owner_user_id: uuid.UUID | None = Field(default=None, description="The identifier of the owning member, a UUID of an active member of the same bank; null by default.")
    service_terms: list[str] = Field(
        default_factory=list, max_length=50, description=f"The services it covers, at most 50 keys, each {_TERM_KEY}; empty by default."
    )


class TenantLicencePatch(WriteBody):
    """A change to a licence or certificate. Send only the fields you are changing."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"withdrawnOn": "2026-12-31"}]})

    licence_type: str | None = Field(default=None, max_length=80, description=f"A new type, at most 80 characters, the key of {_TERM_KEY}; null by default, which leaves it alone.")
    reference: str | None = Field(default=None, max_length=200, description="A new reference, at most 200 characters; null by default, which leaves it alone.")
    granted_on: date | None = Field(default=None, description="A new grant date, a plain date; null by default, which leaves it alone.")
    withdrawn_on: date | None = Field(default=None, description="The date it was withdrawn, a plain date; null by default, which leaves it alone.")
    scope_note: str | None = Field(default=None, max_length=4000, description="A new note, at most 4000 characters; null by default, which leaves it alone.")
    issuer: SingleLineName | None = Field(
        default=None, max_length=200, description="A new issuer, at most 200 characters of one line of visible text; null by default, which leaves it alone."
    )
    number: str | None = Field(default=None, max_length=100, description="A new certificate number, at most 100 characters; null by default, which leaves it alone.")
    scope_statement: str | None = Field(default=None, max_length=4000, description="A new scope statement, at most 4000 characters; null by default, which leaves it alone.")
    issued_on: date | None = Field(default=None, description="A new issue date, a plain date; null by default, which leaves it alone.")
    valid_until: date | None = Field(default=None, description="A new validity end, a plain date; null by default, which leaves it alone.")
    next_audit_on: date | None = Field(default=None, description="A new next audit date, a plain date; null by default, which leaves it alone.")
    owner_user_id: uuid.UUID | None = Field(default=None, description="A new owner, a UUID of an active member of the same bank; null by default, which leaves it alone.")
    service_terms: list[str] | None = Field(
        default=None, max_length=50, description=f"The complete new list of services, at most 50 keys, each {_TERM_KEY}; null by default, which leaves it alone."
    )


class TenantProductOut(CamelSchema):
    """A product the bank offers, described the way obligations are scoped (TEN-02)."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_PRODUCT]})

    id: uuid.UUID = Field(description="The product's identifier, a UUID that never changes.")
    name: str = Field(description="The product's name as the bank wrote it, unique within the bank; match on the id.")
    description: str = Field(description="The bank's own description of the product; empty when there is none.")
    status: ProductStatusValue = Field(description=f"Where the product stands: {_PRODUCT_STATUSES}.")
    launch_date: date | None = Field(description="The date the product went or goes live, a plain date, or null.")
    org_unit_id: uuid.UUID | None = Field(description="The identifier of the unit that offers it, a UUID of the same bank, or null.")
    owner: PersonRef | None = Field(description="The member who owns the product, or null.")
    terms: list[TermRef] = Field(
        description=(
            "The product's scope as terms of the shared library, the same terms obligations are "
            "scoped with; a vocabulary an administrator may extend only through an approved "
            "proposal. An empty list when it is not scoped yet."
        )
    )
    version: int = Field(description="The product's version; send it back in `If-Match` on a change, and a stale one is refused with `stale_write`.")


class TenantProductPage(CamelSchema):
    """One page of the bank's products, ordered by name."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_PRODUCT], "total": 1}]})

    items: list[TenantProductOut] = Field(description="The products on this page, retired ones included; an empty list is a 200.")
    total: int = Field(description="How many products the bank has in total, not how many are on this page.")


class TenantProductBody(WriteBody):
    """A new product. A field the schema does not name is refused."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"name": "Custody", "status": "live", "terms": ["custody"]}]})

    name: SingleLineName = Field(
        min_length=1,
        max_length=200,
        description="The product's name, unique within the bank, at most 200 characters of one line of visible text; blank or a line break is refused with a 422.",
    )
    description: str = Field(default="", max_length=4000, description="The bank's description, at most 4000 characters; empty by default.")
    status: ProductStatusValue = Field(default="live", description=f"Where the product stands, `live` by default: {_PRODUCT_STATUSES}.")
    launch_date: date | None = Field(default=None, description="The launch date, a plain date; null by default.")
    org_unit_id: uuid.UUID | None = Field(default=None, description="The unit that offers it, a UUID of the same bank; null by default.")
    owner_user_id: uuid.UUID | None = Field(default=None, description="The owning member, a UUID of an active member of the same bank; null by default.")
    terms: list[str] = Field(default_factory=list, max_length=50, description=f"The product's scope, at most 50 keys, each {_TERM_KEY}; empty by default.")


class TenantProductPatch(WriteBody):
    """A change to a product. Send only the fields you are changing; retiring is a status."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "retired"}]})

    name: SingleLineName | None = Field(
        default=None, min_length=1, max_length=200, description="A new name, at most 200 characters of one line of visible text; null by default, which leaves it alone."
    )
    description: str | None = Field(default=None, max_length=4000, description="A new description, at most 4000 characters; null by default, which leaves it alone.")
    status: ProductStatusValue | None = Field(default=None, description=f"A new status, null by default, which leaves it alone: {_PRODUCT_STATUSES}.")
    launch_date: date | None = Field(default=None, description="A new launch date, a plain date; null by default, which leaves it alone.")
    org_unit_id: uuid.UUID | None = Field(default=None, description="A new offering unit, a UUID of the same bank; null by default, which leaves it alone.")
    owner_user_id: uuid.UUID | None = Field(default=None, description="A new owner, a UUID of an active member of the same bank; null by default, which leaves it alone.")
    terms: list[str] | None = Field(
        default=None, max_length=50, description=f"The complete new scope, at most 50 keys, each {_TERM_KEY}; null by default, which leaves it alone."
    )


class TenantTeam(CamelSchema):
    """A team of the bank, which can own work and take part in it (TEN-03). A team is a row
    of the bank's `team` list, so creating, renaming and retiring one is `/vocab/team`."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_TEAM]})

    key: str = Field(
        description=(
            "The team's immutable key, such as `compliance`, the only part to store or send back. "
            "A row of the bank's own `team` vocabulary, which an administrator with `vocab.manage` "
            "may extend at `GET /vocab/team`; `compliance` is seeded for every bank."
        )
    )
    label: str = Field(description="The team's name in the reader's language, for display only; it may be reworded at any time.")
    org_unit_id: uuid.UUID | None = Field(description="The identifier of the department the team sits in, a UUID of the same bank, or null.")
    email: str = Field(description="The team's shared mailbox, where the bank gave one; empty otherwise.")
    member_count: int = Field(description="How many active members are in the team at the moment of the call.")
    active: bool = Field(description="False once the team is retired; a retired team keeps what it owns until someone moves it.")


class TenantTeamPage(CamelSchema):
    """One page of the bank's teams."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_TEAM], "total": 1}]})

    items: list[TenantTeam] = Field(description="The teams on this page, in the list's order; an empty list is a 200.")
    total: int = Field(description="How many teams the bank has in total, not how many are on this page.")


class TenantPeoplePage(CamelSchema):
    """One page of people: ids and names, nothing else about them."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_PERSON], "total": 1}]})

    items: list[PersonRef] = Field(description="The people on this page, by name; an empty list is a 200 and means nobody is in it.")
    total: int = Field(description="How many people there are in total, not how many are on this page.")


class TenantOpenWork(CamelSchema):
    """One kind of open work a member holds, counted, before their removal (TEN-05)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"kind": "register_entry", "count": 3}]})

    kind: OpenWorkKind = Field(description=f"What the member holds. Moved to a new owner on removal: {_OWNER_KINDS}. Ended on removal: {_ENDING_KINDS}.")
    count: int = Field(description="How many of that kind the member holds at the moment of the call, at least one; a kind they hold none of is not listed.")


class TenantMemberOpenWork(CamelSchema):
    """Everything a member owns or takes part in, by kind, so a removal can ask for a new
    owner per kind before anything changes."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"member": _EXAMPLE_PERSON, "items": [{"kind": "register_entry", "count": 3}, {"kind": "case", "count": 2}]}]}
    )

    member: PersonRef = Field(description="The member whose open work this is.")
    items: list[TenantOpenWork] = Field(description="One row per kind the member holds; an empty list is a 200 and means the removal moves nothing.")


class TenantRemovalOwner(WriteBody):
    """Who takes over one kind of the removed member's work: a person or a team, exactly one."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"kind": "register_entry", "teamKey": "compliance"}]})

    kind: ReassignableKind = Field(description=f"The kind of work being moved: {_OWNER_KINDS}. Participations and team memberships end and are never moved.")
    user_id: uuid.UUID | None = Field(default=None, description="The new owner, a UUID of another active member of the same bank; null by default. Send this or `teamKey`, never both.")
    team_key: str | None = Field(
        default=None,
        max_length=80,
        description=(
            "The new owning team, at most 80 characters, the key of a row of the bank's `team` "
            "vocabulary, which an administrator may extend at `GET /vocab/team`; null by default. "
            "Send this or `userId`, never both."
        ),
    )

    @model_validator(mode="after")
    def _one_owner(self) -> TenantRemovalOwner:
        if (self.user_id is None) == (self.team_key is None):
            raise ValueError("Name exactly one new owner: a person or a team.")
        return self


class TenantMemberRemoveBody(WriteBody):
    """The removal of a member, with a new owner for each kind of work they own."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"owners": [{"kind": "register_entry", "teamKey": "compliance"}, {"kind": "case", "userId": _EXAMPLE_PERSON["id"]}]}]})

    owners: list[TenantRemovalOwner] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "One new owner per kind of work the member owns, at most 10, empty by default for a "
            "member who owns nothing. A kind the member owns with no owner named here answers "
            "`validation_error` and nothing changes."
        ),
    )


class SupportAccessGrant(CamelSchema):
    """A request by platform support to read the bank's data, and what became of it (TEN-06,
    D-49). The bank reads every one; support never writes under a grant."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_GRANT]})

    id: uuid.UUID = Field(description="The request's identifier, a UUID that never changes.")
    state: SupportAccessState = Field(description=f"Where the request stands: {_SUPPORT_STATES}.")
    purpose: str = Field(description="Why platform support asked, in their own words, written for the bank.")
    ticket_ref: str = Field(description="The support ticket it was asked under, such as `SUP-2511`; empty when there is none.")
    hours: int = Field(description="How long the window asked for is, in hours; the window starts when the bank approves.")
    platform_person: PersonRef = Field(description="The platform support person who asked; their name and id, nothing else.")
    requested_at: datetime = Field(description="When the request was made, a UTC timestamp.")
    decided_by: PersonRef | None = Field(description="The member who approved, declined or revoked it, or null while it is pending or once it lapsed.")
    decided_at: datetime | None = Field(description="When the bank last decided on it, a UTC timestamp, or null.")
    ends_at: datetime | None = Field(description="When an approved window closes or closed, a UTC timestamp, or null until it is approved.")


class SupportAccessPage(CamelSchema):
    """One page of the bank's support access requests, newest first."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_GRANT], "total": 1}]})

    items: list[SupportAccessGrant] = Field(description="The requests on this page, newest first; an empty list is a 200 and means support never asked.")
    total: int = Field(description="How many requests the bank has had in total, not how many are on this page.")


class ConsoleSupportAccessBody(WriteBody):
    """Platform support asks one bank to let it read, for a purpose and a limited time. The
    request grants nothing until a tenant admin approves it."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"purpose": "The bank reports that its watch feed stopped updating on Monday.", "ticketRef": "SUP-2511", "hours": 2}]})

    purpose: str = Field(
        min_length=1,
        max_length=1000,
        description="Why support needs to look, at most 1000 characters, written for the bank, which reads it before it decides; blank is refused with a 422.",
    )
    ticket_ref: SingleLineName = Field(default="", max_length=100, description="The support ticket, at most 100 characters of one line; empty by default.")
    hours: int = Field(
        ge=1,
        description=(
            "How long the window should be, in whole hours, at least 1 and at most the platform's "
            "`SUPPORT_ACCESS_MAX_HOURS` (4 by default); a longer one answers `validation_error`. The "
            "window starts when the bank approves, not when support asks."
        ),
    )


class ConsoleSupportAccessGrant(CamelSchema):
    """One of the caller's own requests, as the console lists it: the bank by its name and
    never a member's name; the approval is a time, not a person."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_CONSOLE_GRANT]})

    id: uuid.UUID = Field(description="The request's identifier, a UUID; the one to enter with.")
    tenant_id: uuid.UUID = Field(description="The identifier of the bank asked, a UUID.")
    tenant_name: str = Field(description="The bank's organisation name, for display; no member of the bank is ever named here.")
    state: SupportAccessState = Field(description=f"Where the request stands: {_SUPPORT_STATES}.")
    purpose: str = Field(description="The purpose the caller gave.")
    ticket_ref: str = Field(description="The ticket the caller gave; empty when there is none.")
    hours: int = Field(description="The window asked for, in hours.")
    requested_at: datetime = Field(description="When the caller asked, a UTC timestamp.")
    decided_at: datetime | None = Field(description="When the bank decided, a UTC timestamp, or null; who decided is the bank's to know.")
    ends_at: datetime | None = Field(description="When an approved window closes or closed, a UTC timestamp, or null.")


class ConsoleSupportAccessPage(CamelSchema):
    """One page of the caller's own support access requests, newest first."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_CONSOLE_GRANT], "total": 1}]})

    items: list[ConsoleSupportAccessGrant] = Field(description="The caller's requests on this page, newest first; an empty list is a 200.")
    total: int = Field(description="How many requests the caller has made in total, not how many are on this page.")
