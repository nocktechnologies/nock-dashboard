# ADR-001: Django Monolith Architecture

**Status:** Accepted
**Date:** 2026-03-14

## Context
NockCC needed a framework for rapid development of a multi-feature dashboard (pipeline, sessions, spend, context, notifications, remote control).

## Decision
Django monolith with app-per-domain pattern, using Channels for WebSocket and Celery for async work.

## Rationale
- Django's ORM, admin, and auth provide fast iteration
- Channels adds WebSocket without a separate service
- Celery handles async (webhooks, polling, notifications)
- Matches the Nexus pattern already proven at Nock Technologies
- Microservices would add deployment complexity without proportional benefit at current scale

## Consequences
- All features share one database and one deployment
- App boundaries are enforced by convention (separate models.py, views.py, tasks.py per app)
- Cross-app imports happen (e.g., pipeline.tasks → teams.signals) — keep these explicit
