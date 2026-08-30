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

## Execution rules

- Source repository environment variables from root .env before running commands.
- Use the repository Python interpreter at .venv/bin/python.
- Select one open issue, create a feature branch from main, implement with tests, raise PR.
- PR body must include one of: Closes #<id>, Fixes #<id>, Resolves #<id>.
- After merge, update continuity files:
  - .copilot/current-state.md
  - FUTURE_SCOPE.md
  - .github/workflows/copilot-instructions.md

## Definition of done

- Code merged to main
- Linked issue auto-closed
- Tests executed and reported
- Continuity state updated for next session
