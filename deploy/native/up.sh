#!/usr/bin/env bash
# Bring the deployed stack back after the VM container restarted, without pulling code or reinstalling:
#   ./deploy/native/up.sh                    # start databases, broker and supervisord if they are down
#   ./deploy/native/up.sh --install-autostart   # also run this automatically on every SSH login
# The container has no init system, so nothing starts on its own; deploy.sh must have run once before.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
RUN="$ROOT/run"
SC="supervisorctl -c $RUN/supervisord.conf"

if [ "${1:-}" = "--install-autostart" ]; then
  MARK="# rtbs-autostart"
  if grep -q "$MARK" "$HOME/.profile" 2>/dev/null; then
    echo "autostart already installed in ~/.profile"
  else
    printf '\n%s\n[ -x "%s/deploy/native/up.sh" ] && ( "%s/deploy/native/up.sh" >>"%s/logs/autostart.log" 2>&1 & ) %s\n' \
      "$MARK" "$ROOT" "$ROOT" "$RUN" "$MARK" >> "$HOME/.profile"
    echo "autostart installed: the stack comes back on your next SSH login"
  fi
  shift
fi

[ -f "$RUN/supervisord.conf" ] || { echo "run deploy/native/deploy.sh once first"; exit 1; }
if [ -S "$RUN/supervisor.sock" ] && $SC pid >/dev/null 2>&1; then
  echo "$(date -Is) already running"
  exit 0
fi
echo "$(date -Is) starting"
mkdir -p "$RUN/logs"
./deploy/native/services.sh start
supervisord -c "$RUN/supervisord.conf"
for _ in $(seq 1 40); do
  curl -fsS http://127.0.0.1:3000/readyz >/dev/null 2>&1 && { $SC status; echo "$(date -Is) up"; exit 0; }
  sleep 3
done
echo "$(date -Is) not ready; see $RUN/logs"; exit 1
