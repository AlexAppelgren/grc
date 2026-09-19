#!/usr/bin/env bash
# Poetry wrapper for the backend (playbook 2.1). Usage, from anywhere:
#
#   backend/run.sh run python manage.py test apps --settings=config.test_settings
#
# It unsets VIRTUAL_ENV first. An activated venv in the calling shell (an IDE's, another
# project's) makes Poetry 2 use that environment instead of the project's own, and the
# last repo lost an afternoon to tests importing a different Django. Then it execs
# `poetry "$@"` from the backend directory so relative paths in the canonical commands
# resolve the same way locally, in CI and in the Dockerfile.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
unset VIRTUAL_ENV
exec poetry "$@"
