#!/usr/bin/env bash
# Creates .env.prod with random secrets. Run once on the server.
set -euo pipefail
URL="${1:?usage: gen-env.sh <public-url>   e.g. http://10.1.75.53:3501}"
cd "$(dirname "$0")/.."
[ -e .env.prod ] && { echo ".env.prod already exists; refusing to overwrite it"; exit 1; }
rand() { openssl rand -hex "$1"; }
PGPW=$(rand 16); MQPW=$(rand 16); JWT=$(rand 32); SEEDPW=$(rand 6)
umask 077
cat > .env.prod <<EOF
POSTGRES_USER=rtbs
POSTGRES_PASSWORD=$PGPW
POSTGRES_DB=rtbs
DATABASE_URL=postgresql+asyncpg://rtbs:$PGPW@postgres:5432/rtbs
REDIS_URL=redis://redis:6379/0
RABBITMQ_DEFAULT_USER=rtbs
RABBITMQ_DEFAULT_PASS=$MQPW
AMQP_URL=amqp://rtbs:$MQPW@rabbitmq:5672/
JWT_SECRET=$JWT
CAMPUS_TZ=UTC
CORS_ORIGINS=$URL
DB_POOL_SIZE=10
SEED_PASSWORD=$SEEDPW
EOF
echo "wrote .env.prod (mode 600). Demo users' password: $SEEDPW   <- save it"
echo "Set CAMPUS_TZ in .env.prod to your campus time zone (an IANA name) BEFORE running the seed."