"""What one caller may spend on search and on Ask in a minute (NFR-02, playbook 11.2).

Both cost more than an ordinary read, and Ask costs money. A bucket per caller (not per bank,
so one busy colleague cannot lock the bank out) stops one runaway client from spending
everyone's budget. Mechanics are `apps.identity.rate_limit.enforce`: a fixed window keyed on
a hash of the caller's id, 429 `rate_limited`; nothing the caller typed reaches the key.

Open Ask streams are capped too (H47): a stream holds a server thread until the model
finishes. `ask_stream_slot` takes one of `ASK_STREAMS_PER_USER` slots and returns its
release; a lost slot expires `ASK_STREAM_SLOT_TTL_S` after the caller's last take.

No `e2e_exempt`: a journey searches a handful of times, and exempting these would leave
them untested on the real stack.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable

from django.conf import settings
from django.core.cache import cache

from apps.identity.rate_limit import enforce
from apps.shared.errors import ProblemError

WINDOW_SECONDS = 60


def search_bucket(caller_id: uuid.UUID) -> None:
    """`POST /search` and `POST /search/similar`. One bucket, whoever is calling: the
    caller is a person's session or an agent's key, and neither may spend the other's
    share."""
    enforce("search", str(caller_id), settings.SEARCH_RATE_PER_USER_PER_MINUTE, WINDOW_SECONDS)


def ask_bucket(caller_id: uuid.UUID) -> None:
    """`POST /ask`. Tighter than search, because every call that gets past here is a model
    call (D-07), and the tenant pays for it."""
    enforce("ask", str(caller_id), settings.ASK_RATE_PER_USER_PER_MINUTE, WINDOW_SECONDS)


def ask_stream_slot(caller_id: uuid.UUID) -> Callable[[], None]:
    """One of the caller's open Ask streams, or 429 `rate_limited` when all are taken.
    Returns the release, which gives the slot back once however often it is called."""
    if not settings.RATE_LIMITING_ENABLED:
        return lambda: None
    key = f"streams:ask:{hashlib.sha256(str(caller_id).encode('utf-8')).hexdigest()}"
    cache.add(key, 0, timeout=settings.ASK_STREAM_SLOT_TTL_S)
    try:
        taken = cache.incr(key)
    except ValueError:
        # The counter expired between add and incr; this is the only open stream.
        cache.set(key, 1, timeout=settings.ASK_STREAM_SLOT_TTL_S)
        taken = 1
    cache.touch(key, timeout=settings.ASK_STREAM_SLOT_TTL_S)
    released = False

    def release() -> None:
        nonlocal released
        if released:
            return
        released = True
        try:
            if cache.decr(key) < 0:
                cache.delete(key)
        except ValueError:
            pass  # the counter expired while the stream was open: nothing is held

    if taken > settings.ASK_STREAMS_PER_USER:
        release()
        raise ProblemError(
            status=429, code="rate_limited", detail="You already have answers on their way. Try again when one has finished."
        )
    return release
