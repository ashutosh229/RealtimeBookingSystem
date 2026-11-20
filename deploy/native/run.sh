#!/usr/bin/env bash
# Run a command with the production environment: run.sh alembic upgrade head
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
set -a; . "$ROOT/.env.prod"; set +a
export PATH="$ROOT/.venv/bin:$PATH"
cd "$ROOT/backend"
exec "$@"