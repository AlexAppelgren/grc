"""Request and response schemas of the tenants app (TEN-01, ID-05 console): camelCase
through CamelSchema. Every field carries the description and the example the reader of
openapi.json needs (CONVENTIONS 1.8, gated by scripts/openapi_quality.py); examples come
from the prototype's bank, Example Bank AB."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from apps.identity.schemas import RoleRef
from apps.shared.schemas import CamelSchema

__all__ = ["CamelSchema"]


class OnboardingStep(CamelSchema):
    """One thing a bank does once, when it starts, before the product is any use to it."""

    key: str = Field(
        description="Which step this is: `profile`, `members`, `footprint`, `vocabularies` or `passkey`, in the order a bank works through them. The five are fixed in code.",
        examples=["footprint"],
    )
    done: bool = Field(description="Whether the bank has finished it. The home screen shows what is left and stops showing anything once all five are true.")


class Onboarding(CamelSchema):
    """How far the bank has got in setting itself up (TEN-01)."""

    steps_done: int = Field(description="How many of the five are finished, so a screen can show progress without counting them itself.", examples=[3])
    steps: list[OnboardingStep] = Field(description="Every step and whether it is done, in the order a bank works through them.")


class TenantOut(CamelSchema):
    """The bank's own profile: who it is, which languages its content is kept in, and how
    far its setting-up has got."""

    id: uuid.UUID = Field(description="The bank itself, as every tenant row refers to it.")
    name: str = Field(description="The bank as it names itself, shown in the shell and on everything it exports.", examples=["Example Bank AB"])
    slug: str = Field(description="The bank's short name in links and in support conversations; lower-case letters, digits and hyphens, and it never changes.", examples=["example-bank"])
    timezone: str = Field(
        description="The zone the bank's own days are counted in, so a deadline falls where its compliance officers sit rather than where a server does.",
        examples=["Europe/Stockholm"],
    )
    status: str = Field(
        description="`active` while the bank is working in the product, `deactivated` once its subscription has ended and it may only be read. The pair is fixed in code.",
        examples=["active"],
    )
    default_language: RoleRef | None = Field(
        description="Which language the bank reads regulation in when a person has chosen none, or null before it has picked one.",
    )
    content_languages: list[RoleRef] = Field(
        description="The languages the bank keeps its own assessments and summaries in; a Nordic bank usually holds its own and English.",
    )
    onboarding: Onboarding = Field(description="How far the bank has got in setting itself up.")


class TenantPatch(CamelSchema):
    name: str | None = Field(
        default=None,
        max_length=200,
        description="What the bank should be called from now on; leave it out to keep the name it has.",
        examples=["Example Bank AB"],
    )
    timezone: str | None = Field(
        default=None,
        max_length=64,
        description="Which zone the bank's days should be counted in from now on, as an IANA name; anything else answers 422 `unknown_key`.",
        examples=["Europe/Stockholm"],
    )
    default_language: str | None = Field(
        default=None,
        max_length=8,
        description="Which language to fall back on for people who have chosen none. A key from the languages list, which an admin manages.",
        examples=["sv"],
    )
    content_languages: list[str] | None = Field(
        default=None,
        description="The languages the bank keeps its own content in from now on, replacing the ones it keeps today; at least one. Keys from the languages list, which an admin manages.",
        examples=[["sv", "en"]],
    )


class ConsoleReissueBody(CamelSchema):
    """Why bleqq is putting a bank's member back on an emailed code (ID-05). Nobody can
    do this without writing down what they checked, and the answer is audited."""

    reason: str = Field(
        max_length=1000,
        description="Why the bank asked for this, in the words the audit trail and the bank's own security log will carry.",
        examples=["Every device was lost when the laptop was stolen; the bank's administrator asked us in ticket 4471."],
    )
    ticket_ref: str = Field(
        default="",
        max_length=100,
        description="Where the request is recorded on bleqq's side, so an assessor can follow it out of the product.",
        examples=["SUP-4471"],
    )
    out_of_band_check: str = Field(
        max_length=1000,
        description="How the person was proved to be themselves away from the product: a call back on a known number, an identity check by the bank. Without it the answer is 422 `check_required`.",
        examples=["Called back on the bank's switchboard number and confirmed with the head of compliance."],
    )


class ConsoleTenantRow(CamelSchema):
    """One bank as the platform console lists it (ADM-02). No member count and no
    tenant-side content: a platform session reads the tenant row and nothing under it."""

    id: uuid.UUID = Field(description="The bank, for the console's own calls about it.")
    name: str = Field(description="The bank as it names itself.", examples=["Example Bank AB"])
    slug: str = Field(description="The bank's short name in links and support conversations.", examples=["example-bank"])
    status: str = Field(
        description="`active` while the bank is working in the product, `deactivated` once its subscription has ended. The pair is fixed in code.",
        examples=["active"],
    )
    default_language: RoleRef | None = Field(description="Which language the bank reads regulation in by default, or null before it has picked one.")
    created_at: datetime = Field(description="When the bank was created here, UTC.", examples=["2026-01-15T09:30:00Z"])


class ConsoleTenantPage(CamelSchema):
    items: list[ConsoleTenantRow] = Field(description="The banks on this page, in order of their short name.")
    total: int = Field(description="How many banks there are in all.", examples=[12])


class ConsoleTenantCreateBody(CamelSchema):
    """Create a bank and invite its first administrator in one action (ADM-02, ID-01).
    The address must be the administrator's own: platform staff are separate accounts."""

    name: str = Field(max_length=200, description="What the bank calls itself; it goes on its screens and its exports.", examples=["Example Bank AB"])
    slug: str = Field(
        max_length=80,
        description="The short name for links and support conversations: lower-case letters, digits and hyphens, unique across banks, and never changed afterwards.",
        examples=["example-bank"],
    )
    timezone: str = Field(
        max_length=64,
        description="The zone the bank's days are counted in, as an IANA name, so its deadlines fall where its people sit.",
        examples=["Europe/Stockholm"],
    )
    default_language: str = Field(
        max_length=8,
        description="Which language the bank reads regulation in until someone chooses otherwise. A key from the languages list, which an admin manages.",
        examples=["sv"],
    )
    content_languages: list[str] = Field(
        min_length=1,
        description="The languages the bank will keep its own assessments in; at least one. Keys from the languages list, which an admin manages.",
        examples=[["sv", "en"]],
    )
    first_admin_email: str = Field(
        max_length=254,
        description="Where the first invitation goes. It must belong to somebody at the bank, never to bleqq: from here on the bank invites its own people.",
        examples=["admin@example-bank.test"],
    )
    first_admin_title: str = Field(
        default="",
        max_length=200,
        description="What that person does at the bank, shown beside their name; leave it empty if it is not known yet.",
        examples=["Administrator"],
    )
