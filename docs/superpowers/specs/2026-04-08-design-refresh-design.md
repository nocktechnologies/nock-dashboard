# Design Refresh — NockCC Command Center
**Date:** 2026-04-08  
**Branch:** `design/refresh-with-toolkit`  
**Status:** Approved — ready for implementation plan

---

## Overview

Full design system refresh of NockCC (cc.nocktechnologies.io). The codebase has drifted from its intended design language: blue-purple gradients have replaced emerald, DM Sans has replaced Geist, and card depth is flat rather than layered. This refresh restores the intended system and elevates it to Supabase-level production quality.

NockCC is Kevin's daily driver — a mission-control cockpit for multi-agent AI workflows. It must feel like premium devtool software, not a generic SaaS dashboard.

---

## Decisions Made

| Decision | Choice | Rationale |
|---|---|---|
| **Font** | Geist (UI) + Geist Mono (code) | Spec font; technical, razor-sharp, made for developer tools. Load from Google Fonts. |
| **Card depth** | Supabase-level B | Layered shadows + inset highlights + emerald accent borders. Not flat, not glowing — precise depth. |
| **Animation** | Pure CSS + Alpine.js | Zero new dependencies. `@starting-style`, custom cubic-beziers, Alpine `x-transition`. |
| **PR scope** | Phased | Phase 1: tokens + base + Nerve Center. Phase 2: remaining 10 apps. |

---

## Design System

### Color Tokens

```css
/* Core palette — restoring from blue-purple drift */
--color-bg:            #0A0A0F;   /* pitch black */
--color-surface-1:     #0f0f1a;   /* card background */
--color-surface-2:     #111119;   /* elevated surface */
--color-surface-3:     #18182a;   /* hover / selected */
--color-border:        #1a1a2e;   /* default border */
--color-border-subtle: #14141f;   /* hairline separator */
--color-border-accent: #166534;   /* emerald border */

/* Emerald accent — PRIMARY brand color (replacing blue-purple gradient) */
--color-accent:        #10B981;   /* emerald 500 */
--color-accent-dark:   #059669;   /* emerald 600 — pressed states */
--color-accent-dim:    #052e16;   /* emerald bg tint */
--color-accent-glow:   rgba(16, 185, 129, 0.08);

/* Text scale */
--color-text-primary:  #F1F5F9;
--color-text-secondary:#94A3B8;
--color-text-muted:    #64748B;
--color-text-accent:   #34D399;   /* emerald 400 — on dark surfaces */

/* Status (unchanged) */
--color-success:       #34D399;
--color-warning:       #FBBF24;
--color-danger:        #F87171;
--color-info:          #06B6D4;
```

**Migration note:** Remove all instances of `#3B6FD4`, `#7C5CFC`, and the `linear-gradient(135deg, #3B6FD4, #7C5CFC)` pattern from `nockcc.css`. Replace with `--color-accent` (emerald) for primary actions, `--color-surface-*` for backgrounds.

### Typography

Load from Google Fonts (replace current DM Sans + JetBrains Mono import):

```html
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
```

```css
--font-ui:   'Geist', system-ui, sans-serif;
--font-mono: 'Geist Mono', 'JetBrains Mono', monospace;

/* Weight hierarchy */
--fw-light:    300;  /* page headlines */
--fw-regular:  400;  /* body text */
--fw-medium:   500;  /* labels, nav items */
--fw-semibold: 600;  /* emphasis, badges */
```

### Spacing (8px base grid)

```css
--space-1:  4px;
--space-2:  8px;
--space-3:  12px;
--space-4:  16px;
--space-5:  20px;
--space-6:  24px;
--space-8:  32px;
--space-10: 40px;
--space-12: 48px;
```

### Depth System (Supabase-level)

Cards use three composited layers — no single box-shadow:

```css
/* ncc-card base */
.ncc-card {
  background: var(--color-surface-1);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  box-shadow:
    0 1px 2px rgba(0,0,0,0.4),
    0 4px 12px rgba(0,0,0,0.2),
    inset 0 1px 0 rgba(255,255,255,0.03);
}

/* Active / selected card */
.ncc-card[data-active],
.ncc-card:focus-within {
  border-color: var(--color-border-accent);
  box-shadow:
    0 1px 2px rgba(0,0,0,0.4),
    0 4px 12px rgba(0,0,0,0.2),
    0 0 0 1px rgba(16,185,129,0.15),
    inset 0 1px 0 rgba(255,255,255,0.03);
}

/* Hover */
.ncc-card:hover {
  border-color: #22223a;
  transition: border-color 150ms var(--ease-out), box-shadow 150ms var(--ease-out);
}
```

### Animation Tokens (Pure CSS)

```css
/* Custom easing curves (Emil Kowalski) */
--ease-out:    cubic-bezier(0.23, 1, 0.32, 1);
--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);
--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);

/* Duration scale */
--dur-fast:    150ms;  /* button press, tooltip */
--dur-default: 200ms;  /* dropdowns, cards */
--dur-slow:    350ms;  /* modals, drawers */
```

**Rules:**
- Animate only `transform` and `opacity` (GPU-composited, no layout thrashing)
- Never `transition: all` — always specify exact properties
- Keyboard-initiated actions: no animation
- `@media (prefers-reduced-motion: reduce)`: remove transform animations, keep opacity/color only
- Entry scale starts at `scale(0.97)`, never `scale(0)` — nothing appears from nothing
- Hover states: gate behind `@media (hover: hover) and (pointer: fine)` — touch devices fire hover on tap

---

## Phase 1 Scope

### 1. Design tokens (`static/css/nockcc.css`)

- Replace all 76+ custom properties with the updated token set above
- Remove blue-purple gradient references entirely
- Add animation tokens (`--ease-*`, `--dur-*`)
- Add `@media (prefers-reduced-motion)` block

### 2. Base template (`templates/base.html`)

**Font swap:** Replace Google Fonts import (DM Sans → Geist + Geist Mono). Apply `font-family: var(--font-ui)` globally.

**Sidebar polish:**
- Active nav item: `color: var(--color-accent)` + left border `border-left: 2px solid var(--color-accent)` + `background: var(--color-accent-dim)`
- Inactive: `color: var(--color-text-muted)`, no border
- Group labels: `--fw-medium`, `--color-text-muted`, 9px, uppercase
- Sidebar hover: `background: var(--color-surface-3)`, transition `150ms var(--ease-out)`
- Collapse on mobile: already implemented, ensure bottom-nav tap targets ≥ 44px

**Alpine transitions:** Replace any instant show/hide with:
```html
x-transition:enter="transition ease-out duration-200"
x-transition:enter-start="opacity-0 scale-95"
x-transition:enter-end="opacity-100 scale-100"
x-transition:leave="transition ease-in duration-150"
x-transition:leave-start="opacity-100 scale-100"
x-transition:leave-end="opacity-0 scale-95"
```

### 3. Nerve Center (`dashboard/templates/dashboard/index.html`)

**3×2 card grid — each card:**
- `.ncc-card` with depth system above
- Card title: 11px, `--fw-medium`, uppercase, `--color-accent` (emerald)
- Primary stat: 28px, `--fw-light`, `--color-text-primary`
- Secondary text: 12px, `--color-text-muted`
- Pill badges: `font-family: var(--font-mono)`, 10px

**Per card:**

| Card | Stat shown | Live indicator |
|---|---|---|
| Mac Sessions | Active count | Pulsing green dot per active session |
| Pipeline | Open PR count | Badge breakdown: review / approved / failing |
| Brain | Memory count | Last consolidation timestamp |
| Tasks | Due today count | Overdue count in danger color |
| Financial | Today's spend | Budget remaining |
| Alerts | Unread count | Severity breakdown |

**Live data pulse:** Active session dots get `animation: pulse 2s ease-in-out infinite` — subtle opacity 1→0.4→1. Nothing else pulses.

**Empty states:** Each card shows a muted message + action link when no data — never a blank card.

**Loading:** CSS `animate-pulse` skeleton via `background: linear-gradient(90deg, var(--color-surface-1) 25%, var(--color-surface-2) 50%, var(--color-surface-1) 75%); background-size: 200% 100%; animation: shimmer 1.5s ease-in-out infinite`.

**Card hover micro-interaction:**
```css
.ncc-card {
  transition: transform var(--dur-fast) var(--ease-out),
              border-color var(--dur-fast) var(--ease-out);
}
@media (hover: hover) and (pointer: fine) {
  .ncc-card:hover { transform: translateY(-1px); }
}
```

### 4. Known bug fixes (in Phase 1)

**Keyboard covers inputs on Android (mobile):**
- Add `<meta name="viewport" content="width=device-width, initial-scale=1, interactive-widget=resizes-content">` — forces browser to resize viewport instead of overlapping
- Wrap forms in a container with `padding-bottom: env(keyboard-inset-height, 0)` for additional safety

**Spend shows $0 on mobile:**
- Check `spend/templates/spend/dashboard.html` — the KPI card values likely render correctly on desktop but fail a template conditional (e.g., `{% if revenue %}` failing when `revenue` is a `Decimal('0.00')`). Fix: use `{% if revenue is not None %}` or `{% if revenue != None %}` depending on the queryset return. Not a CSS issue.

**Agent status shows offline in app when online on web:**
- Root cause: mobile browsers (Safari, Chrome Android) aggressively throttle background tabs, causing WebSocket heartbeat to miss and the consumer to mark the session as offline. Fix path: (1) in `remote/consumers.py`, increase heartbeat tolerance before marking offline; (2) add an HTTP polling fallback in `remote/templates/remote/control.html` — poll `/api/agent-status/` every 30s when the WS connection drops (detect via `websocket.onclose`); (3) re-establish WS on page `visibilitychange` event when tab returns to foreground.

---

## Phase 2 Scope (future PR)

Apply the same token system to all remaining app templates:

- `pipeline/` (2 templates)
- `sessions/` (1 template)
- `context/` (2 templates)
- `intelligence/` (3 templates: advisor, alerts, executive)
- `crm/` (5 templates)
- `spend/` (5 templates — partially done with KPI cards)
- `vault/` (3 templates)
- `teams/` (2 templates)
- `remote/` (4 templates)
- `notifications/` (1 template)
- `brain/` (1 template)
- `tasks/` (2 templates)

Run `/impeccable` audit and motion audit pass on each.

---

## Anti-Patterns (Do Not Do)

From `DESIGN.md` — enforced in this refresh:

- No blue-purple gradients anywhere
- No Inter, Arial, or system-ui as primary font
- No light mode elements leaking in
- No flat, featureless cards (must use depth system)
- No `transition: all`
- No animations on keyboard-triggered actions
- No `scale(0)` entry animations
- No hover states without `@media (hover: hover)` guard

---

## Motion Audit Checklist (pre-push Phase 1)

Emil (primary — productivity tool):
- [ ] No animation on keyboard-initiated actions
- [ ] All durations ≤ 300ms for UI interactions
- [ ] Entry/exit at `scale(0.97)` not `scale(0)`
- [ ] Custom `cubic-bezier` easing (not browser defaults)
- [ ] `ease-out` for entries, `ease-in-out` for on-screen moves

Jakub (secondary — production polish):
- [ ] All conditional Alpine shows have x-transition
- [ ] Exits subtler than entries (smaller values, same blur)
- [ ] Hover states: 150ms minimum transition

Accessibility:
- [ ] `@media (prefers-reduced-motion: reduce)` block present and tested
- [ ] Touch hover states gated behind pointer:fine media query

---

## Pre-Push Checklist (Phase 1)

- [ ] `ruff check . --fix` clean
- [ ] `pytest -q` — all 678+ tests pass
- [ ] Geist font loads (check network tab, no 404)
- [ ] No blue-purple references remaining in nockcc.css (`grep -r "3B6FD4\|7C5CFC"`)
- [ ] Nerve Center renders correctly at 320px, 768px, 1024px, 1440px
- [ ] Android keyboard fix verified (test at ~412px viewport width)
- [ ] Spend $0 bug investigated and fixed or filed
- [ ] Agent status bug investigated and fixed or filed
- [ ] CHANGELOG.md updated
- [ ] `.impeccable.md` written to project root (use `teach-impeccable` skill output)

---

## File Map (Phase 1)

| File | Change |
|---|---|
| `templates/base.html` | Font import, sidebar active states, Alpine transitions, mobile viewport meta |
| `static/css/nockcc.css` | Full token update, remove blue-purple, add animation tokens, add reduced-motion block |
| `dashboard/templates/dashboard/index.html` | Nerve Center card grid redesign with depth, live indicators, empty states |
| `.impeccable.md` | Design context for future sessions |
| `CHANGELOG.md` | Entry for Phase 1 |
