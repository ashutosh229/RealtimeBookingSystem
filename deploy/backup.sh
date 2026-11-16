#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
f="backups/rtbs-$(date +%Y%m%d-%H%M%S).sql.gz"
docker compose -f deploy/compose.prod.yml exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$f"
test -s "$f" && echo "wrote $f"
ls -1t backups/rtbs-*.sql.gz | tail -n +15 | xargs -r rm --      # keep the 14 newest