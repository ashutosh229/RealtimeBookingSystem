#!/usr/bin/env bash
# Runs under supervisord: a database backup every BACKUP_EVERY_HOURS (default 24). backup.sh keeps the newest 14.
# On start it waits until the newest backup is that old, so redeploys do not pile up extra backups.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
EVERY=$(( ${BACKUP_EVERY_HOURS:-24} * 3600 ))
while true; do
  newest=$(ls -1t backups/rtbs-*.sql.gz 2>/dev/null | head -n 1)
  age=$EVERY
  [ -n "$newest" ] && age=$(( $(date +%s) - $(stat -c %Y "$newest") ))
  if [ "$age" -ge "$EVERY" ]; then
    echo "$(date -Is) backup starting"
    ./deploy/native/backup.sh || echo "$(date -Is) BACKUP FAILED"
    age=0
  fi
  sleep $(( EVERY - age > 60 ? EVERY - age : 60 ))
done
