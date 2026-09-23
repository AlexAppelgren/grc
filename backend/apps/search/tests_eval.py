"""The evaluation retriever's database (SRC-05): never the development one.

`apps.search.eval.Retriever` seeds the fixture library before it answers a question, so
the database it seeds is the whole safety of running it. Inside the test runner it is the
runner's throwaway database; from the command line it is one of its own, made by Django's
test machinery under a name nothing else uses and dropped when the process ends. SRC-S8
proves the first path by running; this pins the second, which a test process cannot take
for real without making a database inside a database's test run.
"""

from __future__ import annotations

import os
from unittest import mock

from django.db import connection
from django.test import SimpleTestCase

from apps.search.eval import _drop, _throwaway_database


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

