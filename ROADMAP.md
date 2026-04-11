# NockCC Roadmap

> Source of truth: [Asana Project — Claude Command Center Development Roadmap](https://app.asana.com/1/1213385942922471/project/1213659188123153)
>
> **Last synced:** 2026-04-03 | **43/52 tasks complete** | **9 remaining**

---

## Completed Phases

### Phase 1 — Pipeline Command (Complete)
- [x] Project scaffold — Django, 8 apps, base templates, CI
- [x] Pipeline models — Repository, PullRequest, PREvent, Branch
- [x] GitHub webhook receiver — HMAC verification, event routing
- [x] PR event processing — 4 Celery tasks, idempotency
- [x] Pipeline dashboard — PR cards, CI badges, merge history

### Phase 2 — Session Radar (Complete)
- [x] Session models — AgentSession, SessionLog + REST API
- [x] CLI tool — `nockcc session start/end/list/status`
- [x] Sessions dashboard — Active sessions, agent cards, history

### Phase 3 — Context Map (Complete)
- [x] Context models — ContextDocument, ContextSnapshot + GitHub sync
- [x] Context dashboard — File inventory, staleness alerts

### Phase 4 — Spend Tracker (Complete)
- [x] Spend models — UsagePeriod, SpendBudget, SubscriptionTracker + API polling
- [x] Spend dashboard — Charts, budget gauge, cost-per-PR, projections
- [x] Expense tracking — Expense model, redesigned dashboard

### Phase 5 — Notifications & Polish (Complete)
- [x] Notification system — Slack/Discord webhooks, alert rules engine
- [x] Polish — Dark/light theme, responsive design, documentation

### MCP Remote Transport + claude.ai Connector (Complete — 2026-04-11)
- [x] MCP server stdio transport — 42 tools across 12 groups (`mcp_server/server.py`)
- [x] Shared tool registry — `mcp_server/registry.py`, imported by both transports
- [x] Streamable HTTP transport at `/mcp` — Starlette sub-app mounted in Django ASGI (`mcp_server/http_app.py`)
- [x] Bearer auth middleware + `/mcp/health` unauthed liveness probe
- [x] Lifespan wiring — outer Starlette router drives `StreamableHTTPSessionManager.run()`
- [x] Daphne → Uvicorn swap — Daphne 4.x lacks ASGI lifespan support
- [x] `/mcp` trailing-slash 308 redirect — claude.ai probes the bare path
- [x] OAuth 2.1 shim (`core/oauth/`) — RFC 9728 + 8414 + 7591 + 7636 (PKCE S256)
- [x] Discovery endpoints — `/.well-known/oauth-protected-resource/mcp` + `/.well-known/oauth-authorization-server`
- [x] Dynamic client registration, auto-approved authorize, single-use codes in Redis
- [x] `WWW-Authenticate: resource_metadata=…` breadcrumb for claude.ai discovery
- [x] Handoff tools — `nockcc_handoff_read/write/list` so claude.ai can read/write session handoffs directly

### Deployment (Complete)
- [x] Deploy NockCC to Railway — production cloud deployment
- [x] Security hardening — auth, production settings, rate limiting
- [x] Custom domain — cc.nocktechnologies.io

### Phase 2 — Remote Mac Agent (Complete)
- [x] WebSocket server — Django Channels consumer for agent connection
- [x] Command queue & REST API — phone → NockCC → Mac pipeline
- [x] Mac agent daemon — WebSocket client, subprocess manager, auto-reconnect
- [x] Agent security — encrypted commands, token rotation, audit log
- [x] Mobile-optimized UI — responsive views, PWA support
- [x] Push notifications — Web Push with VAPID
- [x] Real-time output streaming — WebSocket → SSE → phone
- [x] Session prompt injection — send prompts to running sessions

### Phase 2 — Mobile PWA (Complete)
- [x] Fix Railway worker service

### Phase 4 — React Native App (Complete)
- [x] React Native scaffold — Expo, navigation, auth, dark theme
- [x] Dashboard screen — executive summary cards + charts
- [x] Chat screen — Claude Code conversational interface
- [x] Spend screen — expenses, subscriptions, P&L, tax prep
- [x] CRM screen — pipeline kanban, deal detail, contacts
- [x] Vault screen — document list, upload, preview
- [x] Pipeline & sessions screens — PR tracking, session history

### Phase 5 — AI Intelligence Layer (Mostly Complete)
- [x] Weekly strategy memo — auto-generated business intelligence
- [x] AI business advisor — conversational BI chat
- [x] Predictive alerts — pattern detection + projections
- [x] Executive dashboard — single-page business health overview

---

## In Progress / Upcoming

### Remaining Tasks (9 open)

#### Nock Terminal — GTM Planning & Product Fork
**Due:** 2026-04-05 | **Priority:** High

Productize Nock Terminal as standalone Mac app. Fork claude-terminal, strip NockCC-specific code, keep core value (multi-AI session management). Positioning: "Stop managing terminals. Start managing agents."

Recent progress shipped on 2026-04-11:
- Terminal Electron security boundary hardened: validated settings writes, root-scoped file access, symlink/prefix escape protection
- UX bugs closed: prompt-library execution now opens AI chat correctly, context-file detection works cross-platform, and file-tree copy-content works again
- Toolchain stabilized for release work: Electron/Vite/build dependencies upgraded, dead code removed, audits reduced to 0 known vulnerabilities, and packaged Mac artifacts build successfully

- [ ] Create fork, strip NockCC-specific code
- [ ] Define product feature set
- [ ] Build onboarding flow + generic memory + plugin architecture
- [ ] Branding: app icon, name finalization, landing page
- [ ] Build .app bundle with code signing
- [ ] Launch strategy (open source core? paid? freemium?)

#### Multi-Tenancy Scaffold
**Due:** 2026-05-20

Organization model, row isolation, API key auth. Prepare architecture for multi-user product mode without fully building it out.

#### Push Notifications — Native (Mobile)
**Due:** Overdue (2026-03-25)

Replace web push with Firebase Cloud Messaging for native mobile push. Triggers: command completion, agent offline, deal updates, daily digest, anomaly alerts.

#### Biometric Auth (Mobile)
**Due:** Overdue (2026-03-28)

Fingerprint/face unlock via expo-local-authentication for app unlock and sensitive actions.

#### Anomaly Detection
**Due:** Overdue (2026-03-30)

Detect unusual patterns: spend spikes, subscription price changes, PR velocity anomalies, session patterns, CRM deal stage regression. Compare to rolling averages.

#### Research Library ✅ Shipped 2026-04-10
**Due:** Overdue (2026-03-31)

Index 370K+ lines of Kimi research with pgvector embeddings. Full-text search, topic tagging. Future: Claude answers grounded in research corpus.

**Shipped:** `brain/` ResearchDocument + ResearchChunk with pgvector 1536-d vectors (text-embedding-3-small), ivfflat cosine index, chunking on markdown headers with overlap, `ingest_research` / `embed_research` / `search_research` management commands, and `/api/brain/research/` endpoints (search, documents, topics, stats). Any Mara instance can now semantically query the full vault via API — no local file access required.

#### Content Pipeline
**Due:** Overdue (2026-04-01)

Kanban board for content lifecycle: Idea → Outline → Draft → Review → Published. Track Academy Playbook chapters. Link to Research Library.

---

## Long-Term Vision

- **Mara as CEO** — AI orchestration layer (Paperclip-style) with Kit, Codex, Gemini, Kimi as agents
- **Persistence infrastructure** — Memory server or local workstation for always-on AI
- **Multi-machine agent support** — Coordinate agents across multiple developer Macs
- **NockCC + Terminal as SaaS** — Potential commercial products
- **RAGFlow integration** — Self-hosted RAG for research corpus

---

## Living Documents

- **Session Handoff** — [Asana task 1213659188132165](https://app.asana.com/1/1213385942922471/project/1213659188123153/task/1213659188132165) — Updated every session with current state
- **Mara Mindset** — Personality & working style persistence file
- **Expense Tracking** — NockCC infrastructure costs (Railway ~$25/mo)
