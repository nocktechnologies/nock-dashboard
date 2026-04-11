# Design Document: Claude Command Center (NockCC)

**Created:** 2026-03-14
**Author:** Kevin Wills / Nock Technologies
**GitHub:** kkwills13/nock-command-center
**Asana Project:** 1213659188123153

## Vision

NockCC is a unified operations dashboard for multi-agent AI development workflows at Nock Technologies. It centralizes visibility into Claude Code sessions, GitHub PR pipelines, Anthropic API spend, prompt/skill context inventory, and push alert routing.

## Problem Statement

As multi-agent AI development scales — multiple Claude Code instances, multiple repos, multiple team members running parallel sessions — there is no single place to see what is happening. Costs are opaque, context (CLAUDE.md files, skill files, memory) is scattered, and important events (failed PRs, budget overruns, agent errors) require manual monitoring.

NockCC solves this with a live, WebSocket-driven dashboard.

## Architecture Decision: Django Monolith

Chosen over microservices for speed of initial development. Django's ORM, admin, and auth system provide fast iteration. Channels adds WebSocket capability without a separate service. Celery handles async work (webhook processing, polling, notifications). This matches the Nexus pattern already proven effective at Nock Technologies.

## App Design

### dashboard/
Main overview. Shows live counts: active sessions, open PRs, spend this month, unread alerts. WebSocket consumer pushes updates every 30s. No page reload needed.

### pipeline/
Receives GitHub webhooks (push, pull_request, check_run events). Stores PRs with CI status. Shows per-repo pipeline boards. Validates webhook HMAC signature using `GITHUB_WEBHOOK_SECRET`.

### sessions/
Tracks Claude Code sessions. Each session has: project, branch, start time, end time, model used, token count, cost estimate. Status: active / completed / error. Agent type tracking (subagent_type field).

### context/
Inventory of CLAUDE.md files and skill files across repos. Each entry: repo, file path, last_updated, word count, key topics (extracted). Allows searching across all context files from one UI.

### spend/
Polls Anthropic Admin API for usage data. Stores daily snapshots. Shows: total spend, spend by model, spend by project, budget burn rate, projected month-end. Alerts when approaching budget threshold.

### notifications/
Alert rules engine. Rules: trigger_type (spend_threshold, pr_failed, session_error, etc.) + channel (slack/discord) + threshold. Celery task evaluates rules every 5 minutes and dispatches webhooks.

### accounts/
Custom user model (extends AbstractUser). API key model for programmatic access. Roles: admin, viewer. Login/logout views.

### core/
Shared: TimeStampedModel (created_at, updated_at), SlugMixin, JSONResponseMixin. Utility functions for Decimal handling, ID generation.

## Data Model Sketch

```
Project
  - name, slug, github_repo, github_org
  - created_at, updated_at

PullRequest
  - project FK, pr_number, title, state, branch
  - ci_status, author, created_at, merged_at
  - last_synced

AgentSession
  - project FK, branch, model, session_type
  - started_at, ended_at, status
  - prompt_tokens, completion_tokens, cost_usd (Decimal)

ContextFile
  - project FK, file_path, file_type (claude_md / skill / memory)
  - content_hash, word_count, last_updated

SpendSnapshot
  - date, model, prompt_tokens, completion_tokens, total_cost (Decimal)
  - project FK (nullable — org-level snapshots)

AlertRule
  - name, trigger_type, channel, threshold
  - active, last_fired_at

Notification
  - rule FK, fired_at, payload, delivered (bool)
```

## WebSocket Plan

Django Channels consumer on `/ws/dashboard/`. Broadcasts:
- Session start/end events
- New PR opened / CI status changed
- Spend threshold crossed
- New alert fired

Frontend (Alpine.js) connects on page load and updates counters in real time.

## Webhook Security

GitHub webhooks: HMAC-SHA256 signature validation using `GITHUB_WEBHOOK_SECRET`. Validation in `pipeline/views.py` before any processing. Invalid signatures → 403.

## Celery Tasks (planned)

- `pipeline.tasks.sync_github_prs` — poll GitHub API every 5 min for PR status
- `spend.tasks.poll_anthropic_usage` — poll Anthropic Admin API daily
- `notifications.tasks.evaluate_alert_rules` — check rules every 5 min
- `sessions.tasks.mark_stale_sessions` — mark sessions inactive after 4h with no update

## Phased Roadmap

### Phase 1 — Scaffold + Auth (current)
Django project, 8 apps, base template, auth, basic admin.

### Phase 2 — Pipeline
GitHub webhook receiver, PR model, CI status board, per-repo views.

### Phase 3 — Sessions
Session tracking API (accept POST from Claude Code hooks), session list/detail UI.

### Phase 4 — Spend
Anthropic Admin API polling, spend snapshots, cost dashboard with Chart.js.

### Phase 5 — Context
CLAUDE.md inventory, skill file catalog, search UI.

### Phase 6 — Notifications
Alert rules engine, Slack/Discord dispatch, notification log.

### Phase 7 — WebSockets
Live dashboard updates via Channels, real-time session status.

### Phase 8 — Polish
Proper Tailwind build, responsive layout, dark/light toggle, user preferences.

## Initial Conversation Context

This design document was created from the following project initialization prompt:

> Full Django project scaffold with these apps:
> - config/ — Django project settings (dev/prod split), urls, wsgi, asgi
> - dashboard/ — Main overview dashboard
> - pipeline/ — GitHub webhook receiver, PR tracking, CI status
> - sessions/ — Claude Code session tracking, agent status
> - context/ — CLAUDE.md inventory, skill files, memory map
> - spend/ — Anthropic API usage, cost tracking, budgets
> - notifications/ — Slack/Discord push alerts
> - accounts/ — User auth, API key management
> - core/ — Shared models, utils, base views
>
> Stack: Django 5.x + PostgreSQL, Celery + Redis, Django Channels + Daphne, Alpine.js + Tailwind CSS (CDN), Chart.js (CDN)

The GitHub repository is `kkwills13/nock-command-center`, a private repo under the Nock Technologies organization.
