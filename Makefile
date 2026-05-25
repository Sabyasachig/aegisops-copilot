COMPOSE ?= docker compose

.PHONY: up down restart logs ps build start stop migrate migrate-down db-shell redis-cli worker-logs

start:
	$(COMPOSE) up -d --build

stop:
	$(COMPOSE) down

up:
	$(COMPOSE) up --build

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) down
	$(COMPOSE) up --build

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

build:
	$(COMPOSE) build

## ── Database ────────────────────────────────────────────────────────────────

migrate:        ## Apply all pending Alembic migrations inside the running api container
	$(COMPOSE) exec api alembic upgrade head

migrate-down:   ## Roll back the last Alembic migration
	$(COMPOSE) exec api alembic downgrade -1

db-shell:       ## Open an interactive psql shell
	$(COMPOSE) exec postgres psql -U aegisops -d aegisops

redis-cli:      ## Open an interactive redis-cli shell
	$(COMPOSE) exec redis redis-cli

## ── Worker ──────────────────────────────────────────────────────────────────

worker-logs:    ## Tail Celery worker logs
	$(COMPOSE) logs -f worker