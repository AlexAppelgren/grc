"""Settings refuse to boot outside their range (CLAUDE.md section 12: every threshold is a
setting with an env override, and one no value turns off). Each is proven by running
`config/settings.py` again with the one variable out of range, and the refusal names the
variable and the bound it broke (review 2026-11-11 B-6, L-16)."""

from __future__ import annotations

import os
import runpy
from pathlib import Path
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

SETTINGS = Path(__file__).resolve().parents[2] / "config" / "settings.py"


class OutOfRangeCapsRefuseToBoot(SimpleTestCase):
    def test_each_cap_out_of_range_refuses_to_boot_and_names_itself(self) -> None:
        cases = {
            "TENANT_LIST_MAX_ROWS": ["0"],
            "DIGEST_MAX_ITEMS": ["0", "101"],
            "SCOPE_ITEM_DESCRIPTION_MAX_CHARS": ["0"],
            "AGENT_BEAT_INTERVAL_MINUTES": ["0"],
            "AGENT_RUNS_PER_BEAT": ["0"],
            "AGENT_RECENT_RUNS": ["0", "101"],
            "AGENT_RUN_BUDGET_LIMIT": ["0", "NaN", "five"],
            # public-registers (TEN-07, TEN-08)
            "REGISTERS_PROVIDER": ["gleif"],
            "REGISTERS_GLEIF_URL": ["http://api.gleif.org/api/v1"],
            "REGISTERS_FI_URL": ["ftp://www.fi.se/"],
            "REGISTERS_TIMEOUT_SECONDS": ["0", "121"],
            "REGISTERS_MAX_BYTES": ["9999", "50000001"],
            "REGISTERS_MAX_ENTITIES": ["0", "501"],
            "REGISTERS_MAX_BRANCHES": ["-1", "201"],
            "REGISTERS_RECHECK_HOUR": ["-1", "24"],
            "REGISTERS_JOB_SECONDS": ["29", "3601"],
        }
        for name, values in cases.items():
            for value in values:
                with self.subTest(setting=name, value=value), mock.patch.dict(os.environ, {name: value}):
                    with self.assertRaisesMessage(ImproperlyConfigured, name):
                        runpy.run_path(str(SETTINGS))

    def test_each_bound_refuses_one_past_it_and_boots_on_it(self) -> None:
        """Review 2026-11-11 L-16: the security-relevant thresholds had no bound at all. Each
        row is (variable, below or above, the bound): one past the bound refuses and names
        both, the bound itself boots."""
        bounds = [
            ("ENROLMENT_CODE_MAX_ATTEMPTS", "minimum", 1),
            ("ENROLMENT_CODE_MAX_ATTEMPTS", "maximum", 10),
            ("ENROLMENT_CODE_DIGITS", "minimum", 6),
            ("ENROLMENT_CODE_TTL_MINUTES", "maximum", 60),
            ("ENROLMENT_CODE_RATE_PER_ADDRESS_PER_HOUR", "minimum", 1),
            ("ENROLMENT_CODE_RATE_PER_IP_PER_HOUR", "minimum", 1),
            ("AUTH_RATE_PER_IP_PER_MINUTE", "minimum", 1),
            ("AUTH_RATE_PER_IP_PER_MINUTE", "maximum", 1000),
            ("STEP_UP_FRESHNESS_MINUTES", "minimum", 1),
            ("STEP_UP_FRESHNESS_MINUTES", "maximum", 15),
            ("SESSION_ABSOLUTE_HOURS_MAX", "maximum", 168),
            ("SESSION_IDLE_MINUTES_MAX", "maximum", 1440),
            ("SESSION_IDLE_MINUTES_MIN", "minimum", 11),  # it must outlast the 10-minute access token
            ("SUPPORT_ACCESS_MAX_HOURS", "minimum", 1),
            ("SUPPORT_ACCESS_MAX_HOURS", "maximum", 72),
            ("SUPPORT_ACCESS_REQUEST_TTL_HOURS", "maximum", 168),
            ("INVITATION_TTL_HOURS", "maximum", 720),
            ("EVIDENCE_MAX_BYTES", "minimum", 1),
            ("EVIDENCE_MAX_BYTES", "maximum", 512 * 1024 * 1024),
            ("CHALLENGE_TTL_SECONDS", "minimum", 10),
            ("CHALLENGE_TTL_SECONDS", "maximum", 600),
            ("OUTBOX_MAX_ATTEMPTS", "minimum", 1),
            ("TRUSTED_PROXY_HOPS", "maximum", 5),
            ("API_PAGE_SIZE_DEFAULT", "maximum", 100),  # no larger than API_PAGE_SIZE_MAX
            ("ASK_STREAMS_PER_USER", "minimum", 1),
            ("LIBRARY_DIFF_MAX_SENTENCES", "maximum", 200),
            ("WORKFLOW_TRIAGE_TARGET_HOURS", "maximum", 720),
        ]
        for name, side, bound in bounds:
            past = bound - 1 if side == "minimum" else bound + 1
            with self.subTest(setting=name, value=past), mock.patch.dict(os.environ, {name: str(past)}):
                with self.assertRaisesMessage(ImproperlyConfigured, f"{name} is {past}, {'below' if side == 'minimum' else 'above'} its {side} of {bound}"):
                    runpy.run_path(str(SETTINGS))
            with self.subTest(setting=name, value=bound), mock.patch.dict(os.environ, {name: str(bound)}):
                self.assertEqual(runpy.run_path(str(SETTINGS))[name], bound)

    def test_a_choice_outside_its_list_and_a_float_outside_its_range_refuse(self) -> None:
        """Review 2026-11-11 B-6: a provider name nobody built is refused at boot, not at first
        use, and a fraction outside 0 to 1 or a non-number never reaches the SDK."""
        refused = {
            "AGENT_RUNNER": "lambda",
            "LLM_PROVIDER": "openai",
            "STORAGE_BACKEND": "disk",
            "WORKFLOW_DIGEST_WEEKDAY": "funday",
            "SENTRY_TRACES_SAMPLE_RATE": "1.5",
            "SEARCH_CONCEPT_SCORE_FLOOR": "nan",
            "HEALTH_CACHE_SECONDS": "61",
        }
        for name, value in refused.items():
            with self.subTest(setting=name, value=value), mock.patch.dict(os.environ, {name: value}):
                with self.assertRaisesMessage(ImproperlyConfigured, name):
                    runpy.run_path(str(SETTINGS))

    def test_the_defaults_boot(self) -> None:
        names = ("TENANT_LIST_MAX_ROWS", "DIGEST_MAX_ITEMS", "SCOPE_ITEM_DESCRIPTION_MAX_CHARS", "AGENT_BEAT_INTERVAL_MINUTES")
        with mock.patch.dict(os.environ, {}, clear=False):
            for name in names:
                os.environ.pop(name, None)
            loaded = runpy.run_path(str(SETTINGS))
        self.assertEqual((loaded["TENANT_LIST_MAX_ROWS"], loaded["DIGEST_MAX_ITEMS"]), (500, 20))
