"""Request and response schemas of the tenants app (TEN-01, ID-05 console): camelCase
through CamelSchema."""

from __future__ import annotations

import uuid

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
