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

There is no `e2e_exempt` here, which the auth buckets need. A journey searches a handful
of times, not sixty, so these limits are never in a journey's way, and exempting them
would leave the thing they protect untested against the real stack.
"""

from __future__ import annotations

import uuid

from django.conf import settings

from apps.identity.rate_limit import enforce

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
