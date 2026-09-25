"""A query string carries what a person typed (`GET /obligations?q=...`), so no log line
may hold one (CLAUDE.md section 5: tenant content never reaches logs). Security review
2026-09-19: gunicorn's default access format printed the request line, query included,
with the client address, referrer and user agent, on every request. The Sentry side is
in tests_middleware.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


ENTRYPOINT = Path(settings.BASE_DIR) / "docker-entrypoint.sh"
# Gunicorn 26.2.0 atoms that hold nothing a caller chose beyond the path. Everything else
# is refused: r (request line) and q (query), h (client address), u (Basic auth user),
# f (referrer), a (user agent), any request header ({...}i), any environ variable
# ({...}e, QUERY_STRING is one) and any response header but the request id ({...}o: a
# Location or Content-Disposition can carry a query or a file name).
SAFE_ATOMS = frozenset({"m", "U", "H", "s", "b", "B", "T", "M", "D", "L", "t", "p", "l", "{x-request-id}o"})


def _gunicorn_args() -> list[str]:
    script = ENTRYPOINT.read_text(encoding="utf-8").replace("\\\n", " ")
    command = next(line for line in script.splitlines() if line.strip().startswith("exec gunicorn "))
    return shlex.split(command)


def _option(args: list[str], name: str) -> str | None:
    for index, arg in enumerate(args):
        if arg == name:
            return args[index + 1]
        if arg.startswith(f"{name}="):
            return arg.split("=", 1)[1]
    return None


class GunicornAccessLog(SimpleTestCase):
    def test_the_access_log_format_holds_no_query_address_referrer_or_agent(self) -> None:
        args = _gunicorn_args()
        log_format = _option(args, "--access-logformat")
        if _option(args, "--access-logfile") is not None:
            self.assertIsNotNone(
                log_format, "gunicorn's default format prints the request line, query included"
            )
        if log_format is not None:
            atoms = re.findall(r"%\((.*?)\)s", log_format)
            self.assertIn("U", atoms)
            self.assertIn("{x-request-id}o", atoms)
            self.assertEqual(set(atoms) - SAFE_ATOMS, set(), log_format)

