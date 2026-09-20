#!/usr/bin/env bash
# Pre-push gates: runs locally what CI (.github/workflows/ci.yml) and CodeQL
# (.github/workflows/codeql.yml) run, with the same tools, versions, flags and
# thresholds, so a green run here predicts a green run there (CLAUDE.md section 7).
#
#   bash scripts/prepush.sh          the gates for what changed since origin/main
#   bash scripts/prepush.sh --all    every gate, full E2E suite (what the nightly run does)
#   bash scripts/prepush.sh --quick  the fast static gates only (secrets, lockfiles, migration
#                                    drift, lint, types, compliance, requirements and contract
#                                    checks, OpenAPI drift). Test suites, coverage, the
#                                    production build, E2E, CodeQL and image scans are left to
#                                    the real CI, which scripts/ship.sh runs on `candidate`
#                                    before main moves
#
# "Changed" is the committed, uncommitted and untracked work since origin/main. Tiers
# mirror the `changes` job in ci.yml: backend, frontend, lockfiles, containers, and a
# change under .github/ counts as everything. The secret scan always runs. CodeQL runs
# per language whenever a Python or JavaScript/TypeScript file changed.
# Stops at the first failing gate, naming it and the command that reproduces it.
#
# Tools download once into <main checkout>/.tools/ (git-ignored), are verified against
# the SHA-256 each release publishes, and are reused by every worktree. The pins were
# read from the pinned actions on 2026-09-19 (docs/plans/Verification_Log.md):
#   CodeQL 2.27.0      github/codeql-action@1c5b675 (v4.38.1), src/defaults.json bundleVersion
#   gitleaks 8.30.1    ci.yml `secrets` job, GITLEAKS_VERSION
#   osv-scanner 2.6.0  google/osv-scanner-action@a345acf (v2.6.0), image osv-scanner-action:v2.6.0
#   Trivy 0.70.0       aquasecurity/trivy-action@ed142fd (v0.36.0), input `version` default
# When a workflow moves one of those pins, this script stops and says which to update.
# Commands and thresholds are copied from the workflows: change them there and here together.
set -euo pipefail

die() { echo "prepush: $*" >&2; exit 2; }
root="$(git rev-parse --show-toplevel)"
cd "$root"
main="$(git worktree list --porcelain | awk '/^worktree /{print substr($0,10); exit}')"
TOOLS="$(cd "$main" && pwd)/.tools"
[ -f .env.worktree ] && { set -a; . ./.env.worktree; set +a; }   # a worktree's own slot
all=0 quick=0
case "${1:-}" in --all) all=1 ;; --quick) quick=1 ;; "") ;; *) die "usage: bash scripts/prepush.sh [--all|--quick]" ;; esac

pinned() { grep -qF "$2" "$1" || die "$1 no longer pins '$2'; update the matching pin in scripts/prepush.sh"; }
pinned .github/workflows/codeql.yml "github/codeql-action/analyze@1c5b675653bb5c22dbe9b12b556ec555138e09fd"
pinned .github/workflows/ci.yml 'GITLEAKS_VERSION: "8.30.1"'
pinned .github/workflows/ci.yml "google/osv-scanner-action/osv-scanner-action@a345acffa64b0eaede81a3d9aae6141214d9c8fc"
pinned .github/workflows/ci.yml "aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25"

gh=https://github.com
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) x=.exe
    codeql_url=$gh/github/codeql-action/releases/download/codeql-bundle-v2.27.0/codeql-bundle-win64.tar.gz
    codeql_sha=c472bbd03b0f70a468f5b77b16e26bd8248d5c570fca120605eedcdcc3abd3c0
    gitleaks_url=$gh/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_windows_x64.zip
    gitleaks_sha=d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e
    osv_url=$gh/google/osv-scanner/releases/download/v2.6.0/osv-scanner_windows_amd64.exe
    osv_sha=e0ed7644118b717b028c249ee9d3515024e55e8510747ca08906eb96765354d6
    trivy_url=$gh/aquasecurity/trivy/releases/download/v0.70.0/trivy_0.70.0_windows-64bit.zip
    trivy_sha=eea5442eab86f9e26cd718d7618d43899e72a83767619e8bee47911bddbfb825 ;;
  Linux) x=
    codeql_url=$gh/github/codeql-action/releases/download/codeql-bundle-v2.27.0/codeql-bundle-linux64.tar.gz
    codeql_sha=8e870433e5c80d0e916c3c1aa9005fc88aab990bcdcc649fade9dfc4d7e94305
    gitleaks_url=$gh/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz
    gitleaks_sha=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
    osv_url=$gh/google/osv-scanner/releases/download/v2.6.0/osv-scanner_linux_amd64
    osv_sha=ca69b3d3cd08f889a49dc0a383122f71cc528b83803671df5fd874d97485b108
    trivy_url=$gh/aquasecurity/trivy/releases/download/v0.70.0/trivy_0.70.0_Linux-64bit.tar.gz
    trivy_sha=8b4376d5d6befe5c24d503f10ff136d9e0c49f9127a4279fd110b727929a5aa9 ;;
  *) die "unsupported platform $(uname -s)" ;;
esac

tool() { # tool <dir> <binary> <url> <sha256>: download once, verify, unpack; prints the binary path
  local dir="$TOOLS/$1" file="$TOOLS/$1-${3##*/}"
  if [ ! -x "$dir/$2" ]; then
    mkdir -p "$dir" && printf '*\n' > "$TOOLS/.gitignore"
    [ -f "$file" ] || { echo "prepush: downloading $3" >&2; curl -fsSL -o "$file" "$3"; }
    echo "$4  $file" | sha256sum -c --quiet - >&2 || { rm -f "$file"; die "checksum mismatch for $3"; }
    case "$file" in
      *.tar.gz) tar -xzf "$file" -C "$dir" ;;
      *.zip) python3 -m zipfile -e "$file" "$dir" ;;
      *) cp "$file" "$dir/$2" && chmod +x "$dir/$2" ;;
    esac
    rm -f "$file"
  fi
  echo "$dir/$2"
}

# The work as `git add -A` would commit it, as a commit object, without touching the
# index: the secret scan and the change detection both see uncommitted and untracked files.
index="$(git rev-parse --git-path index)"
cp "$index" "$index.prepush"
GIT_INDEX_FILE="$index.prepush" git add -A
snapshot="$(git commit-tree "$(GIT_INDEX_FILE="$index.prepush" git write-tree)" -p HEAD -m "prepush snapshot")"
rm -f "$index.prepush"

be=0 fe=0 lock=0 cont=0 py=0 js=0 full=$all
while IFS= read -r f; do
  case "$f" in .github/*) full=1 ;; esac
  case "$f" in backend/apps/*/app.md|PRD.md|docs/inputs/openapi.yaml|docs/inputs/INPUT_DELTAS.md|generate-types.sh|openapi.json|infra/db/*|docker-compose.yml) be=1 ;;
               backend/*.md) ;; backend/*) be=1 ;; esac
  case "$f" in openapi.json|generate-types.sh) fe=1 ;; frontend/*.md) ;; frontend/*) fe=1 ;; esac
  case "$f" in backend/poetry.lock|backend/pyproject.toml|frontend/package-lock.json|frontend/package.json|frontend/THIRD_PARTY_NOTICES.md|scripts/*) lock=1 ;; esac
  case "$f" in backend/Dockerfile|frontend/Dockerfile|.dockerignore|*/.dockerignore|backend/entrypoint.sh) cont=1 ;; esac
  case "$f" in *.py) py=1 ;; *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs) js=1 ;; esac
done <<< "$(git diff --name-only "origin/main...$snapshot")"
[ "$full" = 1 ] && be=1 fe=1 lock=1 cont=1 py=1 js=1
[ "$quick" = 1 ] && echo "prepush: quick: static gates only; tests, build, E2E, CodeQL and image scans run in CI on candidate (scripts/ship.sh)"
echo "prepush: full=$full backend=$be frontend=$fe lockfiles=$lock containers=$cont codeql-python=$py codeql-js=$js"

timings=()
gate() { # gate <name> <dir> <command...>: run it, time it, stop on failure
  local name="$1" dir="$2" start=$SECONDS; shift 2
  echo; echo "==> $name"
  if ! (cd "$dir" && "$@"); then
    printf '%s\n' "${timings[@]}"
    echo "prepush: FAILED gate '$name' after $((SECONDS - start))s" >&2
    echo "prepush: reproduce: (cd $dir && $*)" >&2
    exit 1
  fi
  timings+=("$(printf '  %-52s %5ss' "$name" $((SECONDS - start)))")
}

# Secret scan (ci.yml `secrets`, gitleaks-action's flags). CI scans the pushed commits;
# here the full history plus the uncommitted work, a superset.
gitleaks="$(tool gitleaks-8.30.1 gitleaks$x "$gitleaks_url" "$gitleaks_sha")"
gate "gitleaks" . "$gitleaks" git --config .gitleaks.toml --redact -v --exit-code=2 --log-opts="$snapshot"

# A merge resolved by hand can leave a conflict marker behind, and no other gate reads for
# one (2026-09-19: a verification log was committed with its markers). Checked in the snapshot.
gate "No conflict markers" . bash -c '! git grep -nE "^(<<<<<<<|>>>>>>>)( |$)" "$0" -- . ":!*.png" ":!*.jpg"' "$snapshot"

if [ "$lock" = 1 ]; then  # ci.yml `cve` and `licences`
  gate "CVE: lockfiles present and not empty" . test -s backend/poetry.lock -a -s frontend/package-lock.json
  gate "CVE: lockfiles committed" . git ls-files --error-unmatch backend/poetry.lock frontend/package-lock.json
  osv="$(tool osv-scanner-2.6.0 osv-scanner$x "$osv_url" "$osv_sha")"
  gate "CVE: osv-scanner" . "$osv" --lockfile=backend/poetry.lock --lockfile=frontend/package-lock.json
  gate "CVE: npm audit" frontend npm audit --audit-level=moderate
  gate "Licences: self-test" . python3 scripts/check_licences.py self-test
  gate "Licences: backend" backend bash ./run.sh run python ../scripts/check_licences.py backend
  gate "Licences: frontend" . python3 scripts/check_licences.py frontend
fi

# CodeQL analyses CI's checkout, so here an export of the snapshot: no linked .venv or
# node_modules, no ignored files, the same source root and relative paths.
[ "$quick" = 1 ] && py=0 js=0
if [ "$py" = 1 ] || [ "$js" = 1 ]; then
  rm -rf sarif-results/src && mkdir -p sarif-results/src && git archive "$snapshot" | tar -x -C sarif-results/src
fi
for lang in python javascript-typescript; do  # codeql.yml, init `with:` read from the workflow
  [ "$lang" = python ] && [ "$py" = 0 ] && continue
  [ "$lang" = javascript-typescript ] && [ "$js" = 0 ] && continue
  codeql="$(tool codeql-2.27.0 codeql/codeql$x "$codeql_url" "$codeql_sha")"
  rm -rf "sarif-results/$lang" && mkdir -p "sarif-results/$lang"
  # On stdin: Poetry on Windows cuts a multi-line `python -c` at its first newline; and
  # Python there ends lines with CRLF, so the CR is stripped before `read`.
  read -r build_mode suite < <(cd backend && bash ./run.sh run python - <<'PY' | tr -d '\r'
import yaml
w = yaml.safe_load(open("../.github/workflows/codeql.yml", encoding="utf-8"))
init = next(s["with"] for s in w["jobs"]["analyze"]["steps"] if "codeql-action/init@" in s.get("uses", ""))
open("../sarif-results/codeql-config.yml", "w", encoding="utf-8").write(init["config"])
print(init["build-mode"], init["queries"])
PY
) || die "could not read the CodeQL settings from codeql.yml"
  pack="${lang%%-*}"
  gate "CodeQL $lang: database" . "$codeql" database create "sarif-results/$lang-db" --overwrite --language="$lang" \
    --build-mode="$build_mode" --source-root=sarif-results/src --codescanning-config=sarif-results/codeql-config.yml --threads=0
  gate "CodeQL $lang: analyse ($suite)" . "$codeql" database analyze "sarif-results/$lang-db" \
    "codeql/$pack-queries:codeql-suites/$pack-$suite.qls" --format=sarif-latest \
    --output="sarif-results/$lang/$lang.sarif" --sarif-category="/language:$lang" --threads=0
  gate "CodeQL $lang: gate" . python3 .github/scripts/codeql_gate.py \
    --sarif-dir "sarif-results/$lang" --accepted .github/codeql-accepted.json --language "$lang"
done

if [ "$be" = 1 ]; then  # ci.yml `backend`
  gate "Backend: migration drift" backend bash ./run.sh run python manage.py makemigrations --check --dry-run --settings=config.test_settings
  if [ "$quick" = 0 ]; then
    gate "Backend: migration graph from zero" backend bash ./run.sh run python manage.py migrate_from_zero --settings=config.test_settings
    gate "Backend: tests under coverage" backend bash ./run.sh run coverage run manage.py test apps --settings=config.test_settings --noinput
    gate "Backend: coverage report" backend bash ./run.sh run coverage report
    gate "Backend: coverage floors" backend bash ./run.sh run python scripts/coverage_gate.py
  fi
  gate "Backend: ruff" backend bash ./run.sh run ruff check .
  gate "Backend: mypy" backend bash ./run.sh run mypy
  gate "Backend: compliance lint" backend bash ./run.sh run python scripts/compliance_check.py --all
  gate "Backend: requirements coverage" backend bash ./run.sh run python scripts/requirements_coverage.py
  gate "Backend: contract drift" backend bash ./run.sh run python scripts/contract_drift.py
  gate "Backend: API documentation" backend bash ./run.sh run python scripts/api_docs_gate.py
  [ "$quick" = 0 ] && gate "Backend: search evaluation" backend bash ./run.sh run python scripts/search_eval.py
fi

if [ "$be" = 1 ] || [ "$fe" = 1 ]; then  # ci.yml `openapi-types-drift`, against the work before regeneration
  gate "OpenAPI/TS: regenerate" . bash generate-types.sh
  gate "OpenAPI/TS: artefacts tracked" . git ls-files --error-unmatch openapi.json frontend/src/types/api.generated.ts
  gate "OpenAPI/TS: artefacts match the contract" . git diff --exit-code "$snapshot" -- openapi.json frontend/src/types/api.generated.ts
fi

export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://localhost:8000}"
if [ "$fe" = 1 ]; then  # ci.yml `frontend`
  steps="build:tokens lint typecheck test:coverage check:messages check:copy-drift build"
  [ "$quick" = 1 ] && steps="build:tokens lint typecheck check:messages check:copy-drift"
  for step in $steps; do
    gate "Frontend: $step" frontend npm run "$step"
  done
fi

if [ "$quick" = 0 ] && { [ "$be" = 1 ] || [ "$fe" = 1 ]; }; then  # ci.yml `e2e`: @smoke, the full suite when everything runs
  gate "E2E: design tokens" frontend npm run build:tokens
  if [ "$full" = 1 ]; then gate "E2E: full suite" frontend env CI=true E2E_MODE=true npm run test:e2e
  else gate "E2E: @smoke" frontend env CI=true E2E_MODE=true npm run test:e2e -- --grep @smoke; fi
fi

if [ "$quick" = 0 ] && { [ "$cont" = 1 ] || [ "$lock" = 1 ]; }; then  # ci.yml `container-scan`
  trivy="$(tool trivy-0.70.0 trivy$x "$trivy_url" "$trivy_sha")"
  for image in backend frontend; do
    gate "Container $image: build" . docker build -t "compliance-watch/$image:ci" -f "$image/Dockerfile" "$image"
    gate "Container $image: Trivy" . "$trivy" image --scanners vuln --pkg-types os,library \
      --severity MEDIUM,HIGH,CRITICAL --ignore-unfixed=false --exit-code 1 --format table \
      --cache-dir "$TOOLS/trivy-cache" "compliance-watch/$image:ci"
  done
fi

echo; echo "prepush: all gates green"; printf '%s\n' "${timings[@]}"
