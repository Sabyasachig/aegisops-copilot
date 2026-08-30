# AegisOps Copilot

> **AI-powered incident operations platform** — multi-agent triage, evidence gathering, mitigation planning, and human-in-the-loop control for production incidents.

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-orange)](https://langchain-ai.github.io/langgraph/)
[![Next.js 15](https://img.shields.io/badge/Next.js-15-black)](https://nextjs.org/)
[![Docker](https://img.shields.io/badge/docker-compose-blue)](https://docs.docker.com/compose/)

---

## Overview

AegisOps Copilot is a multi-agent AI ops platform designed for SREs, DevOps engineers, and on-call teams. When a production incident fires, the platform:

1. **Ingests** the incident from PagerDuty, OpsGenie, or any generic webhook
2. **Triages** it automatically using a 4-node LangGraph agent workflow
3. **Generates** a structured mitigation plan with evidence and recommended runbook steps
4. **Keeps humans in control** — agents surface recommendations, engineers decide

---

## Architecture

```
                ┌─────────────────────────────────────────┐
                │           Next.js Dashboard              │
                │    Incident queue · Agent status · Runs  │
                └──────────────┬──────────────────────────┘
                               │ REST / WebSocket
                ┌──────────────▼──────────────────────────┐
                │         FastAPI Control Plane            │
                │  /api/auth   /api/incidents  /api/runs   │
                │  /api/execute  /api/webhooks /api/health │
                └───┬──────────────┬───────────────────────┘
                    │              │
          ┌─────────▼──────┐  ┌───▼──────────────────────┐
          │  LangGraph     │  │  PostgreSQL + Redis        │
          │  Agent Graph   │  │  Incidents · Runs · Cache  │
          │                │  └──────────────────────────-─┘
          │  assess        │
          │   → evidence   │  LangSmith (tracing)
          │   → draft      │  Groq / OpenAI / Anthropic
          │   → package    │
          └────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **API** | Python 3.11, FastAPI, Uvicorn |
| **Agents** | LangGraph (Python), LangChain |
| **LLM providers** | Groq (default), OpenAI, Anthropic |
| **Observability** | LangSmith tracing |
| **Database** | PostgreSQL 16 (SQLAlchemy async + asyncpg) |
| **Cache** | Redis 7 (async redis-py) |
| **Migrations** | Alembic |
| **UI** | Next.js 15, TypeScript, Tailwind CSS |
| **Infrastructure** | Docker Compose, named volumes |

---

## Workspace Layout

```
aegisops-copilot/
├── apps/
│   ├── api/                         # Python FastAPI service
│   │   ├── src/aegisops_api/
│   │   │   ├── main.py              # App factory + lifespan (DB init, seeding)
│   │   │   ├── agents.py            # LangGraph 4-node incident workflow
│   │   │   ├── auth.py              # JWT helpers + get_current_user dependency
│   │   │   ├── llm.py               # Multi-provider LLM factory
│   │   │   ├── models.py            # Pydantic models
│   │   │   ├── settings.py          # Pydantic-settings (env vars)
│   │   │   ├── cache.py             # Async Redis helpers
│   │   │   ├── store.py             # Seed data
│   │   │   └── routers/
│   │   │       ├── auth.py          # POST /api/auth/token|refresh
│   │   │       ├── health.py        # GET /api/health (checks PG + Redis)
│   │   │       ├── incidents.py     # GET /api/incidents, /api/incidents/{id}
│   │   │       ├── runs.py          # GET /api/runs/{incident_id}
│   │   │       ├── execute.py       # POST /api/incidents/{id}/execute
│   │   │       ├── providers.py     # GET /api/providers
│   │   │       └── webhooks.py      # POST /api/webhooks/generic|pagerduty
│   │   │   └── db/
│   │   │       ├── engine.py        # Async SQLAlchemy engine + session
│   │   │       ├── orm_models.py    # IncidentRow, AgentRunRow, UserRow ORM
│   │   │       └── repository.py   # Async CRUD functions
│   │   ├── alembic/                 # Database migrations
│   │   └── pyproject.toml
│   └── web/                         # Next.js 15 dashboard
│       ├── app/
│       │   ├── page.tsx             # Incident command center
│       │   ├── layout.tsx
│       │   └── globals.css
│       └── lib/
│           ├── api.ts               # Fetch helpers
│           └── dashboard-data.ts    # Static fallback data
├── docs/
│   ├── architecture.md
│   └── product-plan.md
├── docker-compose.yml               # 4 services: postgres, redis, api, web
├── Makefile
├── .env.example
└── FUTURE_SCOPE.md                  # Planned features and PRs
```

---

## Quick Start

### Prerequisites
- Docker + Docker Compose v2
- A [Groq API key](https://console.groq.com/) (free tier works)

### 1. Clone and configure
```bash
git clone <repo-url>
cd aegisops-copilot
cp .env.example .env
# Edit .env and set GROQ_API_KEY=your_key_here
```

### 2. Start the full stack
```bash
make start
```

This starts 4 containers: **PostgreSQL 16**, **Redis 7**, **FastAPI API**, **Next.js UI**.

### 3. Open the dashboard
- **UI:** http://localhost:3000
- **API docs (Swagger):** http://localhost:4001/docs
- **Health check:** http://localhost:4001/api/health

---

## Makefile Commands

```bash
make start        # Start all containers in background (with build)
make stop         # Stop and remove all containers
make restart      # Stop then start
make logs         # Follow all container logs
make ps           # Show container status

make migrate      # Apply pending Alembic migrations (inside api container)
make migrate-down # Roll back last migration
make db-shell     # Open interactive psql
make redis-cli    # Open interactive redis-cli
```

---

## API Endpoints

> All endpoints except `/api/health`, `/api/auth/token`, `/api/auth/refresh`, and `/api/webhooks/*` require a `Authorization: Bearer <token>` header.

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/health` | public | Health check (PostgreSQL + Redis status) |
| `POST` | `/api/auth/token` | public | Login — returns access + refresh token pair |
| `POST` | `/api/auth/refresh` | public | Exchange refresh token for new access token |
| `GET` | `/api/incidents` | 🔒 | List all incidents (Redis-cached, 60s TTL) |
| `GET` | `/api/incidents/{id}` | 🔒 | Get a single incident |
| `POST` | `/api/incidents/{id}/execute` | 🔒 | Trigger LangGraph agent workflow |
| `GET` | `/api/incidents/{id}/stream` | 🔒 | Stream real-time workflow events over SSE |
| `GET` | `/api/runs/{incident_id}` | 🔒 | List all agent runs for an incident |
| `GET` | `/api/tasks/{task_id}` | 🔒 | Poll async task status |
| `GET` | `/api/providers` | 🔒 | List available LLM providers |
| `POST` | `/api/webhooks/generic` | public* | Ingest incident from any alerting tool |
| `POST` | `/api/webhooks/pagerduty` | public* | Ingest PagerDuty v3 webhook |

\* Webhook endpoints are public but will be secured with HMAC signature validation (Issue #3).

Full interactive docs at **http://localhost:4001/docs**

---

## LLM Provider Switching

Change provider in `.env` — no code changes needed:

```bash
# Groq (default, fastest, free tier)
AIOPS_LLM_PROVIDER=groq
AIOPS_LLM_MODEL=llama-3.1-8b-instant
GROQ_API_KEY=your_key

# OpenAI
AIOPS_LLM_PROVIDER=openai
AIOPS_LLM_MODEL=gpt-4o
OPENAI_API_KEY=your_key

# Anthropic
AIOPS_LLM_PROVIDER=anthropic
AIOPS_LLM_MODEL=claude-3-5-sonnet-20241022
ANTHROPIC_API_KEY=your_key
```

Then `make restart`.

---

## Agent Workflow

The LangGraph pipeline runs 4 nodes per incident:

```
assess → gather_evidence → draft_response → package_output
```

| Node | Responsibility |
|---|---|
| **assess** | Classifies risk, identifies owner, lists immediate actions |
| **gather_evidence** | Summarizes observability signals and deploy clues |
| **draft_response** | Generates a ranked mitigation plan |
| **package_output** | Bundles summary + runbook recommendation |

Every run is traced in [LangSmith](https://smith.langchain.com) when `LANGSMITH_API_KEY` is set.

---

## Webhook Integration

Send incidents from any alerting tool directly into the platform:

```bash
# Compute HMAC signature (when AIOPS_WEBHOOK_SECRET is set)
SECRET="your-webhook-secret"
BODY='{"id":"INC-9999","title":"API gateway 502","service":"api-gateway","severity":"critical","owner":"platform-team"}'
SIG="sha256=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')"

curl -X POST http://localhost:4001/api/webhooks/generic \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: $SIG" \
  -d "$BODY"
```

When `AIOPS_WEBHOOK_SECRET` is **not** set, signature verification is skipped (useful for local development).

| Endpoint | Signature header | Format |
|---|---|---|
| `/api/webhooks/generic` | `X-Webhook-Signature` | `sha256=<hmac-hex>` |
| `/api/webhooks/pagerduty` | `X-PagerDuty-Signature` | `v1=<hmac-hex>` (PagerDuty native) |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `AIOPS_LLM_PROVIDER` | `groq` | Active LLM provider |
| `AIOPS_LLM_MODEL` | `llama-3.1-8b-instant` | Model name |
| `AIOPS_DATABASE_URL` | *(postgres container)* | Async PostgreSQL URL |
| `AIOPS_REDIS_URL` | *(redis container)* | Redis URL |
| `AIOPS_JWT_SECRET_KEY` | *(dev default)* | Secret for signing JWTs — **change in production** |
| `AIOPS_JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token TTL in minutes |
| `AIOPS_JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL in days |
| `AIOPS_LOG_FORMAT` | `auto` | Logging renderer: `auto`, `json`, or `console` |
| `AIOPS_LOG_LEVEL` | `INFO` | Root logging level |
| `AIOPS_SSE_KEEPALIVE_SECONDS` | `15` | SSE keepalive comment interval in seconds |
| `AIOPS_SSE_STREAM_POLL_SECONDS` | `1` | Redis pub/sub poll timeout for SSE stream loop |
| `AIOPS_INITIAL_ADMIN_USERNAME` | `admin` | Username seeded on first startup |
| `AIOPS_INITIAL_ADMIN_PASSWORD` | `changeme` | Password seeded on first startup — **change in production** |
| `GROQ_API_KEY` | — | Groq API key |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `LANGSMITH_API_KEY` | — | LangSmith tracing key |
| `AIOPS_LANGSMITH_PROJECT` | `aegisops-copilot` | LangSmith project name |

---

## Structured Logging

The API and worker now emit structured logs using `structlog`.

- `AIOPS_LOG_FORMAT=auto` renders JSON in production and console logs in development.
- Context fields are attached where available: `request_id`, `incident_id`, `run_id`, `user_id`.
- Workflow observability events include node transitions and LLM call durations.

---

## Real-Time SSE Progress Stream

Use Server-Sent Events to stream workflow progress for a single incident:

```bash
curl -N http://localhost:4001/api/incidents/INC-2048/stream \
  -H "Authorization: Bearer <access_token>"
```

Event types emitted include:

- `workflow_queued`
- `workflow_started`
- `node_started`
- `node_completed`
- `workflow_done`

---

## Session Workflow (No Repeated Overview Needed)

To continue work in a new session without repeating project context, start with:

1. `execute-steps.md`
2. `.copilot/current-state.md`
3. `.github/workflows/copilot-instructions.md`
4. `FUTURE_SCOPE.md`

This captures current implementation state, active issue, branch workflow, PR requirements, and post-merge updates.

---

## Documentation

- [Architecture](docs/architecture.md)
- [Product Plan](docs/product-plan.md)
- [Future Scope](FUTURE_SCOPE.md)
- [Execution Playbook](execute-steps.md)

