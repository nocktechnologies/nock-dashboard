# NockCC UI Reimagine Phase 2 — Design Spec

**Date:** 2026-04-06
**Author:** Kevin + Claude
**Branch:** `feature/ui-reimagine-phase2`
**Status:** Approved

## Overview

Reskin all remaining NockCC pages to match the Phase 1 design system established in `nockcc.css`. Replace Tailwind utility-class styling with `ncc-*` component classes. No backend changes.

## Scope

### Pages to Redesign (9 total)

| # | Page | Template Path | Complexity |
|---|------|--------------|------------|
| 1 | Spend Dashboard | `spend/templates/spend/dashboard.html` | High (charts + tables) |
| 2 | CRM Pipeline | `crm/templates/crm/pipeline.html` | High (kanban + table dual view) |
| 3 | Tasks | `tasks/templates/tasks/feed.html` | Medium |
| 4 | Vault | `vault/templates/vault/list.html` | Medium (tabs + grid) |
| 5 | Teams | `teams/templates/teams/index.html` | High (complex Alpine.js state) |
| 6 | Remote Chat | `remote/templates/remote/chat.html` | Medium |
| 7 | Notifications | `notifications/templates/notifications/list.html` | Medium |
| 8 | Context | `context/templates/context/list.html` | Low-Medium |
| 9 | Logo Integration | `templates/base.html` + `templates/accounts/login.html` | Low |

### What Stays Untouched

- All backend code (models, views, URLs, APIs, serializers)
- Phase 1 pages: Nerve Center, Pipeline, Brain, Sessions, Intelligence (Alerts, Advisor, Executive), Login layout
- Test files
- All existing Alpine.js functionality (x-data, x-model, @click preserved)

## Design System Reference

All tokens live in `static/css/nockcc.css`. Key references:

- **Backgrounds:** `--bg-base` (#0A0A0F), `--bg-surface` (#111119), `--bg-surface-hover` (#1A1A2E), `--bg-border` (#1E1E2E)
- **Brand:** `--accent-start` (#3B6FD4), `--accent-end` (#7C5CFC)
- **Status:** `--color-success`, `--color-warning`, `--color-danger`, `--color-info`
- **Text:** `--text-primary`, `--text-secondary`, `--text-muted`
- **Typography:** `--font-sans` (DM Sans), `--font-mono` (JetBrains Mono)
- **Components:** `.ncc-card`, `.ncc-table`, `.ncc-badge-*`, `.ncc-btn-primary`, `.ncc-btn-ghost`, `.ncc-input`, `.ncc-select`, `.ncc-progress`, `.ncc-hero-number`, `.ncc-compact-row`

## New CSS Components (extend nockcc.css)

### Tab Bar
```css
.ncc-tabs — flex container with bottom border
.ncc-tab — individual tab with padding, muted text
.ncc-tab.active — accent-colored bottom border, primary text
```

### Kanban Board
```css
.ncc-kanban-board — horizontal flex with gap, overflow-x auto
.ncc-kanban-col — vertical column with header and card stack
.ncc-kanban-card — card within a column (uses .ncc-card base)
```

### Toggle Switch
```css
.ncc-toggle — checkbox-based toggle with accent gradient when active
```

### Staleness Indicators
```css
.ncc-staleness-fresh — green left border (< 7 days)
.ncc-staleness-stale — yellow left border (7-14 days)
.ncc-staleness-critical — red left border (> 14 days)
```

### KPI Row
```css
.ncc-kpi-row — 4-column grid for KPI cards, responsive to 2-col on tablet, 1-col on mobile
```

### Chat Components
```css
.ncc-chat-container — full-height flex column
.ncc-chat-messages — scrollable message area
.ncc-chat-bubble — message bubble (user vs assistant variants)
.ncc-chat-input — bottom input bar with send button
```

## Page Designs

### 1. Spend Dashboard (`/spend/`)

**Top section:** 4 KPI cards in `.ncc-kpi-row`:
- Total Spend to Date — hero number + trend indicator
- Monthly Burn Rate — hero number + month label
- API Spend MTD — hero number from Anthropic data
- Tax Paid to Date — hero number

**Budget section:** Horizontal `.ncc-progress` bar with gradient fill, showing budget amount vs spent, projected month-end text.

**Cost per PR:** Hero number with calculation breakdown in muted text.

**Annual projection:** Hero number with `.ncc-gradient-text`.

**Subscriptions table:** `.ncc-table` with columns: Vendor, Description, Monthly Cost, Next Billing, Notes. Sorted by cost (highest first). Total row at bottom. Rows with billing within 7 days get `--color-warning` highlight.

**Expense Log table:** `.ncc-table` with columns: Date, Vendor, Description, Category, Total, Tax, Payment. Filter row above with `.ncc-select` dropdowns for category, payment method, date range.

**Charts:** Restyle Chart.js with design system colors (accent gradient for primary data, muted borders, dark grid lines).

**Quick action:** "+ Quick Add P&L Tax Prep" as `.ncc-btn-primary`.

### 2. CRM Pipeline (`/crm/`)

**Top bar:** "+ New Deal" (`.ncc-btn-primary`) and "Contacts" (`.ncc-btn-ghost`).

**View toggle:** Kanban / Table switcher using `.ncc-tabs`.

**KPI row:** 4 mini `.ncc-card` items: Open Deals, Pipeline Value, Win Rate, Actions This Week.

**Kanban view (default):** `.ncc-kanban-board` with columns for each stage: Prospect, Contacted, Proposal Sent, Negotiation, Active Engagement, Closed Won, Closed Lost. Each column has header with stage name + count `.ncc-badge`. Deal cards show company name, value, days in stage, assigned contact. Empty columns: dashed border + "No deals" muted text. Alpine.js drag-and-drop preserved.

**Table view:** `.ncc-table` with columns: Company, Stage (badge), Value, Contact, Days Open, Last Activity, Actions.

### 3. Tasks (`/tasks/`)

**Page header:** "Tasks" with project summary cards in horizontal scroll — each card shows project name + completion stats.

**Filter bar:** Project, Priority, Status dropdowns (`.ncc-select`) matching Pipeline filter pattern.

**Overdue counter:** Prominent `.ncc-badge` in danger color showing "X overdue".

**Task table:** `.ncc-table` with columns: Task, Project, Section, Due, Priority, PR, Assignee.
- Priority: colored `.ncc-dot` (red=High, yellow=Medium, gray=Low)
- Due dates: `--color-danger` text if overdue, `--color-warning` if due within 3 days
- PR column: clickable number linking to GitHub
- Row hover: `--bg-surface-hover`

### 4. Vault (`/vault/`)

**Tab interface:** `.ncc-tabs` with "Documents" / "Session Reports".

**Documents tab:**
- Search bar (`.ncc-input`) above grid
- Upload button: "+ Upload Document" (`.ncc-btn-primary`)
- 3-column `.ncc-card` grid (2-col tablet, 1-col mobile)
- Each card: document icon, title, type `.ncc-badge`, created date, file size
- Empty state: icon + "No documents yet" + upload prompt

**Session Reports tab:**
- `.ncc-table`: Project, Machine, Date, Duration, summary preview (truncated)
- Click row to expand and show full report content
- Filter by project (`.ncc-select`)

### 5. Teams (`/teams/`)

Preserve all existing Alpine.js state management (team selector, kanban, modals, agent roster).

**Team cards:** Restyle to `.ncc-card` with team name, mission (truncated), status `.ncc-badge` (Planning/Active/Paused/Completed), member count, task count.

**Agent roster:** Cards with `.ncc-card` styling, online/offline `.ncc-dot` indicators.

**Task kanban:** Use `.ncc-kanban-*` classes for the existing kanban board.

**Activity feed:** `.ncc-compact-row` style entries.

**Modals:** Restyle with `--bg-surface` background, `--bg-border` borders, `.ncc-input`/`.ncc-select` form elements.

**Prompt Queue section:** `.ncc-table` with columns: Prompt name, Target repo, Status badge, Created, Actions. "+ Add Prompt" button.

### 6. Remote Chat (`/remote/chat/`)

Match AI Advisor visual style from Phase 1.

**Layout:** `.ncc-chat-container` full-height flex column.

**Messages area:** `.ncc-chat-messages` with scrollable content. User messages right-aligned with accent background. Assistant messages left-aligned with `--bg-surface` background.

**Input bar:** `.ncc-chat-input` with `.ncc-input` text field + `.ncc-btn-primary` send button.

**Terminal toggle:** Keep existing toggle but restyle with `.ncc-tabs` or `.ncc-btn-ghost` toggle.

Preserve WebSocket/SSE streaming, markdown rendering (marked.js), and all real-time functionality.

### 7. Notifications (`/notifications/`)

**Two sections:** "Notification Rules" and "Channels".

**Rules section:**
- `.ncc-card` list of notification rules
- Each card: rule name, event type `.ncc-badge`, channel indicator, `.ncc-toggle` enabled/disabled
- "+ Add Rule" button (`.ncc-btn-primary`)

**Channels section:**
- `.ncc-card` list: Telegram, Slack, Discord, Email
- Each card: channel icon (Lucide), name, connection `.ncc-dot` (green=connected, red=disconnected), "Configure" `.ncc-btn-ghost`

### 8. Context (`/context/`)

**Page header:** "Context Documents" with last sync time in muted text.

**Stats bar:** `.ncc-kpi-row` with: total documents tracked, healthy count, stale count, last sync time.

**Document cards:** `.ncc-card` grid with staleness-coded left borders:
- `.ncc-staleness-fresh` (green, <7 days)
- `.ncc-staleness-stale` (yellow, 7-14 days)
- `.ncc-staleness-critical` (red, >14 days)
- Each card: repo name, file name, last updated (relative time), staleness badge

**Actions:** "Sync Now" (`.ncc-btn-ghost`).

### 9. Logo Integration

**Sidebar (base.html):**
- Copy `static/nock_icon_transparent.png` to `static/images/nock-logo-icon.png`
- Replace `.ncc-sidebar-logo-icon` "N" div with `<img>` tag pointing to the logo
- Expanded: 28px icon + "NockCC" text
- Collapsed: 28px icon only

**Login page (login.html):**
- Replace CSS-generated V-nock with actual logo image (48-64px)
- Keep "Nock Command Center" gradient text
- Keep "TECHNOLOGIES" subtitle
- Update tagline to "Align · Decide · Deploy"

## Responsive Breakpoints

Follow Phase 1 patterns:
- **Desktop (>1200px):** Full layouts, 3-4 column grids, expanded sidebar
- **Tablet (768-1200px):** 2-column grids, condensed cards
- **Mobile (<767px):** 1-column stacked, sidebar hidden (hamburger), bottom tab bar, card-based layouts instead of tables where appropriate

## Commit Strategy

One commit per logical unit:
1. `style: redesign Spend dashboard with KPI cards and styled tables`
2. `style: redesign CRM pipeline with kanban layout`
3. `style: polish Tasks page to match Pipeline design`
4. `style: redesign Vault with document cards and session reports`
5. `style: redesign Teams with agent cards and prompt queue`
6. `style: redesign Remote Chat to match Advisor style`
7. `style: redesign Notifications with rules and channels`
8. `style: redesign Context with staleness indicators`
9. `style: integrate actual Nock logo in sidebar and login`
10. `style: add new CSS components for Phase 2 pages`

## Review Pipeline

1. Push to `feature/ui-reimagine-phase2`
2. Open PR to main
3. CodeRabbit auto-review
4. Kevin + Mara visual review
5. Deploy to Railway for live review
6. Merge when approved
