# Nock Dashboard

Multi-tenant SaaS product fork of NockCC (`kkwills13/nock-command-center`). Nock Dashboard is the commercially-deployed version of the command center, built for Nock Technologies customers and hosted on Railway.

---

## What is Nock Dashboard?

Nock Dashboard packages the NockCC agent orchestration platform as a multi-tenant SaaS product. Where NockCC is a single-tenant internal tool, Nock Dashboard adds tenant isolation, subscription billing, multi-user auth (django-allauth), and a hardened deployment path.

**Key differences from NockCC:**
- Multi-tenant data isolation via `tenancy/` app
- `django-allauth` for email-first auth with brute-force protection
- Subscription and billing layer (`billing/` app)
- Independent git history from NockCC (forked 2026-04-11)
- Deployed at `nocktechnologies/nock-dashboard` on Railway

---

## Stack

| Layer | Technology |
|---|---|
| Framework | Django 5.x |
| Database | PostgreSQL (prod), SQLite (dev fallback) |
| Async / WebSockets | Django Channels + Daphne |
| Task queue | Celery + Redis |
| Frontend | Alpine.js + Tailwind CSS (CDN) |
| Charts | Chart.js (CDN) |
| Auth | django-allauth 65.x (email-first) |
| CLI | Click + Rich + httpx |
| Python | 3.12+ |
| Hosting | Railway (auto-deploy from `main`) |

---

## Key Directories

```
nock-dashboard/
├── accounts/        — User account management (allauth integration)
├── agent/           — Agent session tracking
├── billing/         — Subscription and billing (product-fork addition)
├── brain/           — Long-term memory, continuity, morning notes
├── cli/             — nockcc CLI tool
├── config/          — Django settings (base, dev, prod)
│   └── settings/
├── context/         — CLAUDE.md inventory, skill catalog, GitHub sync
├── core/            — Shared utilities
├── crm/             — Deal pipeline, contact directory
├── dashboard/       — Nerve Center homepage
├── intelligence/    — AI executive dashboard, smart watch, weekly memos
├── notifications/   — Slack/Discord/Telegram delivery layer
├── pipeline/        — GitHub webhook receiver, PR tracking
├── projects/        — Projects, sections, tasks REST API
├── remote/          — WebSocket remote control, push notifications
├── sessions/        — Claude Code session tracking
├── spend/           — Anthropic API usage and cost dashboards
├── tasks/           — Task management
├── teams/           — Multi-agent orchestration, prompt queue
├── tenancy/         — Multi-tenant isolation (product-fork addition)
├── vault/           — Document storage
├── workspaces/      — Workspace management
└── manage.py
```

---

## Dev Setup

```bash
git clone git@github.com:nocktechnologies/nock-dashboard.git
cd nock-dashboard
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your values
python manage.py migrate
python manage.py runserver
```

---

## Development

```bash
pytest -q              # Run tests
ruff check . --fix     # Lint
python manage.py runserver 8001

# Celery (separate terminal)
celery -A config worker -l info
celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

---

## Relationship to NockCC

Nock Dashboard is a downstream fork of `kkwills13/nock-command-center`. The fork diverged on 2026-04-11 and does not sync upstream. Architectural changes in NockCC may be cherry-picked into Nock Dashboard when relevant, but the product fork evolves independently toward a multi-tenant SaaS model.

Changes that belong in NockCC (agent harness fixes, internal tooling) should be made in `nock-command-center`, not here. Changes that belong in Nock Dashboard (billing, tenancy, product features) stay here.

---

## Deployment

Nock Dashboard deploys automatically from `main` on Railway (`striking-serenity` project). A 3–5 minute HTTP 502 window is normal after every merge while Railway cycles the deployment.
