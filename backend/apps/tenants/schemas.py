"""Request and response schemas of the tenants app (TEN-01, ID-05 console): camelCase
through CamelSchema."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from apps.identity.schemas import RoleRef
from apps.shared.schemas import CamelSchema

__all__ = ["CamelSchema"]


class OnboardingStep(CamelSchema):
    key: str
    done: bool


class Onboarding(CamelSchema):
    steps_done: int
    steps: list[OnboardingStep]


class TenantOut(CamelSchema):
    id: uuid.UUID
    name: str
    slug: str
    timezone: str
    status: str
    default_language: RoleRef | None
    content_languages: list[RoleRef]
    onboarding: Onboarding


class TenantPatch(CamelSchema):
    name: str | None = Field(default=None, max_length=200)
    timezone: str | None = Field(default=None, max_length=64)
    default_language: str | None = Field(default=None, max_length=8)
    content_languages: list[str] | None = None


class ConsoleReissueBody(CamelSchema):
    reason: str = Field(max_length=1000)
    ticket_ref: str = Field(default="", max_length=100)
    out_of_band_check: str = Field(max_length=1000)


class ConsoleTenantRow(CamelSchema):
    """One bank as the platform console lists it (ADM-02). No member count and no
    tenant-side content: a platform session reads the tenant row and nothing under it."""

    id: uuid.UUID
    name: str
    slug: str
    status: str
    default_language: RoleRef | None
    created_at: datetime


class ConsoleTenantPage(CamelSchema):
    items: list[ConsoleTenantRow]
    total: int


class ConsoleTenantCreateBody(CamelSchema):
    """Create a bank and invite its first administrator in one action (ADM-02, ID-01).
    The address must be the administrator's own: platform staff are separate accounts."""

    name: str = Field(max_length=200)
    slug: str = Field(max_length=80)
    timezone: str = Field(max_length=64)
    default_language: str = Field(max_length=8)
    content_languages: list[str] = Field(min_length=1)
    first_admin_email: str = Field(max_length=254)
    first_admin_title: str = Field(default="", max_length=200)
