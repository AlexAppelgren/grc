"""Sentry event scrubbers (playbook 11.2). Both hooks exist because transactions bypass
`before_send`; the last repo sampled 10% of traces and each carried the request it
came from. Personal data beyond a person's id, and any tenant content, never leaves.

Kept free of Django imports so settings.py can import it before apps load; it imports
only sentry_sdk's type aliases.
"""

from __future__ import annotations

import re
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
        # Django's request and security loggers pass the request itself, whose repr is the
        # full path with the query string.
        "request",
    }
)
REDACTED = "[redacted]"
_TOKEN_PATH = re.compile(r"(/auth/invitations/)[^/?#]+")
# A query string attached to a path or URL, and anything shaped like an IPv4 or IPv6
# address (a clock time with seconds matches too, which costs nothing). IPv4 goes first,
# or the IPv6 pattern would take the first octet of `::ffff:198.51.100.9` and leave the rest.
_QUERY = re.compile(r"(?<=\S)\?[^\s\"'<>]+")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6 = re.compile(r"(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])")


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


def scrub_url(url: str) -> str:
    """A path can carry a credential. The invitation token used to, in
    `/auth/invitations/{token}/open` (finding F6); since F29 it rides in the body and no
    route takes it in a path, so this stays as defence in depth against a stale link."""
    return _TOKEN_PATH.sub(rf"\1{REDACTED}", url)


def scrub_message(message: str) -> str:
    """A log line recorded as a breadcrumb can hold a request line: gunicorn's access line
    did, search text and client address included (security review 2026-09-19)."""
    scrubbed = _QUERY.sub(f"?{REDACTED}", scrub_url(message))
    return _IPV6.sub(REDACTED, _IPV4.sub(REDACTED, scrubbed))


def scrub_event(event: dict[str, Any]) -> dict[str, Any]:
    request = event.get("request")
    if isinstance(request, dict):
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = _scrub_mapping(headers, SENSITIVE_HEADERS)
        for key in ("cookies", "data", "query_string", "env"):
            if key in request:
                request[key] = REDACTED
        if isinstance(request.get("url"), str):
            request["url"] = scrub_url(request["url"])
    user = event.get("user")
    if isinstance(user, dict):
        # A person's id is permitted (playbook 4.7); nothing else about them is.
        event["user"] = {"id": user.get("id")} if user.get("id") is not None else {}
    for key in ("extra", "contexts", "tags"):
        value = event.get(key)
        if isinstance(value, dict):
            event[key] = _scrub_mapping(value, SENSITIVE_KEYS)
    exception = event.get("exception")
    if isinstance(exception, dict) and isinstance(exception.get("values"), list):
        for value in exception["values"]:
            # A database error's message holds row values (`DETAIL: Failing row contains
            # (...)`, security review 2026-09-19). Type, module and frames say where.
            if isinstance(value, dict) and "value" in value:
                value["value"] = REDACTED
    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        # The template stays; whatever logging interpolated into it does not.
        if logentry.pop("params", None):
            logentry.pop("formatted", None)
        for key in ("message", "formatted"):
            if isinstance(logentry.get(key), str):
                logentry[key] = scrub_message(logentry[key])
    breadcrumbs = event.get("breadcrumbs")
    if isinstance(breadcrumbs, dict) and isinstance(breadcrumbs.get("values"), list):
        for crumb in breadcrumbs["values"]:
            if not isinstance(crumb, dict):
                continue
            if isinstance(crumb.get("data"), dict):
                crumb["data"] = _scrub_mapping(crumb["data"], SENSITIVE_KEYS)
            if isinstance(crumb.get("message"), str):
                crumb["message"] = scrub_message(crumb["message"])
    return event


def before_send(event: Event, hint: Hint) -> Event | None:
    return cast(Event, scrub_event(cast(dict[str, Any], event)))


def before_send_transaction(event: Event, hint: Hint) -> Event | None:
    return cast(Event, scrub_event(cast(dict[str, Any], event)))
