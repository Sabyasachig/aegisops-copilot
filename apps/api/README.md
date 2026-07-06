# AegisOps API

FastAPI service for incident data, agent orchestration, and execution traces.

## Running locally

```bash
cd apps/api
python -m uvicorn aegisops_api.main:app --reload --host 0.0.0.0 --port 4001
```

Requires PostgreSQL and Redis — use the docker-compose services from the repo root:

```bash
docker compose up -d postgres redis
```

## Authentication

All endpoints except `/api/health`, `/api/auth/token`, `/api/auth/refresh`, and `/api/webhooks/*` require a Bearer JWT.

**Get a token:**
```bash
curl -X POST http://localhost:4001/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "changeme"}'
```

**Use the token:**
```bash
curl http://localhost:4001/api/incidents \
  -H "Authorization: Bearer <access_token>"
```

**Refresh an expired access token:**
```bash
curl -X POST http://localhost:4001/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'
```

The initial admin user is seeded on first startup using `AIOPS_INITIAL_ADMIN_USERNAME` / `AIOPS_INITIAL_ADMIN_PASSWORD`. Change these in production via environment variables.

## Running tests

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Tests use an isolated `aegisops_test` database. Make sure PostgreSQL and Redis are running (docker-compose or local).
