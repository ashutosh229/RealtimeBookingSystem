#!/usr/bin/env bash
set -euo pipefail
URL="${1:?usage: gen-env.sh http://10.1.75.53:3501}"
cd "$(dirname "$0")/../.."
[ -e .env.prod ] && { echo ".env.prod already exists; not overwriting"; exit 1; }
rand() { openssl rand -hex "$1"; }
PGPW=$(rand 16); MQPW=$(rand 16); JWT=$(rand 32); SEEDPW=$(rand 6)
umask 077
cat > .env.prod <<EOF
POSTGRES_PASSWORD=$PGPW
DATABASE_URL=postgresql+asyncpg://rtbs:$PGPW@127.0.0.1:5432/rtbs
REDIS_URL=redis://127.0.0.1:6379/0
RABBITMQ_PASSWORD=$MQPW
AMQP_URL=amqp://rtbs:$MQPW@127.0.0.1:5672/
JWT_SECRET=$JWT
CAMPUS_TZ=UTC
CORS_ORIGINS=$URL
DB_POOL_SIZE=10
SEED_PASSWORD=$SEEDPW
EOF
echo "wrote .env.prod. Demo users' password: $SEEDPW   <- save it"
echo "Edit CAMPUS_TZ in .env.prod (IANA name) BEFORE running the seed."