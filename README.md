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
                │  /api/incidents  /api/runs  /api/execute │
                │  /api/webhooks   /api/providers          │
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
│   │   │   ├── llm.py               # Multi-provider LLM factory
│   │   │   ├── models.py            # Pydantic models
│   │   │   ├── settings.py          # Pydantic-settings (env vars)
│   │   │   ├── cache.py             # Async Redis helpers
│   │   │   ├── store.py             # Seed data
│   │   │   └── routers/
│   │   │       ├── health.py        # GET /api/health (checks PG + Redis)
│   │   │       ├── incidents.py     # GET /api/incidents, /api/incidents/{id}
│   │   │       ├── runs.py          # GET /api/runs/{incident_id}
│   │   │       ├── execute.py       # POST /api/incidents/{id}/execute
│   │   │       ├── providers.py     # GET /api/providers
│   │   │       └── webhooks.py      # POST /api/webhooks/generic|pagerduty
│   │   │   └── db/
│   │   │       ├── engine.py        # Async SQLAlchemy engine + session
│   │   │       ├── orm_models.py    # IncidentRow, AgentRunRow ORM
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

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Health check (PostgreSQL + Redis status) |
| `GET` | `/api/incidents` | List all incidents (Redis-cached, 60s TTL) |
| `GET` | `/api/incidents/{id}` | Get a single incident |
| `POST` | `/api/incidents/{id}/execute` | Trigger LangGraph agent workflow |
| `GET` | `/api/runs/{incident_id}` | List all agent runs for an incident |
| `GET` | `/api/providers` | List available LLM providers |
| `POST` | `/api/webhooks/generic` | Ingest incident from any alerting tool |
| `POST` | `/api/webhooks/pagerduty` | Ingest PagerDuty v3 webhook |

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
# Generic webhook
curl -X POST http://localhost:4001/api/webhooks/generic \
  -H "Content-Type: application/json" \
  -d '{
    "id": "INC-9999",
    "title": "API gateway 502 rate exceeding threshold",
    "service": "api-gateway",
    "severity": "critical",
    "owner": "platform-team",
    "summary": "502 error rate jumped from 0.1% to 8% after last deploy"
  }'
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `AIOPS_LLM_PROVIDER` | `groq` | Active LLM provider |
| `AIOPS_LLM_MODEL` | `llama-3.1-8b-instant` | Model name |
| `AIOPS_DATABASE_URL` | *(postgres container)* | Async PostgreSQL URL |
| `AIOPS_REDIS_URL` | *(redis container)* | Redis URL |
| `GROQ_API_KEY` | — | Groq API key |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `LANGSMITH_API_KEY` | — | LangSmith tracing key |
| `AIOPS_LANGSMITH_PROJECT` | `aegisops-copilot` | LangSmith project name |

---

## Documentation

- [Architecture](docs/architecture.md)
- [Product Plan](docs/product-plan.md)
- [Future Scope](FUTURE_SCOPE.md)

