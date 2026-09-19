#!/usr/bin/env bash
# Isolated worktrees for parallel sub-agents (docs/runbooks/WORKTREES.md).
#
# Why this exists: on 2026-09-19 four agents shared one working tree and one test
# database. Django's runner creates and destroys `test_compliance_watch` on every run, so
# concurrent runs dropped each other's database mid-run ("database test_compliance_watch
# does not exist"), and two E2E stacks would have fought over ports 8000 and 3000. A
# worktree gives each task its own files; a SLOT gives it its own databases, Redis index
# and ports. Slot 0 is the main checkout and has no .env.worktree.
#
#   scripts/worktree.sh new <task> [--own-deps] [--no-baseline]
#   scripts/worktree.sh init [--own-deps] [--no-baseline]     # inside an existing worktree
#   scripts/worktree.sh list
#   scripts/worktree.sh remove <task|path> [--force]
#
# Inside a worktree, load the slot before any backend or E2E command:
#   set -a; . ./.env.worktree; set +a
set -euo pipefail

MAX_SLOT=14   # Redis has 16 databases; slot N uses index N+1 (docs/runbooks/WORKTREES.md)
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
WT_DIR_REL=".claude/worktrees"   # git-ignored in .gitignore, checked in `ensure_ignored`
APP_PW="cw-app-dev-only"
MIG_PW="cw-migrator-dev-only"

die() { echo "worktree: $*" >&2; exit 1; }
say() { echo "worktree: $*"; }

main_root() {
  # The first entry of `git worktree list` is always the main checkout.
  git worktree list --porcelain | awk '/^worktree /{print substr($0,10); exit}'
}

is_windows() { case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) return 0 ;; *) return 1 ;; esac; }

ensure_ignored() {
  local root; root="$(main_root)"
  git -C "$root" check-ignore -q "$WT_DIR_REL/probe" \
    || die "$WT_DIR_REL is not git-ignored in $root; add it to .gitignore before creating worktrees"
}

used_slots() {
  git worktree list --porcelain | awk '/^worktree /{print substr($0,10)}' | while read -r path; do
    [ -f "$path/.env.worktree" ] && sed -n 's/^WORKTREE_SLOT=//p' "$path/.env.worktree"
  done
}

free_slot() {
  local used n; used="$(used_slots | tr '\n' ' ')"
  for n in $(seq 1 "$MAX_SLOT"); do
    case " $used " in *" $n "*) ;; *) echo "$n"; return 0 ;; esac
  done
  die "all $MAX_SLOT slots are in use; remove a finished worktree first (scripts/worktree.sh list)"
}

link_dir() {
  # Share an installed dependency tree with the main checkout. A junction on Windows (no
  # admin rights needed), a symlink elsewhere. Never change dependencies through a link:
  # it would change them for every worktree and for main (use --own-deps for that).
  local target="$1" link="$2"
  [ -e "$link" ] && return 0
  [ -d "$target" ] || die "cannot share $target: it does not exist in the main checkout (install there first)"
  if is_windows; then
    # Absolute paths as separate arguments. Embedding quotes inside one `cmd //c "..."`
    # string is mangled by Git Bash's argument conversion ("cannot find the path").
    cmd //c mklink //J "$(cygpath -w "$(pwd)/$link")" "$(cygpath -w "$target")" >/dev/null
  else
    ln -s "$target" "$link"
  fi
}

write_env() {
  local slot="$1" root="$2" be=$((8000 + slot * 10)) fe=$((3000 + slot * 10)) db="compliance_watch_wt$1"
  cat > .env.worktree <<EOF
# Written by scripts/worktree.sh. Slot $slot of $MAX_SLOT. Load with: set -a; . ./.env.worktree; set +a
WORKTREE_SLOT=$slot
ENVIRONMENT=local
DATABASE_URL=postgres://cw_app:$APP_PW@localhost:5432/$db
MIGRATOR_DATABASE_URL=postgres://cw_migrator:$MIG_PW@localhost:5432/$db
REDIS_URL=redis://localhost:6379/$((slot + 1))
E2E_DATABASE_NAME=${db}_e2e
E2E_BACKEND_PORT=$be
E2E_FRONTEND_PORT=$fe
NEXT_PUBLIC_API_URL=http://localhost:$be
CORS_ALLOWED_ORIGINS=http://localhost:$fe
WEBAUTHN_ORIGINS=http://localhost:$fe
APP_BASE_URL=http://localhost:$fe
# node_modules is linked from the main checkout; Turbopack must see both (frontend/next.config.ts).
NEXT_TURBOPACK_ROOT=$root
EOF
}

load_env() { set -a; # shellcheck disable=SC1091
  . ./.env.worktree; set +a; }

cmd_init() {
  local own_deps=0 baseline=1 root
  while [ $# -gt 0 ]; do case "$1" in
    --own-deps) own_deps=1 ;; --no-baseline) baseline=0 ;; *) die "init: unknown option $1" ;;
  esac; shift; done
  [ -f backend/run.sh ] && [ -d frontend ] || die "init must run from the root of a worktree"
  root="$(main_root)"
  [ "$(cd "$root" && pwd -P)" != "$(pwd -P)" ] || die "this is the main checkout (slot 0); init is for worktrees"

  local slot
  if [ -f .env.worktree ]; then slot="$(sed -n 's/^WORKTREE_SLOT=//p' .env.worktree)"; say "reusing slot $slot"
  else slot="$(free_slot)"; write_env "$slot" "$root"; say "allocated slot $slot"; fi

  if [ "$own_deps" = 1 ]; then
    say "installing own dependencies (this worktree may change them)"
    bash backend/run.sh install --no-interaction --no-root
    (cd frontend && npm ci --no-audit --no-fund)
  else
    link_dir "$root/backend/.venv" backend/.venv
    link_dir "$root/frontend/node_modules" frontend/node_modules
    say "sharing backend/.venv and frontend/node_modules with the main checkout"
  fi
  [ -f frontend/src/styles/tokens.generated.css ] || (cd frontend && npm run -s build:tokens)

  load_env
  say "creating and migrating ${DATABASE_URL##*/} from zero"
  (cd backend && DATABASE_URL="$MIGRATOR_DATABASE_URL" bash ./run.sh run python manage.py \
     migrate_from_zero --name "${DATABASE_URL##*/}" --keep --settings=config.test_settings)

  if [ "$baseline" = 1 ]; then
    say "verifying a clean baseline before any work starts (backend suite)"
    if ! (cd backend && bash ./run.sh run python manage.py test apps --settings=config.test_settings --noinput); then
      die "the baseline is RED on this branch. Do not start the task: report the failures to the main agent."
    fi
    say "baseline green"
  fi
  say "ready: slot $slot, API port ${E2E_BACKEND_PORT}, web port ${E2E_FRONTEND_PORT}"
}

cmd_new() {
  local task="" rest=()
  while [ $# -gt 0 ]; do case "$1" in
    --own-deps|--no-baseline) rest+=("$1") ;;
    -*) die "new: unknown option $1" ;; *) task="$1" ;;
  esac; shift; done
  [ -n "$task" ] || die "new: name the task, e.g. scripts/worktree.sh new chunk3-library-api"
  case "$task" in *[!a-z0-9-]*) die "new: task names are lowercase letters, digits and hyphens" ;; esac
  ensure_ignored
  local root path; root="$(main_root)"; path="$root/$WT_DIR_REL/$task"
  [ -e "$path" ] && die "new: $path already exists"
  git -C "$root" worktree add "$path" -b "wt/$task" main
  (cd "$path" && bash "$SELF" init ${rest[@]+"${rest[@]}"})
  say "worktree for '$task' at $path on branch wt/$task"
}

cmd_list() {
  local main; main="$(main_root)"
  git worktree list --porcelain | awk '/^worktree /{p=substr($0,10)} /^branch /{b=substr($0,8)} /^$/{print p"\t"b}' \
  | while IFS="$(printf '\t')" read -r path branch; do
      # Only the main checkout is slot 0. A worktree made without this script (for example
      # by a tool) has no slot until `init` runs in it, and must not claim the defaults.
      local slot="- (none)"
      [ "$path" = "$main" ] && slot="0 (main)"
      [ -f "$path/.env.worktree" ] && slot="$(sed -n 's/^WORKTREE_SLOT=//p' "$path/.env.worktree")"
      printf 'slot %-9s %-40s %s\n' "$slot" "${branch#refs/heads/}" "$path"
    done
}

drop_databases() {
  # Drop every database the slot created. As cw_migrator, which created and owns them.
  local base="$1" py="$2"
  "$py" - "$base" <<'PY'
import sys, psycopg
base = sys.argv[1]
url = "postgres://cw_migrator:cw-migrator-dev-only@localhost:5432/postgres"
with psycopg.connect(url, autocommit=True) as conn:
    for name in (base, f"{base}_scratch", f"{base}_e2e", f"test_{base}"):
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        print(f"worktree: dropped {name} (if it existed)")
PY
}

cmd_remove() {
  local target="" force=0
  while [ $# -gt 0 ]; do case "$1" in --force) force=1 ;; *) target="$1" ;; esac; shift; done
  [ -n "$target" ] || die "remove: name the task or path"
  local root path branch; root="$(main_root)"
  if [ -d "$target" ]; then path="$(cd "$target" && pwd)"; else path="$root/$WT_DIR_REL/$target"; fi
  [ -d "$path" ] || die "remove: no worktree at $path"
  branch="$(git -C "$path" rev-parse --abbrev-ref HEAD)"
  if [ -f "$path/.env.worktree" ]; then
    local db py; db="$(sed -n 's#^DATABASE_URL=.*/##p' "$path/.env.worktree")"
    py="$root/backend/.venv/Scripts/python.exe"; [ -x "$py" ] || py="$root/backend/.venv/bin/python"
    drop_databases "$db" "$py"
  fi
  # Remove the dependency links first, so nothing can follow them into main's trees.
  for link in "$path/backend/.venv" "$path/frontend/node_modules"; do
    # rmdir on a junction removes the link only, never the target it points at (verified).
    if is_windows; then [ -e "$link" ] && cmd //c rmdir "$(cygpath -w "$link")" 2>/dev/null || true
    else [ -L "$link" ] && rm "$link"; fi
  done
  # Safety: never let anything delete a directory that still holds a dependency link, since
  # a recursive delete could follow it into the main checkout's venv or node_modules.
  for link in "$path/backend/.venv" "$path/frontend/node_modules"; do
    [ -e "$link" ] && die "remove: $link still exists after unlinking; not deleting $path (remove the link by hand)"
  done
  local flag=""; [ "$force" = 1 ] && flag="--force"
  if ! git -C "$root" worktree remove $flag "$path"; then
    # On Windows a process holding a handle (a finished test run, a shell's working
    # directory) lets git empty the tree but fail on the directory itself (seen 2026-09-19).
    # rmdir only ever removes an EMPTY directory, so retrying it is safe; nothing recurses.
    local i; for i in 1 2 3 4 5; do rmdir "$path" 2>/dev/null && break; sleep 2; done
    git -C "$root" worktree prune
  fi
  # A worktree the Agent tool created stays locked by the harness until that agent is fully
  # done, and git refuses to remove it. Say so and stop, rather than report a removal that
  # did not happen (seen 2026-09-19). Its databases are already dropped; rerun later.
  if [ -d "$path" ]; then
    die "remove: $path is still there (locked by the harness, or files still held); rerun later. Branch $branch kept."
  fi
  if [ "$force" = 1 ]; then git -C "$root" branch -D "$branch" || true
  else git -C "$root" branch -d "$branch" 2>/dev/null || say "kept branch $branch (not merged into HEAD; --force deletes it)"; fi
  say "removed $path"
}

case "${1:-}" in
  new) shift; cmd_new "$@" ;; init) shift; cmd_init "$@" ;;
  list) shift; cmd_list ;; remove) shift; cmd_remove "$@" ;;
  *) sed -n '2,20p' "$0"; exit 2 ;;
esac
