#!/usr/bin/env bash
# Usage: ./deploy/deploy.sh [branch-or-commit]        API_REPLICAS=3 ./deploy/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."
C="docker compose -f deploy/compose.prod.yml"
[ -f .env.prod ] || { echo "missing .env.prod: run deploy/gen-env.sh first"; exit 1; }

if [ -d .git ]; then
  git fetch --quiet origin
  git checkout --quiet "${1:-main}"
  if git symbolic-ref -q HEAD >/dev/null; then git pull --quiet --ff-only; fi   # a pinned commit is not pulled
  VERSION=$(git rev-parse --short HEAD)
else
  VERSION="uploaded copy"
fi

N="${API_REPLICAS:-1}"
echo "deploying $VERSION with $N API replica(s)"

# The proxy needs an explicit upstream list; compose names replicas rtbs-prod-api-1..N.
{
  printf 'reverse_proxy'
  for i in $(seq 1 "$N"); do printf ' rtbs-prod-api-%s:8000' "$i"; done
  printf ' {\n\tlb_policy round_robin\n\tlb_try_duration 5s\n\tlb_try_interval 250ms\n'
  printf '\thealth_uri /readyz\n\thealth_interval 5s\n\thealth_timeout 2s\n}\n'
} > deploy/upstreams.caddy

$C build
$C up -d --remove-orphans --scale api="$N"
$C exec -T caddy caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 || true

echo "waiting for the site..."
for _ in $(seq 1 40); do
  if curl -fsS http://localhost:3000/readyz >/dev/null 2>&1; then
    $C ps
    echo "ready: $VERSION  (public: see CORS_ORIGINS in .env.prod)"
    exit 0
  fi
  sleep 3
done
echo "the site did not become ready; last log lines:"
$C logs --tail 60 api caddy
exit 1