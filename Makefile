export DOCKER_CONFIG := $(USERPROFILE)/.docker
COMPOSE=docker compose -f deploy/docker-compose.yml

up:
	$(COMPOSE) up --build -d
down:
	$(COMPOSE) down
reset:
	$(COMPOSE) down -v
logs:
	$(COMPOSE) logs -f api
lint:
	cd backend && ruff check . && ruff format --check .
fmt:
	cd backend && ruff check --fix . && ruff format .
test:
	cd backend && pytest tests/unit

seed:
	$(COMPOSE) exec api python -m app.platform.seed
