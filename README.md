# NockCC — Claude Command Center

Unified dashboard for multi-agent AI development workflows. A Nock Technologies product.

## Features

- **Pipeline** — GitHub webhook receiver, PR tracking, CI status, CodeRabbit integration
- **Sessions** — Claude Code session tracking, agent status, REST API + CLI tool (`nockcc`)
- **Remote** — Phone-to-Mac agent control, WebSocket, chat interface, push notifications
- **Context** — CLAUDE.md inventory, skill file catalog, GitHub sync with staleness detection
- **Spend** — Anthropic API usage tracking, cost dashboards with Chart.js, budget alerts, subscriptions, expenses
- **Brain** — Long-term memory, continuity layer, daily consolidation, morning notes via Telegram
- **Intelligence** — AI executive dashboard, business advisor chat, predictive alerts, smart watch, weekly memos
- **CRM** — Deal pipeline (prospect → closed), contact directory, sales tracking
- **Vault** — Document storage, session reports from Nock Terminal
- **Teams** — Multi-agent orchestration, prompt queue, task dependencies, PR lifecycle signals
- **Notifications** — Slack/Discord/Telegram push alerts with rules engine, retry logic, delivery logging
- **Dashboard** — Nerve Center homepage with live polling: pipeline, sessions, brain, spend, terminal status
- **Projects** — standalone reusable REST API for projects, sections, tasks, comments, and cross-project views
- **Desktop** — Native macOS Electron app with tray icon, global shortcuts, offline handling
- **Desktop (Windows)** — Native Windows Electron app with system tray, custom title bar, Ctrl+Shift+N toggle
- **Terminal Electron** — Cross-platform Electron + React shell for local terminal tabs, AI chat, prompt library, secure file editing, and packaged Mac distribution
- **MCP Server** — 42 tools across 12 groups (diary, memory, pipeline, sessions, spend, tasks, CRM, teams, prompts, alerts, research, handoffs) exposed via two transports: **stdio** for local Claude Code (`claude mcp add nockcc …`) and **Streamable HTTP at `/mcp`** for claude.ai custom connectors. Full OAuth 2.1 shim (RFC 9728 + 8414 + 7591 + 7636) so every claude.ai Mara instance can read/write diary entries, handoffs, tasks, and research docs natively. Full docs in `mcp_server/README.md`.

## Stack

| Layer | Technology |
|-------|-----------|
| Framework | Django 5.x |
| Database | PostgreSQL (prod), SQLite (dev fallback) |
| Async | Celery + Redis |
| WebSockets | Django Channels + Daphne |
| Frontend | Alpine.js + Tailwind CSS (CDN) |
| Charts | Chart.js (CDN) |
| CLI | Click + Rich + httpx |
| Python | 3.12+ |

## Setup

```bash
git clone git@github.com:kkwills13/nock-command-center.git
cd nock-command-center
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your values (see Environment Variables below)
python manage.py migrate
python manage.py runserver
```

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Django secret key |
| `FERNET_KEYS` | Field encryption key |
| `DATABASE_URL` | PostgreSQL (optional — SQLite fallback in dev) |
| `REDIS_URL` | Redis for Celery/Channels |
| `GITHUB_WEBHOOK_SECRET` | GitHub webhook HMAC verification |
| `GITHUB_PAT` | GitHub Personal Access Token for context sync |
| `ANTHROPIC_ADMIN_API_KEY` | Anthropic Usage API polling |
| `NOCKCC_API_KEY` | Session tracking REST API auth |
| `SLACK_WEBHOOK_URL` | Slack notification channel |
| `DISCORD_WEBHOOK_URL` | Discord notification channel |
| `ASANA_PAT` | Asana project/task sync |

## Development

```bash
# Run tests (494+ tests)
pytest -q

# Lint
ruff check . --fix

# Dev server
python manage.py runserver 8001

# Celery worker (separate terminal, or use CELERY_TASK_ALWAYS_EAGER in dev)
celery -A config worker -l info

# Celery beat (scheduled tasks)
celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

## Management Commands

```bash
# Data seeding
python manage.py register_repos          # Register core repositories
python manage.py register_context_docs   # Register context files
python manage.py seed_subscriptions      # Seed AI subscriptions
python manage.py seed_notifications      # Seed notification channels + rules
python manage.py seed_vault              # Seed placeholder documents
python manage.py seed_smart_watch        # Seed smart watch rules

# Sync
python manage.py sync_context            # Sync context docs from GitHub
python manage.py sync_spend --days 30    # Sync Anthropic usage data
python manage.py sync_asana              # Sync Asana tasks

# Budget
python manage.py set_budget --month 2026-04 --amount 500

# Agent tokens
python manage.py create_agent_token      # Generate new agent token
python manage.py rotate_agent_token      # Rotate existing token

# Production setup (runs all seed commands)
python manage.py setup_production

# Cleanup
python manage.py clear_seed_data --confirm

# CLI tool
cd cli && pip install -e .
nockcc --help

# Desktop app (Mac)
cd desktop && npm install && npm start

# Desktop app (Windows)
cd desktop-win && npm install && npm start

# Terminal Electron app
cd terminal-electron && npm install
npm test
npm run build
```

## App Structure

| App | Purpose |
|-----|---------|
| `config/` | Settings (dev/prod), URLs, ASGI/WSGI, Celery |
| `dashboard/` | Main overview with live polling |
| `pipeline/` | GitHub webhooks, PR tracking, CI status |
| `sessions/` | Claude Code session tracking, REST API |
| `remote/` | Agent remote control, WebSocket, chat, push notifications |
| `context/` | CLAUDE.md inventory, GitHub sync, staleness |
| `spend/` | Anthropic API usage, budgets, subscriptions, expenses |
| `brain/` | Long-term memory, continuity layer, morning notes |
| `intelligence/` | AI executive dashboard, advisor, alerts, smart watch, memos |
| `crm/` | Deal pipeline, contacts, sales tracking |
| `vault/` | Document storage, session reports |
| `teams/` | Agent teams, prompt queue, multi-agent orchestration |
| `projects/` | Standalone project-management REST API plugin (Projects → Sections → Tasks) |
| `notifications/` | Slack/Discord/Telegram alerts, rules engine |
| `tasks/` | Asana project/task sync |
| `agent/` | Mac-side daemon (WebSocket client, subprocess manager) |
| `cli/` | `nockcc` CLI tool (Click + Rich) |
| `desktop/` | Electron macOS app (native wrapper) |
| `terminal-electron/` | Cross-platform Electron shell for local terminal + AI session management |
| `core/` | Shared utilities, management commands |
| `accounts/` | User auth, brute-force protection |

See [projects/README.md](projects/README.md) for install and API details.

## License

Proprietary — Nock Technologies (K Wills Technologies LLC DBA)
