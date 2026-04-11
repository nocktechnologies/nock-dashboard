# Design Refresh Phase 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate NockCC from its drifted blue-purple design to the intended emerald-on-pitch-black system with Geist font, Supabase-level card depth, and Emil-style CSS animations — across the base CSS file, base template, and Nerve Center — while fixing three known mobile bugs.

**Architecture:** Edit `static/css/nockcc.css` (design tokens + components), `templates/base.html` (font + viewport), and `dashboard/templates/dashboard/index.html` (inline style cleanup). Three bug fixes: service worker (Spend $0), agent status reconnect (offline-when-online). Zero new JS dependencies — all animation via pure CSS + Alpine.js transitions.

**Tech Stack:** Django 5.x, Alpine.js v3.14.9, Lucide Icons, Geist/Geist Mono from Google Fonts, vanilla CSS custom properties

**Spec:** `docs/superpowers/specs/2026-04-08-design-refresh-design.md`

---

## Task 1: Add Emerald Tokens to nockcc.css

**Files:**
- Modify: `static/css/nockcc.css:10-75`

- [ ] **Step 1: Replace the brand gradient block and font/shadow tokens in `:root`**

Replace lines 18–70 of `static/css/nockcc.css`. The old `:root` block has `--accent-start: #3B6FD4`, `--accent-end: #7C5CFC`, `--font-sans: 'DM Sans'`, and `--shadow-hover` with a blue tint. Replace the entire `:root` block (from `:root {` to its closing `}`) with:

```css
:root {
  /* Backgrounds */
  --bg-base: #0A0A0F;
  --bg-surface: #0f0f1a;
  --bg-surface-hover: #18182a;
  --bg-border: #1a1a2e;
  --bg-border-hover: #22223a;

  /* Brand Accent — Emerald (replaces blue-purple) */
  --color-accent:      #10B981;
  --color-accent-dark: #059669;
  --color-accent-dim:  #052e16;
  --color-accent-glow: rgba(16, 185, 129, 0.08);
  --color-text-accent: #34D399;
  --color-border-accent: #166534;

  /* Phase 1 backwards-compat aliases — templates using these inline
     will now render emerald instead of blue-purple.
     Remove these in Phase 2 when all template inline styles are cleaned up. */
  --accent-start: var(--color-accent);
  --accent-end:   var(--color-accent);

  /* Status Colors */
  --color-success: #34D399;
  --color-warning: #FBBF24;
  --color-danger:  #F87171;
  --color-info:    #06B6D4;

  /* Text Colors */
  --text-primary:   #F1F5F9;
  --text-secondary: #94A3B8;
  --text-muted:     #64748B;

  /* Typography — Geist replaces DM Sans */
  --font-sans: 'Geist', system-ui, -apple-system, sans-serif;
  --font-mono: 'Geist Mono', monospace;
  --fw-light:    300;
  --fw-regular:  400;
  --fw-medium:   500;
  --fw-semibold: 600;

  /* Font Sizes */
  --text-xs:   0.75rem;
  --text-sm:   0.875rem;
  --text-base: 1rem;
  --text-lg:   1.125rem;
  --text-xl:   1.5rem;
  --text-2xl:  2rem;

  /* Spacing — 8px base grid */
  --space-1:  4px;
  --space-2:  8px;
  --space-3:  12px;
  --space-4:  16px;
  --space-5:  20px;
  --space-6:  24px;
  --space-8:  32px;
  --space-10: 40px;
  --space-12: 48px;

  /* Radius */
  --radius-sm:   4px;
  --radius-md:   8px;
  --radius-lg:   12px;
  --radius-xl:   16px;
  --radius-full: 9999px;

  /* Shadows */
  --shadow-card: 0 1px 2px rgba(0,0,0,0.4), 0 4px 12px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.03);
  --shadow-hover: 0 8px 24px rgba(16, 185, 129, 0.06), 0 2px 8px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.03);

  /* Animation — Emil Kowalski easing curves */
  --ease-out:    cubic-bezier(0.23, 1, 0.32, 1);
  --ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);
  --dur-fast:    150ms;
  --dur-default: 200ms;
  --dur-slow:    350ms;

  /* Transitions (kept for backwards compat with existing usage) */
  --transition-fast: var(--dur-fast) var(--ease-out);
  --transition-base: var(--dur-default) var(--ease-out);
  --transition-slow: var(--dur-slow) var(--ease-out);

  /* Layout */
  --sidebar-width:     220px;
  --sidebar-collapsed: 64px;
}
```

- [ ] **Step 2: Verify the file parses after the token change**

```bash
cd /Users/kevin/Dev/nock-command-center
python -c "
import subprocess
result = subprocess.run(['python', 'manage.py', 'collectstatic', '--noinput', '--dry-run'],
    capture_output=True, text=True)
print(result.returncode)
"
```

Expected: prints `0` (Django can find and parse static files). If it errors, check for unclosed braces in the CSS edit.

- [ ] **Step 3: Commit tokens-only change**

```bash
git add static/css/nockcc.css
git commit -m "style: replace blue-purple tokens with emerald + add animation vars"
```

---

## Task 2: Update CSS Component Styles — Sidebar, Cards, Buttons

**Files:**
- Modify: `static/css/nockcc.css` (multiple component sections)

- [ ] **Step 1: Update `.ncc-gradient-text` (line ~165)**

Find and replace:
```css
.ncc-gradient-text {
  background: linear-gradient(135deg, var(--accent-start), var(--accent-end));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
```
With:
```css
.ncc-gradient-text {
  background: linear-gradient(135deg, var(--color-accent), var(--color-text-accent));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
```

- [ ] **Step 2: Update `.ncc-sidebar-logo-icon` gradient (line ~224)**

Find and replace the single line:
```css
  background: linear-gradient(135deg, var(--accent-start), var(--accent-end));
```
With (within the `.ncc-sidebar-logo-icon` block only):
```css
  background: var(--color-accent);
```

- [ ] **Step 3: Update `.ncc-sidebar-item.active` — add emerald color, replace gradient pill**

Find:
```css
.ncc-sidebar-item.active {
  color: var(--text-primary);
  background-color: var(--bg-surface-hover);
}

.ncc-sidebar-item.active::before {
  content: '';
  position: absolute;
  left: -8px;
  top: 4px;
  bottom: 4px;
  width: 3px;
  border-radius: var(--radius-full);
  background: linear-gradient(180deg, var(--accent-start), var(--accent-end));
}
```
Replace with:
```css
.ncc-sidebar-item.active {
  color: var(--color-accent);
  background-color: var(--color-accent-dim);
}

.ncc-sidebar-item.active::before {
  content: '';
  position: absolute;
  left: -8px;
  top: 4px;
  bottom: 4px;
  width: 3px;
  border-radius: var(--radius-full);
  background: var(--color-accent);
}
```

- [ ] **Step 4: Update `.ncc-sidebar-user-avatar` gradient (line ~352)**

Find (within `.ncc-sidebar-user-avatar`):
```css
  background: linear-gradient(135deg, var(--accent-start), var(--accent-end));
```
Replace with:
```css
  background: var(--color-accent);
```

- [ ] **Step 5: Update `.ncc-card` — Supabase-level depth system**

Find:
```css
.ncc-card {
  background-color: var(--bg-surface);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  box-shadow: var(--shadow-card);
  transition: border-color var(--transition-base), box-shadow var(--transition-base);
}

.ncc-card:hover {
  border-color: var(--bg-border-hover);
  box-shadow: var(--shadow-hover);
}
```
Replace with:
```css
.ncc-card {
  background: var(--bg-surface);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  box-shadow: var(--shadow-card);
  transition: transform var(--dur-fast) var(--ease-out),
              border-color var(--dur-fast) var(--ease-out),
              box-shadow var(--dur-fast) var(--ease-out);
}

@media (hover: hover) and (pointer: fine) {
  .ncc-card:hover {
    transform: translateY(-1px);
    border-color: var(--bg-border-hover);
    box-shadow: var(--shadow-hover);
  }
}
```

- [ ] **Step 6: Update `.ncc-card-label` color (line ~436)**

Find the line inside `.ncc-card-label`:
```css
  color: var(--accent-start);
```
Replace with:
```css
  color: var(--color-accent);
```

- [ ] **Step 7: Update `.ncc-btn-primary` — solid emerald, press feedback**

Find:
```css
.ncc-btn-primary {
  background: linear-gradient(135deg, var(--accent-start), var(--accent-end));
```
Replace that opening line with:
```css
.ncc-btn-primary {
  background: var(--color-accent);
```

Then find the `.ncc-btn-primary:hover` rule and update it to:
```css
.ncc-btn-primary:hover {
  background: var(--color-accent-dark);
}

.ncc-btn-primary:active {
  transform: scale(0.97);
}
```

- [ ] **Step 8: Add button/interactive press feedback and hover guards**

Find the `button { ... }` block in section 2 (Base Resets, ~line 109) and update the transition:
```css
button {
  font-family: inherit;
  font-size: inherit;
  border: none;
  background: none;
  cursor: pointer;
  color: inherit;
  transition: transform var(--dur-fast) var(--ease-out);
}

button:active {
  transform: scale(0.97);
}
```

- [ ] **Step 9: Add `@media (prefers-reduced-motion)` block at end of file**

Append to the very end of `static/css/nockcc.css`:
```css

/* ==========================================================================
   Reduced Motion — accessibility
   ========================================================================== */

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }

  /* Keep the pulse dot but remove the animation */
  .ncc-dot-pulse {
    animation: none;
    opacity: 1;
  }
}
```

- [ ] **Step 10: Verify no remaining raw hex blue-purple values in nockcc.css**

```bash
grep -n "3B6FD4\|7C5CFC\|accent-start\|accent-end" static/css/nockcc.css | grep -v "^.*--accent-start:\|^.*--accent-end:"
```

Expected: empty output (no lines). If any appear, the compatibility alias lines are fine — any gradient usage lines are not.

- [ ] **Step 11: Commit component style changes**

```bash
git add static/css/nockcc.css
git commit -m "style: emerald sidebar, card depth, buttons — replace gradient components"
```

---

## Task 3: Swap Font and Fix Viewport in base.html

**Files:**
- Modify: `templates/base.html:6-12`

- [ ] **Step 1: Replace Google Fonts import and fix viewport meta**

Find in `templates/base.html`:
```html
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
```
Replace with:
```html
    <meta name="viewport" content="width=device-width, initial-scale=1, interactive-widget=resizes-content" />
```

Then find:
```html
    <!-- Fonts: DM Sans (UI) + JetBrains Mono (code/technical) -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```
Replace with:
```html
    <!-- Fonts: Geist (UI) + Geist Mono (code/technical) -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
```

- [ ] **Step 2: Verify font loads in browser**

Run the dev server: `python manage.py runserver`

Open `http://127.0.0.1:8000` in Chrome. Open DevTools → Network tab → filter by `fonts.gstatic.com`. Confirm Geist font files load (not DM Sans). Check console for 404 errors.

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "style: swap DM Sans → Geist, add interactive-widget viewport meta for Android keyboard"
```

---

## Task 4: Clean Up Nerve Center Inline Styles

**Files:**
- Modify: `dashboard/templates/dashboard/index.html`

The template has several `style="color:var(--accent-start);"` inline styles. With the Phase 1 compat aliases in place these will now render as emerald, but we should clean up the three most visible ones on the Nerve Center page for correctness.

- [ ] **Step 1: Replace `var(--accent-start)` inline styles in dashboard/index.html**

Across the file, find every occurrence of `var(--accent-start)` in inline styles and replace with `var(--color-accent)`. There are 4 occurrences:

```
line 181: style="color:var(--accent-start);"
line 359: style="color:var(--accent-start);"
line 444: style="color:var(--accent-start);"
line 490: style="border-left:2px solid var(--accent-start);"
line 501: style="color:var(--accent-start);"
```

Run:
```bash
sed -i '' 's/var(--accent-start)/var(--color-accent)/g' dashboard/templates/dashboard/index.html
```

Verify:
```bash
grep "accent-start\|accent-end" dashboard/templates/dashboard/index.html
```
Expected: empty output.

- [ ] **Step 2: Commit**

```bash
git add dashboard/templates/dashboard/index.html
git commit -m "style: replace accent-start inline styles with color-accent on Nerve Center"
```

---

## Task 5: Fix Spend $0 Bug — Service Worker Not Handling /spend/api/

**Files:**
- Modify: `static/sw.js:26`

**Root cause:** The service worker's network-first handler covers `/api/` and `/remote/api/` but not `/spend/api/`. When mobile network is poor or the fetch fails, the SW serves its HTML offline fallback. `JSON.parse()` on HTML throws, the catch swallows it, and `spendData` stays at defaults of `'0.00'`.

- [ ] **Step 1: Write a test that fails — verify the SW gap**

Create `tests/test_sw_coverage.py`:
```python
"""Verify spend API path is covered by service worker network-first handler."""

import re


def test_sw_handles_spend_api_path():
    """Service worker must handle /spend/api/ as a network-first API call,
    not fall through to the HTML page handler."""
    sw = open("static/sw.js").read()
    # The SW should match any pathname containing /api/ — not just /api/ and /remote/api/
    assert "pathname.includes('/api/')" in sw or (
        "pathname.startsWith('/spend/api/')" in sw
    ), (
        "SW fetch handler must cover /spend/api/ with the network-first + JSON fallback. "
        "Currently only covers /api/ and /remote/api/."
    )
```

Run: `pytest tests/test_sw_coverage.py -v`
Expected: FAIL — `AssertionError: SW fetch handler must cover /spend/api/...`

- [ ] **Step 2: Fix the service worker**

In `static/sw.js`, find:
```javascript
  // Network-first for API calls
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/remote/api/')) {
```
Replace with:
```javascript
  // Network-first for API calls — covers /api/, /remote/api/, /spend/api/, /brain/api/, etc.
  if (url.pathname.includes('/api/')) {
```

- [ ] **Step 3: Run the test — verify it passes**

```bash
pytest tests/test_sw_coverage.py -v
```
Expected: PASS

- [ ] **Step 4: Bump the service worker cache name so mobile browsers update**

In `static/sw.js`, find:
```javascript
const CACHE_NAME = 'nockcc-v1';
```
Replace with:
```javascript
const CACHE_NAME = 'nockcc-v2';
```

- [ ] **Step 5: Commit**

```bash
git add static/sw.js tests/test_sw_coverage.py
git commit -m "fix: service worker handles /spend/api/ as network-first — resolves \$0 spend on mobile"
```

---

## Task 6: Fix Agent Status Offline Bug — WS Reconnect on Tab Visibility

**Files:**
- Modify: `templates/base.html` (end of `<body>`)
- Modify: `remote/views.py` (agent_status endpoint — add Cache-Control header)

**Root cause:** Two issues compounding: (1) mobile browsers throttle/kill WebSocket connections when the tab goes to background; (2) the agent status view has no `Cache-Control: no-store`, so the service worker (now fixed) could return a stale response. When the user returns to the tab, `is_online` is False because the WS disconnected, and there's no reconnect logic.

- [ ] **Step 1: Write a test that fails — verify Cache-Control header on agent_status**

```python
# tests/remote/test_agent_status_view.py
import pytest
from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_agent_status_has_no_cache_header(client):
    """Agent status API must not be cached — stale data causes offline-when-online bug."""
    user = User.objects.create_user(username="tester", password="pass")
    client.force_login(user)
    response = client.get("/remote/api/agent-status/")
    assert response.status_code == 200
    cc = response.get("Cache-Control", "")
    assert "no-store" in cc, (
        f"Cache-Control header must include 'no-store', got: '{cc}'"
    )
```

Run: `pytest tests/remote/test_agent_status_view.py -v`
Expected: FAIL — `AssertionError: Cache-Control header must include 'no-store'`

- [ ] **Step 2: Add `Cache-Control: no-store` to the agent_status view**

In `remote/views.py`, find and replace the `return JsonResponse(...)` at the bottom of `agent_status` (line ~243):

```python
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "agents": agent_data,
            "any_online": any(a.is_online for a in agents),
        },
    })
```

Replace with:
```python
    response = JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "agents": agent_data,
            "any_online": any(a.is_online for a in agents),
        },
    })
    response["Cache-Control"] = "no-store"
    return response
```

- [ ] **Step 3: Run the test — verify it passes**

```bash
pytest tests/remote/test_agent_status_view.py -v
```
Expected: PASS

- [ ] **Step 4: Add `visibilitychange` WebSocket reconnect to base.html**

Append before the closing `</body>` tag in `templates/base.html`:

```html
    <!-- WS reconnect on mobile tab resume — fixes agent showing offline after backgrounding -->
    <script>
    (function () {
      document.addEventListener('visibilitychange', function () {
        if (document.visibilityState !== 'visible') return;
        // Dispatch a custom event so Alpine.js components can listen and re-poll
        document.dispatchEvent(new CustomEvent('nockcc:tabvisible'));
      });
    })();
    </script>
```

This fires `nockcc:tabvisible` whenever the user returns to the tab. The remote control page can listen to this event and trigger a status re-fetch. (The remote control template handles this in Phase 2's full mobile pass; this step adds the plumbing to base.html so it's available sitewide.)

- [ ] **Step 5: Run full test suite to confirm no regressions**

```bash
pytest -q
```
Expected: all tests pass (existing 678+, plus 2 new ones).

- [ ] **Step 6: Commit**

```bash
git add remote/views.py templates/base.html tests/remote/test_agent_status_view.py
git commit -m "fix: add Cache-Control no-store to agent status + visibilitychange reconnect hook"
```

---

## Task 7: Write .impeccable.md

**Files:**
- Create: `.impeccable.md`

- [ ] **Step 1: Create the design context file**

Create `.impeccable.md` in the project root:

```markdown
## Design Context

### Users
Kevin — sole operator of a personal multi-agent AI development command center. Uses on desktop (Mac/Windows browser) and mobile (Pixel 10 Pro XL browser/PWA). Context: actively monitoring running AI agents, reviewing PRs, checking spend, reading Brain memories, and managing tasks. Always in "work mode" — this is a tool, not a product to sell.

### Brand Personality
Precise. Commanding. Purposeful.

### Aesthetic Direction
Dark devtool cockpit — emerald (#10B981) on pitch black (#0A0A0F). Geist font. Feels like mission control, not a SaaS dashboard. Reference: Supabase (dark depth layers, precise borders) + Linear (restraint, fast animations). Anti-references: generic purple/indigo SaaS, rounded-2xl everything, heavy gradients, light mode.

### Design Principles
1. **Data-forward** — every pixel serves information density. No decorative chrome.
2. **Emerald is signal** — use emerald only for active/alive/actionable states. Never decorative.
3. **Depth without noise** — cards have layered shadows and inset highlights, not flat surfaces.
4. **Motion is earned** — animate entrances (200ms ease-out), not steady states. Work tool, not marketing site.
5. **Mobile is a peer** — Pixel 10 Pro XL gets the same information density as desktop. 44px tap targets. No horizontal scroll.

### Token Reference
- Primary accent: `#10B981` (emerald 500)
- Accent text: `#34D399` (emerald 400)
- Background: `#0A0A0F`
- Card surface: `#0f0f1a`
- Border: `#1a1a2e`
- Font: Geist (UI), Geist Mono (code)
- Easing: `cubic-bezier(0.23, 1, 0.32, 1)` (ease-out for UI interactions)
```

- [ ] **Step 2: Commit**

```bash
git add .impeccable.md
git commit -m "docs: add .impeccable.md design context for NockCC"
```

---

## Task 8: Final Verification Pass

**Files:** none (verification only)

- [ ] **Step 1: Lint**

```bash
ruff check . --fix
```
Expected: `All checks passed!` (or only fixable warnings, now fixed).

- [ ] **Step 2: Full test suite**

```bash
pytest -q
```
Expected: all tests pass. Note the final count — should be ≥ 680 (678 + 2 new).

- [ ] **Step 3: Grep for stale token references in CSS**

```bash
grep -n "3B6FD4\|7C5CFC\|DM Sans\|JetBrains Mono" static/css/nockcc.css templates/base.html
```
Expected: empty output. If any appear, fix them before pushing.

- [ ] **Step 4: Visual spot-check (5 pages)**

Run `python manage.py runserver` and visit:
1. `/` (Nerve Center) — cards have depth shadow, labels are emerald, sidebar active item is emerald
2. `/pipeline/` — active nav item is emerald
3. `/spend/` — KPI value colors now emerald (not blue/purple)
4. `/brain/` — filter buttons use emerald border when active
5. Mobile viewport (DevTools → 412px width, Pixel 5) — sidebar collapses, bottom nav shows, tap targets ≥ 44px, no horizontal overflow

- [ ] **Step 5: Motion spot-check (Emil checklist)**

```
[ ] Card hover: lifts 1px with border highlight — not on touch devices
[ ] Active nav item: instant color, no animation (keyboard-like)
[ ] Primary button: scale(0.97) on press
[ ] No animation durations > 300ms in UI interactions
[ ] Reduced motion: enable in OS → all transforms disabled
```

- [ ] **Step 6: Update CHANGELOG.md**

Add entry at top of CHANGELOG.md:
```markdown
## [Unreleased] — 2026-04-08

### Changed
- Design system migrated from blue-purple gradient to emerald (#10B981) brand accent
- Font swapped from DM Sans → Geist (UI) + Geist Mono (code/technical)
- Card depth system upgraded to Supabase-level layered shadows with inset highlights
- Sidebar active states now use emerald color + emerald-dim background (no longer blue gradient bar)
- Primary buttons now solid emerald with darker hover and scale-on-press feedback
- Emil Kowalski animation tokens added (cubic-bezier ease-out, dur-fast/default/slow)
- prefers-reduced-motion block added — all transform animations disabled for accessibility

### Fixed
- Android keyboard no longer covers input fields (interactive-widget=resizes-content viewport meta)
- Spend dashboard showing $0 on mobile — service worker now handles /spend/api/ as network-first
- Agent status cache-control set to no-store — prevents stale offline readings on mobile
```

- [ ] **Step 7: Final commit + push**

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for Phase 1 design refresh"
git push origin design/refresh-with-toolkit
```

- [ ] **Step 8: Open PR**

```bash
gh pr create \
  --title "style: Phase 1 design refresh — emerald tokens, Geist font, mobile bug fixes" \
  --body "$(cat <<'EOF'
## Summary
- Migrates NockCC from drifted blue-purple design to intended emerald-on-pitch-black system
- Geist (UI) + Geist Mono (code) replace DM Sans + JetBrains Mono — loaded from Google Fonts
- Supabase-level card depth: layered shadows + inset highlights + emerald hover borders
- Sidebar active state: emerald text + emerald-dim background (replaces blue gradient pill)
- Emil Kowalski animation tokens: custom cubic-bezier, duration scale, reduced-motion support
- Fixes Android keyboard covering inputs (interactive-widget viewport meta)
- Fixes Spend showing \$0 on mobile (service worker now handles /spend/api/ as network-first)
- Fixes agent status stale offline reading (Cache-Control: no-store on status endpoint)

## Test plan
- [ ] `pytest -q` — all tests pass (≥ 680)
- [ ] `ruff check .` — clean
- [ ] Geist font loads in DevTools Network tab (no DM Sans)
- [ ] `grep "3B6FD4\|7C5CFC" static/css/nockcc.css` returns empty
- [ ] Nerve Center cards have depth shadow on desktop, no hover lift on touch
- [ ] Sidebar active item is emerald on every page
- [ ] Spend KPI values show correct amounts on mobile browser (Pixel viewport)
- [ ] Reduced motion OS setting disables all transform animations

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Notes for Phase 2

The following templates still have `var(--accent-start)` / `var(--accent-end)` inline styles that render as emerald via the Phase 1 aliases. Clean them up in Phase 2 when you tackle each app:

- `remote/templates/remote/chat.html` (4 uses)
- `spend/templates/spend/dashboard.html` (3 uses)
- `vault/templates/vault/list.html` (2 uses)
- `brain/templates/brain/index.html` (2 uses)
- `context/templates/context/list.html` (1 use)
- `intelligence/templates/intelligence/advisor.html` (2 uses)
- `tasks/templates/tasks/feed.html` (1 use)
- `pipeline/templates/pipeline/detail.html` (2 uses)
- `pipeline/templates/pipeline/list.html` (4 uses)
- `teams/templates/teams/prompts.html` (1 use)

Remove `--accent-start` and `--accent-end` compat aliases from `:root` once all template inline styles are cleaned up.
