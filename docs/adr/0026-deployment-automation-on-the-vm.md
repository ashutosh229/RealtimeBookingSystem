# ADR-0026: Deployment automation on the allotted VM

Status: Accepted | Date: 2026-11-27 | Closes the costs accepted in ADR-0021

## Context
ADR-0021 left four manual steps: the web build was copied to the VM by hand, backups ran only when someone remembered, nothing restarted after the container restarted (no init system), and the self-hosted runner for the deploy workflow was intended but not set up. Separately, CI installed whatever newest versions `>=` allowed; a cache-key change pulled FastAPI 0.165, aio-pika 10 and pytest-asyncio 1.5 at once and broke tests that had not changed.

## Decision
1. Pinned versions: `backend/constraints.txt` is the `pip freeze` of the last fully green run. CI, the Docker image and `deploy.sh` install with `-c constraints.txt`; `requirements*.txt` keep only what we need. Upgrades are deliberate: fresh venv without `-c`, full test suite, new freeze.
2. Web app: `deploy.sh` runs `build-web.sh` when Node 20+ is on the VM and swaps the new build in only after it succeeds; otherwise it keeps serving the current one. `push-web.sh` builds on a laptop and replaces `~/rtbs/web` over SSH.
3. Backups: supervisord runs `backup-loop.sh`, which calls `backup.sh` every `BACKUP_EVERY_HOURS` (24) and keeps the newest 14 dumps. It counts from the newest dump, so redeploys do not add extra ones.
4. Restart: `up.sh` starts the data services and supervisord from the last deployed configuration without pulling or reinstalling. `up.sh --install-autostart` adds a guarded line to `~/.profile`, so the first SSH login after a container restart brings the stack back.
5. Runner: `runner.sh <token>` registers the VM as the `rtbs-vm` runner; `deploy.sh` then supervises it like any other process and never restarts it, because a deploy started from GitHub runs inside it.

## Consequences
Rationale: every step that used to depend on memory is now a script or a supervised process, and CI fails only when our code changes.
Cost accepted: after a container restart the stack is down until someone logs in (there is still no init system); the runner registration token must come from a repository admin; pinned versions need a periodic, tested refresh to pick up security fixes; backups stay on the same machine as the database, so copy them off the VM for real disaster recovery.
