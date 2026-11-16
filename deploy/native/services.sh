#!/usr/bin/env bash
# ./deploy/native/services.sh start|stop|status|init
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RUN="$ROOT/run"; mkdir -p "$RUN/redis" "$RUN/logs"
pg_up()    { pg_isready -q -h 127.0.0.1 -p 5432; }
redis_up() { redis-cli -h 127.0.0.1 ping 2>/dev/null | grep -q PONG; }
mq_up()    { sudo -H -u rabbitmq rabbitmqctl -q status >/dev/null 2>&1; }
RC="sudo -H -u rabbitmq rabbitmqctl"

case "${1:-status}" in
  start)
    pg_lsclusters 2>/dev/null | grep -q '^16' || sudo pg_createcluster 16 main
    pg_up || { sudo pg_ctlcluster 16 main start; for _ in $(seq 1 30); do pg_up && break; sleep 1; done; }
    redis_up || redis-server --daemonize yes --bind 127.0.0.1 --port 6379 --save "" --appendonly no \
        --dir "$RUN/redis" --logfile "$RUN/logs/redis.log" --pidfile "$RUN/redis.pid"
    mq_up || { sudo -H -u rabbitmq rabbitmq-server -detached; $RC await_startup; }
    "$0" status ;;
  stop)
    redis-cli -h 127.0.0.1 shutdown nosave 2>/dev/null
    $RC stop 2>/dev/null
    sudo pg_ctlcluster 16 main stop ;;
  status)
    pg_up    && echo "postgres : up" || echo "postgres : DOWN"
    redis_up && echo "redis    : up" || echo "redis    : DOWN"
    mq_up    && echo "rabbitmq : up" || echo "rabbitmq : DOWN" ;;
  init)  # create the database role, database, and RabbitMQ user from .env.prod (safe to repeat)
    set -a; . "$ROOT/.env.prod"; set +a
    cd /tmp
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='rtbs'" | grep -q 1 \
      || sudo -u postgres psql -c "CREATE ROLE rtbs LOGIN PASSWORD '$POSTGRES_PASSWORD'"
    sudo -u postgres psql -c "ALTER ROLE rtbs PASSWORD '$POSTGRES_PASSWORD'"
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='rtbs'" | grep -q 1 \
      || sudo -u postgres createdb -O rtbs rtbs
    $RC -q add_user rtbs "$RABBITMQ_PASSWORD" 2>/dev/null || $RC -q change_password rtbs "$RABBITMQ_PASSWORD"
    $RC -q set_permissions -p / rtbs ".*" ".*" ".*"
    $RC -q delete_user guest 2>/dev/null || true
    echo "init done" ;;
  *) echo "usage: $0 start|stop|status|init"; exit 1 ;;
esac