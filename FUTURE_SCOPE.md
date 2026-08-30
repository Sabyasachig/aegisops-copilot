# Future Scope — AegisOps Copilot

## Current State Checkpoint (2026-08-31)

This section is the session handoff snapshot so future work starts from the
latest known state without rediscovery.

### Delivered in codebase

- Issue #1 (JWT auth): implemented
- Issue #2 (RBAC): implemented
- Issue #3 (Webhook HMAC validation): implemented
- Issue #4 (Rate limiting): implemented
- Issue #5 (Async task queue): implemented
- Issue #6 (SSE real-time agent progress): merged to `main` via PR #31
- Issue #7 (Structured logging): merged to `main` via PR #30
- Issue #8 (Prometheus Metrics + Grafana Dashboard): merged to `main` via PR #32

### PR status for Issue #7

- Merged PR: `#30` (`feat/issue-7-structured-logging-observability` -> `main`)
- GitHub Issue #7 status: closed.

### Current active implementation

- Issue #9: OpenTelemetry Distributed Tracing
- Active branch: `feat/issue-9-opentelemetry-distributed-tracing`
- Status: implemented locally, pending PR
- Validation: `23 passed, 1 warning` on targeted backend suite

### Recently completed

- Issue #8: merged PR `#32` and issue closed
- Validation: `21 passed, 1 warning` on targeted tests (`test_metrics`, `test_health`, `test_execute`, `test_events`, `test_logging`)
- Issue #6: merged PR `#31` and issue closed
- Validation: `23 passed` on targeted tests (`test_events`, `test_incidents`, `test_execute`, `test_logging`)

### Open issues currently visible on GitHub

- #9 OpenTelemetry Distributed Tracing
- #10 Circuit Breaker for LLM Providers
- #11 Human-in-the-Loop Approval Gate
- #12 Tool Use — Real Integrations
- #13 Agent Memory & Context Store (pgvector)
- #14 RAG Runbook Knowledge Base
- #15 Confidence Scoring & Auto-Escalation
- #16 Audit Log
- #17 OpsGenie & Alertmanager Webhook Handlers
- #18 Slack Notification on Run Completion
- #20 Kubernetes Helm Chart
- #21 Managed Database & Cache (Cloud-Ready)
- #22 LLM Cost Tracking per Run

### Issue #7 implementation notes (local branch)

- Added centralized structured logging config with `structlog`.
- Added environment-aware renderer selection:
	- `AIOPS_LOG_FORMAT=json|console|auto`
	- `auto` => JSON in production, console in non-production
- Added log context propagation (`incident_id`, `run_id`, `user_id`, `request_id`) for API and worker flows.
- Added workflow/node timing logs for LLM and graph transitions.
- Added tests: `apps/api/tests/test_logging.py`.

### Test command used in this session

Run from repo root:

```bash
set -a && source /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/.env && set +a \
&& cd /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/apps/api \
&& PYTHONPATH=src /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/.venv/bin/python -m pytest -q tests/test_logging.py
```

Result in this session: `4 passed`.

### Important environment note

- `apps/api/pyproject.toml` requires Python `>=3.11`.
- Current root `.venv` is Python `3.12.2`.

Each section below maps to a GitHub Issue / Pull Request.
Label convention: `enhancement`, `security`, `infra`, `agent`, `integration`, `observability`

---

## Phase 1 — Security & Auth
> Goal: No endpoint is publicly accessible without authentication.

### Issue #1 · JWT Authentication middleware
**Label:** `security` `enhancement`

Add JWT-based authentication to every API endpoint.

- [ ] Add `python-jose` + `passlib` dependencies
- [ ] `POST /api/auth/token` — issue JWT on valid credentials
- [ ] `POST /api/auth/refresh` — refresh access token
- [ ] FastAPI `Depends(get_current_user)` guard on all protected routes
- [ ] Store hashed user credentials in a `users` table (Alembic migration)
- [ ] Unit tests for token issuance and rejection

**Acceptance criteria:** Unauthenticated requests return `401`. Valid tokens expire after a configurable TTL.

---

### Issue #2 · Role-Based Access Control (RBAC)
**Label:** `security` `enhancement`

Three roles: `viewer` (read-only), `operator` (can execute agents), `admin` (full access).

- [ ] Add `role` column to `users` table
- [ ] Permission decorators / dependencies per endpoint
- [ ] Admin-only: `DELETE /api/incidents/{id}`
- [ ] Operator+: `POST /api/incidents/{id}/execute`
- [ ] Viewer: read-only access to incidents and runs

---

### Issue #3 · Webhook HMAC Signature Validation
**Label:** `security`

PagerDuty, OpsGenie, and Alertmanager sign their webhook payloads. We must verify them.

- [ ] Verify `X-PagerDuty-Signature` on `/api/webhooks/pagerduty`
- [ ] Generic HMAC-SHA256 verification with configurable secret
- [ ] Return `403` on invalid signatures
- [ ] Add `WEBHOOK_SECRET` env var

---

### Issue #4 · Rate Limiting
**Label:** `security` `infra`

Prevent API abuse and runaway LLM costs.

- [ ] Add `slowapi` (Redis-backed) rate limiter
- [ ] Per-IP and per-user limits on `/api/incidents/{id}/execute`
- [ ] Configurable limits via env vars
- [ ] Return `429 Too Many Requests` with `Retry-After` header

---

## Phase 2 — Reliability & Observability

### Issue #5 · Async Task Queue for Agent Execution
**Label:** `enhancement` `infra`

LLM calls block for 10–30 seconds. Move agent execution to background jobs.

- [ ] Add `arq` (async task queue backed by Redis) dependency
- [ ] `POST /api/incidents/{id}/execute` enqueues a job and returns `202 Accepted` immediately
- [ ] Worker picks up job, runs LangGraph, updates DB
- [ ] `GET /api/runs/{run_id}/status` for polling
- [ ] Add `arq` worker service to `docker-compose.yml`

---

### Issue #6 · Server-Sent Events (SSE) for Real-Time Agent Progress
**Label:** `enhancement`

Push each agent node completion to the UI in real time instead of polling.

- [ ] `GET /api/incidents/{id}/stream` — SSE endpoint
- [ ] Emit events: `node_started`, `node_completed`, `workflow_done`
- [ ] Next.js dashboard subscribes to event stream and updates stage indicators live
- [ ] Graceful fallback to polling if SSE not supported

---

### Issue #7 · Structured Logging with structlog
**Label:** `observability`

Replace plain `print`/`logging` with structured JSON logs for Datadog/CloudWatch ingestion.

- [ ] Add `structlog` dependency
- [ ] Configure JSON renderer in production, console renderer in development
- [ ] Attach `incident_id`, `run_id`, `user_id` to every log entry via context vars
- [ ] Log all agent node transitions and LLM call durations

---

### Issue #8 · Prometheus Metrics + Grafana Dashboard
**Label:** `observability` `infra`

Expose application metrics for operational visibility.

- [ ] Add `prometheus-fastapi-instrumentator`
- [ ] `GET /metrics` endpoint
- [ ] Custom metrics: `agent_run_duration_seconds`, `llm_token_total`, `incident_mttr_seconds`
- [ ] Add `prometheus` + `grafana` services to `docker-compose.yml`
- [ ] Import pre-built Grafana dashboard JSON

---

### Issue #9 · OpenTelemetry Distributed Tracing
**Label:** `observability`

Trace requests end-to-end across FastAPI → LangGraph → LLM provider.

- [ ] Add `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`
- [ ] Export traces to Jaeger (add to docker-compose) or OTLP collector
- [ ] Propagate trace context into LangGraph nodes
- [ ] Correlate with LangSmith traces via trace ID

---

### Issue #10 · Circuit Breaker for LLM Providers
**Label:** `enhancement` `infra`

Automatically failover to a backup LLM provider when the primary is down or slow.

- [ ] Add `tenacity` retry + circuit breaker around `get_chat_model()` calls
- [ ] Configurable fallback chain: `groq → openai → anthropic`
- [ ] Expose circuit state in `/api/health`
- [ ] Alert on open circuit via structured log event

---

## Phase 3 — Agentic Intelligence

### Issue #11 · Human-in-the-Loop Approval Gate
**Label:** `agent` `enhancement`

Before the agent executes high-risk runbook steps, require an explicit engineer approval.

- [ ] Use LangGraph `interrupt()` to pause the graph before `draft_response` node
- [ ] `POST /api/runs/{run_id}/approve` — resume graph with approval
- [ ] `POST /api/runs/{run_id}/reject` — abort graph with rejection reason
- [ ] UI: "Approve / Reject" buttons on run detail view
- [ ] Timeout: auto-escalate if no response within configurable window

---

### Issue #12 · Tool Use — Real Integrations
**Label:** `agent` `integration`

Give agents the ability to call real systems during investigation.

- [ ] Kubernetes tool: `kubectl get pods`, describe deployments
- [ ] Datadog/Grafana tool: fetch metric snapshots for the affected service
- [ ] Slack tool: post incident summary to configured channel
- [ ] Jira/Linear tool: create post-incident ticket
- [ ] Each tool is a `@tool`-decorated LangChain function registered on the graph

---

### Issue #13 · Agent Memory & Context Store
**Label:** `agent` `enhancement`

Let the agent recall patterns from past incidents affecting the same service.

- [ ] Add `pgvector` extension to PostgreSQL
- [ ] Embed incident summaries and store in `incident_embeddings` table
- [ ] At triage time, retrieve top-k similar past incidents
- [ ] Inject retrieved context into the `assess` node prompt
- [ ] Alembic migration for `incident_embeddings`

---

### Issue #14 · RAG Runbook Knowledge Base
**Label:** `agent` `integration`

Agent retrieves relevant runbooks via semantic search before drafting a response.

- [ ] Ingest Markdown runbooks from a configurable directory
- [ ] Chunk and embed into `pgvector`
- [ ] `gather_evidence` node queries the knowledge base
- [ ] Surface retrieved runbook snippets in the run output
- [ ] `POST /api/admin/runbooks` — upload new runbook

---

### Issue #15 · Confidence Scoring & Auto-Escalation
**Label:** `agent` `enhancement`

Agent reports how confident it is; low-confidence automatically escalates to a human.

- [ ] Structured LLM output with a `confidence` field (0.0–1.0)
- [ ] If `confidence < 0.6`, set run status to `needs_human` and skip auto-actions
- [ ] Expose confidence score in run response and UI
- [ ] Configurable threshold via env var

---

## Phase 4 — Data & Integrations

### Issue #16 · Audit Log
**Label:** `enhancement` `security`

Immutable record of every agent action and human decision for compliance.

- [ ] `audit_logs` table: `actor`, `action`, `resource_id`, `payload`, `timestamp`
- [ ] Write audit entries on: incident creation, agent execution, approval/rejection, status change
- [ ] `GET /api/audit?incident_id=X` — paginated audit trail
- [ ] Alembic migration

---

### Issue #17 · OpsGenie & Alertmanager Webhook Handlers
**Label:** `integration`

Extend webhook ingestion to natively support OpsGenie and Prometheus Alertmanager.

- [ ] `POST /api/webhooks/opsgenie` — parse OpsGenie v2 alert payload
- [ ] `POST /api/webhooks/alertmanager` — parse Prometheus Alertmanager webhook
- [ ] Signature validation for each provider
- [ ] Map severity levels to AegisOps severity schema

---

### Issue #18 · Slack Notification on Run Completion
**Label:** `integration`

Notify the on-call channel when an agent run completes or requires approval.

- [ ] Add `slack-sdk` dependency
- [ ] Post formatted message with incident title, severity, summary, and action URL
- [ ] Configurable `SLACK_WEBHOOK_URL` env var
- [ ] Include Approve/Reject deep-links when run is `needs_human`

---

## Phase 5 — Infrastructure & CI/CD

### Issue #19 · GitHub Actions CI Pipeline
**Label:** `infra`

Automated test and lint on every pull request.

- [ ] `.github/workflows/ci.yml`
- [ ] Steps: `ruff` lint → `pytest` unit tests → Docker build smoke test
- [ ] Python test coverage report as PR comment
- [ ] Next.js type-check + build validation

---

### Issue #20 · Kubernetes Helm Chart
**Label:** `infra`

Package the application for deployment to any Kubernetes cluster.

- [ ] `helm/aegisops/` chart with templates for all services
- [ ] `values.yaml` with sane production defaults
- [ ] Horizontal Pod Autoscaler for the API deployment
- [ ] Kubernetes `Secret` for all sensitive env vars
- [ ] Health check probes wired to `/api/health`

---

### Issue #21 · Managed Database & Cache (Cloud-Ready)
**Label:** `infra`

Replace Docker containers with managed cloud services for production.

- [ ] Document migration path to AWS RDS / GCP Cloud SQL
- [ ] Document migration path to AWS ElastiCache / GCP Memorystore
- [ ] Terraform module for RDS + ElastiCache (optional)
- [ ] Ensure `DATABASE_URL` / `REDIS_URL` are the only required changes

---

### Issue #22 · Cost Tracking per LLM Call
**Label:** `observability` `enhancement`

Track token spend per incident, per provider, and per model.

- [ ] `llm_usage` table: `run_id`, `provider`, `model`, `prompt_tokens`, `completion_tokens`, `cost_usd`
- [ ] Intercept LangChain callbacks to capture token counts
- [ ] `GET /api/admin/usage` — aggregated cost report
- [ ] Alert threshold: `AIOPS_MAX_COST_PER_RUN_USD`

---

## Contribution Guide

1. Pick an issue from the list above.
2. Create a branch: `git checkout -b feature/issue-<N>-short-description`
3. Implement the feature with tests.
4. Open a PR referencing the issue: `Closes #N`
5. Ensure CI passes before requesting review.
