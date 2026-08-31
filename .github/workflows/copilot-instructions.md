# Copilot Continuation Instructions

## Purpose

This file is the restart context for the next coding session. Start from this
state instead of re-discovering project progress.

## Mandatory Session Start Order

Before any coding, always read these files in order:

1. `execute-steps.md`
2. `.copilot/current-state.md`
3. `.github/workflows/copilot-instructions.md`
4. `FUTURE_SCOPE.md`

Do not ask for a project overview if these files are available.

## Project Status Snapshot (2026-08-31)

- Security/auth baseline is implemented (JWT, RBAC, webhook HMAC, rate limits).
- Async execution path is implemented (queue + status polling).
- SSE incident progress streaming (Issue #6) is merged to `main` via PR #31.
- Structured logging (Issue #7) is merged to `main` via PR #30.
- Prometheus + Grafana observability (Issue #8) is merged to `main` via PR #32.
- OpenTelemetry distributed tracing (Issue #9) is merged to `main` via PR #33.
- Circuit breaker for LLM providers (Issue #10) is merged to `main` via PR #34.
- Human-in-the-loop approval gate (Issue #11) is merged to `main` via PR #35.
- Tool integrations K8s/Datadog/Slack/Jira (Issue #12) is merged to `main` via PR #36.
- Agent memory + pgvector context store (Issue #13) is merged to `main` via PR #37.
- RAG runbook knowledge base (Issue #14) — PR #38 open on `feat/issue-14-rag-runbook-kb`.
- Issues #6, #7, #8, #9, #10, #11, #12, #13 are closed.

## Files changed for Issue #12

- `apps/api/src/aegisops_api/tools.py` (new) — four `@tool` functions: `k8s_get_pod_status`, `datadog_get_metric_snapshot`, `slack_post_incident_summary`, `jira_create_incident_ticket`; `ALL_TOOLS` registry
- `apps/api/src/aegisops_api/settings.py` — tool integration config fields
- `apps/api/src/aegisops_api/agents.py` — import ALL_TOOLS + ToolNode; tool calls in `gather_evidence` and `package_outcome`
- `apps/api/pyproject.toml` — `httpx` moved to main deps
- `apps/api/tests/test_tools.py` (new)

## Files changed for Issue #11

- `apps/api/src/aegisops_api/agents.py` — `human_review` interrupt node, `MemorySaver` checkpointer, `GraphInterrupt` handling, `resume_approved`/`resume_thread_id` params
- `apps/api/src/aegisops_api/tasks.py` — `_wait_for_approval_decision()` Redis poller, approval gate in `_execute_async`, `status` passed to `complete_agent_run`
- `apps/api/src/aegisops_api/models.py` — `RunStatus` extended with `needs_human`/`rejected`; `ApproveRunRequest`/`RejectRunRequest`
- `apps/api/src/aegisops_api/settings.py` — `approval_timeout_seconds: int = 300`
- `apps/api/src/aegisops_api/routers/runs.py` — `POST /runs/{run_id}/approve` and `/reject` (require_operator)
- `apps/api/src/aegisops_api/db/repository.py` — `get_run_by_id`, `update_agent_run_status`
- `apps/api/tests/test_approval.py` (new)

## Files changed for Issue #10

- `apps/api/src/aegisops_api/circuit_breaker.py` (new)
- `apps/api/src/aegisops_api/llm.py`
- `apps/api/src/aegisops_api/agents.py`
- `apps/api/src/aegisops_api/settings.py`
- `apps/api/src/aegisops_api/routers/health.py`
- `apps/api/pyproject.toml`
- `apps/api/tests/test_circuit_breaker.py` (new)

## Files changed for Issue #7

- `.env.example`
- `apps/api/pyproject.toml`
- `apps/api/src/aegisops_api/logging_config.py` (new)
- `apps/api/src/aegisops_api/main.py`
- `apps/api/src/aegisops_api/settings.py`
- `apps/api/src/aegisops_api/routers/execute.py`
- `apps/api/src/aegisops_api/tasks.py`
- `apps/api/src/aegisops_api/worker.py`
- `apps/api/src/aegisops_api/agents.py`
- `apps/api/tests/test_logging.py` (new)

## Logging behavior implemented

- Structured logger configured via `structlog`.
- Renderer selection:
	- `AIOPS_LOG_FORMAT=json` forces JSON logs
	- `AIOPS_LOG_FORMAT=console` forces console logs
	- `AIOPS_LOG_FORMAT=auto` uses JSON in production, console otherwise
- Context fields bound through context vars where available:
	- `request_id`
	- `incident_id`
	- `run_id`
	- `user_id`
- Agent instrumentation logs:
	- `workflow_started` / `workflow_completed`
	- `node_started` / `node_completed`
	- `llm_call_started` / `llm_call_completed` with `duration_ms`

## How to run with the repository .env

Always source the repo root `.env` with an absolute path to avoid path issues:

```bash
set -a && source /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/.env && set +a
```

## Test checkpoint

Verified in this session (Issue #12):

```bash
set -a && source /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/.env && set +a \
&& cd /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/apps/api \
&& PYTHONPATH=src /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/.venv/bin/python -m pytest -q tests/
```

Result: `131 passed, 1 warning`.

Previous checkpoint (Issue #11):

```bash
set -a && source /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/.env && set +a \
&& cd /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/apps/api \
&& PYTHONPATH=src /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/.venv/bin/python -m pytest -q tests/
```

Result: `118 passed, 1 warning`.

Previous checkpoint (Issue #10):

```bash
set -a && source /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/.env && set +a \
&& cd /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/apps/api \
&& PYTHONPATH=src /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/.venv/bin/python -m pytest -q tests/test_logging.py
```

Result: `4 passed`.

Additional verification for Issue #8 in this session:

```bash
set -a && source /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/.env && set +a \
&& cd /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/apps/api \
&& PYTHONPATH=src /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/.venv/bin/python -m pytest -q tests/test_metrics.py tests/test_health.py tests/test_execute.py tests/test_events.py tests/test_logging.py
```

Result: `21 passed, 1 warning`.

## Known environment constraint

- `apps/api/pyproject.toml` requires Python `>=3.11`.
- Current root `.venv` is Python `3.12.2`.

## Branch, PR, and Issue-Closure Workflow

- Create feature branches from `main` using `feat/issue-<id>-<slug>` naming.
- PR must include `Closes #<id>` or `Fixes #<id>` to auto-close issue on merge.
- Use `.github/pull_request_template.md` for every PR.
- After merge, update all continuity files:
	- `.copilot/current-state.md`
	- `FUTURE_SCOPE.md`
	- `.github/workflows/copilot-instructions.md`

## Files changed for Issue #14

- `apps/api/src/aegisops_api/memory.py` — `RunbookRow(MemoryBase)`, `RunbookChunk`, `chunk_markdown`, `store_runbook`, `find_relevant_runbooks`, `format_runbooks_for_prompt`, `ingest_runbook_directory`
- `apps/api/src/aegisops_api/agents.py` — `runbook_context: NotRequired[str]` in state; `gather_evidence` injects runbook block into system prompt; `run_incident_workflow` kwarg
- `apps/api/src/aegisops_api/tasks.py` — runbook retrieval + format in pre-workflow memory block alongside similar-incident retrieval
- `apps/api/src/aegisops_api/settings.py` — `runbook_dir: str | None = None`
- `apps/api/src/aegisops_api/routers/runbooks.py` (new) — `POST /api/admin/runbooks` (admin-only, 201)
- `apps/api/src/aegisops_api/main.py` — register `runbooks_router`; `_ingest_runbooks()` startup hook
- `apps/api/alembic/versions/0005_add_runbook_embeddings.py` (new) — `runbook_embeddings` table + IVFFlat cosine index
- `apps/api/tests/test_runbooks.py` (new) — 15 tests

## Files changed for Issue #13

- `apps/api/src/aegisops_api/memory.py` (new) — `IncidentEmbeddingRow(MemoryBase)`, `generate_embedding`, SHA-256 dummy fallback, `store_incident_embedding`, `find_similar_incidents`, `format_similar_incidents_for_prompt`; separate `MemoryBase(DeclarativeBase)` isolates vector tables from main `Base`
- `apps/api/src/aegisops_api/agents.py` — `similar_incidents: NotRequired[str]` in state; `_generate_role_output` injects similar-incident block into HumanMessage
- `apps/api/src/aegisops_api/tasks.py` — memory retrieval + embedding persistence post-workflow
- `apps/api/src/aegisops_api/settings.py` — `memory_enabled`, `memory_embedding_model`, `memory_embedding_dim`, `memory_top_k`
- `apps/api/pyproject.toml` — `pgvector>=0.3` in main deps
- `apps/api/alembic/versions/0004_add_incident_embeddings.py` (new) — pgvector extension + `incident_embeddings` table + IVFFlat index
- `apps/api/tests/test_memory.py` (new) — 11 tests

## Test checkpoint

Verified in this session (Issue #14):

```bash
set -a && source /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/.env && set +a \
&& cd /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/apps/api \
&& PYTHONPATH=src /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/.venv/bin/python -m pytest -q tests/
```

Result: `157 passed, 1 warning`.

Previous checkpoint (Issue #13 — before #14 runbook tests added):

Result: `142 passed, 1 warning`.

## Next recommended actions

1. Merge PR #38 (Issue #14 — RAG runbook knowledge base).
2. After merge: `git checkout main && git pull origin main` and update all continuity files.
3. Start Issue #15 (Confidence Scoring + Auto-Escalation) on branch `feat/issue-15-confidence-scoring`.
