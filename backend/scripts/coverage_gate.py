#!/usr/bin/env python
"""Per-module coverage floors (playbook 8.2). Run after `coverage run ... && coverage report`.

Floors sit just below measured coverage with a margin sized to the module: minus 2 at
400+ statements, minus 3 at 100 to 400, minus 4 below 100. Never lowered to go green;
raised when a module climbs away. The measured value, the statement count and the date sit
beside each floor and are restated whenever this file is touched.

The gate refuses to judge a partial run: if the aggregate sits more than
PARTIAL_RUN_MARGIN points under the global floor in pyproject.toml, the suite was
subsetted and the question is wrong, so the answer is "cannot judge" (exit 2), not pass.
"""

from __future__ import annotations

import json
import sys
import tempfile
import tomllib
from pathlib import Path

import coverage

BACKEND = Path(__file__).resolve().parent.parent
PARTIAL_RUN_MARGIN = 15.0

# module path (as coverage reports it, forward slashes) -> (floor %, measured %, statements, date)
# Only the modules where a bug costs money, mis-states a statutory figure or lets the wrong
# person through: tenancy, authentication, permissions, audit, health, the role guard.
FLOORS: dict[str, tuple[int, int, int, str]] = {
    "apps/shared/tenancy.py": (96, 100, 85, "2026-09-19"),
    "apps/shared/authentication.py": (96, 100, 55, "2026-09-19"),
    "apps/shared/permissions.py": (97, 99, 142, "2026-09-19"),
    "apps/shared/audit.py": (96, 100, 45, "2026-09-19"),
    "apps/shared/db_role_guard.py": (86, 90, 53, "2026-09-19"),
    "apps/shared/health_check.py": (88, 92, 65, "2026-09-19"),
    "apps/shared/middleware.py": (96, 100, 68, "2026-09-19"),
    # The code and invitation mail leaves through the worker after commit, so a code request
    # takes the same time whether or not it sends (security review F12).
    "apps/identity/tasks.py": (96, 100, 6, "2026-09-19"),
    "apps/shared/adapters/mailer.py": (96, 100, 38, "2026-09-19"),
    "apps/shared/sentry_scrub.py": (89, 93, 41, "2026-09-19"),
    "apps/shared/storage.py": (95, 99, 62, "2026-09-19"),
    "apps/shared/vocabulary.py": (91, 96, 55, "2026-09-19"),
    "apps/shared/e2e_seed.py": (96, 97, 93, "2026-09-19"),
    "config/settings.py": (85, 87, 166, "2026-09-19"),
    # Identity and tenant admin: the modules that let the wrong person through.
    "apps/identity/tokens.py": (94, 98, 84, "2026-09-19"),
    "apps/identity/rate_limit.py": (96, 100, 19, "2026-09-19"),
    "apps/identity/session_logic.py": (92, 95, 160, "2026-09-19"),
    "apps/identity/code_logic.py": (92, 96, 77, "2026-09-19"),
    "apps/identity/invitation_logic.py": (91, 94, 134, "2026-09-19"),
    "apps/identity/passkey_logic.py": (90, 93, 181, "2026-09-19"),
    "apps/identity/api_keys_logic.py": (92, 96, 67, "2026-09-19"),
    "apps/identity/roles_logic.py": (92, 95, 137, "2026-09-19"),
    "apps/identity/members_logic.py": (96, 99, 101, "2026-09-19"),
    "apps/identity/me_logic.py": (89, 93, 45, "2026-09-19"),
    "apps/identity/security_log.py": (89, 93, 22, "2026-09-19"),
    "apps/identity/mail.py": (96, 100, 20, "2026-09-19"),
    "apps/identity/api.py": (95, 98, 215, "2026-09-19"),
    "apps/tenants/logic.py": (87, 91, 91, "2026-09-19"),
    "apps/tenants/api.py": (96, 100, 31, "2026-09-19"),
    # Vocabularies, taxonomy and footprint: matching, retire and merge.
    "apps/taxonomy/api.py": (96, 99, 216, "2026-09-19"),
    "apps/taxonomy/footprint_logic.py": (97, 100, 109, "2026-09-19"),
    "apps/taxonomy/http.py": (93, 96, 103, "2026-09-19"),
    "apps/taxonomy/library_lists_logic.py": (94, 98, 86, "2026-09-19"),
    "apps/taxonomy/matching.py": (96, 100, 31, "2026-09-19"),
    "apps/taxonomy/reading.py": (82, 86, 63, "2026-09-19"),
    "apps/taxonomy/registry.py": (96, 100, 38, "2026-09-19"),
    "apps/taxonomy/repoint.py": (96, 100, 19, "2026-09-19"),
    "apps/taxonomy/tenant_hooks.py": (96, 100, 37, "2026-09-19"),
    "apps/taxonomy/tenant_lists_logic.py": (94, 97, 304, "2026-09-19"),
    "apps/taxonomy/terms_logic.py": (94, 98, 72, "2026-09-19"),
    # Library and inventory: the provision tree, instrument and provision reads, "as of" and
    # diff rules.
    "apps/library/seeds/__init__.py": (96, 100, 22, "2026-09-22"),
    "apps/library/seeds/library.py": (97, 100, 106, "2026-09-22"),
    "apps/library/logic.py": (96, 100, 57, "2026-09-22"),
    "apps/library/api.py": (97, 100, 121, "2026-09-22"),
    "apps/library/reading.py": (95, 98, 322, "2026-09-22"),
    "apps/library/reports.py": (96, 100, 18, "2026-09-22"),
    # Proposals and the console: four eyes, apply, the agent as second principal, standards,
    # library updates and problem reports. `logic.py`'s floor stays 97 as it grew: never lowered.
    "apps/proposals/apply.py": (92, 95, 281, "2026-09-24"),
    "apps/proposals/logic.py": (97, 98, 462, "2026-09-24"),
    "apps/proposals/api.py": (96, 100, 85, "2026-09-24"),
    "apps/proposals/reading.py": (93, 97, 79, "2026-09-24"),
    "apps/proposals/updates.py": (92, 96, 99, "2026-09-24"),
    "apps/proposals/standards.py": (96, 100, 51, "2026-09-24"),
    "apps/governance/problem_reports_logic.py": (90, 94, 73, "2026-09-24"),
    # Watch and the agent API: registration, curation, sources, the keys, the watch
    # door, the "So what?", the case fan-out, runs and the screen, the AI log and the outbox.
    "apps/watch/reading.py": (96, 99, 203, "2026-09-24"),
    "apps/watch/registration.py": (97, 100, 121, "2026-09-24"),
    "apps/watch/curation.py": (96, 99, 256, "2026-09-24"),
    "apps/watch/sources.py": (96, 99, 103, "2026-09-24"),
    "apps/watch/keys.py": (97, 100, 164, "2026-09-24"),
    "apps/watch/write.py": (96, 100, 36, "2026-09-24"),
    "apps/watch/so_what_draft.py": (96, 100, 17, "2026-09-24"),
    "apps/cases/creation.py": (96, 100, 41, "2026-09-24"),
    "apps/cases/so_what.py": (96, 100, 58, "2026-09-24"),
    "apps/cases/links.py": (96, 100, 32, "2026-09-24"),
    "apps/cases/matching.py": (96, 100, 39, "2026-09-24"),
    "apps/agents/runs.py": (94, 97, 117, "2026-09-24"),
    "apps/agents/screen.py": (96, 100, 31, "2026-09-24"),
    "apps/governance/ai_log.py": (96, 100, 48, "2026-09-24"),
    "apps/shared/outbox.py": (96, 100, 97, "2026-09-24"),
    "apps/shared/ai.py": (93, 97, 66, "2026-09-24"),
    # Home, briefing and roadmap: every module of apps/home, the calendar feed first.
    "apps/home/api.py": (96, 100, 84, "2026-09-24"),
    "apps/home/briefing.py": (96, 100, 28, "2026-09-24"),
    "apps/home/calendar.py": (96, 100, 15, "2026-09-24"),
    "apps/home/feed.py": (97, 100, 166, "2026-09-24"),
    "apps/home/logic.py": (96, 100, 37, "2026-09-24"),
    "apps/home/mail.py": (96, 100, 21, "2026-09-24"),
    "apps/home/models.py": (96, 100, 38, "2026-09-24"),
    "apps/home/roadmap.py": (96, 100, 60, "2026-09-24"),
    "apps/home/schemas.py": (96, 100, 98, "2026-09-24"),
    "apps/home/tasks.py": (82, 86, 54, "2026-09-24"),
    # Search and Ask: the hybrid ranking, the index, Ask and the evaluation set.
    "apps/search/api.py": (96, 100, 55, "2026-09-24"),
    "apps/search/ask.py": (96, 99, 147, "2026-09-24"),
    "apps/search/eval_sets.py": (96, 99, 119, "2026-09-24"),
    "apps/search/hybrid.py": (97, 100, 153, "2026-09-24"),
    "apps/search/indexing.py": (94, 97, 148, "2026-09-24"),
    "apps/search/sources.py": (95, 98, 110, "2026-09-24"),
    # Register: applicability, status per entity, gaps, internal links and units, history,
    # the overlay and the agent's register read; organisation, member removal, support
    # access; My work and participants.
    "apps/register/applicability.py": (95, 98, 167, "2026-09-27"),
    "apps/register/status_logic.py": (96, 99, 173, "2026-09-27"),
    "apps/register/gaps.py": (95, 98, 209, "2026-09-27"),
    "apps/register/links.py": (92, 95, 100, "2026-09-27"),
    "apps/register/units.py": (97, 100, 145, "2026-09-27"),
    "apps/register/history.py": (96, 100, 47, "2026-09-27"),
    "apps/register/overlay.py": (96, 100, 79, "2026-09-27"),
    "apps/register/agent_read.py": (93, 97, 66, "2026-09-27"),
    "apps/tenants/organisation.py": (94, 97, 176, "2026-09-27"),
    "apps/tenants/reassignment.py": (95, 98, 130, "2026-09-27"),
    "apps/tenants/support_access.py": (97, 100, 156, "2026-09-27"),
    "apps/home/my_work.py": (96, 99, 299, "2026-09-27"),
    "apps/collab/participants.py": (97, 100, 137, "2026-09-27"),
    # Case workflow: the state machine, triage, assessment, actions, evidence and
    # its scanner, sign-off with four eyes, and the case file.
    "apps/cases/state.py": (96, 100, 42, "2026-09-27"),
    "apps/cases/triage.py": (95, 98, 101, "2026-09-27"),
    "apps/cases/assessment.py": (96, 100, 87, "2026-09-27"),
    "apps/cases/actions.py": (94, 98, 94, "2026-09-27"),
    "apps/cases/evidence.py": (95, 98, 148, "2026-09-27"),
    "apps/cases/signoff.py": (96, 100, 54, "2026-09-27"),
    "apps/cases/case_file.py": (94, 97, 183, "2026-09-27"),
    "apps/cases/logic.py": (93, 97, 72, "2026-09-27"),
    "apps/shared/adapters/scanner.py": (94, 98, 98, "2026-09-27"),
    # Collaboration: comments and who may read them, notifications, reminders,
    # escalation, delegation while away, and tagging.
    "apps/collab/comments.py": (96, 100, 93, "2026-09-27"),
    "apps/collab/subjects.py": (96, 100, 44, "2026-09-27"),
    "apps/collab/me_comments.py": (96, 100, 42, "2026-09-27"),
    "apps/collab/inbox.py": (91, 95, 36, "2026-09-27"),
    "apps/collab/reminders.py": (96, 99, 133, "2026-09-27"),
    "apps/collab/escalation.py": (96, 100, 36, "2026-09-27"),
    "apps/collab/tasks.py": (93, 97, 80, "2026-09-27"),
    "apps/tenants/out_of_office.py": (94, 98, 65, "2026-09-27"),
    "apps/taxonomy/tagging_logic.py": (96, 100, 62, "2026-09-27"),
    # Agents and agent access: the runner's events, run control and the cap,
    # research requests, a bank's agents, platform definitions, re-tag batches, the bank's own
    # queue, what applies, entries, keys and tokens, tenant reach, the access log, the fence
    # on an agent credential, the MCP server and the session policy.
    "apps/agents/runner_events.py": (96, 100, 98, "2026-09-27"),
    "apps/agents/control.py": (96, 100, 64, "2026-09-27"),
    "apps/agents/budget.py": (96, 100, 63, "2026-09-27"),
    "apps/agents/opener.py": (96, 100, 52, "2026-09-27"),
    "apps/agents/requests.py": (89, 92, 234, "2026-09-27"),
    "apps/agents/tenant_agents.py": (96, 99, 155, "2026-09-27"),
    "apps/agents/definitions.py": (96, 100, 90, "2026-09-27"),
    "apps/agents/scope.py": (96, 100, 65, "2026-09-27"),
    "apps/agents/what_applies.py": (93, 97, 81, "2026-09-27"),
    "apps/agents/agent_access.py": (92, 95, 132, "2026-09-27"),
    "apps/proposals/batch.py": (94, 97, 217, "2026-09-27"),
    "apps/proposals/private_controls.py": (85, 89, 44, "2026-09-27"),
    "apps/proposals/tenant_agent.py": (90, 94, 58, "2026-09-27"),
    "apps/identity/personal_tokens.py": (96, 100, 58, "2026-09-27"),
    "apps/governance/access_log.py": (93, 96, 104, "2026-09-27"),
    "apps/governance/reach.py": (93, 97, 85, "2026-09-27"),
    "apps/shared/agent_access_guard.py": (95, 99, 83, "2026-09-27"),
    "apps/integrations/mcp.py": (96, 99, 171, "2026-09-27"),
    "apps/integrations/mcp_tools.py": (94, 98, 80, "2026-09-27"),
    "apps/tenants/security_policy.py": (96, 100, 44, "2026-09-27"),
}


def global_floor() -> float:
    with (BACKEND / "pyproject.toml").open("rb") as fh:
        data = tomllib.load(fh)
    return float(data["tool"]["coverage"]["report"]["fail_under"])


def load_report() -> dict:
    cov = coverage.Coverage(data_file=str(BACKEND / ".coverage"), config_file=str(BACKEND / "pyproject.toml"))
    cov.load()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "coverage.json"
        cov.json_report(outfile=str(out))
        return json.loads(out.read_text(encoding="utf-8"))


def main() -> int:
    report = load_report()
    total = float(report["totals"]["percent_covered"])
    floor = global_floor()
    print(f"aggregate {total:.1f}% (global floor {floor:.0f}%)")
    if total < floor - PARTIAL_RUN_MARGIN:
        print(
            f"coverage_gate: refusing to judge a partial run: aggregate {total:.1f}% is more than "
            f"{PARTIAL_RUN_MARGIN:.0f} points under the global floor. Run the whole suite."
        )
        return 2
    files = {Path(name).as_posix(): data for name, data in report["files"].items()}
    # coverage reports paths relative to the run's cwd (backend/) on every platform.
    normalised = {name.replace("\\", "/"): data for name, data in files.items()}
    failures: list[str] = []
    for module, (module_floor, measured, statements, date) in FLOORS.items():
        data = normalised.get(module)
        if data is None:
            failures.append(f"{module}: not in the coverage report (renamed? deleted?)")
            continue
        percent = float(data["summary"]["percent_covered"])
        mark = "ok" if percent >= module_floor else "BELOW FLOOR"
        print(f"  {module}: {percent:.1f}% (floor {module_floor}, measured {measured} on {date}, {statements} stmts) {mark}")
        if percent < module_floor:
            failures.append(f"{module}: {percent:.1f}% < floor {module_floor}%")
    if total < floor:
        failures.append(f"aggregate {total:.1f}% < global floor {floor:.0f}%")
    if failures:
        print("coverage_gate: FAILED\n  " + "\n  ".join(failures))
        return 1
    print("coverage_gate: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
