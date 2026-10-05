"""The caps wave 4 made settings refuse to boot outside their range (CLAUDE.md section 12:
every threshold is a setting with an env override, and one no value turns off). Each is
proven by running `config/settings.py` again with the one variable out of range."""

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

    def test_the_defaults_boot(self) -> None:
        names = ("TENANT_LIST_MAX_ROWS", "DIGEST_MAX_ITEMS", "SCOPE_ITEM_DESCRIPTION_MAX_CHARS", "AGENT_BEAT_INTERVAL_MINUTES")
        with mock.patch.dict(os.environ, {}, clear=False):
            for name in names:
                os.environ.pop(name, None)
            loaded = runpy.run_path(str(SETTINGS))
        self.assertEqual((loaded["TENANT_LIST_MAX_ROWS"], loaded["DIGEST_MAX_ITEMS"]), (500, 20))
