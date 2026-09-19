"""Sentry event scrubbers (playbook 11.2). Both hooks exist because transactions bypass
`before_send`; the last repo sampled 10% of traces and each carried the request it
came from. Personal data beyond a person's id, and any tenant content, never leaves.

Kept free of Django imports so settings.py can import it before apps load; it imports
only sentry_sdk's type aliases.
"""

from __future__ import annotations

from typing import Any, cast

from sentry_sdk.types import Event, Hint

SENSITIVE_HEADERS = frozenset(
    {"authorization", "cookie", "set-cookie", "x-api-key", "x-forwarded-for", "x-real-ip"}
)
# Keys whose values are dropped wherever they appear in the event's request or extra.
SENSITIVE_KEYS = frozenset(
    {
        "email",
        "phone",
        "token",
        "secret",
        "password",
        "code",
        "api_key",
        "apikey",
        "cookies",
        "data",
        "body",
        "query_string",
        "text",
        "content",
        "summary",
        "note",
        "comment",
        "question",
        "answer",
        "before",
        "after",
    }
)
REDACTED = "[redacted]"


def _scrub_mapping(mapping: dict[str, Any], sensitive: frozenset[str]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in mapping.items():
        if key.lower() in sensitive:
            cleaned[key] = REDACTED
        elif isinstance(value, dict):
            cleaned[key] = _scrub_mapping(value, sensitive)
        else:
            cleaned[key] = value
    return cleaned


def scrub_event(event: dict[str, Any]) -> dict[str, Any]:
    request = event.get("request")
    if isinstance(request, dict):
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = _scrub_mapping(headers, SENSITIVE_HEADERS)
        for key in ("cookies", "data", "query_string", "env"):
            if key in request:
                request[key] = REDACTED
    user = event.get("user")
    if isinstance(user, dict):
        # A person's id is permitted (playbook 4.7); nothing else about them is.
        event["user"] = {"id": user.get("id")} if user.get("id") is not None else {}
    for key in ("extra", "contexts", "tags"):
        value = event.get(key)
        if isinstance(value, dict):
            event[key] = _scrub_mapping(value, SENSITIVE_KEYS)
    breadcrumbs = event.get("breadcrumbs")
    if isinstance(breadcrumbs, dict) and isinstance(breadcrumbs.get("values"), list):
        for crumb in breadcrumbs["values"]:
            if isinstance(crumb, dict) and isinstance(crumb.get("data"), dict):
                crumb["data"] = _scrub_mapping(crumb["data"], SENSITIVE_KEYS)
    return event


def before_send(event: Event, hint: Hint) -> Event | None:
    return cast(Event, scrub_event(cast(dict[str, Any], event)))


def before_send_transaction(event: Event, hint: Hint) -> Event | None:
    return cast(Event, scrub_event(cast(dict[str, Any], event)))
