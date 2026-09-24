#!/usr/bin/env bash
# Ship: `main` reaches GitHub only through the real CI (ADR 0015, amendment of 2026-09-19).
#
#   bash scripts/ship.sh
#
# 1. Refuses unless this is the main checkout on `main`, clean, and ahead of origin/main.
# 2. Runs the local tiered gates without the heavy ones (scripts/prepush.sh --quick).
# 3. Pushes HEAD to origin/candidate. `candidate` only ever holds the next candidate for main.
# 4. Starts ci.yml and codeql.yml on `candidate` by hand. A manual run is a full run in ci.yml:
#    every gate and the full E2E suite, like the nightly one. Waits for both, on this commit.
# 5. Only when both are green, pushes the same commit to origin/main (a fast-forward).
#
# The heavy gates then run on GitHub's runners instead of this laptop, and main never holds a
# commit that CI has not passed. A newer ship cancels an older one's CI run (ci.yml concurrency);
# the older ship then stops without touching main. Takes 20 to 40 minutes: run it in the background.
set -euo pipefail
die() { echo "ship: $*" >&2; exit 1; }
say() { echo "ship: $*"; }

root="$(git rev-parse --show-toplevel)"; cd "$root"
main="$(git worktree list --porcelain | awk '/^worktree /{print substr($0,10); exit}')"
[ "$(cd "$main" && pwd -P)" = "$(pwd -P)" ] || die "run this from the main checkout, not a worktree"
[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || die "HEAD is not main"
[ -z "$(git status --porcelain)" ] || die "the working tree is not clean; commit or stash first"
git fetch -q origin main
sha="$(git rev-parse HEAD)"
git merge-base --is-ancestor origin/main "$sha" || die "main does not descend from origin/main; rebase first"
[ "$sha" != "$(git rev-parse origin/main)" ] || die "nothing to ship: origin/main is already at ${sha:0:7}"

say "local gates (quick) for ${sha:0:7}"
bash scripts/prepush.sh --quick

say "pushing ${sha:0:7} to origin/candidate"
git push -q --force origin "$sha:refs/heads/candidate"   # a slot for the next candidate, never history

since="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
for wf in ci.yml codeql.yml; do gh workflow run "$wf" --ref candidate; done

run_id() { # run_id <workflow>: the manual run on candidate for this commit, started after $since
  gh run list --workflow "$1" --branch candidate --event workflow_dispatch --limit 10 \
    --json databaseId,headSha,createdAt \
    --jq "[.[] | select(.headSha == \"$sha\" and .createdAt >= \"$since\")][0].databaseId // empty"
}
declare -A ids
for wf in ci.yml codeql.yml; do
  for _ in $(seq 1 30); do ids[$wf]="$(run_id "$wf")"; [ -n "${ids[$wf]}" ] && break; sleep 4; done
  [ -n "${ids[$wf]}" ] || die "no $wf run appeared on candidate for ${sha:0:7}"
  say "$wf run ${ids[$wf]}: $(gh run view "${ids[$wf]}" --json url --jq .url)"
done

failed=0
for wf in ci.yml codeql.yml; do
  if gh run watch "${ids[$wf]}" --interval 5 --exit-status >/dev/null 2>&1; then
    say "$wf green"
  else
    failed=1
    say "$wf NOT green: $(gh run view "${ids[$wf]}" --json conclusion --jq .conclusion)"
    gh run view "${ids[$wf]}" --json jobs \
      --jq '.jobs[] | select(.conclusion != "success" and .conclusion != "skipped") | "  \(.name): \(.conclusion)"'
  fi
done
[ "$failed" = 0 ] || die "main stays at $(git rev-parse --short origin/main); fix, commit, ship again"

say "CI and CodeQL green on ${sha:0:7}; moving origin/main"
git push -q origin "$sha:refs/heads/main"
say "shipped ${sha:0:7} to main"
