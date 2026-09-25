"""What one caller may spend on search and on Ask in a minute (NFR-02, playbook 11.2).

Both routes cost more than an ordinary read. A search runs two legs and a reranker over
the whole index; Ask adds a model call on top of that, which costs money as well as time.
A bucket per caller is what keeps one runaway client — a script behind a person's session,
an agent in a retry loop — from spending the budget every other reader is measured
against, and it is per caller rather than per bank so that one busy colleague does not
lock the bank out.

The mechanics are the auth ceremonies' (`apps.identity.rate_limit.enforce`): a fixed
window in the cache, keyed on a hash of the caller's id so no id sits in the cache as
itself, and a hit answers 429 `rate_limited` in the problem shape. Nothing of what the
caller typed reaches the key or the refusal: the caller's own id is all that travels
(playbook 4.7).

**Open Ask streams are capped as well as counted** (hardening H47). The rate bounds how
often a caller asks, not how long each answer holds a server thread: a stream lasts until
the model finishes, up to `LLM_DEADLINE_S`, so a few callers could hold every thread for
every bank. `ask_stream_slot` takes one of `ASK_STREAMS_PER_USER` slots before the first
byte and hands back the function that gives it back, which the stream calls when it
closes. It is keyed on a caller id like the buckets, so an agent's key can hold slots of
its own under the same counter. A worker lost mid-stream never gives its slot back; the
counter expires `ASK_STREAM_SLOT_TTL_S` after the caller's last take, which is longer than
any model call can run, so a lost slot is lost for minutes, not for ever.

There is no `e2e_exempt` here, which the auth buckets need. A journey searches a handful
of times, not sixty, so these limits are never in a journey's way, and exempting them
would leave the thing they protect untested against the real stack.
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
