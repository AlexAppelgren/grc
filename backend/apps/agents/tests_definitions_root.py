"""Where the shipped agent definitions are read from (AGT-03, c11-e2e-console).

A version is published only from a folder the build ships, `backend/agents/`. The E2E stack
alone may point the reader at a copy of it that also holds the fixture version folders
AGT-S4's journey publishes: `AGENT_DEFINITIONS_DIR` is read only under `E2E_MODE`, which a
deployed environment refuses at boot (tests_production_guard.py, rule 4). Each case imports
the settings module in a fresh interpreter, so the runner's own settings cannot leak in.
"""

from __future__ import annotations

import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase

READ = "import config.settings as s; print(s.AGENT_DEFINITIONS_DIR)"
ELSEWHERE = "/tmp/cw-e2e-agents"  # noqa: S108 a path that is never created, only compared


def _read(**overrides: str) -> str:
    env = {key: value for key, value in os.environ.items() if key not in {"E2E_MODE", "AGENT_DEFINITIONS_DIR"}}
    env.update(overrides)
    done = subprocess.run([sys.executable, "-c", READ], cwd=settings.BASE_DIR, env=env, capture_output=True, text=True, check=True)  # noqa: S603 our own interpreter and a fixed program
    return done.stdout.strip()


class TheDefinitionsRoot(SimpleTestCase):
    def test_it_is_the_shipped_folder_by_default(self) -> None:
        self.assertEqual(_read(), str(settings.BASE_DIR / "agents"))

    def test_outside_e2e_mode_another_folder_is_ignored(self) -> None:
        self.assertEqual(_read(AGENT_DEFINITIONS_DIR=ELSEWHERE), str(settings.BASE_DIR / "agents"))

    def test_the_e2e_stack_may_point_it_at_its_copy(self) -> None:
        self.assertEqual(_read(E2E_MODE="1", AGENT_DEFINITIONS_DIR=ELSEWHERE), ELSEWHERE)
