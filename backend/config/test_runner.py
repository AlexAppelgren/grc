"""The suite's runner: Django's own, able to run one shard of the suite (CI, D-90).

CI splits the backend suite across parallel jobs so a push is answered in minutes, not a
quarter of an hour. With `TEST_SHARD=i/N` set, the runner discovers the whole suite as
usual, deals every test module to exactly one of N shards and runs the modules dealt to
shard i. Because the deal is made from the modules Django itself discovered, the N shards
together are always the whole suite; `TEST_SHARD_REPORT` names a file where the shard
writes what it found and what it kept, and `scripts/test_shards_check.py` fails the build
unless the reports of all N shards add up to everything discovered, each module once.
Unset, the runner is Django's, unchanged, which is how `prepush.sh` and a laptop run it.

Modules are dealt heaviest first to the lightest shard (longest processing time first),
weighed by their measured seconds in `scripts/test_module_seconds.json`. A module not
measured yet weighs the median, so a new test file lands somewhere sensible until the
weights are measured again.
"""

from __future__ import annotations

import json
import os
import statistics
import unittest
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from django.test.runner import DiscoverRunner

WEIGHTS_FILE = Path(__file__).resolve().parent.parent / "scripts" / "test_module_seconds.json"
# A module that failed to import is reported by unittest under this module name; sharding
# stops then, so every shard shows the failure instead of one shard hiding it.
FAILED_IMPORT_MODULE = "unittest.loader"


def iter_tests(suite: unittest.TestSuite | unittest.TestCase) -> Iterator[unittest.TestCase]:
    """Every test case in a suite of suites, in order."""
    if isinstance(suite, unittest.TestCase):
        yield suite
        return
    for item in suite:
        yield from iter_tests(item)


def parse_shard(value: str) -> tuple[int, int]:
    """`i/N` with 1 <= i <= N, as the CI matrix writes it."""
    index, _, count = value.partition("/")
    shard, total = int(index), int(count)
    if not 1 <= shard <= total:
        raise ValueError(f"TEST_SHARD must read i/N with 1 <= i <= N, not {value!r}")
    return shard, total


def deal(modules: list[str], weights: dict[str, float], count: int) -> dict[str, int]:
    """Each module's shard, 0-based: heaviest first onto the lightest shard, ties by name."""
    default = statistics.median(weights.values()) if weights else 1.0
    loads = [0.0] * count
    assignment: dict[str, int] = {}
    for module in sorted(modules, key=lambda name: (-weights.get(name, default), name)):
        lightest = min(range(count), key=lambda shard: (loads[shard], shard))
        assignment[module] = lightest
        loads[lightest] += weights.get(module, default)
    return assignment


class ShardingDiscoverRunner(DiscoverRunner):
    def build_suite(self, test_labels: Any = None, **kwargs: Any) -> Any:
        setting = os.environ.get("TEST_SHARD", "")
        if not setting:
            return super().build_suite(test_labels, **kwargs)
        shard, total = parse_shard(setting)
        discover_kwargs: dict[str, str] = {}
        if self.pattern is not None:
            discover_kwargs["pattern"] = self.pattern
        if self.top_level is not None:
            discover_kwargs["top_level_dir"] = self.top_level
        found = [
            test
            for label in (test_labels or ["."])
            for test in iter_tests(self.load_tests_for_label(label, discover_kwargs))
        ]
        per_module: dict[str, int] = {}
        for test in found:
            module = type(test).__module__
            per_module[module] = per_module.get(module, 0) + 1
        if FAILED_IMPORT_MODULE in per_module:
            return super().build_suite(test_labels, **kwargs)
        weights = json.loads(WEIGHTS_FILE.read_text(encoding="utf-8")) if WEIGHTS_FILE.exists() else {}
        assignment = deal(sorted(per_module), weights, total)
        mine = sorted(module for module, index in assignment.items() if index == shard - 1)
        report = os.environ.get("TEST_SHARD_REPORT")
        if report:
            Path(report).write_text(
                json.dumps(
                    {
                        "shard": shard,
                        "of": total,
                        "found": len(found),
                        "kept": sum(per_module[module] for module in mine),
                        "modules": mine,
                    },
                    indent=1,
                ),
                encoding="utf-8",
            )
        self.log(f"Shard {shard}/{total}: {len(mine)} of {len(per_module)} test modules.")
        if not mine:
            return self.test_suite([])
        return super().build_suite(mine, **kwargs)
