# NockCC UI Reimagine — Design Spec

**Date:** 2026-04-06
**Author:** Kevin + Claude
**Branch:** `feature/ui-reimagine`
**Scope:** Visual-only redesign. No backend changes, no new models, no new API endpoints.

---

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Navigation | Left sidebar | Industry-standard SaaS pattern, scales to 12+ nav items |
| Card style | Data-dense cockpit | Bloomberg meets Stripe — big numbers, sparklines, status dots |
| Sidebar style | Grouped + collapsible | Section headers organize nav, collapse toggle for max content space |

---

## 1. Design System

### CSS Architecture

Single file: `static/css/nockcc.css` with CSS custom properties as design tokens. Every template drops Tailwind CDN and uses hand-crafted CSS. Base.html imports this file plus Google Fonts.

### Design Tokens

```css
:root {
  /* Backgrounds */
  --bg-base: #0A0A0F;
  --bg-surface: #111119;
  --bg-surface-hover: #1A1A2E;
  --bg-border: #1E1E2E;

  /* Brand gradient */
  --accent-start: #3B6FD4;
  --accent-end: #7C5CFC;

  /* Status */
  --color-success: #34D399;
  --color-warning: #FBBF24;
  --color-danger: #F87171;
  --color-info: #06B6D4;

  /* Text */
  --text-primary: #E2E8F0;
  --text-secondary: #94A3B8;
  --text-muted: #64748B;

  /* Typography */
  --font-sans: 'DM Sans', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
  --text-xs: 12px;
  --text-sm: 14px;
  --text-base: 16px;
  --text-lg: 20px;
  --text-xl: 24px;
  --text-2xl: 32px;

  /* Spacing */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;

  /* Effects */
  --shadow-card: 0 1px 3px rgba(0, 0, 0, 0.4);
  --shadow-hover: 0 4px 12px rgba(59, 111, 212, 0.15);
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;
  --transition-fast: 150ms ease;
  --transition-normal: 200ms ease;

  /* Layout */
  --sidebar-width: 220px;
  --sidebar-collapsed: 64px;
}
```

### Icons

Lucide icons via CDN (`https://unpkg.com/lucide@latest`). Each nav item and card header uses a Lucide icon.

### Fonts

Google Fonts CDN in `base.html`:
- DM Sans (400, 500, 600, 700)
- JetBrains Mono (400, 500)

---

## 2. Layout — Sidebar + Content

### Sidebar (expanded: 220px, collapsed: 64px)

- **Position:** Fixed, full viewport height
- **Background:** `var(--bg-surface)`, right border `var(--bg-border)`
- **Top section:** Nock logo (32px gradient square with "N") + "NockCC" text + collapse toggle button (« icon)
- **Middle section:** Grouped nav items with section headers:
  - **Operations:** Nerve Center, Pipeline, Sessions
  - **Intelligence:** Brain, AI Advisor, Alerts
  - **Business:** Spend, CRM, Tasks, Vault
  - **System:** Teams, Prompts, Context, Notifications
- **Active item:** Left gradient accent bar (2px) + subtle `rgba(59,111,212,0.1)` background
- **Hover:** Background `var(--bg-surface-hover)` with `var(--transition-fast)`
- **Bottom section:** User avatar (initials circle), name, role. Logout icon on hover.
- **Collapse behavior:** Click toggle → animate to 64px with CSS transition, show icons only, native title attribute tooltips. State stored in `localStorage('nockcc-sidebar-collapsed')`.

### Mobile (<768px)

- Sidebar hidden by default
- Hamburger button in top-left corner of content area
- Tap → sidebar slides in as overlay with dark backdrop (`rgba(0,0,0,0.5)`)
- Tap backdrop or nav item → sidebar closes
- Bottom tab bar preserved: Home, Pipeline, Brain, Sessions, Chat (restyled with new tokens)

### Main Content Area

- `margin-left: var(--sidebar-width)` (or `var(--sidebar-collapsed)`)
- Padding: `var(--space-8)` (32px)
- Transition: `margin-left var(--transition-normal)`
- No max-width constraint — grids fill available space

---

## 3. Nerve Center (Homepage `/`)

### Page Header

"Nerve Center" in gradient text (32px), current date in `var(--text-muted)` right-aligned.

### Grid

- 3 columns on desktop (>1200px)
- 2 columns on tablet (768–1200px)
- 1 column on mobile (<768px)
- Gap: `var(--space-4)` (16px)
- `grid-auto-rows: minmax(0, 1fr)` for equal height rows

### Card Template (shared by all 6 panels)

```
┌─────────────────────────────────────┐
│ ● LABEL          [icon]  View All → │  ← header row
│                                     │
│  32px    32px    32px               │  ← hero numbers
│  label   label   label              │
│                                     │
│  ▁▂▃▅▃▂▄▅▆▅▃▂▃▅▇                   │  ← sparkline/detail
│                                     │
│  compact row 1                      │  ← supporting data
│  compact row 2                      │
│  compact row 3                      │
└─────────────────────────────────────┘
```

- Background: `var(--bg-surface)`
- Border: `1px solid var(--bg-border)`
- Radius: `var(--radius-lg)`
- Padding: `var(--space-5)` (20px)
- Hover: border color `rgba(59,111,212,0.2)`, box-shadow `var(--shadow-hover)`
- Shadow: `var(--shadow-card)`

### Panel Details

**Panel 1 — Mac Sessions:** Active count (hero), machine status list (dot + name + uptime), 24h sparkline.

**Panel 2 — Pipeline:** Open PRs / Merged Today / Awaiting Review (3 hero numbers, white/green/yellow), 7-day velocity bar chart, last 3 PRs as compact rows with status badges.

**Panel 3 — Mara's Brain:** Total entries (hero), category count + last consolidation (relative time), gate status dot, action buttons (Generate Brief, Consolidate).

**Panel 4 — Tasks:** Incomplete count (hero), top 5 tasks (priority dot + name + due), progress bar with gradient fill.

**Panel 5 — Financial:** Month spend (hero, gradient text), budget bar (spent/total + percentage), daily trend sparkline, remaining budget text.

**Panel 6 — Alerts:** Active count (hero), severity breakdown (dots + counts), last 3 alerts as compact rows, "All clear" state with green check.

### Sparklines

Inline SVG, 100% width of card, ~40px tall. Gradient fill from `var(--accent-start)` to transparent. No axis labels — pure visual indicator.

---

## 4. Pipeline (`/pipeline/`)

### Filter Bar

Row of filter controls above the table:
- Status dropdown (multi-select)
- Repo dropdown
- Reviewer dropdown
- Date range picker (simple from/to inputs)
- Active filters shown as removable pill tags

### PR Table

| Column | Details |
|--------|---------|
| Status | Color-coded pill badge: Draft (gray), Open (blue), Review (yellow), Approved (green), Merged (purple), Closed (red) |
| Repo | Repo name in mono font |
| Branch | Branch name, truncated |
| Title | PR title, truncated with ellipsis |
| Reviewers | Icon row: 🐰 CodeRabbit, ✨ Gemini, 🤖 Copilot, 🟣 Claude, 👤 Human |
| Time Open | Relative time; yellow >24h, red >72h |
| CI | Green ✓, red ✗, or yellow spinner |

- Row hover: `var(--bg-surface-hover)`
- Click row: expands inline detail panel with review comments, file change count, CI job details
- Alternating row backgrounds: `var(--bg-surface)` / `var(--bg-base)`

---

## 5. Brain (`/brain/`)

### Two-Column Layout

**Left sidebar (240px):**
- Category list: colored dot + category name + count badge (right-aligned)
- Active category: accent background tint
- "All" option at top

**Main area:**
- Search bar: full-width, search icon left, placeholder "Search memory entries...", instant filtering via Alpine.js
- Memory entry cards (vertical list):
  - Key: bold, `var(--text-primary)`
  - Value preview: 2 lines max, truncated, `var(--text-secondary)`
  - Tags: small pills with muted background
  - Confidence: thin horizontal bar (red/yellow/green gradient based on level)
  - Last updated: relative time, right-aligned
  - Hover: edit/delete icon buttons appear (Lucide pencil/trash)
- Inline editing: click edit → key/value become input/textarea in-place, Save/Cancel buttons

**Consolidation panel:**
- Collapsible section at top of main area
- Last consolidation time, gate status (dot + label), "Run Consolidation" button
- "Generate Brief" with scope dropdown + "Generate" button + output preview area

---

## 6. Sessions (`/sessions/`)

### Active Sessions (top section)

Horizontal row of live cards:
- Project name (bold), machine name (muted)
- Duration: ticking timer via Alpine.js `x-data` with `setInterval`
- Status dot: green (active), yellow (idle)
- Subtle pulsing glow (`box-shadow` animation) on active cards

### Recent Sessions (table below)

Columns: Project, Machine, Start Time, Duration, Status badge.
- Click row → navigates to session detail page
- Sortable column headers

---

## 7. Intelligence (`/intelligence/`)

### Executive Dashboard (`/intelligence/executive/`)

KPI cards across top (reuse card component), full-width chart/metric sections below.

### AI Advisor (`/intelligence/advisor/`)

Chat interface:
- Message list: scrollable, AI messages left-aligned with accent border, user messages right-aligned
- Input bar: fixed bottom, textarea + send button with gradient background
- AI responses: markdown rendered, `var(--font-mono)` for code blocks

### Alerts (`/intelligence/alerts/`)

Feed layout:
- Each alert: card with left colored bar (severity), message body, timestamp, dismiss button
- Critical = red bar, Warning = yellow, Info = blue
- Dismissed alerts fade out

---

## 8. Login Page (`/accounts/login/`)

Standalone page (does not extend base.html):
- Background: `var(--bg-base)` with subtle radial gradient (very faint purple/blue glow from center)
- Centered card: `var(--bg-surface)`, `var(--radius-lg)`, animated gradient border (CSS `@keyframes` rotating a conic gradient on a pseudo-element)
- Logo: 48px gradient square with "N", centered above card
- Title: "Nock Command Center" in gradient text
- Inputs: `var(--bg-base)` background, `var(--bg-border)` border, focus → gradient border transition
- Login button: full-width, gradient background, white text, hover brightens 10%
- Error messages: `var(--color-danger)` text above form
- Footer: "Nock Technologies" in `var(--text-muted)`

---

## 9. Responsive Breakpoints

| Breakpoint | Sidebar | Grid Columns | Notes |
|------------|---------|-------------|-------|
| >1200px | Expanded (220px) | 3 | Full desktop |
| 768–1200px | Collapsed (64px) | 2 | Tablet / narrow desktop |
| <768px | Hidden (overlay) | 1 | Mobile + bottom tab bar |

---

## 10. Files to Create/Modify

### New Files
- `static/css/nockcc.css` — full design system + component styles

### Modified Files (templates only)
- `templates/base.html` — new sidebar layout, drop Tailwind CDN, add nockcc.css + Lucide CDN
- `templates/accounts/login.html` — full restyle
- `dashboard/templates/dashboard/index.html` — Nerve Center redesign
- `pipeline/templates/pipeline/list.html` — table redesign
- `pipeline/templates/pipeline/detail.html` — detail panel restyle
- `brain/templates/brain/index.html` — two-column browser redesign
- `sessions/templates/sessions/list.html` — active cards + table redesign
- `intelligence/templates/intelligence/executive.html` — KPI cards restyle
- `intelligence/templates/intelligence/advisor.html` — chat interface restyle
- `intelligence/templates/intelligence/alerts.html` — feed restyle
- `templates/404.html` — match new theme
- `templates/500.html` — match new theme

### Not Modified
- All backend files (models.py, views.py, urls.py, serializers, etc.)
- All test files
- requirements.txt / pyproject.toml
- Static JS files (sw.js, manifest.json)
- Desktop/Electron apps
- Any other templates not listed above (spend, CRM, vault, teams, etc. — future passes)

---

## 11. What Stays the Same

- Django template inheritance pattern (`{% extends "base.html" %}`)
- Alpine.js for all interactivity (x-data, x-show, @click, etc.)
- Chart.js for spend/metric charts
- All API endpoints and data bindings
- CSRF token handling
- PWA manifest and service worker
- All existing Alpine.js component logic (nerveCenter(), brainBrowser(), etc.)
- Mobile bottom tab bar pattern (restyled)
