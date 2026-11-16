#!/usr/bin/env bash
set -euo pipefail
# RabbitMQ's Erlang node cannot use a hostname with an underscore (yours is stu129_sys1), so pin it to localhost.
sudo mkdir -p /etc/rabbitmq
printf 'NODENAME=rabbit@localhost\nNODE_IP_ADDRESS=127.0.0.1\n' | sudo tee /etc/rabbitmq/rabbitmq-env.conf >/dev/null

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  postgresql redis-server rabbitmq-server nginx supervisor \
  python3.12 python3.12-venv curl openssl git

# Packages may have auto-started their own copies; we run our own configured ones.
sudo service nginx stop 2>/dev/null || sudo nginx -s stop 2>/dev/null || true
sudo service supervisor stop 2>/dev/null || true
sudo service redis-server stop 2>/dev/null || true
sudo pg_ctlcluster 16 main stop 2>/dev/null || true

sudo mkdir -p /etc/postgresql/16/main/conf.d
sudo tee /etc/postgresql/16/main/conf.d/rtbs.conf >/dev/null <<'EOF'
max_connections = 300
shared_buffers = 1GB
effective_cache_size = 6GB
max_parallel_workers_per_gather = 0   # parallel query needs /dev/shm, which is small inside a container
EOF
echo "bootstrap done"