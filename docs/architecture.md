# Architecture

## System Overview

AegisOps Copilot uses a layered monorepo design so the product can grow without turning into a single tangled app.

```mermaid
flowchart LR
  user[On-call Engineer] --> web[Next.js Control Room]
  web --> api[Python FastAPI Service]
  api --> graph[LangGraph Incident Workflow]
  graph --> smith[LangSmith Traces]
  graph --> store[(Incident Store)]
  graph --> provider[LLM Provider Switcher]
  provider --> graph
  api --> web
```

## Layered Design

### Presentation Layer

The web app is a command-center style dashboard that emphasizes incident status, active agent steps, and the current recommendation.

### API Layer

The API service owns request validation, orchestration entry points, and the in-memory data facade used by the demo. It is implemented in Python with FastAPI, and it becomes the integration point for queues, persistence, auth, and external systems.

### Agent Layer

The agent workflow lives inside the Python backend. LangGraph coordinates a small set of focused agents: assess, evidence gathering, mitigation drafting, and response packaging. The active LLM is selected at runtime so the same graph can be exercised with Groq, OpenAI, or Anthropic models.

### Observability Layer

LangSmith is wired through environment variables and traceable workflow entrypoints so every agent step can be inspected, compared, and evaluated.

## Runtime Boundaries

- Web: presentation and command-center UX
- API: routing, validation, orchestration, and persistence adapters
- Agent core: graph execution, prompt logic, and LLM selection
- Shared models: Python Pydantic schemas inside the API package

## Production Extension Points

- Replace the in-memory store with Postgres + Prisma or Drizzle
- Add Redis-backed queues for long-running incident workflows
- Connect real telemetry providers and runbook search
- Add a provider registry for model routing, evals, and fallback policies
- Add auth, RBAC, and audit logging before external rollout
