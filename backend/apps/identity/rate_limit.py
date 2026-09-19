"""Rate limiting on the auth ceremonies (playbook 11.2, ID-02): per address and per IP,
fixed windows in the cache, off in tests except the one test that proves it fires
(RATE_LIMITING_ENABLED, config/test_settings.py override 6). A hit answers 429
`rate_limited` in the problem shape."""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.core.cache import cache

from apps.shared.errors import ProblemError


def _cache_key(bucket: str, key: str) -> str:
    # The key is hashed so an address never appears in the cache backend as itself.
    return f"rl:{bucket}:{hashlib.sha256(key.encode('utf-8')).hexdigest()}"


def enforce(bucket: str, key: str, limit: int, window_seconds: int, *, e2e_exempt: bool = False) -> None:
    """`e2e_exempt=True` marks the steps a journey repeats from one address in a run (code
    request and verify, invitation open, passkey sign-in options and verify; a full run
    signs in from localhost well over the per-minute limit, and the sign-in verify step
    was left out until it failed ADM-S3 on 2026-09-19): they are unlimited under E2E_MODE, which
    a deployed environment refuses at boot (playbook 8.3: "off in tests except the one
    test that proves it fires", and that test sets E2E_MODE=False explicitly)."""
    if not settings.RATE_LIMITING_ENABLED or not key:
        return
    if e2e_exempt and settings.E2E_MODE:
        return
    cache_key = _cache_key(bucket, key)
    cache.add(cache_key, 0, timeout=window_seconds)
    try:
        count = cache.incr(cache_key)
    except ValueError:
        # The key expired between add and incr; start a fresh window.
        cache.set(cache_key, 1, timeout=window_seconds)
        count = 1
    if count > limit:
        raise ProblemError(status=429, code="rate_limited", detail="Too many attempts. Try again later.")
