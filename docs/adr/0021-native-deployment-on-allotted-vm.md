# ADR-0021: Native deployment on the allotted course VM

Status: Accepted | Date: 2026-11-21

## Context
ADR-0005 chose a low-cost VM running Docker Compose. The course instead allots each team an SSH container (stu129_sys1) with no Docker and no systemd (PID 1 is sshd), an 8 CPU and 30 GB cgroup limit on a shared host, and five forwarded ports: a service on VM port 3000 is public as http://10.1.75.53:3501.

## Decision
Run the stack natively from apt packages (PostgreSQL 16, Redis 7, RabbitMQ 3.12, nginx) with the API replicas, worker, relay and consumers under supervisord, using the scripts in deploy/native (bootstrap, gen-env, services, deploy, backup, run). nginx listens on 3000, serves the built web app and proxies /v1, /healthz and /readyz to the uvicorn replicas; /metrics is not proxied. Docker Compose stays for local development and CI. Deploys are run with deploy/native/deploy.sh; a manually triggered job on a self-hosted runner on the VM is the intended automation.

## Consequences
Rationale: the only layout that works on the allotted host, and it runs the same code and the same migrations as Compose, so the design and the tests do not change.
Cost accepted: a shared host adds noise to benchmarks, so every result records the cgroup limits; the public port is plain HTTP on the campus network; all services share one machine, so the scaling test cannot use a separate data host; processes do not survive a container restart until deploy.sh is run again; there is no systemd to supervise supervisord itself.
