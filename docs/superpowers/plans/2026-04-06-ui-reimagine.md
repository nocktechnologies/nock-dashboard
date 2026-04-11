# NockCC UI Reimagine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Visual-only redesign of NockCC from functional dark dashboard to product-grade SaaS UI — left sidebar navigation, data-dense cockpit cards, hand-crafted CSS design system.

**Architecture:** Replace Tailwind CDN with a hand-crafted `static/css/nockcc.css` design system. Restructure `base.html` from top-nav to collapsible left sidebar. Restyle each page template using CSS classes instead of Tailwind utilities. No backend changes.

**Tech Stack:** Django templates, CSS custom properties, Alpine.js (existing), Chart.js (existing), Lucide icons (CDN), Google Fonts (DM Sans, JetBrains Mono)

**Design Spec:** `docs/superpowers/specs/2026-04-06-ui-reimagine-design.md`

---

### Task 1: Create CSS Design System

**Files:**
- Create: `static/css/nockcc.css`

This is the foundation everything else depends on. All design tokens, base resets, component classes, layout utilities, and responsive breakpoints in one file.

- [ ] **Step 1: Create the CSS file with design tokens and base resets**

```css
/* static/css/nockcc.css — NockCC Design System */

/* ============================================
   DESIGN TOKENS
   ============================================ */
:root {
  /* Backgrounds */
  --bg-base: #0A0A0F;
  --bg-surface: #111119;
  --bg-surface-hover: #1A1A2E;
  --bg-border: #1E1E2E;
  --bg-border-hover: #2A2A3E;

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
  --font-sans: 'DM Sans', system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, monospace;
  --text-xs: 0.75rem;
  --text-sm: 0.875rem;
  --text-base: 1rem;
  --text-lg: 1.25rem;
  --text-xl: 1.5rem;
  --text-2xl: 2rem;

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

/* ============================================
   BASE RESETS
   ============================================ */
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html {
  font-size: 14px;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

body {
  font-family: var(--font-sans);
  background: var(--bg-base);
  color: var(--text-primary);
  line-height: 1.5;
  min-height: 100vh;
}

a { color: inherit; text-decoration: none; }
button { cursor: pointer; font-family: inherit; }
input, select, textarea { font-family: inherit; }
img { max-width: 100%; display: block; }

/* ============================================
   TYPOGRAPHY
   ============================================ */
.text-xs { font-size: var(--text-xs); }
.text-sm { font-size: var(--text-sm); }
.text-base { font-size: var(--text-base); }
.text-lg { font-size: var(--text-lg); }
.text-xl { font-size: var(--text-xl); }
.text-2xl { font-size: var(--text-2xl); }
.font-mono { font-family: var(--font-mono); }
.font-medium { font-weight: 500; }
.font-semibold { font-weight: 600; }
.font-bold { font-weight: 700; }
.text-primary { color: var(--text-primary); }
.text-secondary { color: var(--text-secondary); }
.text-muted { color: var(--text-muted); }
.text-success { color: var(--color-success); }
.text-warning { color: var(--color-warning); }
.text-danger { color: var(--color-danger); }
.uppercase { text-transform: uppercase; }
.tracking-wide { letter-spacing: 0.05em; }

/* Gradient text */
.ncc-gradient-text {
  background: linear-gradient(135deg, var(--accent-start), var(--accent-end));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* ============================================
   LAYOUT — SIDEBAR
   ============================================ */
.ncc-layout {
  display: flex;
  min-height: 100vh;
}

.ncc-sidebar {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  width: var(--sidebar-width);
  background: var(--bg-surface);
  border-right: 1px solid var(--bg-border);
  display: flex;
  flex-direction: column;
  z-index: 40;
  transition: width var(--transition-normal);
  overflow: hidden;
}

.ncc-sidebar.collapsed {
  width: var(--sidebar-collapsed);
}

.ncc-sidebar-header {
  padding: var(--space-5) var(--space-4);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  border-bottom: 1px solid var(--bg-border);
  flex-shrink: 0;
}

.ncc-sidebar-logo {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
}

.ncc-sidebar-logo-icon {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-lg);
  background: linear-gradient(135deg, var(--accent-start), var(--accent-end));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: white;
  font-weight: 700;
  font-size: var(--text-sm);
}

.ncc-sidebar-logo-text {
  white-space: nowrap;
  overflow: hidden;
}

.ncc-sidebar-logo-text h1 {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.ncc-sidebar-logo-text p {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.collapsed .ncc-sidebar-logo-text,
.collapsed .ncc-sidebar-section-label,
.collapsed .ncc-sidebar-item-label,
.collapsed .ncc-sidebar-collapse-text,
.collapsed .ncc-sidebar-user-info {
  display: none;
}

.ncc-sidebar-collapse-btn {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  background: var(--bg-surface-hover);
  border: none;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: color var(--transition-fast);
}

.ncc-sidebar-collapse-btn:hover {
  color: var(--text-primary);
}

/* Nav sections */
.ncc-sidebar-nav {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-3) var(--space-2);
}

.ncc-sidebar-section-label {
  font-size: 0.625rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--text-muted);
  padding: var(--space-3) var(--space-3) var(--space-1);
  white-space: nowrap;
}

.ncc-sidebar-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  transition: all var(--transition-fast);
  margin-bottom: 1px;
  position: relative;
  white-space: nowrap;
}

.ncc-sidebar-item:hover {
  background: var(--bg-surface-hover);
  color: var(--text-primary);
}

.ncc-sidebar-item.active {
  background: rgba(59, 111, 212, 0.1);
  color: var(--text-primary);
}

.ncc-sidebar-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 6px;
  bottom: 6px;
  width: 2px;
  background: linear-gradient(180deg, var(--accent-start), var(--accent-end));
  border-radius: 1px;
}

.ncc-sidebar-item-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  opacity: 0.7;
}

.ncc-sidebar-item.active .ncc-sidebar-item-icon {
  opacity: 1;
}

.collapsed .ncc-sidebar-item {
  justify-content: center;
  padding: var(--space-2);
}

.collapsed .ncc-sidebar-item.active::before {
  top: 8px;
  bottom: 8px;
}

/* User section */
.ncc-sidebar-user {
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid var(--bg-border);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-shrink: 0;
}

.ncc-sidebar-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--bg-surface-hover);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-secondary);
}

.ncc-sidebar-user-info {
  min-width: 0;
}

.ncc-sidebar-user-info .name {
  font-size: var(--text-xs);
  color: var(--text-primary);
  font-weight: 500;
}

.ncc-sidebar-user-info .role {
  font-size: 0.625rem;
  color: var(--text-muted);
}

.collapsed .ncc-sidebar-user {
  justify-content: center;
  padding: var(--space-3) var(--space-2);
}

/* Main content */
.ncc-main {
  flex: 1;
  margin-left: var(--sidebar-width);
  padding: var(--space-8);
  transition: margin-left var(--transition-normal);
  min-height: 100vh;
}

.ncc-sidebar.collapsed ~ .ncc-main,
.collapsed + .ncc-main {
  margin-left: var(--sidebar-collapsed);
}

/* ============================================
   COMPONENTS — CARDS
   ============================================ */
.ncc-card {
  background: var(--bg-surface);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  box-shadow: var(--shadow-card);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.ncc-card:hover {
  border-color: rgba(59, 111, 212, 0.2);
  box-shadow: var(--shadow-hover);
}

.ncc-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}

.ncc-card-label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
}

.ncc-card-link {
  font-size: var(--text-xs);
  color: var(--text-muted);
  transition: color var(--transition-fast);
}

.ncc-card-link:hover {
  color: var(--text-secondary);
}

/* Hero numbers */
.ncc-hero-row {
  display: flex;
  gap: var(--space-6);
  margin-bottom: var(--space-4);
}

.ncc-hero-number {
  font-size: var(--text-2xl);
  font-weight: 700;
  font-family: var(--font-mono);
  line-height: 1;
  color: var(--text-primary);
}

.ncc-hero-label {
  font-size: 0.6875rem;
  color: var(--text-muted);
  margin-top: var(--space-1);
}

/* Status dots */
.ncc-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}

.ncc-dot-success { background: var(--color-success); }
.ncc-dot-warning { background: var(--color-warning); }
.ncc-dot-danger { background: var(--color-danger); }
.ncc-dot-info { background: var(--color-info); }
.ncc-dot-muted { background: var(--text-muted); }

@keyframes ncc-pulse {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}

.ncc-dot-pulse {
  animation: ncc-pulse 2s ease-in-out infinite;
}

/* ============================================
   COMPONENTS — BADGES
   ============================================ */
.ncc-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: 0.6875rem;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 9999px;
}

.ncc-badge-draft { background: rgba(100, 116, 139, 0.15); color: #94A3B8; }
.ncc-badge-open { background: rgba(59, 111, 212, 0.15); color: #3B6FD4; }
.ncc-badge-review { background: rgba(251, 191, 36, 0.15); color: #FBBF24; }
.ncc-badge-approved { background: rgba(52, 211, 153, 0.15); color: #34D399; }
.ncc-badge-merged { background: rgba(124, 92, 252, 0.15); color: #7C5CFC; }
.ncc-badge-closed { background: rgba(248, 113, 113, 0.15); color: #F87171; }

/* ============================================
   COMPONENTS — BUTTONS
   ============================================ */
.ncc-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  border: none;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.ncc-btn-primary {
  background: linear-gradient(135deg, var(--accent-start), var(--accent-end));
  color: white;
}

.ncc-btn-primary:hover {
  filter: brightness(1.1);
}

.ncc-btn-ghost {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--bg-border);
}

.ncc-btn-ghost:hover {
  background: var(--bg-surface-hover);
  color: var(--text-primary);
}

.ncc-btn-sm {
  padding: var(--space-1) var(--space-3);
  font-size: var(--text-xs);
}

/* ============================================
   COMPONENTS — FORMS
   ============================================ */
.ncc-input {
  width: 100%;
  background: var(--bg-base);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  color: var(--text-primary);
  transition: border-color var(--transition-fast);
}

.ncc-input:focus {
  outline: none;
  border-color: var(--accent-start);
}

.ncc-input::placeholder {
  color: var(--text-muted);
}

.ncc-select {
  background: var(--bg-base);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  color: var(--text-primary);
  transition: border-color var(--transition-fast);
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1L5 5L9 1' stroke='%2364748B' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
  padding-right: 32px;
}

.ncc-select:focus {
  outline: none;
  border-color: var(--accent-start);
}

/* ============================================
   COMPONENTS — TABLES
   ============================================ */
.ncc-table {
  width: 100%;
  border-collapse: collapse;
}

.ncc-table th {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  text-align: left;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--bg-border);
}

.ncc-table td {
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  border-bottom: 1px solid var(--bg-border);
}

.ncc-table tr:hover td {
  background: var(--bg-surface-hover);
}

.ncc-table tr:last-child td {
  border-bottom: none;
}

/* ============================================
   COMPONENTS — SPARKLINES (SVG)
   ============================================ */
.ncc-sparkline {
  width: 100%;
  height: 40px;
  display: block;
}

/* ============================================
   COMPONENTS — PROGRESS BAR
   ============================================ */
.ncc-progress {
  width: 100%;
  height: 4px;
  background: var(--bg-border);
  border-radius: 2px;
  overflow: hidden;
}

.ncc-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent-start), var(--accent-end));
  border-radius: 2px;
  transition: width var(--transition-normal);
}

/* ============================================
   COMPONENTS — ALERTS / MESSAGES
   ============================================ */
.ncc-alert {
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  border: 1px solid;
  margin-bottom: var(--space-3);
}

.ncc-alert-error {
  background: rgba(248, 113, 113, 0.08);
  border-color: rgba(248, 113, 113, 0.2);
  color: #FCA5A5;
}

.ncc-alert-success {
  background: rgba(52, 211, 153, 0.08);
  border-color: rgba(52, 211, 153, 0.2);
  color: #6EE7B7;
}

.ncc-alert-warning {
  background: rgba(251, 191, 36, 0.08);
  border-color: rgba(251, 191, 36, 0.2);
  color: #FDE68A;
}

.ncc-alert-info {
  background: rgba(6, 182, 212, 0.08);
  border-color: rgba(6, 182, 212, 0.2);
  color: #67E8F9;
}

/* ============================================
   COMPONENTS — LIVE BADGE
   ============================================ */
.ncc-live-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: rgba(52, 211, 153, 0.1);
  color: var(--color-success);
  font-size: 0.6875rem;
  font-weight: 500;
  padding: 2px 10px;
  border-radius: 9999px;
}

/* ============================================
   GRID — NERVE CENTER
   ============================================ */
.ncc-nerve-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-4);
}

/* ============================================
   PAGE HEADER
   ============================================ */
.ncc-page-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: var(--space-8);
}

.ncc-page-title {
  font-size: var(--text-2xl);
  font-weight: 700;
}

/* ============================================
   COMPACT ROW (for lists inside cards)
   ============================================ */
.ncc-compact-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  border-bottom: 1px solid rgba(30, 30, 46, 0.5);
}

.ncc-compact-row:last-child {
  border-bottom: none;
}

/* ============================================
   ANIMATIONS
   ============================================ */
@keyframes ncc-fade-in {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

.ncc-stagger { animation: ncc-fade-in 0.3s ease both; }
.ncc-stagger:nth-child(1) { animation-delay: 0s; }
.ncc-stagger:nth-child(2) { animation-delay: 0.05s; }
.ncc-stagger:nth-child(3) { animation-delay: 0.05s; }
.ncc-stagger:nth-child(4) { animation-delay: 0.1s; }
.ncc-stagger:nth-child(5) { animation-delay: 0.15s; }
.ncc-stagger:nth-child(6) { animation-delay: 0.2s; }

@keyframes ncc-glow-pulse {
  0%, 100% { box-shadow: 0 0 8px rgba(52, 211, 153, 0.2); }
  50% { box-shadow: 0 0 16px rgba(52, 211, 153, 0.4); }
}

.ncc-glow-active {
  animation: ncc-glow-pulse 2s ease-in-out infinite;
}

/* Login animated gradient border */
@keyframes ncc-border-rotate {
  0% { --angle: 0deg; }
  100% { --angle: 360deg; }
}

/* ============================================
   RESPONSIVE
   ============================================ */

/* Tablet */
@media (max-width: 1200px) {
  .ncc-nerve-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* Mobile */
@media (max-width: 767px) {
  .ncc-sidebar {
    transform: translateX(-100%);
    transition: transform var(--transition-normal);
    z-index: 50;
  }

  .ncc-sidebar.mobile-open {
    transform: translateX(0);
  }

  .ncc-sidebar-backdrop {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 45;
  }

  .ncc-sidebar.mobile-open ~ .ncc-sidebar-backdrop {
    display: block;
  }

  .ncc-main {
    margin-left: 0;
    padding: var(--space-4);
    padding-bottom: 80px;
  }

  .ncc-nerve-grid {
    grid-template-columns: 1fr;
  }

  /* Mobile top bar */
  .ncc-mobile-topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--bg-border);
    margin: calc(-1 * var(--space-4));
    margin-bottom: var(--space-4);
  }

  /* Bottom tab bar */
  .ncc-bottom-tabs {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    height: 56px;
    background: var(--bg-surface);
    border-top: 1px solid var(--bg-border);
    display: flex;
    align-items: stretch;
    z-index: 40;
    padding-bottom: env(safe-area-inset-bottom, 0);
  }

  .ncc-bottom-tab {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    color: var(--text-muted);
    font-size: 0.625rem;
    font-weight: 500;
    min-height: 48px;
  }

  .ncc-bottom-tab.active {
    color: var(--accent-start);
  }

  .ncc-bottom-tab svg {
    width: 22px;
    height: 22px;
  }

  /* Tap targets */
  a, button, select, [role="button"] {
    min-height: 44px;
  }

  .ncc-badge, .ncc-dot, .ncc-compact-row a {
    min-height: auto;
  }

  .ncc-card {
    padding: var(--space-4);
  }

  .ncc-hero-number {
    font-size: var(--text-xl);
  }

  .ncc-page-header {
    flex-direction: column;
    gap: var(--space-2);
    margin-bottom: var(--space-6);
  }

  .ncc-page-title {
    font-size: var(--text-xl);
  }
}

/* Desktop: hide mobile-only elements */
@media (min-width: 768px) {
  .ncc-mobile-topbar { display: none; }
  .ncc-bottom-tabs { display: none; }
  .ncc-sidebar-backdrop { display: none !important; }
}

/* ============================================
   SCROLLBAR
   ============================================ */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--bg-border);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--bg-border-hover);
}
```

- [ ] **Step 2: Verify the file is syntactically valid**

Run: `python -c "open('static/css/nockcc.css').read(); print('CSS file created, {} bytes'.format(__import__('os').path.getsize('static/css/nockcc.css')))"`

Expected: Shows byte count, no errors.

- [ ] **Step 3: Commit**

```bash
git add static/css/nockcc.css
git commit -m "style: add design tokens and CSS design system"
```

---

### Task 2: Rewrite base.html — Sidebar Navigation

**Files:**
- Modify: `templates/base.html` (full rewrite)

Replace the current top-nav base template with the new sidebar layout. This is the most impactful change — every page inherits from this.

- [ ] **Step 1: Rewrite base.html**

Replace the entire contents of `templates/base.html` with the new sidebar layout. Key changes:
- Remove Tailwind CDN `<script>` and its config block
- Remove the inline `<style>` design system (now in nockcc.css)
- Add `<link>` to `static/css/nockcc.css`
- Add Lucide icons CDN: `<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>`
- Replace `<nav>` top toolbar with `<aside class="ncc-sidebar">` containing:
  - Sidebar header with logo, "NockCC" text, collapse toggle button
  - Grouped nav sections (Operations, Intelligence, Business, System) with Lucide icons
  - Active state detection using `{% if request.path == '/' %}active{% endif %}` pattern
  - User section at bottom with initials avatar
- Alpine.js `x-data` on `<body>` for sidebar state: `{ sidebarCollapsed: localStorage.getItem('nockcc-sidebar-collapsed') === 'true', mobileSidebarOpen: false }`
- Main content wrapped in `<main class="ncc-main">`
- Mobile: hamburger button in `ncc-mobile-topbar`, sidebar backdrop, bottom tab bar
- Keep: Google Fonts CDN, Alpine.js CDN, Chart.js CDN, PWA meta tags, `{% block %}` structure, messages section, service worker registration

The full template should be:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{% block title %}NockCC — Command Center{% endblock %}</title>

    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">

    <!-- Design System -->
    <link rel="stylesheet" href="/static/css/nockcc.css">

    <!-- Alpine.js -->
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.9/dist/cdn.min.js"></script>

    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>

    <!-- Lucide Icons -->
    <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>

    <!-- PWA -->
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#0A0A0F">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">

    {% block extra_head %}{% endblock %}
</head>
<body x-data="{
    sidebarCollapsed: localStorage.getItem('nockcc-sidebar-collapsed') === 'true',
    mobileSidebarOpen: false,
    toggleSidebar() {
        this.sidebarCollapsed = !this.sidebarCollapsed;
        localStorage.setItem('nockcc-sidebar-collapsed', this.sidebarCollapsed);
    }
}">

<div class="ncc-layout">
    {% if user.is_authenticated %}
    <!-- Sidebar -->
    <aside class="ncc-sidebar"
           :class="{ 'collapsed': sidebarCollapsed, 'mobile-open': mobileSidebarOpen }">

        <!-- Header -->
        <div class="ncc-sidebar-header">
            <a href="/" class="ncc-sidebar-logo">
                <div class="ncc-sidebar-logo-icon">N</div>
                <div class="ncc-sidebar-logo-text">
                    <h1>NockCC</h1>
                    <p>Command Center</p>
                </div>
            </a>
            <button class="ncc-sidebar-collapse-btn" @click="toggleSidebar()" title="Toggle sidebar">
                <i data-lucide="panel-left-close" style="width:16px;height:16px;" x-show="!sidebarCollapsed"></i>
                <i data-lucide="panel-left-open" style="width:16px;height:16px;" x-show="sidebarCollapsed"></i>
            </button>
        </div>

        <!-- Navigation -->
        <nav class="ncc-sidebar-nav">
            <!-- Operations -->
            <div class="ncc-sidebar-section-label">Operations</div>
            <a href="/" class="ncc-sidebar-item {% if request.path == '/' %}active{% endif %}" title="Nerve Center">
                <i data-lucide="radar" class="ncc-sidebar-item-icon"></i>
                <span class="ncc-sidebar-item-label">Nerve Center</span>
            </a>
            <a href="/pipeline/" class="ncc-sidebar-item {% if '/pipeline/' in request.path %}active{% endif %}" title="Pipeline">
                <i data-lucide="git-pull-request" class="ncc-sidebar-item-icon"></i>
                <span class="ncc-sidebar-item-label">Pipeline</span>
            </a>
            <a href="/sessions/" class="ncc-sidebar-item {% if '/sessions/' in request.path %}active{% endif %}" title="Sessions">
                <i data-lucide="terminal" class="ncc-sidebar-item-icon"></i>
                <span class="ncc-sidebar-item-label">Sessions</span>
            </a>

            <!-- Intelligence -->
            <div class="ncc-sidebar-section-label">Intelligence</div>
            <a href="/brain/" class="ncc-sidebar-item {% if '/brain/' in request.path %}active{% endif %}" title="Brain">
                <i data-lucide="brain" class="ncc-sidebar-item-icon"></i>
                <span class="ncc-sidebar-item-label">Brain</span>
            </a>
            <a href="/intelligence/advisor/" class="ncc-sidebar-item {% if '/intelligence/advisor/' in request.path %}active{% endif %}" title="AI Advisor">
                <i data-lucide="sparkles" class="ncc-sidebar-item-icon"></i>
                <span class="ncc-sidebar-item-label">AI Advisor</span>
            </a>
            <a href="/intelligence/alerts/" class="ncc-sidebar-item {% if '/intelligence/alerts/' in request.path %}active{% endif %}" title="Alerts">
                <i data-lucide="bell-ring" class="ncc-sidebar-item-icon"></i>
                <span class="ncc-sidebar-item-label">Alerts</span>
            </a>
            <a href="/intelligence/executive/" class="ncc-sidebar-item {% if '/intelligence/executive/' in request.path %}active{% endif %}" title="Executive">
                <i data-lucide="bar-chart-3" class="ncc-sidebar-item-icon"></i>
                <span class="ncc-sidebar-item-label">Executive</span>
            </a>

            <!-- Business -->
            <div class="ncc-sidebar-section-label">Business</div>
            <a href="/spend/" class="ncc-sidebar-item {% if '/spend/' in request.path %}active{% endif %}" title="Spend">
                <i data-lucide="wallet" class="ncc-sidebar-item-icon"></i>
                <span class="ncc-sidebar-item-label">Spend</span>
            </a>
            <a href="/crm/" class="ncc-sidebar-item {% if '/crm/' in request.path %}active{% endif %}" title="CRM">
                <i data-lucide="users" class="ncc-sidebar-item-icon"></i>
                <span class="ncc-sidebar-item-label">CRM</span>
            </a>
            <a href="/tasks/" class="ncc-sidebar-item {% if '/tasks/' in request.path or '/handoffs/' in request.path %}active{% endif %}" title="Tasks">
                <i data-lucide="check-square" class="ncc-sidebar-item-icon"></i>
                <span class="ncc-sidebar-item-label">Tasks</span>
            </a>
            <a href="/vault/" class="ncc-sidebar-item {% if '/vault/' in request.path %}active{% endif %}" title="Vault">
                <i data-lucide="archive" class="ncc-sidebar-item-icon"></i>
                <span class="ncc-sidebar-item-label">Vault</span>
            </a>

            <!-- System -->
            <div class="ncc-sidebar-section-label">System</div>
            <a href="/teams/" class="ncc-sidebar-item {% if request.path == '/teams/' %}active{% endif %}" title="Teams">
                <i data-lucide="bot" class="ncc-sidebar-item-icon"></i>
                <span class="ncc-sidebar-item-label">Teams</span>
            </a>
            <a href="/prompts/" class="ncc-sidebar-item {% if '/prompts/' in request.path %}active{% endif %}" title="Prompts">
                <i data-lucide="message-square" class="ncc-sidebar-item-icon"></i>
                <span class="ncc-sidebar-item-label">Prompts</span>
            </a>
            <a href="/remote/chat/" class="ncc-sidebar-item {% if '/remote/' in request.path %}active{% endif %}" title="Chat">
                <i data-lucide="message-circle" class="ncc-sidebar-item-icon"></i>
                <span class="ncc-sidebar-item-label">Chat</span>
            </a>
            <a href="/notifications/" class="ncc-sidebar-item {% if '/notifications/' in request.path %}active{% endif %}" title="Notifications">
                <i data-lucide="bell" class="ncc-sidebar-item-icon"></i>
                <span class="ncc-sidebar-item-label">Notifications</span>
            </a>
            <a href="/context/" class="ncc-sidebar-item {% if '/context/' in request.path %}active{% endif %}" title="Context">
                <i data-lucide="file-text" class="ncc-sidebar-item-icon"></i>
                <span class="ncc-sidebar-item-label">Context</span>
            </a>
        </nav>

        <!-- User -->
        <div class="ncc-sidebar-user">
            <div class="ncc-sidebar-avatar">
                {{ user.username|make_list|first|upper }}
            </div>
            <div class="ncc-sidebar-user-info">
                <div class="name">{{ user.username }}</div>
                <a href="/accounts/logout/" class="role" style="cursor:pointer;">Sign out</a>
            </div>
        </div>
    </aside>

    <!-- Mobile sidebar backdrop -->
    <div class="ncc-sidebar-backdrop"
         x-show="mobileSidebarOpen"
         @click="mobileSidebarOpen = false"></div>
    {% endif %}

    <!-- Main Content -->
    <main class="ncc-main">
        {% if user.is_authenticated %}
        <!-- Mobile top bar -->
        <div class="ncc-mobile-topbar">
            <button @click="mobileSidebarOpen = true" style="background:none;border:none;color:var(--text-secondary);min-height:auto;">
                <i data-lucide="menu" style="width:22px;height:22px;"></i>
            </button>
            <span class="ncc-gradient-text font-semibold">NockCC</span>
            <div style="width:22px;"></div>
        </div>
        {% endif %}

        <!-- Messages -->
        {% if messages %}
        <div style="margin-bottom: var(--space-4);">
            {% for message in messages %}
            <div class="ncc-alert ncc-alert-{% if message.tags == 'error' %}error{% elif message.tags == 'success' %}success{% elif message.tags == 'warning' %}warning{% else %}info{% endif %}">
                {{ message }}
            </div>
            {% endfor %}
        </div>
        {% endif %}

        {% block content %}{% endblock %}
    </main>
</div>

{% if user.is_authenticated %}
<!-- Mobile Bottom Tabs -->
<nav class="ncc-bottom-tabs">
    <a href="/" class="ncc-bottom-tab {% if request.path == '/' %}active{% endif %}">
        <i data-lucide="radar" style="width:22px;height:22px;"></i>
        <span>Home</span>
    </a>
    <a href="/pipeline/" class="ncc-bottom-tab {% if '/pipeline/' in request.path %}active{% endif %}">
        <i data-lucide="git-pull-request" style="width:22px;height:22px;"></i>
        <span>Pipeline</span>
    </a>
    <a href="/brain/" class="ncc-bottom-tab {% if '/brain/' in request.path %}active{% endif %}">
        <i data-lucide="brain" style="width:22px;height:22px;"></i>
        <span>Brain</span>
    </a>
    <a href="/sessions/" class="ncc-bottom-tab {% if '/sessions/' in request.path %}active{% endif %}">
        <i data-lucide="terminal" style="width:22px;height:22px;"></i>
        <span>Sessions</span>
    </a>
    <a href="/remote/chat/" class="ncc-bottom-tab {% if '/remote/' in request.path %}active{% endif %}">
        <i data-lucide="message-circle" style="width:22px;height:22px;"></i>
        <span>Chat</span>
    </a>
</nav>
{% endif %}

<!-- Initialize Lucide Icons -->
<script>
    document.addEventListener('DOMContentLoaded', function() {
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    });
</script>

<!-- Service Worker -->
<script>
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/sw.js').catch(() => {});
}
</script>

{% block extra_scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 2: Verify template renders without syntax errors**

Run: `cd /Users/kevin/Dev/nock-command-center && python -c "from django.template.loader import get_template; import django; import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.dev'); django.setup(); t = get_template('base.html'); print('Template compiles OK')"`

Expected: "Template compiles OK"

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "style: rewrite base.html with sidebar navigation layout"
```

---

### Task 3: Redesign Nerve Center Dashboard

**Files:**
- Modify: `dashboard/templates/dashboard/index.html`

Replace all Tailwind utility classes with nockcc.css classes. Restructure the 6-panel grid to use `ncc-nerve-grid`, `ncc-card`, `ncc-hero-number`, `ncc-dot`, and `ncc-compact-row` components. Keep all Alpine.js `x-data="nerveCenter()"` logic intact — only change the HTML/CSS wrapper around the data bindings.

- [ ] **Step 1: Read current dashboard template fully to understand all data bindings**

Run: Read the full `dashboard/templates/dashboard/index.html` — map every `x-text`, `x-show`, `@click`, `x-for`, template expression, and API endpoint used. The Alpine.js `nerveCenter()` function and all its methods must be preserved exactly.

- [ ] **Step 2: Rewrite the template**

Replace the `{% block extra_head %}` styles with page-specific overrides only (the design system handles base styles now). Replace the `{% block content %}` with:

- Page header: `<div class="ncc-page-header"><h1 class="ncc-page-title ncc-gradient-text">Nerve Center</h1><span class="text-muted text-sm" x-text="...">date</span></div>`
- Grid: `<div class="ncc-nerve-grid">` containing 6 `ncc-card ncc-stagger` panels
- Each panel follows the card template: header row (dot + label + icon + "View All" link), hero numbers row, sparkline/detail section, compact rows

**Critical:** Every `x-text`, `x-show`, `@click`, `x-for`, `template`, and `fetch()` call from the original must appear in the rewritten template in the same logical position. The Alpine.js component function at the bottom of the template must remain untouched.

- [ ] **Step 3: Verify the page loads**

Run: `cd /Users/kevin/Dev/nock-command-center && python manage.py check --deploy 2>&1 | head -20`

Expected: No template errors.

- [ ] **Step 4: Commit**

```bash
git add dashboard/templates/dashboard/index.html
git commit -m "style: redesign Nerve Center homepage with cockpit cards"
```

---

### Task 4: Redesign Pipeline Page

**Files:**
- Modify: `pipeline/templates/pipeline/list.html`
- Modify: `pipeline/templates/pipeline/detail.html`

- [ ] **Step 1: Read both pipeline templates fully**

Read `pipeline/templates/pipeline/list.html` and `pipeline/templates/pipeline/detail.html` completely. Map all Django template tags, form handling, filter logic, and any Alpine.js components.

- [ ] **Step 2: Rewrite pipeline list template**

Replace Tailwind utilities with nockcc.css classes:
- Page header with `ncc-page-header`
- Filter bar: replace Tailwind-styled selects with `ncc-select` class
- PR table: use `ncc-table` with columns — Status (badge), Repo (mono), Branch, Title, Reviewers (emoji icons), Time Open, CI
- Status badges: `ncc-badge-draft`, `ncc-badge-open`, `ncc-badge-review`, `ncc-badge-approved`, `ncc-badge-merged`, `ncc-badge-closed`
- Row hover via `ncc-table tr:hover`

Keep all Django template logic (`{% for pr in prs %}`, `{% if %}` blocks, filter form `method="get"`) exactly as-is.

- [ ] **Step 3: Rewrite pipeline detail template**

Same approach — replace Tailwind with nockcc.css classes. Keep all Django context variables and template logic.

- [ ] **Step 4: Commit**

```bash
git add pipeline/templates/pipeline/list.html pipeline/templates/pipeline/detail.html
git commit -m "style: redesign Pipeline page with table and status badges"
```

---

### Task 5: Redesign Brain Memory Browser

**Files:**
- Modify: `brain/templates/brain/index.html`

- [ ] **Step 1: Read the full brain template**

Read `brain/templates/brain/index.html` completely. Map the `brainBrowser()` Alpine.js component, all data bindings, API endpoints, category filtering, search, inline editing, consolidation, and brief generation.

- [ ] **Step 2: Rewrite the template**

New layout: two-column with CSS Grid (`grid-template-columns: 240px 1fr` on desktop, single column on mobile).

Left panel:
- Category list using existing category data. Each category: colored dot + name + count badge. Use existing `cat-*` CSS classes (keep those, they're page-specific).
- Active category highlighted with accent background.

Main area:
- Search bar: `<input class="ncc-input" placeholder="Search memory entries...">`
- Memory entries: `ncc-card` for each entry with key (bold), value preview (truncated), tags (pills using existing `cat-*` classes), confidence bar, last updated.
- Inline editing: keep existing Alpine.js `x-show` toggle pattern.

Consolidation section: collapsible at top. Keep existing `@click` handlers for consolidate and generate brief.

**Critical:** The `brainBrowser()` function and all its methods, fetch calls, and state variables must be preserved exactly.

- [ ] **Step 3: Commit**

```bash
git add brain/templates/brain/index.html
git commit -m "style: redesign Brain memory browser with two-column layout"
```

---

### Task 6: Redesign Sessions Page

**Files:**
- Modify: `sessions/templates/sessions/list.html`

- [ ] **Step 1: Read the full sessions template**

Read `sessions/templates/sessions/list.html` completely.

- [ ] **Step 2: Rewrite the template**

- Page header: `ncc-page-header` with title and filter controls
- Active sessions section: horizontal flex row of `ncc-card` items, each with `ncc-glow-active` animation. Show project, machine, duration timer, status dot.
- Recent sessions: `ncc-table` with columns — Project, Machine, Start Time, Duration, Status badge.
- Filters: replace Tailwind selects with `ncc-select`, button with `ncc-btn`.

Keep all Django template logic and Alpine.js exactly as-is.

- [ ] **Step 3: Commit**

```bash
git add sessions/templates/sessions/list.html
git commit -m "style: redesign Sessions page with active cards and table"
```

---

### Task 7: Redesign Intelligence Pages

**Files:**
- Modify: `intelligence/templates/intelligence/executive.html`
- Modify: `intelligence/templates/intelligence/advisor.html`
- Modify: `intelligence/templates/intelligence/alerts.html`

- [ ] **Step 1: Read all three intelligence templates fully**

Read each template completely. Map all Alpine.js components, API calls, and data bindings.

- [ ] **Step 2: Rewrite executive dashboard**

Replace Tailwind with nockcc.css. KPI cards across top using `ncc-card`, chart sections below.

- [ ] **Step 3: Rewrite AI advisor chat interface**

Replace Tailwind with nockcc.css. Chat messages styled with:
- AI messages: left-aligned, `border-left: 2px solid var(--accent-start)`, surface background
- User messages: right-aligned, subtle accent background
- Input bar: fixed to bottom of chat container, `ncc-input` + `ncc-btn-primary`
- Keep `marked.js` import and all markdown rendering logic.
- Keep `advisorChat()` Alpine.js component exactly as-is.

- [ ] **Step 4: Rewrite alerts page**

Feed layout with `ncc-card` per alert. Left colored bar for severity (red/yellow/blue). Dismiss button. Keep existing Alpine.js.

- [ ] **Step 5: Commit**

```bash
git add intelligence/templates/intelligence/executive.html intelligence/templates/intelligence/advisor.html intelligence/templates/intelligence/alerts.html
git commit -m "style: redesign Intelligence pages — executive, advisor, alerts"
```

---

### Task 8: Redesign Login Page

**Files:**
- Modify: `templates/accounts/login.html`

- [ ] **Step 1: Rewrite the login page**

This is a standalone page (no `{% extends "base.html" %}`). Replace the entire file:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Sign In — NockCC</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/nockcc.css">
    <style>
        .login-page {
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: var(--bg-base);
            background-image: radial-gradient(ellipse at center, rgba(59, 111, 212, 0.03) 0%, transparent 70%);
        }

        .login-card {
            width: 100%;
            max-width: 380px;
            padding: var(--space-8);
            background: var(--bg-surface);
            border: 1px solid var(--bg-border);
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow-card);
            position: relative;
        }

        /* Animated gradient border */
        .login-card::before {
            content: '';
            position: absolute;
            inset: -1px;
            border-radius: calc(var(--radius-lg) + 1px);
            background: conic-gradient(from var(--angle, 0deg), transparent 40%, var(--accent-start) 50%, var(--accent-end) 60%, transparent 70%);
            z-index: -1;
            animation: login-border-spin 4s linear infinite;
            opacity: 0.4;
        }

        @keyframes login-border-spin {
            to { --angle: 360deg; }
        }

        @property --angle {
            syntax: '<angle>';
            initial-value: 0deg;
            inherits: false;
        }

        .login-logo {
            width: 48px;
            height: 48px;
            border-radius: var(--radius-lg);
            background: linear-gradient(135deg, var(--accent-start), var(--accent-end));
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto var(--space-4);
            font-size: var(--text-xl);
            font-weight: 700;
            color: white;
        }

        .login-title {
            text-align: center;
            margin-bottom: var(--space-8);
        }

        .login-title h1 {
            font-size: var(--text-lg);
            font-weight: 700;
        }

        .login-title p {
            font-size: var(--text-xs);
            color: var(--text-muted);
            margin-top: var(--space-1);
        }

        .login-field {
            margin-bottom: var(--space-4);
        }

        .login-field label {
            display: block;
            font-size: var(--text-sm);
            font-weight: 500;
            color: var(--text-secondary);
            margin-bottom: var(--space-1);
        }

        .login-submit {
            width: 100%;
            padding: var(--space-3) var(--space-4);
            background: linear-gradient(135deg, var(--accent-start), var(--accent-end));
            color: white;
            font-weight: 600;
            font-size: var(--text-sm);
            border: none;
            border-radius: var(--radius-md);
            cursor: pointer;
            transition: filter var(--transition-fast);
            margin-top: var(--space-2);
        }

        .login-submit:hover {
            filter: brightness(1.1);
        }

        .login-footer {
            text-align: center;
            font-size: var(--text-xs);
            color: var(--text-muted);
            margin-top: var(--space-12);
        }
    </style>
</head>
<body>
    <div class="login-page">
        <div>
            <div class="login-card">
                <div class="login-logo">N</div>
                <div class="login-title">
                    <h1 class="ncc-gradient-text">Nock Command Center</h1>
                    <p>Sign in to continue</p>
                </div>

                {% if form.errors %}
                <div class="ncc-alert ncc-alert-error" style="margin-bottom: var(--space-4);">
                    Invalid username or password.
                </div>
                {% endif %}

                <form method="post">
                    {% csrf_token %}
                    <div class="login-field">
                        <label for="id_username">Username</label>
                        <input type="text" name="username" id="id_username" autofocus autocomplete="username"
                               class="ncc-input"
                               value="{{ form.username.value|default:'' }}">
                    </div>
                    <div class="login-field">
                        <label for="id_password">Password</label>
                        <input type="password" name="password" id="id_password" autocomplete="current-password"
                               class="ncc-input">
                    </div>
                    <button type="submit" class="login-submit">Sign In</button>
                </form>
            </div>
            <p class="login-footer">Nock Technologies</p>
        </div>
    </div>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add templates/accounts/login.html
git commit -m "style: redesign login page with gradient border and brand styling"
```

---

### Task 9: Restyle Error Pages

**Files:**
- Modify: `templates/404.html`
- Modify: `templates/500.html`

- [ ] **Step 1: Read current error pages**

Read both `templates/404.html` and `templates/500.html`.

- [ ] **Step 2: Restyle both pages**

Match the login page style — centered card on dark background with branded typography. Use `ncc-gradient-text` for the error code, muted text for description, `ncc-btn-primary` for "Go Home" link.

These are standalone pages (don't extend base.html since they may render when the app is broken). Include the nockcc.css link and DM Sans font import.

- [ ] **Step 3: Commit**

```bash
git add templates/404.html templates/500.html
git commit -m "style: restyle 404 and 500 error pages"
```

---

### Task 10: Add .superpowers to .gitignore and Final Verification

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add .superpowers to gitignore**

Add `.superpowers/` to the `.gitignore` file if not already present.

- [ ] **Step 2: Run full verification**

Run: `cd /Users/kevin/Dev/nock-command-center && python manage.py check && echo "Django check passed"`

Run: `cd /Users/kevin/Dev/nock-command-center && python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.dev')
django.setup()
from django.template.loader import get_template
templates = ['base.html', 'accounts/login.html', '404.html', '500.html', 'dashboard/index.html', 'pipeline/list.html', 'pipeline/detail.html', 'brain/index.html', 'sessions/list.html', 'intelligence/executive.html', 'intelligence/advisor.html', 'intelligence/alerts.html']
for t in templates:
    try:
        get_template(t)
        print(f'OK: {t}')
    except Exception as e:
        print(f'FAIL: {t} — {e}')
"`

Expected: All templates compile OK.

- [ ] **Step 3: Run ruff check**

Run: `cd /Users/kevin/Dev/nock-command-center && ruff check . --fix`

Expected: No Python errors (we didn't change any Python files, but verify nothing broke).

- [ ] **Step 4: Commit and push**

```bash
git add .gitignore
git commit -m "chore: add .superpowers to gitignore"
```

---

### Task 0 (Do First): Create Feature Branch

- [ ] **Step 1: Create and switch to feature branch**

```bash
git checkout -b feature/ui-reimagine
```

All subsequent tasks (1-10) commit to this branch.

---

### Task 11: Push and Open PR

- [ ] **Step 1: Push and open PR**

```bash
git push -u origin feature/ui-reimagine
```

Open PR with title: "style: UI reimagine — sidebar nav, design system, page restyling" and body summarizing all changes.

- [ ] **Step 3: Verify CI passes**

Check that any CI checks pass on the PR.
