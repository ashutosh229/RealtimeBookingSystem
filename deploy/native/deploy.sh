#!/usr/bin/env bash
# ./deploy/native/deploy.sh [branch-or-commit]        API_REPLICAS=4 ./deploy/native/deploy.sh
# Also the command to run after a container restart: it brings everything back up.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
RUN="$ROOT/run"; mkdir -p "$RUN/logs" "$RUN/nginx" "$RUN/redis" web backups
[ -f .env.prod ] || { echo "missing .env.prod: run deploy/native/gen-env.sh first"; exit 1; }
N="${API_REPLICAS:-1}"
[[ "$N" =~ ^[1-9]$ ]] || { echo "API_REPLICAS must be 1-9"; exit 1; }

if [ -d .git ]; then
  git fetch --quiet origin
  git checkout --quiet "${1:-main}"
  if git symbolic-ref -q HEAD >/dev/null; then git pull --quiet --ff-only; fi
  VERSION=$(git rev-parse --short HEAD)
else
  VERSION="uploaded copy"
fi
echo "deploying $VERSION with $N API replica(s)"

./deploy/native/services.sh start
[ -x .venv/bin/python ] || python3.12 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r backend/requirements.txt -c backend/constraints.txt
./deploy/native/run.sh alembic upgrade head

# Web app: rebuilt here when Node 20+ is installed, otherwise the current ./web keeps being served
# (build it on a laptop with deploy/native/push-web.sh). SKIP_WEB=1 skips the build.
PUBLIC_URL="$( (set -a; . ./.env.prod; echo "${CORS_ORIGINS%%,*}") )"
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
if [ "${SKIP_WEB:-0}" = 1 ]; then
  echo "web: skipped (SKIP_WEB=1)"
elif command -v npm >/dev/null && [ "$NODE_MAJOR" -ge 20 ]; then
  ./deploy/native/build-web.sh "$PUBLIC_URL" "$ROOT/web" || echo "web: BUILD FAILED, still serving the previous build"
else
  echo "web: Node 20+ not found on this machine; serving the existing ./web (use deploy/native/push-web.sh)"
fi

SERVERS=""; for i in $(seq 1 "$N"); do SERVERS="$SERVERS    server 127.0.0.1:800$i max_fails=2 fail_timeout=5s;"$'\n'; done
cat > "$RUN/nginx.conf" <<EOF
worker_processes 4;
pid $RUN/nginx.pid;
error_log $RUN/logs/nginx_error.log warn;
events { worker_connections 4096; }
http {
  include /etc/nginx/mime.types;
  default_type application/octet-stream;
  access_log $RUN/logs/nginx_access.log;
  client_body_temp_path $RUN/nginx/body;
  proxy_temp_path $RUN/nginx/proxy;
  fastcgi_temp_path $RUN/nginx/fastcgi;
  uwsgi_temp_path $RUN/nginx/uwsgi;
  scgi_temp_path $RUN/nginx/scgi;
  gzip on;
  gzip_types application/json text/css application/javascript;
  upstream api {
$SERVERS    keepalive 64;
  }
  server {
    listen 3000;
    add_header X-Content-Type-Options nosniff;
    location ~ ^/(v1/|healthz|readyz) {
      proxy_pass http://api;
      proxy_http_version 1.1;
      proxy_set_header Connection "";
      proxy_set_header Host \$host;
      proxy_set_header X-Forwarded-For \$remote_addr;
      # Booking POSTs carry an Idempotency-Key, so retrying them on another replica is safe.
      proxy_next_upstream error timeout http_502 http_503 non_idempotent;
      proxy_next_upstream_tries 3;
      proxy_connect_timeout 2s;
      proxy_read_timeout 60s;
    }
    location / {
      root $ROOT/web;
      try_files \$uri /index.html;
    }
  }
}
EOF

cat > "$RUN/supervisord.conf" <<EOF
[unix_http_server]
file=$RUN/supervisor.sock
[supervisord]
logfile=$RUN/logs/supervisord.log
pidfile=$RUN/supervisord.pid
childlogdir=$RUN/logs
[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface
[supervisorctl]
serverurl=unix://$RUN/supervisor.sock

[program:api]
command=$ROOT/deploy/native/run.sh uvicorn app.main:app --host 127.0.0.1 --port 800%(process_num)d --proxy-headers
process_name=api_%(process_num)d
numprocs=$N
numprocs_start=1
autorestart=true
stopwaitsecs=30
redirect_stderr=true
stdout_logfile=$RUN/logs/api_%(process_num)d.log

[program:worker]
command=$ROOT/deploy/native/run.sh python -m app.worker.main
autorestart=true
stopwaitsecs=30
redirect_stderr=true
stdout_logfile=$RUN/logs/worker.log

[program:relay]
command=$ROOT/deploy/native/run.sh python -m app.worker.runner relay
autorestart=true
stopwaitsecs=30
redirect_stderr=true
stdout_logfile=$RUN/logs/relay.log

[program:consumers]
command=$ROOT/deploy/native/run.sh python -m app.worker.runner consumers
autorestart=true
stopwaitsecs=30
redirect_stderr=true
stdout_logfile=$RUN/logs/consumers.log

[program:backup]
command=$ROOT/deploy/native/backup-loop.sh
autorestart=true
redirect_stderr=true
stdout_logfile=$RUN/logs/backup.log

[program:nginx]
command=/usr/sbin/nginx -e $RUN/logs/nginx_boot.log -p $RUN/nginx -c $RUN/nginx.conf -g "daemon off;"
autorestart=true
redirect_stderr=true
stdout_logfile=$RUN/logs/nginx.log
EOF

# The GitHub Actions runner (deploy/native/runner.sh) lives under supervisord too, so it survives like the rest.
if [ -x "$HOME/actions-runner/run.sh" ] && [ -f "$HOME/actions-runner/.runner" ]; then
  cat >> "$RUN/supervisord.conf" <<EOF

[program:runner]
command=$HOME/actions-runner/run.sh
directory=$HOME/actions-runner
autorestart=true
stopwaitsecs=60
redirect_stderr=true
stdout_logfile=$RUN/logs/runner.log
EOF
fi

SC="supervisorctl -c $RUN/supervisord.conf"
if [ -S "$RUN/supervisor.sock" ] && $SC pid >/dev/null 2>&1; then
  # Not "restart all": a deploy started from GitHub runs inside the runner, which must keep running.
  $SC reread >/dev/null; $SC update >/dev/null
  $SC restart "api:*" worker relay consumers backup nginx >/dev/null
else
  supervisord -c "$RUN/supervisord.conf"
fi

echo "waiting for the site..."
for _ in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:3000/readyz >/dev/null 2>&1; then
    $SC status
    echo "ready: $VERSION  (public: see CORS_ORIGINS in .env.prod)"
    exit 0
  fi
  sleep 3
done
echo "not ready; recent logs:"; tail -n 40 "$RUN"/logs/api_1.log "$RUN"/logs/nginx_error.log 2>/dev/null || true
exit 1