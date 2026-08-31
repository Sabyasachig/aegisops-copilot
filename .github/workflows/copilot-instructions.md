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
- Human-in-the-loop approval gate (Issue #11) is on PR #35 — awaiting merge.
- Issues #6, #7, #8, #9, #10 are closed.

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

Verified in this session (Issue #11):

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

## Next recommended actions

1. Merge PR #35 (Issue #11 — human-in-the-loop approval gate).
2. After merge: `git checkout main && git pull origin main` and update all continuity files.
3. Start Issue #12 (Tool Integrations — K8s, Datadog, Slack, Jira) on branch `feat/issue-12-tool-integrations`.
