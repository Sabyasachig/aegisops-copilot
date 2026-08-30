# Copilot Session Bootstrap Prompt

Use this prompt at the beginning of each coding session for this repository.

## Goal

Start from existing repository context without asking the user for a repeated project overview.

## Mandatory startup sequence

Read these files in order before making changes:

1. execute-steps.md
2. .copilot/current-state.md
3. .github/workflows/copilot-instructions.md
4. FUTURE_SCOPE.md

If these files exist, do not ask the user for project overview again.
Start directly from Active Work in .copilot/current-state.md.

## Execution rules

- Source repository environment variables from root .env before running commands.
- Use the repository Python interpreter at .venv/bin/python.
- If Active Work exists, continue it first; otherwise select one open issue.
- Create a feature branch from main using feat/issue-<id>-<slug> or fix/issue-<id>-<slug>.
- Implement with architecture-safe changes and matching tests.
- Push branch and open PR.
- PR body must include one of: Closes #<id>, Fixes #<id>, Resolves #<id>.
- Use .github/pull_request_template.md for PR description.
- After merge, update continuity files:
  - .copilot/current-state.md
  - FUTURE_SCOPE.md
  - .github/workflows/copilot-instructions.md

## PR and merge completion checklist

- Link the open issue in PR with closing keyword.
- Include exact test commands and test results in PR body.
- After merge, confirm issue is closed.
- Move completed item into Completed Work in .copilot/current-state.md.
- Set Next Suggested Issue for the next session.

## Definition of done

- Code merged to main
- Linked issue auto-closed
- Tests executed and reported
- Continuity state updated for next session
