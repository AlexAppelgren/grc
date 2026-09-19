#!/usr/bin/env bash
# OpenAPI export -> normalise -> openapi-typescript (playbook 2.1, 3 step 7, Appendix D 6).
#
# The export is normalised inside `manage.py export_openapi` (sorted keys, status
# descriptions replaced by the standard reason phrase, servers dropped), so this script
# and CI produce byte-identical files from the same code. Commit openapi.json and
# frontend/src/types/api.generated.ts together.
#
# Needs no database: export_openapi opens no connection (CI runs it without one).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

ENVIRONMENT="${ENVIRONMENT:-ci}" bash backend/run.sh run python manage.py export_openapi --out ../openapi.json

if [[ ! -d frontend/node_modules ]]; then
    echo "generate-types.sh: frontend/node_modules missing; run 'npm ci' in frontend/ first" >&2
    exit 1
fi
mkdir -p frontend/src/types
(cd frontend && npx openapi-typescript ../openapi.json -o src/types/api.generated.ts)
echo "generate-types.sh: wrote openapi.json and frontend/src/types/api.generated.ts"
