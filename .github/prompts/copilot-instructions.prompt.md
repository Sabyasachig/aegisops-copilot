# AegisOps Copilot instructions

Use this prompt at the start of each coding session for this repository.

## Repository context

This repo contains:

- Python 3.11+ FastAPI control plane under `apps/api`
- LangGraph agent orchestration and tool integrations in `apps/api/src/aegisops_api`
- PostgreSQL + Redis backing services via Docker Compose
- Next.js dashboard under `apps/web`
- Repository-level continuity docs in `.copilot/`, `.github/workflows/`, and `FUTURE_SCOPE.md`

The project is organized around issue-driven delivery and must preserve the existing architecture patterns rather than introducing ad hoc structure.

## Mandatory startup sequence

Before making code changes, read these files in this order:

1. `execute-steps.md`
2. `.copilot/current-state.md`
3. `.github/workflows/copilot-instructions.md`
4. `FUTURE_SCOPE.md`

If those files exist, do not ask the user for a project overview again. Start from the active work in `.copilot/current-state.md` and continue it before opening a new task.

## Operating rules

- Source repo environment variables from the root `.env` before running commands.
- Use the repository Python interpreter at `.venv/bin/python`.
- Prefer existing project patterns and naming conventions from the FastAPI + LangGraph codebase.
- If Active Work is present, continue it first; otherwise select one open issue from the repo status and start from there.
- Create a branch from `main` using `feat/issue-<id>-<slug>` or `fix/issue-<id>-<slug>` naming.
- Keep edits narrow, architecture-safe, and consistent with the existing layered design.
- Add or update tests whenever behavior changes.
- Run focused validation before claiming completion.
- Push the branch and open a PR when the change is ready.
- Use `.github/pull_request_template.md` for PR details.
- PR body must include one of: `Closes #<id>`, `Fixes #<id>`, or `Resolves #<id>`.
- After merge, update the continuity files:
  - `.copilot/current-state.md`
  - `FUTURE_SCOPE.md`
  - `.github/workflows/copilot-instructions.md`

## Repo-specific validation pattern

Use the project environment and test conventions from the repo state, for example:

```bash
set -a && source /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/.env && set +a
cd /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/apps/api
PYTHONPATH=src /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/.venv/bin/python -m pytest -q tests/
```

Do not rely on an unrelated global Python environment. Prefer the repo-local `.venv` and the root `.env` configuration.

## Definition of done

- The issue is implemented in the repo without architectural drift
- Tests covering the change pass
- The branch is ready for PR review with a closing issue reference
- Continuity and state files are updated for the next session
