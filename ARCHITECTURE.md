# NockCC Architecture

> Unified dashboard for multi-agent AI development workflows at Nock Technologies.
>
> See also: `.claude/diagrams/` for Mermaid versions of model relationships, API maps, data flow, and Celery task graphs.

## System Overview

NockCC is a Django-based command center that tracks Claude Code sessions, GitHub PR pipelines, Anthropic API spend, CLAUDE.md documentation inventory, and Asana tasks. It provides a real-time web dashboard with WebSocket-powered remote control of Claude Code agents running on developer machines.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        NockCC Dashboard                             │
│  (Django + Alpine.js + Tailwind CSS + Chart.js)                     │
│                                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ Pipeline │ │ Sessions │ │  Spend   │ │ Context  │ │  Tasks   │ │
│  │  (PRs)   │ │ (Agents) │ │  (API $) │ │(CLAUDE.md│ │ (Asana)  │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │              Remote Control + Chat Interface                    ││
│  │  (Commands → WebSocket → Agent Daemon → Claude Code)           ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
         │            │              │              │
    GitHub API   Anthropic API   Asana API    WebSocket (Channels)
         │            │              │              │
    Webhooks     Usage Polling   Task Sync     Agent Daemon
                                               (Mac desktop)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Django 5.0.4 |
| Python | 3.12+ |
| Database | PostgreSQL (prod), SQLite (dev fallback) |
| Async / WebSockets | Django Channels 4.1 + Daphne 4.1 |
| Task queue | Celery 5.3 + Redis |
| Task scheduler | django-celery-beat (DatabaseScheduler) |
| Frontend reactivity | Alpine.js 3.14 (CDN) |
| Styling | Tailwind CSS (CDN) |
| Charts | Chart.js 4.4 (CDN) |
| Static files | WhiteNoise 6.6 (compressed manifest in prod) |
| Auth hardening | django-axes 7.0 (brute-force), django-ratelimit 4.1 |
| Field encryption | django-fernet-fields-v2 0.9 |
| HTTP client | requests + httpx |
| Push notifications | pywebpush 2.3 (VAPID) |
| CLI | Click 8.3 + Rich 14.3 |
| Linting | Ruff (py312, 100-char line length) |
| Testing | pytest + pytest-django |

## Django App Structure

```
nock-command-center/
├── config/              # Project configuration
│   ├── settings/
│   │   ├── base.py      # Shared settings, celery beat schedule
│   │   ├── dev.py       # DEBUG=True, in-memory channels, sync celery
│   │   └── prod.py      # HTTPS, HSTS, secure cookies, Redis channels
│   ├── urls.py          # Root URL router
│   ├── asgi.py          # Daphne entry (HTTP + WebSocket routing)
│   ├── wsgi.py          # WSGI entry (unused in prod — Daphne serves all)
│   └── celery.py        # Celery app init + autodiscovery
│
├── core/                # Shared utilities, base models, management commands
├── accounts/            # Login/logout, brute-force protection
├── dashboard/           # Main overview, aggregated stats, health check
├── pipeline/            # GitHub webhooks, PR tracking, CI status
├── sessions/            # Claude Code session tracking (app_label: agent_sessions)
├── remote/              # Agent remote control, WebSocket, chat, push
├── context/             # CLAUDE.md inventory + GitHub sync
├── spend/               # Anthropic API usage + budget alerts
├── tasks/               # Asana project/task sync + PR linking
├── projects/            # Standalone reusable project-management REST API
├── notifications/       # Slack/Discord alert channels + rules
├── brain/               # Long-term memory, continuity layer, morning notes
├── intelligence/        # AI advisor, executive dashboard, predictive alerts,
│                        #   smart watch, weekly memos, business snapshots
├── crm/                 # Deal pipeline, contacts, sales tracking
├── vault/               # Document storage, session reports, file management
├── teams/               # Agent teams, multi-agent orchestration, prompt queue
│
├── agent/               # Mac-side daemon (separate pip package)
│   └── nockcc_agent/
│       ├── daemon.py    # WebSocket client + reconnection
│       ├── executor.py  # Claude Code subprocess management
│       ├── config.py    # ~/.nockcc/agent.json loader
│       ├── security.py  # HMAC validation + command allowlist
│       └── output.py    # Message formatting helpers
│
├── cli/                 # CLI client (separate pip package)
│   ├── nockcc.py        # Click commands
│   └── client.py        # HTTP wrapper for REST API
│
├── desktop/             # Electron macOS app (native wrapper)
│   ├── main.js          # Window, menu, tray, IPC, global shortcuts
│   ├── preload.js       # IPC bridge (notifications, retry)
│   ├── renderer/        # Loading + offline screens
│   ├── assets/          # App icon (.icns), tray icon
│   └── scripts/         # Build scripts (build-mac.sh, generate-icons.js)
│
├── terminal-electron/   # Standalone Electron + React terminal shell
│   ├── electron/        # Main process, IPC bridge, local file/pty services
│   ├── src/             # React renderer (tabs, AI chat, editor, sidebar)
│   ├── test/            # Node regression tests for Electron-side guards
│   └── dist/            # Built desktop artifacts (.zip/.dmg)
│
├── templates/           # Global templates (base.html, error pages)
└── static/              # PWA manifest, service worker
```

The `terminal-electron/` app is intentionally sandboxed at the main-process boundary: renderer requests are validated before settings writes or filesystem access occur, allowed roots are scoped to configured dev directories plus discovered project roots, and realpath checks prevent sibling-prefix and symlink escapes.

## Models and Relationships

### Pipeline

```
Repository (owner, name, github_id, webhook_secret)
    │
    ├──< PullRequest (number, title, branch, author, state, ci_status,
    │        coderabbit_status, test_count_passed/failed/skipped)
    │        │
    │        └──< PREvent (event_type, actor, delivery_id [unique])
    │
    └──< Branch (name, last_commit_sha, message)
             │
             └──< BranchEvent (delivery_id [unique], ref, deleted)
```

### Sessions

```
AgentSession (agent, machine, status, branch, task_description,
              tokens_input/output, estimated_cost, commits_generated)
    │
    ├── repository → Pipeline.Repository (FK)
    ├── pr_generated → Pipeline.PullRequest (FK)
    │
    └──< SessionLog (level, message, timestamp)
```

### Remote

```
AgentToken (name, token_hash [SHA-256], is_active, last_used_at)
    │
    └── AgentStatus (is_online, last_heartbeat, machine_name,
            ip_address, channel_name, active_sessions)

ConversationThread (repo, title, session_id, is_active, created_by → User)
    │
    └──< CommandRequest (command_type, payload, status, result,
             session_id, hmac_signature, sent_at, completed_at)

SessionOutputBuffer (session_id, line_number, stream, content)
    [unique on (session_id, line_number)]

CommandAuditLog (action, source_ip, payload_hash, duration_ms, details)

PushSubscription (user → User, endpoint, p256dh, auth)
    [unique on (user, endpoint)]
```

### Context

```
ContextDocument (repository, doc_type, file_path, title,
                 content_hash, last_synced, is_stale)
    │
    └──< ContextSnapshot (content_hash, commit_sha, line_count,
             diff_summary, captured_at)
```

### Spend

```
UsagePeriod (date, model, workspace, input_tokens, output_tokens,
             cache_read_tokens, cache_write_tokens, cost_usd, request_count)

SpendBudget (month, budget_usd, alert_threshold_pct, alert_sent)

SubscriptionTracker (name, provider, monthly_cost, renewal_date)
```

### Tasks

```
AsanaProject (asana_gid, name, color, is_active, last_synced)
    │
    └──< AsanaTask (asana_gid, name, section_name, assignee_name,
             due_on, completed, priority, notes_preview, permalink_url)
             │
             └── linked_pr → Pipeline.PullRequest (FK, nullable)
```

### Projects

```
Project (name, slug, description, color, is_active, is_archived, asana_gid)
    │
    ├──< Section (name, order, asana_gid)
    │
    └──< Task (name, priority, status, due_date, assignee, completed,
               completed_at, order, tags, asana_gid)
             │
             └──< TaskComment (text, author, created_at)
```

### Notifications

```
NotificationChannel (name, channel_type [slack/discord/webhook],
                     webhook_url, is_active)
    │
    └──< NotificationRule (trigger_event, is_active)
             │
             └──< NotificationLog (event_type, payload, success, error_message)
```

### Brain

```
MemoryEntry (key, value, category [identity/relationship/domain/decision/
             project/personal/lesson/tool/continuity],
             confidence [observed/inferred/stale], source, tags [JSON])
    [unique on (key, category)]

ConsolidationLog (started_at, completed_at, entries_reviewed,
                  entries_promoted, entries_archived, entries_pruned,
                  contradictions_resolved, notes)
```

### Intelligence

```
BusinessSnapshot (date [unique], content, token_count, generated_at)

AdvisorConversation (owner → User, title, created_at, updated_at)
    │
    └──< AdvisorMessage (role [user/assistant], content, tokens_used,
             cost [Decimal], created_at)

PredictiveAlert (category [spend/pipeline/tasks/context/subscriptions/
                 velocity/revenue], severity [info/warning/critical],
                 title, message, is_resolved, resolved_at)
    [unique on (category, title) where is_resolved=False]

WeeklyMemo (week_start, week_end, content, tokens_used, cost [Decimal],
            vault_document → Vault.Document [FK, nullable])
    [unique on (week_start, week_end)]

SmartWatchRule (name [unique], condition_type [pr_waiting/session_long/
               task_due_tomorrow/context_high/brain_stale/no_activity/custom],
               threshold_minutes, threshold_value, severity, message_template,
               enabled, send_telegram, send_slack, cooldown_minutes,
               last_triggered, trigger_count)
    │
    └──< SmartWatchEvent (message, severity, context [JSON], notified,
             created_at)
```

### CRM

```
Contact (name, company, email, phone, role, notes)
    │
    └──< Deal (title, stage [prospect/contacted/proposal/negotiation/
             active/closed_won/closed_lost], source [consulting/academy/
             licensing/referral/inbound/other], estimated_value [Decimal],
             actual_value [Decimal], next_action, next_action_date, closed_at)
             │
             └──< DealNote (content, created_at)
```

### Vault

```
Document (title, category [formation/legal/financial/insurance/tax/
          trademark/reports/other], file, filename, file_size, file_type,
          description, tags)

SessionReport (project_name, title, content, branch, captured_at,
              received_at, machine)
```

### Teams

```
AgentTeam (name, mission, status [planning/active/paused/completed])
    │
    ├──< TeamMember (agent_name, agent_token → Remote.AgentToken [FK],
    │        role [lead/worker/reviewer], is_online, last_heartbeat,
    │        current_task → TeamTask [FK])
    │        [unique on (team, agent_name)]
    │
    ├──< TeamTask (title, description, status [pending/assigned/in_progress/
    │        blocked/in_review/completed], priority [1-4], assigned_to →
    │        TeamMember, repo, branch, pr_number, pr_url,
    │        depends_on → self [M2M])
    │
    └──< TeamEvent (event_type [task_assigned/started/completed/blocked/
             unblocked/pr_opened/pr_merged/review_completed/agent_joined/
             agent_left/mission_started/mission_completed],
             description, task → TeamTask, member → TeamMember)

PromptFile (title, slug [unique], content, target_repo,
            target_branch_prefix, complexity [quick/standard/deep],
            estimated_minutes, status [draft/ready/queued/in_progress/
            completed/archived], priority [1-100], team_task → TeamTask,
            depends_on_prompts → self [M2M], tags [JSON], author, version,
            executed_by, executed_at, pr_number, pr_url)
    │
    └──< PromptExecution (agent_name, started_at, completed_at,
             result [success/review_requested/failed/abandoned],
             pr_number, pr_url, review_cycles, max_review_cycles, notes)
```

## API Endpoints

All JSON APIs follow the envelope: `{"success": bool, "message": str, "data": ...}`

### Dashboard

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | Session | Main dashboard page |
| GET | `/api/pipeline/status/` | Session | Live PR counts |
| GET | `/api/dashboard/sessions/` | Session | Active session count |
| GET | `/api/dashboard/summary/` | API key | Aggregated stats (CLI) |
| GET | `/healthz/` | None | Health check (Railway) |

### Pipeline

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/webhooks/github/` | HMAC-SHA256 | GitHub webhook receiver |
| GET | `/pipeline/` | Session | PR list page (filterable) |
| GET | `/pipeline/<owner>/<name>/<number>/` | Session | PR detail + event timeline |
| GET | `/api/pipeline/prs/` | API key | PR list (CLI) |

### Sessions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/sessions/` | Session | Session list page |
| GET/POST | `/api/sessions/` | API key / Session | List / create sessions |
| GET/PATCH | `/api/sessions/<id>/` | API key / Session | Fetch / update session |
| POST | `/api/sessions/<id>/end/` | API key / Session | End session |
| POST | `/api/sessions/<id>/log/` | API key / Session | Add log entry |
| GET | `/api/sessions/active/` | API key / Session | Active sessions only |

### Remote (Commands)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/remote/` | Session | Control page |
| GET | `/remote/session/<session_id>/` | Session | Session output viewer |
| GET | `/remote/chat/` | Session | Chat interface |
| GET | `/remote/notifications/` | Session | Push notification prefs |
| GET/POST | `/api/remote/commands/` | Session | List / queue command |
| GET | `/api/remote/commands/<id>/` | Session | Command detail |
| DELETE | `/api/remote/commands/<id>/cancel/` | Session | Cancel queued command |
| GET | `/api/remote/agent/status/` | Session | Agent online/offline |
| GET | `/api/remote/output/<session_id>/` | Session | Session output lines |
| GET | `/api/remote/stream/<session_id>/` | Session | SSE output stream |
| POST | `/api/remote/kill-all/` | Session | Emergency kill all |
| GET/POST | `/api/remote/conversations/` | Session | List / create conversation |
| GET | `/api/remote/conversations/<id>/` | Session | Conversation + commands |
| POST | `/api/remote/conversations/<id>/send/` | Session | Send follow-up prompt |
| POST | `/api/remote/push/subscribe/` | Session | Web Push subscribe |
| POST | `/api/remote/push/unsubscribe/` | Session | Web Push unsubscribe |

### Context

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/context/` | Session | Document inventory |
| GET | `/context/<id>/` | Session | Document detail + snapshots |
| GET | `/context/api/health/` | Session | Health widget data |

### Spend

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/spend/` | Session | Spend dashboard + charts |
| GET | `/spend/api/summary/` | Session | Current month summary |
| GET | `/spend/api/daily/` | Session | Daily chart data |

### Tasks

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/tasks/` | Session | Task feed (priority sort) |
| GET | `/handoffs/` | Session | Latest handoff per project |

### Notifications

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/notifications/` | Session | Event log + channels |

### Brain

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/brain/` | Session | Brain homepage / nerve center |
| GET/POST | `/api/brain/entries/` | Session | List / create memory entries |
| GET/PUT/DELETE | `/api/brain/entries/<id>/` | Session | Entry detail operations |
| GET | `/api/brain/categories/` | Session | Category list with counts |
| POST | `/api/brain/brief/` | Session | Generate context brief by scope |

### Intelligence

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/intelligence/executive/` | Session | Executive dashboard (4-quadrant) |
| GET | `/intelligence/advisor/` | Session | AI Business Advisor chat |
| GET | `/intelligence/alerts/` | Session | Predictive alerts dashboard |
| GET | `/api/dashboard/executive/` | Session | Executive data JSON |
| POST | `/api/intelligence/advisor/chat/` | Session | Send message to AI advisor |
| GET | `/api/intelligence/advisor/conversations/` | Session | List user conversations |
| GET | `/api/intelligence/advisor/conversations/<id>/` | Session | Conversation detail + messages |
| GET | `/api/intelligence/snapshot/latest/` | Session | Latest business snapshot |
| POST | `/api/intelligence/snapshot/generate/` | Staff | Force regenerate snapshot |
| POST | `/api/intelligence/memo/generate/` | Staff | Force generate weekly memo |
| GET | `/api/intelligence/alerts/` | Session | Active predictive alerts |
| GET | `/api/intelligence/smart-watch/rules/` | Session | List smart watch rules |
| POST | `/api/intelligence/smart-watch/rules/create/` | Session | Create smart watch rule |
| GET/PUT/DELETE | `/api/intelligence/smart-watch/rules/<id>/` | Session | Rule detail / update / delete |
| GET | `/api/intelligence/smart-watch/events/` | Session | Recent smart watch events |
| POST | `/api/intelligence/smart-watch/tick/` | Session | Force smart watch evaluation |
| GET | `/api/intelligence/smart-watch/status/` | Session | Smart watch status |

### CRM

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/crm/` | Session | Pipeline kanban / table view |
| GET/POST | `/crm/deals/add/` | Session | Create deal |
| GET/POST | `/crm/deals/<id>/` | Session | Deal detail + notes |
| GET/POST | `/crm/deals/<id>/edit/` | Session | Edit deal |
| GET | `/crm/contacts/` | Session | Contact list |
| GET/POST | `/crm/contacts/add/` | Session | Create contact |
| GET/POST | `/crm/contacts/<id>/edit/` | Session | Edit contact |

### Vault

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/vault/` | Session | Document list (category + search) |
| GET/POST | `/vault/upload/` | Session | Upload document |
| GET | `/vault/<id>/` | Session | Document detail |
| GET/POST | `/api/vault/session-reports/` | API key | Terminal session report capture |

### Teams

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/teams/teams/` | Session | Teams dashboard page |
| GET | `/teams/prompts/` | Session | Prompt queue page |
| GET/POST | `/api/teams/` | API key | List / create teams |
| GET/PUT/DELETE | `/api/teams/<id>/` | API key | Team detail / update / archive |
| GET/POST | `/api/teams/<id>/members/` | API key | List / add members |
| PUT/DELETE | `/api/teams/<id>/members/<mid>/` | API key | Update / remove member |
| GET/POST | `/api/teams/<id>/tasks/` | API key | List / create tasks |
| GET/PUT | `/api/teams/<id>/tasks/<tid>/` | API key | Task detail / update |
| GET/POST | `/api/prompts/` | API key | List / create prompts |
| GET/PUT | `/api/prompts/<slug>/` | API key | Prompt detail / update |
| POST | `/api/prompts/<slug>/execute/` | API key | Execute prompt via agent |
| GET | `/api/prompts/<slug>/executions/` | API key | Execution history |

### Terminal Bridge

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/terminal/heartbeat/` | API key | Terminal heartbeat upsert |
| GET | `/api/terminal/status/` | Session | Terminal online status |
| GET/POST | `/api/terminal/reports/` | API key / Session | List / create session reports |
| GET | `/api/terminal/reports/<id>/` | Session | Report detail |

## WebSocket Consumer

**Endpoint:** `ws://server/ws/agent/?token=<raw_token>`

**Consumer:** `remote.consumers.AgentConsumer` (JsonWebsocketConsumer)

### Authentication
Token passed via query string. Server hashes with SHA-256 and looks up `AgentToken`. Rejected if token invalid or inactive.

### Channel Group
Each agent joins group `agent_{agent_token.pk}` on connect. REST API pushes commands to this group via `channel_layer.group_send()`.

### Message Types

**Agent → Server:**

| Type | Payload | Handling |
|------|---------|----------|
| `heartbeat` | — | Responds `heartbeat_ack` + server time |
| `identify` | `machine`, `repos` | Updates `AgentStatus.machine_name` |
| `output` | `session_id`, `line`, `content`, `stream` | Upserts `SessionOutputBuffer` |
| `command_result` | `command_id`, `status`, `result`, `session_id?` | Updates `CommandRequest` atomically |
| `process_list` | `processes` | Updates `AgentStatus.active_sessions` |

**Server → Agent:**

| Type | Payload | Source |
|------|---------|--------|
| `command` | `id`, `command_type`, `payload`, `hmac_signature` | REST API via channel layer |
| `heartbeat_ack` | `server_time` | Heartbeat response |

## Celery Tasks

### Schedule (via django-celery-beat)

| Task | Interval | App |
|------|----------|-----|
| `sync_asana_projects` | Every 5 minutes | tasks |
| `sync_context_docs_task` | Every 30 minutes | context |
| `sync_anthropic_usage` | Every 15 minutes | spend |
| `daily_usage_backfill` | Daily at 1:00 AM | spend |
| `check_budget_alerts` | Every hour | spend |
| `generate_business_snapshot` | Daily at 6:00 AM CST | intelligence |
| `generate_weekly_memo` | Sunday midnight UTC | intelligence |
| `check_predictive_alerts` | Every 6 hours | intelligence |
| `smart_watch_tick` | Every 15 minutes | intelligence |
| `daily_maintenance` | Daily (consolidation + morning note) | brain |

### Event-Driven Tasks

| Task | Trigger | App |
|------|---------|-----|
| `process_pull_request_event` | GitHub webhook (PR events) | pipeline |
| `process_pull_request_review` | GitHub webhook (review events) | pipeline |
| `process_check_run` | GitHub webhook (CI status) | pipeline |
| `process_push` | GitHub webhook (push events) | pipeline |
| `link_tasks_to_prs` | Called after Asana sync | tasks |

All pipeline tasks use `delivery_id` for idempotency (DB unique constraint).

### Signal-Driven (Teams)

| Signal | Trigger | Behavior |
|--------|---------|----------|
| `on_pr_opened` | Pipeline PR webhook | Links PR to TeamTask, moves to in_review, notifies Telegram |
| `on_pr_merged` | Pipeline PR webhook | Marks TeamTask completed, unblocks dependents, checks mission |
| `on_review_alert` | Pipeline review webhook | Creates TeamEvent for review status changes |

## Agent Daemon Architecture

The agent daemon runs on developer Macs and maintains a persistent WebSocket connection to the server.

```
┌─────────────────────────────────────────────────────────┐
│  Developer Mac                                          │
│                                                         │
│  ┌─────────────────────┐                                │
│  │   AgentDaemon       │                                │
│  │                     │   WebSocket (wss://)           │
│  │  ┌───────────────┐  │ ◄──────────────────────────►   │  NockCC Server
│  │  │  Heartbeat    │  │   (15s interval)               │
│  │  │  Loop         │  │                                │
│  │  └───────────────┘  │                                │
│  │                     │                                │
│  │  ┌───────────────┐  │                                │
│  │  │  Executor     │  │                                │
│  │  │               │  │                                │
│  │  │  ┌─────────┐  │  │   Output lines streamed back  │
│  │  │  │ Claude  │  │  │ ─────────────────────────────► │  SessionOutputBuffer
│  │  │  │ Code    │  │  │                                │
│  │  │  │(subproc)│  │  │                                │
│  │  │  └─────────┘  │  │                                │
│  │  │  ┌─────────┐  │  │                                │
│  │  │  │ Claude  │  │  │                                │
│  │  │  │ Code    │  │  │                                │
│  │  │  │(subproc)│  │  │                                │
│  │  │  └─────────┘  │  │                                │
│  │  └───────────────┘  │                                │
│  └─────────────────────┘                                │
│                                                         │
│  Config: ~/.nockcc/agent.json                           │
│  (server_url, agent_token, hmac_key, repos allowlist)   │
└─────────────────────────────────────────────────────────┘
```

### Command Lifecycle

```
Dashboard (browser)
    │
    │  POST /api/remote/commands/
    │  {command_type: "start_session", payload: {repo, prompt}}
    ▼
Server (Django view)
    │
    │  1. HMAC-sign payload
    │  2. Create CommandRequest (status: queued)
    │  3. channel_layer.group_send("agent_{token_id}", command)
    ▼
WebSocket Consumer
    │
    │  Forward command JSON to agent
    ▼
Agent Daemon
    │
    │  1. Verify HMAC signature
    │  2. Validate command type + repo allowlist
    │  3. Dispatch to Executor
    ▼
Executor
    │
    │  asyncio.create_subprocess_exec("claude", "-p", ...)
    │  (no shell invocation — safe from injection)
    │
    │  Streams stdout (JSON) + stderr (raw) back
    ▼
Agent Daemon
    │
    │  WebSocket: {type: "output", session_id, line, content, stream}
    │  WebSocket: {type: "command_result", command_id, status, result}
    ▼
Server Consumer
    │
    │  1. Upsert SessionOutputBuffer
    │  2. Update CommandRequest (status: completed/failed)
    ▼
Dashboard (browser)
    │
    │  GET /api/remote/output/{session_id}/  (polling)
    │  GET /api/remote/stream/{session_id}/  (SSE)
    ▼
    Rendered in terminal-style chat interface
```

### Command Types

| Type | Payload | Behavior |
|------|---------|----------|
| `start_session` | `{repo, prompt}` | Spawn `claude -p --output-format stream-json` in repo dir |
| `stop_session` | `{session_id}` | SIGTERM, wait 5s, then SIGKILL if needed |
| `send_prompt` | `{session_id, prompt}` | Spawn new process with `--continue` flag (same session_id) |
| `list_processes` | — | Return active subprocesses |
| `kill_all` | — | Terminate all tracked processes |

### Security Measures

- **Token hashing:** Raw tokens stored only on the agent; server stores SHA-256 hash
- **HMAC signing:** All command payloads signed with shared secret; agent verifies before running
- **Repo allowlist:** Agent config explicitly lists allowed repos and their paths
- **No shell invocation:** `create_subprocess_exec()` prevents command injection
- **No root:** Daemon refuses to start as UID 0
- **Timing-safe comparison:** `hmac.compare_digest()` for all secret comparisons
- **Graceful shutdown:** SIGTERM/SIGINT kill all subprocesses

## Deployment Topology (Railway)

```
Railway Project
│
├── Web Service (Uvicorn)
│   ├── Runs migrations on deploy
│   ├── collectstatic + WhiteNoise
│   ├── Serves HTTP + WebSocket on single port
│   ├── Hosts the MCP Streamable HTTP transport at /mcp (see below)
│   ├── Restart on failure (max 5 retries)
│   └── Domain: cc.nocktechnologies.io (custom)
│
│   Note: originally Daphne, switched to Uvicorn 0.44 after discovering
│   Daphne 4.1.2 ships without ASGI lifespan support. The MCP
│   StreamableHTTPSessionManager needs lifespan to start its anyio task
│   group, so Daphne wasn't an option. Channels websockets work
│   unchanged under Uvicorn.
│
├── Worker Service (Celery)
│   ├── Concurrency: 2
│   └── Processes webhook events, syncs, backfills
│
├── Beat Service (Celery Beat)
│   ├── DatabaseScheduler
│   └── Triggers periodic tasks on schedule
│
├── PostgreSQL (Railway managed)
│   └── DATABASE_URL injected
│
└── Redis (Railway managed)
    └── REDIS_URL injected (shared by Channels + Celery)
```

**Procfile:**
```
web:    migrate + collectstatic + setup_production + uvicorn (0.0.0.0:$PORT, --lifespan on)
worker: celery -A config worker -l info --concurrency=2
beat:   celery -A config beat -l info --scheduler DatabaseScheduler
```

## MCP Remote Transport (`/mcp`)

Mara and every other claude.ai instance reach NockCC via an MCP server that
ships in two transports sharing one tool registry:

```
┌──────────────────────────────────────────────────────────────────────┐
│                    mcp_server/registry.py                            │
│        ALL_TOOLS (42) · TOOL_MODULES · dispatch_tool_call()          │
│           diary · memory · pipeline · sessions · spend ·             │
│           tasks · CRM · teams · prompts · alerts ·                   │
│                    research · handoffs                               │
└──────────────────────────────────────────────────────────────────────┘
            ▲                                     ▲
            │                                     │
            │ imports                             │ imports
            │                                     │
┌───────────┴────────────┐       ┌────────────────┴──────────────────┐
│ mcp_server/server.py   │       │ mcp_server/http_app.py            │
│ (stdio entry point)    │       │ (Starlette sub-app)               │
│                        │       │                                   │
│ Run by Claude Code as  │       │ Mounted at /mcp inside the        │
│ a subprocess via       │       │ Django ASGI application in        │
│ `claude mcp add nockcc`│       │ config/asgi.py, exposed to the    │
│                        │       │ public internet via Uvicorn       │
│ stdin/stdout JSON-RPC  │       │                                   │
│                        │       │ Protected by BearerAuthMiddleware │
│ Auth: subprocess env   │       │ (Authorization: Bearer <key> OR   │
│   inherits NOCKCC_*    │       │  X-API-Key: <key>)                │
│                        │       │                                   │
└────────────────────────┘       │ /health is the only unauthed      │
                                 │ route (Railway liveness probe)    │
                                 └───────────────────────────────────┘
                                              ▲
                                              │
                              ┌───────────────┴──────────────┐
                              │ core/oauth/ (OAuth 2.1 shim) │
                              │                              │
                              │ /.well-known/oauth-protected-resource/mcp    (RFC 9728)
                              │ /.well-known/oauth-authorization-server      (RFC 8414)
                              │ /oauth/register                              (RFC 7591, auto-accept)
                              │ /oauth/authorize                             (RFC 6749 + 7636, auto-approve)
                              │ /oauth/token                                 (RFC 6749, PKCE S256, returns
                              │                                               NOCKCC_API_KEY as access token)
                              │                                              │
                              │ Gated on NOCKCC_OAUTH_ENABLED=1              │
                              │ Rate-limited via django-ratelimit (20/min/IP)│
                              │ Storage: direct redis-py, 60s TTL on codes,  │
                              │   30d TTL on registered clients              │
                              └──────────────────────────────────────────────┘
                                              ▲
                                              │
                                         claude.ai
                                         custom connector
```

**Lifespan wiring** (`config/asgi.py`): Starlette's `Mount` silently drops
lifespan events for sub-apps, and Channels' `ProtocolTypeRouter` doesn't
implicitly handle the lifespan scope. So the outer HTTP router has an
explicit `lifespan` callback that wraps `StreamableHTTPSessionManager.run()`,
and `ProtocolTypeRouter` has an explicit `"lifespan": http_router` entry to
forward Uvicorn's lifespan events to it.

**Trailing slash redirect**: `Mount("/mcp", ...)` matches `/mcp/` and
`/mcp/foo` but not the bare `/mcp`. A dedicated `Route("/mcp")` 308s to
`/mcp/` so claude.ai's bare-path probe during discovery doesn't 404.

**Security model**: the OAuth shim is deliberately single-user. Any client
that completes the dance gets `NOCKCC_API_KEY` as its access token because
`BearerAuthMiddleware` validates against that exact value. This keeps the
transport code unchanged and is the right tradeoff for a personal NockCC
instance — do **not** copy the pattern into a multi-tenant service.

Full walkthrough: `mcp_server/README.md`. Lessons from the deployment
hunt: `.claude/lessons/asgi-deployment.md`.

## Authentication Flows

### Browser (Session Auth)

```
User  →  GET /accounts/login/  →  Login form
      →  POST /accounts/login/ →  django-axes checks (5 fail = 15 min lockout)
                                →  AuthenticationForm.is_valid()
                                →  auth.login() → redirect to /
      →  @login_required on all dashboard views
      →  POST /accounts/logout/ → redirect to /accounts/login/
```

### CLI / API (Key Auth)

```
CLI  →  X-API-Key: <NOCKCC_API_KEY> header
     →  @require_api_key decorator
     →  secrets.compare_digest() validation
     →  Access to /api/sessions/* endpoints
```

### Agent Daemon (Token Auth)

```
Agent  →  wss://server/ws/agent/?token=<raw_token>
       →  AgentConsumer.connect()
       →  SHA-256(token) lookup in AgentToken table
       →  Accept if valid + active; reject otherwise
       →  Joins channel group for command dispatch
```

### GitHub Webhooks (HMAC Auth)

```
GitHub  →  POST /webhooks/github/
        →  X-Hub-Signature-256 header
        →  HMAC-SHA256 verification against GITHUB_WEBHOOK_SECRET
        →  Dispatch to Celery task by event type
```

## Data Flow: PR Lifecycle

```
GitHub push event
    │
    ▼
POST /webhooks/github/  (HMAC verified)
    │
    ├── X-GitHub-Event: push
    │   └── process_push.delay() → Create/update Branch + BranchEvent
    │
    ├── X-GitHub-Event: pull_request
    │   └── process_pull_request_event.delay()
    │       └── Create/update PullRequest + PREvent
    │           └── On merge: trigger_event("pr_merged") → Slack/Discord
    │
    ├── X-GitHub-Event: pull_request_review
    │   └── process_pull_request_review.delay()
    │       └── Update PullRequest.coderabbit_status
    │
    └── X-GitHub-Event: check_run
        └── process_check_run.delay()
            └── Update PullRequest.ci_status + test counts
                └── On failure: trigger_event("ci_failed") → Slack/Discord
```

## Data Flow: Remote Session

```
User opens /remote/chat/
    │
    │  POST /api/remote/conversations/
    │  {repo: "nock-command-center", title: "Fix auth bug", prompt: "..."}
    ▼
Server creates ConversationThread + CommandRequest
    │
    │  Signs payload, pushes via channel layer
    ▼
Agent daemon receives command
    │
    │  Validates HMAC + repo allowlist
    │  Spawns: claude -p --output-format stream-json --verbose "..."
    ▼
Claude Code runs in repo directory
    │
    │  Executor parses stream-json output
    │  Extracts text blocks, tool summaries, costs
    ▼
Output streamed back via WebSocket
    │
    │  {type: "output", session_id, line: 1, content: "Reading file...", stream: "stdout"}
    ▼
Consumer upserts SessionOutputBuffer
    │
    ▼
Dashboard polls /api/remote/output/{session_id}/
  or streams via /api/remote/stream/{session_id}/ (SSE)
    │
    ▼
Rendered in terminal-style chat interface
    │
    │  User sends follow-up: POST /api/remote/conversations/{id}/send/
    │  {prompt: "now add tests"}
    ▼
New CommandRequest (send_prompt) → agent spawns claude --continue
```

## Data Flow: Spend Tracking

```
Every 15 min: sync_anthropic_usage
    │
    │  GET Anthropic usage API (ANTHROPIC_ADMIN_API_KEY)
    ▼
Parse response → UsagePeriod records (date, model, tokens, cost)
    ▼
Every hour: check_budget_alerts
    │
    │  Sum current month cost vs SpendBudget.budget_usd
    │  If cost > threshold: trigger_event("budget_alert") → Slack/Discord
    ▼
Daily at 1 AM: daily_usage_backfill
    │  Re-fetch yesterday's complete data (ensures no gaps)
```

## Management Commands

| Command | App | Purpose |
|---------|-----|---------|
| `create_prod_superuser` | accounts | Idempotent superuser from env vars |
| `setup_production` | accounts | Master setup (runs all seed commands) |
| `register_repos` | pipeline | Register GitHub repositories |
| `backfill_prs` | pipeline | Backfill PR history (default: 30 days) |
| `cleanup_duplicate_repos` | pipeline | Remove duplicate repo records |
| `seed_pipeline_data` | pipeline | Seed test data |
| `sync_context` | context | Sync CLAUDE.md docs from GitHub |
| `register_context_docs` | context | Register context file paths |
| `sync_spend` | spend | Sync Anthropic usage |
| `set_budget` | spend | Set monthly budget |
| `seed_subscriptions` | spend | Seed subscription records |
| `seed_asana_projects` | tasks | Seed Asana project mappings |
| `sync_asana` | tasks | Sync tasks from Asana API |
| `seed_notifications` | notifications | Seed notification rules |
| `seed_sessions` | sessions | Seed test session data |
| `create_agent_token` | remote | Generate agent auth token |
| `rotate_agent_token` | remote | Rotate existing token |
| `seed_vault` | vault | Seed placeholder document records |
| `seed_smart_watch` | intelligence | Seed default smart watch rules |
| `clear_seed_data` | core | Delete all seeded test data |

## Configuration

### Environment Variables

**Required:**
- `SECRET_KEY` — Django secret key
- `FERNET_KEYS` — Encryption keys (comma-separated)

**Database and Cache:**
- `DATABASE_URL` — PostgreSQL (optional in dev, falls back to SQLite)
- `REDIS_URL` — Redis for Channels + Celery

**External APIs:**
- `GITHUB_WEBHOOK_SECRET` — Webhook HMAC verification
- `GITHUB_PAT` — GitHub personal access token
- `ANTHROPIC_ADMIN_API_KEY` — Anthropic usage API
- `ANTHROPIC_API_KEY` — AI intelligence features (advisor, memos, digest)
- `ASANA_PAT` — Asana personal access token

**Notifications:**
- `SLACK_WEBHOOK_URL` — Slack incoming webhook
- `DISCORD_WEBHOOK_URL` — Discord webhook

**Remote Agent:**
- `NOCKCC_API_KEY` — Session tracking API key
- `AGENT_HMAC_KEY` — Command payload signing
- `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` — Web Push keys

**Security:**
- `CSRF_TRUSTED_ORIGINS` — Comma-separated trusted origins
- `ALLOWED_HOSTS` — Comma-separated allowed hosts

### Settings Split

| File | Purpose |
|------|---------|
| `config/settings/base.py` | Shared: apps, middleware, celery beat schedule, auth backends |
| `config/settings/dev.py` | `DEBUG=True`, `ALLOWED_HOSTS=["*"]`, in-memory channels, sync celery, console email |
| `config/settings/prod.py` | `DEBUG=False`, SSL redirect, HSTS, secure cookies, Redis channels, WARNING logging |

### Middleware Stack (order matters)

1. `SecurityMiddleware` — HTTPS headers
2. `WhiteNoiseMiddleware` — Static file serving + compression
3. `SessionMiddleware` — Session management
4. `CommonMiddleware` — URL normalization
5. `CsrfViewMiddleware` — CSRF protection
6. `AuthenticationMiddleware` — User auth
7. `MessageMiddleware` — Flash messages
8. `XFrameOptionsMiddleware` — Clickjacking protection
9. `AxesMiddleware` — Brute-force login protection
