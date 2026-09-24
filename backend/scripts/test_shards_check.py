"""Guard: the CI shards of the backend suite add up to the whole suite (D-90).

Each shard of `manage.py test` under `TEST_SHARD=i/N` writes a report of what Django
discovered and what the shard kept (`config/test_runner.py`). This reads every report
and fails unless there is one per shard, all shards saw the same suite, no module ran in
two shards, and the tests kept add up to the tests found. A shard that was skipped,
cancelled or given a different split therefore fails the build instead of quietly
leaving tests unrun.

    python scripts/test_shards_check.py <directory holding shard-*.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def problems(reports: list[dict[str, object]]) -> list[str]:
    if not reports:
        return ["no shard report found"]
    totals = {int(str(report["of"])) for report in reports}
    found = {int(str(report["found"])) for report in reports}
    if len(totals) != 1 or len(found) != 1:
        return [f"shards disagree on the split or the suite: of={sorted(totals)}, found={sorted(found)}"]
    total, suite = totals.pop(), found.pop()
    out = []
    shards = sorted(int(str(report["shard"])) for report in reports)
    if shards != list(range(1, total + 1)):
        out.append(f"expected shards 1..{total}, got {shards}")
    seen: dict[str, int] = {}
    for report in reports:
        for module in report["modules"]:  # type: ignore[attr-defined]
            if module in seen:
                out.append(f"{module} ran in shards {seen[module]} and {report['shard']}")
            seen[module] = int(str(report["shard"]))
    kept = sum(int(str(report["kept"])) for report in reports)
    if kept != suite:
        out.append(f"the shards kept {kept} tests, discovery found {suite}")
    return out


def main(directory: str) -> int:
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(Path(directory).glob("shard-*.json"))]
    found = problems(reports)
    if found:
        print("test_shards_check: the shards do not add up to the whole suite:")
        for problem in found:
            print(f"  {problem}")
        return 1
    print(f"test_shards_check: {len(reports)} shards ran all {reports[0]['found']} tests, each module once")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
