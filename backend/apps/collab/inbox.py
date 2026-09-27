"""A person's notification inbox (COL-02): their own rows, newest first, and marking them
read.

The contract is declared ahead of the logic (CHUNK10_TASKS rule 3), so each function here
answers 501 `not_built` behind the route's real gate until `c10-notifications-api-b` fills
it. The route has already refused a caller without a member session in a bank.
"""

from __future__ import annotations

from typing import NoReturn

from apps.shared.errors import ProblemError


def list_notifications() -> NoReturn:
    """`GET /notifications`. Built by `c10-notifications-api-b`."""
    raise ProblemError(status=501, code="not_built", detail="The notification inbox is not built yet.")


def mark_read() -> NoReturn:
    """`POST /notifications/{notificationId}/read`. Built by `c10-notifications-api-b`."""
    raise ProblemError(status=501, code="not_built", detail="Marking a notification read is not built yet.")


def mark_all_read() -> NoReturn:
    """`POST /notifications/read-all`. Built by `c10-notifications-api-b`."""
    raise ProblemError(status=501, code="not_built", detail="Marking every notification read is not built yet.")
