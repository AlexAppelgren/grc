"""The agents' settings refuse to boot on a value that would make no sense (AGT-03 to AGT-05):
the plan cadence and run hour, the beat and its budget per run, and the research limits.
The settings file is run in this process with the one variable changed, so its guards
are measured as well as proved."""

from __future__ import annotations

import os
import runpy
from unittest import mock

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

SETTINGS_FILE = str(settings.BASE_DIR / "config" / "settings.py")


class AgentSettingsRefuseToBoot(SimpleTestCase):
    def boot(self, variable: str, value: str) -> None:
        with mock.patch.dict(os.environ, {variable: value}):
            runpy.run_path(SETTINGS_FILE)

    def test_each_nonsensical_value_refuses_to_boot(self) -> None:
        refused = {
            "AGENT_MIN_CADENCE": ("hourly", "AGENT_MIN_CADENCE must be daily, weekly or monthly"),
            "AGENT_DEFAULT_RUN_HOUR": ("24", "AGENT_DEFAULT_RUN_HOUR must be an hour from 0 to 23"),
            "AGENT_BEAT_INTERVAL_MINUTES": ("0", "must each be at least 1"),
            "AGENT_RUNS_PER_BEAT": ("0", "must each be at least 1"),
            "AGENT_RUN_BUDGET_LIMIT": ("five euros", "AGENT_RUN_BUDGET_LIMIT must be an amount in EUR above zero"),
            "RESEARCH_URL_MAX_REDIRECTS": ("-1", "RESEARCH_URL_MAX_REDIRECTS at least 0"),
            "RESEARCH_REQUESTS_PER_MONTH": ("0", "The RESEARCH_* settings must be positive"),
        }
        for variable, (value, words) in refused.items():
            with self.subTest(variable=variable), self.assertRaisesMessage(ImproperlyConfigured, words):
                self.boot(variable, value)

    def test_the_defaults_boot(self) -> None:
        self.assertEqual(runpy.run_path(SETTINGS_FILE)["AGENT_MIN_CADENCE"], "weekly")
