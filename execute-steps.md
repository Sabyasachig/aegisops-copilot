# Execute Steps

This playbook is the single source of truth for starting and finishing feature work in this repository.
Follow it exactly so no repeated project overview is needed in future sessions.

## 1. Always load context first

At the start of every session, read these files in order:

1. `execute-steps.md`
2. `.copilot/current-state.md`
3. `.github/workflows/copilot-instructions.md`
4. `FUTURE_SCOPE.md`

Goal:
- understand current implementation status
- identify open target issue
- continue from the latest known checkpoint

## 2. Environment bootstrap

From repository root:

```bash
set -a && source /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/.env && set +a
```

Use project Python:

```bash
/Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/.venv/bin/python --version
```

Expected:
- Python 3.12.x

## 3. Select one issue to implement

Pick one open GitHub issue that is not already in progress.

Selection priority:
1. highest product value
2. lowest architecture risk
3. best testability in current stack

Record selection in `.copilot/current-state.md` under "Active Work" before coding.

## 4. Create feature branch

Branch naming convention:
- `feat/issue-<id>-<short-slug>` for features
- `fix/issue-<id>-<short-slug>` for fixes

Commands:

```bash
git checkout main
git pull origin main
git checkout -b feat/issue-<id>-<short-slug>
```

## 5. Implement with architecture discipline

Rules:
- keep API contracts backward compatible unless issue explicitly requires change
- isolate cross-cutting concerns in dedicated modules
- add tests for all behavior changes
- update docs for runtime/config changes

Minimum touched artifacts per feature:
- code
- tests
- continuity docs (`.copilot/current-state.md`, `FUTURE_SCOPE.md`, `.github/workflows/copilot-instructions.md`)

## 6. Validate before commit

Run relevant tests first, then broader suite when possible.

Example commands:

```bash
cd apps/api
PYTHONPATH=src /Users/sabyasachighosh/Projects/multi_agent/aegisops-copilot/.venv/bin/python -m pytest -q
```

If full suite is heavy, run targeted tests and explicitly note scope in PR.

## 7. Commit and push

```bash
git add -A
git commit -m "feat(issue-<id>): <short summary>"
git push -u origin feat/issue-<id>-<short-slug>
```

## 8. Raise PR

Use `.github/pull_request_template.md`.

PR body must include one of:
- `Closes #<id>`
- `Fixes #<id>`
- `Resolves #<id>`

This ensures issue auto-closes after merge.

## 9. Post-merge mandatory updates

After PR merge, do all of the following:

1. confirm linked issue is closed
2. update `.copilot/current-state.md`:
   - move issue from Active Work to Completed Work
   - add merged PR number and date
   - set next candidate issue
3. update `FUTURE_SCOPE.md` checkpoint section
4. update `.github/workflows/copilot-instructions.md` with latest resume context
5. sync local main and delete feature branch

Commands:

```bash
git checkout main
git pull origin main
git branch -d feat/issue-<id>-<short-slug>
```

## 10. Definition of done

A feature is done only when all are true:
- code merged to `main`
- linked issue closed
- tests executed and reported
- state/checkpoint files updated
- next issue preselected in `.copilot/current-state.md`
