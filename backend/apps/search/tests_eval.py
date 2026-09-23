"""The evaluation retriever's database (SRC-05): never the development one.

`apps.search.eval.Retriever` seeds the fixture library before it answers a question, so
the database it seeds is the whole safety of running it. Inside the test runner it is the
runner's throwaway database; from the command line it is one of its own, made by Django's
test machinery under a name nothing else uses and dropped when the process ends. SRC-S8
proves the first path by running; this pins the second, which a test process cannot take
for real without making a database inside a database's test run.
"""

from __future__ import annotations

from unittest import mock

from django.db import connection
from django.test import SimpleTestCase

from apps.search.eval import _throwaway_database


class ThrowawayDatabaseTests(SimpleTestCase):
    """The connection's name is set per test: a run of these tests alone creates no test
    database at all, so the name the runner left behind cannot be relied on either way."""

    def test_inside_the_test_runner_the_runners_database_is_used(self) -> None:
        with (
            mock.patch.dict(connection.settings_dict, {"NAME": "test_compliance_watch_wt3"}),
            mock.patch.object(connection.creation, "create_test_db") as create,
        ):
            _throwaway_database()

        create.assert_not_called()

    def test_from_the_command_line_a_database_of_its_own_is_made_and_dropped(self) -> None:
        development = {"NAME": "compliance_watch_wt3", "TEST": dict(connection.settings_dict["TEST"], NAME=None)}
        with (
            mock.patch.dict(connection.settings_dict, development),
            mock.patch.object(connection.creation, "create_test_db") as create,
            mock.patch("atexit.register") as at_exit,
        ):
            _throwaway_database()
            scratch = connection.settings_dict["TEST"]["NAME"]

        self.assertEqual(scratch, "test_compliance_watch_wt3_search_eval")
        create.assert_called_once_with(verbosity=0, autoclobber=True)
        at_exit.assert_called_once_with(connection.creation.destroy_test_db, "compliance_watch_wt3", verbosity=0)
