"""The release gate's harness and the evaluation retriever's database (SRC-05).

`apps.search.eval.Retriever` seeds the fixture library before it answers a question, so
the database it seeds is the whole safety of running it. Inside the test runner it is the
runner's throwaway database; from the command line it is one of its own, made by Django's
test machinery under a name nothing else uses and dropped when the process ends. SRC-S8
proves the first path by running; this pins the second, which a test process cannot take
for real without making a database inside a database's test run.

The harness's own unit tests (`eval/tests_scoring.py`: the no-answer rule, the line naming
the tracks that do not gate yet, the recording rules) run here too. CI runs
`scripts/search_eval.py` without `--self-test`, so without this nothing that blocks a build
would run them.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
from pathlib import Path
from types import ModuleType
from unittest import mock

from django.conf import settings
from django.db import connection
from django.test import SimpleTestCase

from apps.search.eval import _drop, _throwaway_database


def load_search_eval() -> ModuleType:
    """`scripts/search_eval.py`, loaded from its file the way the gate runs it."""
    script = Path(settings.BASE_DIR) / "scripts" / "search_eval.py"
    spec = importlib.util.spec_from_file_location("search_eval_under_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {spec.name: module}):  # its dataclasses look themselves up
        spec.loader.exec_module(module)
    return module


class ThrowawayDatabaseTests(SimpleTestCase):
    """The connection's name is set per test: a run of these tests alone creates no test
    database at all, so the name the runner left behind cannot be relied on either way."""

    def test_inside_the_test_runner_the_runners_database_is_used(self) -> None:
        with (
            mock.patch.dict(connection.settings_dict, {"NAME": "test_compliance_watch_wt3"}),
            mock.patch("apps.search.eval.setup_databases") as setup,
        ):
            _throwaway_database()

        setup.assert_not_called()

    def test_from_the_command_line_a_database_of_its_own_is_made_and_dropped(self) -> None:
        development = {"NAME": "compliance_watch_wt3", "TEST": dict(connection.settings_dict["TEST"], NAME=None)}
        with (
            mock.patch.dict(connection.settings_dict, development),
            mock.patch("apps.search.eval.setup_databases", return_value=["created"]) as setup,
            mock.patch("atexit.register") as at_exit,
        ):
            _throwaway_database()
            scratch = connection.settings_dict["TEST"]["NAME"]

        self.assertEqual(scratch, f"test_compliance_watch_wt3_search_eval_{os.getpid()}", "a second run beside it is not dropped")
        # The runner's own setup: `default` is created and every mirror of it (the `app`
        # alias, the production role) points at the scratch database, not the named one.
        setup.assert_called_once_with(verbosity=0, interactive=False, aliases={"default": False}, serialized_aliases=set())
        at_exit.assert_called_once_with(_drop, ["created"])

    def test_the_drop_closes_every_session_first(self) -> None:
        calls = mock.Mock()
        with (
            mock.patch("apps.search.eval.connections", calls.connections),
            mock.patch("apps.search.eval.teardown_databases", calls.teardown),
        ):
            _drop([])

        self.assertEqual(calls.mock_calls, [mock.call.connections.close_all(), mock.call.teardown([], verbosity=0)])


class HarnessUnitTests(SimpleTestCase):
    def test_the_harness_passes_its_own_unit_tests(self) -> None:
        gate = load_search_eval()
        output = io.StringIO()
        # The self-test puts eval/ and scripts/ on the path and imports from there; both
        # are put back afterwards, so nothing leaks into the rest of the suite.
        with mock.patch.object(sys, "path", list(sys.path)), mock.patch.dict(sys.modules), contextlib.redirect_stderr(output):
            code = gate.run(["--self-test"])

        self.assertEqual(code, 0, output.getvalue())
        self.assertRegex(output.getvalue(), r"Ran \d+ tests", "the unit tests were found and run")
