#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
set -a; . .env.prod; set +a
mkdir -p backups
f="backups/rtbs-$(date +%Y%m%d-%H%M%S).sql.gz"
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h 127.0.0.1 -U rtbs rtbs | gzip > "$f"
test -s "$f" && echo "wrote $f"
ls -1t backups/rtbs-*.sql.gz | tail -n +15 | xargs -r rm --