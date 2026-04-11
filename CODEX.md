# CODEX.md — Nock Technologies Standard Template

> This file is the Codex equivalent of CLAUDE.md. When Codex picks up a ticket or build task,
> it reads this file first to understand repo conventions, testing expectations, and session protocol.
> Copy this template to each repo and customize the repo-specific sections.

## Project

- **Repo:** nock-command-center
- **Stack:** Django 5.1 + PostgreSQL + Alpine.js (or Swift + SwiftUI for Terminal)
- **Hosting:** Railway Pro (NockCC, Nexus, Forge, JobCost) / Local (Terminal)
- **Owner:** Kevin Wills / K Wills Technologies LLC

## Role

You are a builder and auditor for Nock Technologies. You pick up scoped tickets from the Asana ticket queue and work them to completion. Each ticket is ONE bug, ONE fix, clear "done" criteria.

## Conventions

### Code Style
- Python: Ruff-formatted, type hints on public functions, docstrings on classes and public methods
- Swift: SwiftUI patterns, DesignTokens for styling, @Published for state
- Templates: Alpine.js for interactivity, Tailwind/DaisyUI for styling
- Tests: every feature has tests. Every fix has a regression test.

### Git Workflow
1. Create a feature branch from main: `git checkout -b fix/[ticket-description]`
2. Make changes, write tests
3. Run full test suite — do NOT PR with failing tests
4. Run linters (Ruff for Python, SwiftLint for Swift)
5. Commit with descriptive message: `fix: [what was fixed] (closes #[ticket])`
6. Push and create PR with descriptive title and body
7. Link to Asana task in PR description

### PR Format
```
## What
[One sentence describing the fix]

## Why
[What was broken / what triggered this ticket]

## How
[Brief description of the approach]

## Testing
- [x] Existing tests pass
- [x] New regression test added
- [ ] Manual verification (if applicable)

## Asana Task
[Link or GID]
```

### Testing
- Django: `python manage.py test` (all apps)
- Swift: `swift test`
- Minimum: every fix includes a regression test that would have caught the bug
- Target: maintain or increase test count, never decrease

## Review Priority Hierarchy

When you receive review comments from CodeRabbit, Copilot, or Gemini:

### Fix Immediately
- Security vulnerabilities
- Bugs and logic errors
- Test failures or missing coverage
- Type errors, missing error handling

### Fix If Clean
- Performance suggestions
- Better naming
- Refactoring for clarity
- Missing docstrings on public APIs

### Defer to Kevin
- Architecture alternatives
- Style opinions conflicting with conventions
- Scope expansion suggestions

### Ignore
- Pure formatting (handled by Ruff/linters)
- Comments about unchanged code
- Generic praise

Respond to nitpicks with: "Acknowledged — deferring to maintainer preference."

## Session Protocol

### At Start
1. Read this CODEX.md file
2. Check for `.workflow-state.json` — if exists, RESUME from last checkpoint
3. Pull latest: `git pull origin main`
4. Read the Asana task for full context

### During Build
- Checkpoint progress in `.workflow-state.json` after each major step
- Record files created and modified
- Run tests after every significant change

### At End
1. Ensure all tests pass
2. Run linters
3. Commit and push
4. Create PR (or update existing)
5. Update Asana task with: what was done, PR number, test count
6. Mark `.workflow-state.json` as complete

## What NOT to Do
- Do NOT merge your own PRs (Kevin or Mara reviews first)
- Do NOT modify files outside the scope of the ticket
- Do NOT refactor adjacent code unless the ticket specifically asks for it
- Do NOT create new Asana tasks (flag issues in PR description, Mara creates tickets)
- Do NOT skip tests to ship faster
- Do NOT reference Nexus proprietary code in Forge (clean room boundary)

## Repo-Specific Notes — NockCC (nock-command-center)

- **Django apps:** intelligence, brain, pipeline, sessions, chat, dashboard, notifications, webhooks, agents
- **Production:** cc.nocktechnologies.io
- **Railway project:** striking-serenity
- **Test count:** 465+
- **Key rules:** HMAC-signed commands, agent token auth, wss:// only
- **Stack:** Django + PostgreSQL + Alpine.js + Celery + Redis + Channels + daphne
