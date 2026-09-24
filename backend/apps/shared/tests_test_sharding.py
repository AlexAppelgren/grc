"""Guard: CI's shards of the backend suite are the whole suite, each module once (D-90).

`config/test_runner.py` deals the discovered test modules to N shards and
`scripts/test_shards_check.py` fails the build unless the shards' reports add up. These
prove the deal is a partition whatever the weights, and that the check refuses every way a
shard could leave a test unrun: a missing shard, a module run twice, a count that falls
short, and shards that saw different suites.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from django.test import SimpleTestCase

from config.test_runner import deal, parse_shard

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "test_shards_check.py"


def _check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("test_shards_check", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULES = [f"apps.a.tests_{index}" for index in range(23)]


class DealTests(SimpleTestCase):
    def test_every_module_lands_in_exactly_one_shard_for_every_count(self) -> None:
        weights = {name: float(index % 7 + 1) for index, name in enumerate(MODULES[:15])}
        for count in (1, 2, 5, 8, 23, 30):
            assignment = deal(MODULES, weights, count)
            self.assertEqual(sorted(assignment), sorted(MODULES))
            self.assertTrue(all(0 <= shard < count for shard in assignment.values()))

    def test_the_deal_is_the_same_on_every_runner(self) -> None:
        weights = {"apps.a.tests_1": 9.0, "apps.a.tests_2": 9.0}
        self.assertEqual(deal(MODULES, weights, 4), deal(list(reversed(MODULES)), weights, 4))

    def test_the_heaviest_modules_go_to_different_shards(self) -> None:
        weights = {"apps.a.tests_0": 100.0, "apps.a.tests_1": 90.0, "apps.a.tests_2": 1.0}
        assignment = deal(MODULES[:3], weights, 2)
        self.assertNotEqual(assignment["apps.a.tests_0"], assignment["apps.a.tests_1"])

    def test_a_shard_setting_reads_i_of_n_and_refuses_anything_else(self) -> None:
        self.assertEqual(parse_shard("3/8"), (3, 8))
        for bad in ("0/8", "9/8", "3", "a/b"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_shard(bad)


def _report(shard: int, of: int, modules: list[str], kept: int, found: int = 10) -> dict[str, object]:
    return {"shard": shard, "of": of, "found": found, "kept": kept, "modules": modules}


class ShardsCheckTests(SimpleTestCase):
    def test_shards_that_add_up_to_the_suite_pass(self) -> None:
        reports = [_report(1, 2, ["m1", "m2"], 6), _report(2, 2, ["m3"], 4)]
        self.assertEqual(_check().problems(reports), [])

    def test_a_missing_shard_fails(self) -> None:
        self.assertTrue(_check().problems([_report(1, 2, ["m1"], 10)]))

    def test_a_module_run_in_two_shards_fails(self) -> None:
        reports = [_report(1, 2, ["m1", "m2"], 6), _report(2, 2, ["m2"], 4)]
        self.assertIn("m2 ran in shards 1 and 2", _check().problems(reports))

    def test_tests_left_unrun_fail(self) -> None:
        reports = [_report(1, 2, ["m1"], 5), _report(2, 2, ["m2"], 4)]
        self.assertIn("the shards kept 9 tests, discovery found 10", _check().problems(reports))

    def test_shards_that_saw_different_suites_fail(self) -> None:
        reports = [_report(1, 2, ["m1"], 6), _report(2, 2, ["m2"], 5, found=11)]
        self.assertTrue(_check().problems(reports))

    def test_no_report_at_all_fails(self) -> None:
        self.assertEqual(_check().problems([]), ["no shard report found"])
