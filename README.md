# RealTime Booking System (CSD Project)

Fairness-aware booking platform for seats, rooms, and compute pools.
Design: see the HLD/LLD document. Targets: Android + web (iOS out of scope).

## Layout
- `backend/`  FastAPI app, worker, migrations, tests
- `mobile/`   Expo app (Android + web)
- `bench/`    workloads, simulator, results
- `deploy/`   Docker Compose and deployment files
- `docs/`     ADRs, OpenAPI, event schemas

## Quick start
    cp .env.example .env
    make up
    curl localhost:8080/healthz

## Dev
    cd backend && python -m venv .venv && source .venv/bin/activate
    pip install -r requirements-dev.txt
    make lint test

## Workflow
Branch from `main`, open a pull request, CI must be green, one teammate reviews, squash-merge.
