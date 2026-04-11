# NockCC UI Reimagine Phase 2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reskin all remaining NockCC pages to use the `ncc-*` design system established in Phase 1, and integrate the actual Nock logo.

**Architecture:** Pure frontend reskin — replace Tailwind utility classes with `ncc-*` component classes from `nockcc.css`. Extend CSS with new components (tabs, kanban, toggles, staleness indicators, chat). No backend changes.

**Tech Stack:** Django templates, CSS custom properties, Alpine.js (preserved), Chart.js (restyled), Lucide icons

---

### Task 0: Create feature branch

**Files:**
- None (git operation only)

- [ ] **Step 1: Create and switch to feature branch**

```bash
git checkout -b feature/ui-reimagine-phase2
```

- [ ] **Step 2: Verify branch**

```bash
git branch --show-current
```

Expected: `feature/ui-reimagine-phase2`

---

### Task 1: Add new CSS components to nockcc.css

**Files:**
- Modify: `static/css/nockcc.css` (append after section 11, before section 12)

- [ ] **Step 1: Append new component CSS**

Add the following sections to `nockcc.css` before the `/* 12. Responsive Breakpoints */` section:

```css
/* ==========================================================================
   11b. Tab Component
   ========================================================================== */

.ncc-tabs {
  display: flex;
  border-bottom: 1px solid var(--bg-border);
  gap: 0;
  margin-bottom: var(--space-5);
}

.ncc-tab {
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-muted);
  border-bottom: 2px solid transparent;
  transition: color var(--transition-fast), border-color var(--transition-fast);
  cursor: pointer;
  white-space: nowrap;
  background: none;
  min-height: 44px;
  display: flex;
  align-items: center;
}

.ncc-tab:hover {
  color: var(--text-secondary);
}

.ncc-tab.active {
  color: var(--text-primary);
  border-bottom-color: var(--accent-start);
}


/* ==========================================================================
   11c. KPI Row
   ========================================================================== */

.ncc-kpi-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

@media (max-width: 1200px) {
  .ncc-kpi-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 767px) {
  .ncc-kpi-row {
    grid-template-columns: repeat(2, 1fr);
    gap: var(--space-3);
  }
}

.ncc-kpi-card {
  background-color: var(--bg-surface);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  transition: border-color var(--transition-base);
}

.ncc-kpi-card:hover {
  border-color: var(--bg-border-hover);
}

.ncc-kpi-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  margin-bottom: var(--space-1);
}

.ncc-kpi-value {
  font-size: var(--text-2xl);
  font-weight: 700;
  font-family: var(--font-mono);
  line-height: 1.2;
  color: var(--text-primary);
}

.ncc-kpi-sub {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin-top: var(--space-1);
}


/* ==========================================================================
   11d. Kanban Board
   ========================================================================== */

.ncc-kanban-board {
  display: flex;
  gap: var(--space-4);
  overflow-x: auto;
  padding-bottom: var(--space-4);
  -webkit-overflow-scrolling: touch;
}

.ncc-kanban-board::-webkit-scrollbar {
  height: 4px;
}

.ncc-kanban-col {
  flex-shrink: 0;
  width: 240px;
  min-height: 200px;
}

.ncc-kanban-col-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
  padding-bottom: var(--space-2);
  border-bottom: 2px solid var(--bg-border);
}

.ncc-kanban-col-title {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}

.ncc-kanban-col-count {
  font-size: 10px;
  color: var(--text-muted);
  background-color: var(--bg-surface-hover);
  padding: 1px 6px;
  border-radius: var(--radius-full);
}

.ncc-kanban-card {
  background-color: var(--bg-surface);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  margin-bottom: var(--space-2);
  transition: border-color var(--transition-fast), transform var(--transition-fast);
  cursor: pointer;
}

.ncc-kanban-card:hover {
  border-color: var(--bg-border-hover);
  transform: translateY(-1px);
}

.ncc-kanban-empty {
  border: 1px dashed var(--bg-border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  text-align: center;
  color: var(--text-muted);
  font-size: var(--text-xs);
}


/* ==========================================================================
   11e. Toggle Switch
   ========================================================================== */

.ncc-toggle {
  position: relative;
  display: inline-flex;
  align-items: center;
  cursor: pointer;
}

.ncc-toggle input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.ncc-toggle-track {
  width: 36px;
  height: 20px;
  background-color: var(--bg-border);
  border-radius: var(--radius-full);
  transition: background-color var(--transition-fast);
  position: relative;
}

.ncc-toggle input:checked + .ncc-toggle-track {
  background: linear-gradient(135deg, var(--accent-start), var(--accent-end));
}

.ncc-toggle-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  background-color: #fff;
  border-radius: var(--radius-full);
  transition: transform var(--transition-fast);
}

.ncc-toggle input:checked ~ .ncc-toggle-track .ncc-toggle-thumb,
.ncc-toggle input:checked + .ncc-toggle-track .ncc-toggle-thumb {
  transform: translateX(16px);
}


/* ==========================================================================
   11f. Staleness Indicators
   ========================================================================== */

.ncc-staleness-fresh {
  border-left: 3px solid var(--color-success);
}

.ncc-staleness-stale {
  border-left: 3px solid var(--color-warning);
}

.ncc-staleness-critical {
  border-left: 3px solid var(--color-danger);
}


/* ==========================================================================
   11g. Chat Components
   ========================================================================== */

.ncc-chat-container {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 120px);
}

.ncc-chat-messages {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding-bottom: var(--space-4);
}

.ncc-chat-bubble {
  border-radius: var(--radius-lg);
  padding: var(--space-2) var(--space-4);
  max-width: 85%;
  font-size: var(--text-sm);
}

.ncc-chat-bubble-user {
  background: rgba(59, 111, 212, 0.08);
  border-bottom-right-radius: var(--radius-sm);
  align-self: flex-end;
}

.ncc-chat-bubble-assistant {
  background: var(--bg-surface);
  border-left: 2px solid var(--accent-start);
  border-bottom-left-radius: var(--radius-sm);
  align-self: flex-start;
}

.ncc-chat-input-bar {
  border-top: 1px solid var(--bg-border);
  padding-top: var(--space-3);
  display: flex;
  gap: var(--space-2);
}

.ncc-chat-input-bar .ncc-input {
  flex: 1;
  border-radius: var(--radius-lg);
}

.ncc-chat-input-bar .ncc-btn {
  border-radius: var(--radius-lg);
}


/* ==========================================================================
   11h. View Toggle (Kanban/Table switcher)
   ========================================================================== */

.ncc-view-toggle {
  display: inline-flex;
  background-color: var(--bg-surface);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.ncc-view-toggle a,
.ncc-view-toggle button {
  padding: var(--space-1) var(--space-3);
  font-size: var(--text-xs);
  color: var(--text-muted);
  transition: background-color var(--transition-fast), color var(--transition-fast);
  white-space: nowrap;
}

.ncc-view-toggle a:hover,
.ncc-view-toggle button:hover {
  color: var(--text-primary);
}

.ncc-view-toggle .active {
  background-color: var(--bg-surface-hover);
  color: var(--text-primary);
}


/* ==========================================================================
   11i. Filter Bar
   ========================================================================== */

.ncc-filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
}

.ncc-filter-bar .ncc-select {
  width: auto;
  min-width: 120px;
}

@media (max-width: 767px) {
  .ncc-filter-bar {
    flex-wrap: nowrap;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    padding-bottom: var(--space-1);
  }
  .ncc-filter-bar::-webkit-scrollbar { display: none; }
  .ncc-filter-bar .ncc-select {
    flex-shrink: 0;
    min-height: 40px;
  }
}


/* ==========================================================================
   11j. Document Grid
   ========================================================================== */

.ncc-doc-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-4);
}

@media (max-width: 1200px) {
  .ncc-doc-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 767px) {
  .ncc-doc-grid {
    grid-template-columns: 1fr;
  }
}


/* ==========================================================================
   11k. Modal
   ========================================================================== */

.ncc-modal-overlay {
  position: fixed;
  inset: 0;
  background-color: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
  padding: var(--space-4);
}

.ncc-modal {
  background-color: var(--bg-surface);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-xl);
  padding: var(--space-6);
  width: 100%;
  max-height: 85vh;
  overflow-y: auto;
}

.ncc-modal-sm { max-width: 400px; }
.ncc-modal-md { max-width: 500px; }
.ncc-modal-lg { max-width: 640px; }
.ncc-modal-xl { max-width: 800px; }

.ncc-modal-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-4);
}


/* ==========================================================================
   11l. Chart Styling
   ========================================================================== */

.ncc-chart-wrap {
  background-color: var(--bg-surface);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
}

.ncc-chart-title {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  margin-bottom: var(--space-3);
}
```

- [ ] **Step 2: Verify CSS is valid**

Run: Open browser dev tools, confirm no CSS parse errors. Check that the nockcc.css file loads cleanly.

- [ ] **Step 3: Commit**

```bash
git add static/css/nockcc.css
git commit -m "style: add new CSS components for Phase 2 pages (tabs, kanban, toggles, chat, KPI)"
```

---

### Task 2: Copy logo files and update sidebar

**Files:**
- Create: `static/images/nock-logo-icon.png` (copy from `static/nock_icon_transparent.png`)
- Modify: `templates/base.html` (sidebar logo only — lines 49-56)

- [ ] **Step 1: Copy logo to images directory**

```bash
mkdir -p static/images
cp static/nock_icon_transparent.png static/images/nock-logo-icon.png
```

- [ ] **Step 2: Update sidebar logo in base.html**

Replace the sidebar logo section (the `.ncc-sidebar-logo` link and its children) with an `<img>` tag. Find this block in `templates/base.html`:

```html
                <a href="/" class="ncc-sidebar-logo">
                    <div class="ncc-sidebar-logo-icon">N</div>
                    <div class="ncc-sidebar-logo-text">
                        <div style="font-weight: 700; font-size: var(--text-base); line-height: 1.2;">NockCC</div>
                        <div style="font-size: 10px; color: var(--text-muted); line-height: 1.2;">Command Center</div>
                    </div>
                </a>
```

Replace with:

```html
                <a href="/" class="ncc-sidebar-logo">
                    <img src="/static/images/nock-logo-icon.png" alt="Nock" style="width: 28px; height: 28px; border-radius: var(--radius-md); flex-shrink: 0;">
                    <div class="ncc-sidebar-logo-text">
                        <div style="font-weight: 700; font-size: var(--text-base); line-height: 1.2;">NockCC</div>
                        <div style="font-size: 10px; color: var(--text-muted); line-height: 1.2;">Command Center</div>
                    </div>
                </a>
```

- [ ] **Step 3: Verify sidebar logo renders**

Run: `python manage.py runserver` and check the sidebar shows the actual logo icon, not the CSS "N" square. Verify collapsed sidebar shows just the icon.

- [ ] **Step 4: Commit**

```bash
git add static/images/nock-logo-icon.png templates/base.html
git commit -m "style: integrate actual Nock logo in sidebar"
```

---

### Task 3: Update login page with actual logo

**Files:**
- Modify: `templates/accounts/login.html` (logo section only — lines 290-303)

- [ ] **Step 1: Replace CSS logo with image**

Find this block in `templates/accounts/login.html`:

```html
                <div class="login-logo">
                    <div class="login-logo-circle">
                        <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <defs>
                                <linearGradient id="nock-v-grad" x1="10" y1="30" x2="30" y2="8" gradientUnits="userSpaceOnUse">
                                    <stop offset="0%" stop-color="#3B6FD4"/>
                                    <stop offset="100%" stop-color="#7C5CFC"/>
                                </linearGradient>
                            </defs>
                            <!-- V-nock arrow notch shape -->
                            <path d="M20 30 L8 14 Q6 11 9 11 L13 11 Q15 11 16 13 L20 22 L24 13 Q25 11 27 11 L31 11 Q34 11 32 14 Z" fill="url(#nock-v-grad)"/>
                        </svg>
                    </div>
                </div>
```

Replace with:

```html
                <div class="login-logo">
                    <div class="login-logo-circle">
                        <img src="/static/images/nock-logo-icon.png" alt="Nock" style="width: 40px; height: 40px; border-radius: 50%; object-fit: cover;">
                    </div>
                </div>
```

- [ ] **Step 2: Verify login page renders**

Run: Visit `/accounts/login/` and confirm the actual logo image appears inside the gradient circle. Confirm "Nock Command Center", "TECHNOLOGIES", and "Align · Decide · Deploy" tagline still show.

- [ ] **Step 3: Commit**

```bash
git add templates/accounts/login.html
git commit -m "style: integrate actual Nock logo in login page"
```

---

### Task 4: Redesign Spend Dashboard

**Files:**
- Modify: `spend/templates/spend/dashboard.html`

- [ ] **Step 1: Rewrite spend dashboard template**

Replace the entire content of `spend/templates/spend/dashboard.html` with the redesigned version. Key changes:
- Replace Tailwind grid/card classes with `ncc-kpi-row`, `ncc-kpi-card`, `ncc-card`, `ncc-table`
- Replace inline Tailwind colors with design system variables
- Update Chart.js colors to use design system palette
- Add budget progress bar using `ncc-progress`
- Add warning highlight for subscriptions renewing within 7 days

Write the complete file:

```html
{% extends "base.html" %}

{% block title %}Spend — NockCC{% endblock %}

{% block content %}
<div>
  <!-- Page header -->
  <div class="ncc-page-header">
    <div>
      <h1 class="ncc-page-title">Spend Dashboard</h1>
      <p class="text-muted text-sm" style="margin-top: var(--space-1);">Financial operations</p>
    </div>
    <div style="display: flex; align-items: center; gap: var(--space-3);">
      <a href="{% url 'spend:add-expense' %}" class="ncc-btn ncc-btn-primary ncc-btn-sm">+ Quick Add</a>
      <a href="{% url 'spend:pnl' %}" class="ncc-card-link" style="font-size: var(--text-xs);">P&L</a>
      <a href="{% url 'spend:tax' %}" class="ncc-card-link" style="font-size: var(--text-xs);">Tax Prep</a>
    </div>
  </div>

  <!-- KPI Cards -->
  <div class="ncc-kpi-row">
    <div class="ncc-kpi-card ncc-stagger">
      <p class="ncc-kpi-label">Total Spend to Date</p>
      <p class="ncc-kpi-value">${{ expense_totals.net|floatformat:2 }}</p>
      <p class="ncc-kpi-sub">net of refunds</p>
    </div>
    <div class="ncc-kpi-card ncc-stagger">
      <p class="ncc-kpi-label">Monthly Burn Rate</p>
      <p class="ncc-kpi-value ncc-gradient-text">${{ subs_total|floatformat:2 }}</p>
      <p class="ncc-kpi-sub">/month subscriptions</p>
    </div>
    <div class="ncc-kpi-card ncc-stagger">
      <p class="ncc-kpi-label">API Spend (MTD)</p>
      <p class="ncc-kpi-value" style="color: var(--accent-start);">${{ mtd_spend|floatformat:2 }}</p>
      <p class="ncc-kpi-sub">Anthropic usage</p>
    </div>
    <div class="ncc-kpi-card ncc-stagger">
      <p class="ncc-kpi-label">Tax Paid to Date</p>
      <p class="ncc-kpi-value" style="color: var(--color-warning);">${{ expense_totals.tax|floatformat:2 }}</p>
    </div>
  </div>

  <!-- Metrics row -->
  <div class="ncc-kpi-row" style="margin-bottom: var(--space-6);">
    <div class="ncc-kpi-card" style="padding: var(--space-3);">
      <p class="ncc-kpi-label" style="margin-bottom: var(--space-2);">Budget</p>
      {% if budget %}
      <p class="text-sm font-medium {% if budget_pct > 80 %}text-danger{% elif budget_pct > 60 %}text-warning{% else %}text-success{% endif %}">{{ budget_pct }}%</p>
      <div class="ncc-progress" style="margin-top: var(--space-2);">
        <div class="ncc-progress-fill {% if budget_pct > 80 %}ncc-progress-danger{% endif %}" style="width: {{ budget_pct }}%;"></div>
      </div>
      <p class="ncc-kpi-sub">${{ mtd_spend|floatformat:2 }} / ${{ budget.budget_usd|floatformat:2 }}</p>
      {% else %}
      <p class="text-sm text-muted">No budget set</p>
      {% endif %}
    </div>
    <div class="ncc-kpi-card" style="padding: var(--space-3);">
      <p class="ncc-kpi-label">Projected Month-End</p>
      <p class="text-sm font-medium text-secondary">${{ projected|floatformat:2 }}</p>
    </div>
    <div class="ncc-kpi-card" style="padding: var(--space-3);">
      <p class="ncc-kpi-label">Cost per PR</p>
      <p class="text-sm font-medium text-secondary">{% if cost_per_pr is not None %}${{ cost_per_pr|floatformat:2 }}{% else %}—{% endif %}</p>
    </div>
    <div class="ncc-kpi-card" style="padding: var(--space-3);">
      <p class="ncc-kpi-label">Annual Projection (Subs)</p>
      <p class="text-sm font-medium ncc-gradient-text">${{ subs_annual|floatformat:2 }}</p>
    </div>
  </div>

  <!-- Subscriptions Table -->
  <div class="ncc-card ncc-stagger" style="padding: 0; overflow: hidden; margin-bottom: var(--space-6);">
    <div class="ncc-card-header" style="padding: var(--space-4); border-bottom: 1px solid var(--bg-border);">
      <span class="ncc-card-label">Monthly Subscriptions</span>
      <span class="text-xs text-muted">{{ subs|length }} active</span>
    </div>
    {% if subs %}
    <div style="overflow-x: auto;">
      <table class="ncc-table">
        <thead>
          <tr>
            <th>Vendor</th>
            <th>Description</th>
            <th style="text-align: right;">Monthly Cost</th>
            <th style="text-align: right;">Next Billing</th>
            <th>Notes</th>
          </tr>
        </thead>
        <tbody>
          {% for s in subs %}
          <tr{% if s.renews_within_7_days %} style="background-color: rgba(251, 191, 36, 0.05);"{% endif %}>
            <td style="color: var(--text-primary);">{{ s.get_provider_display }}</td>
            <td>{{ s.name }}</td>
            <td style="text-align: right; color: var(--text-primary); font-weight: 500;">${{ s.monthly_cost|floatformat:2 }}</td>
            <td style="text-align: right;">{% if s.renews_within_7_days %}<span style="color: var(--color-warning);">{{ s.renewal_date }}</span>{% else %}{{ s.renewal_date }}{% endif %}</td>
            <td style="color: var(--text-muted);">{{ s.notes }}</td>
          </tr>
          {% endfor %}
        </tbody>
        <tfoot>
          <tr style="border-top: 1px solid var(--bg-border);">
            <td colspan="2" class="font-semibold" style="color: var(--text-muted); text-transform: uppercase; font-size: 10px; letter-spacing: 0.08em;">Total</td>
            <td style="text-align: right; font-weight: 700; color: var(--text-primary);">${{ subs_total|floatformat:2 }}/mo</td>
            <td colspan="2" style="text-align: right; color: var(--text-muted);">${{ subs_annual|floatformat:2 }}/yr</td>
          </tr>
        </tfoot>
      </table>
    </div>
    {% else %}
    <p class="text-xs text-muted" style="text-align: center; padding: var(--space-8);">No subscriptions. Run: python manage.py seed_subscriptions --clear</p>
    {% endif %}
  </div>

  <!-- Expense Log -->
  <div class="ncc-card ncc-stagger" style="padding: 0; overflow: hidden; margin-bottom: var(--space-6);">
    <div style="padding: var(--space-4); border-bottom: 1px solid var(--bg-border); display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-2);">
      <span class="ncc-card-label">Expense Log</span>
      <form method="get" style="display: flex; align-items: center; gap: var(--space-2);">
        {% if model_filter %}<input type="hidden" name="model" value="{{ model_filter }}">{% endif %}
        <label for="expense-category-filter" class="sr-only">Expense category</label>
        <select id="expense-category-filter" name="expense_category" class="ncc-select" style="width: auto; min-width: 120px;" onchange="this.form.submit()">
          <option value="">All Categories</option>
          {% for val, label in expense_categories %}
          <option value="{{ val }}" {% if expense_category == val %}selected{% endif %}>{{ label }}</option>
          {% endfor %}
        </select>
        <label for="expense-payment-filter" class="sr-only">Payment method</label>
        <select id="expense-payment-filter" name="expense_payment" class="ncc-select" style="width: auto; min-width: 140px;" onchange="this.form.submit()">
          <option value="">All Payment Methods</option>
          {% for val, label in expense_payment_methods %}
          <option value="{{ val }}" {% if expense_payment == val %}selected{% endif %}>{{ label }}</option>
          {% endfor %}
        </select>
      </form>
    </div>
    <div style="overflow-x: auto;">
      <table class="ncc-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Vendor</th>
            <th class="pipeline-desktop">Description</th>
            <th>Category</th>
            <th style="text-align: right;">Total</th>
            <th style="text-align: right;" class="pipeline-desktop">Tax</th>
            <th class="pipeline-desktop">Payment</th>
            <th style="width: 32px;"></th>
          </tr>
        </thead>
        <tbody>
          {% for e in expenses %}
          <tr{% if e.is_refund %} style="background-color: rgba(248, 113, 113, 0.04);"{% endif %}>
            <td>{{ e.date }}</td>
            <td style="color: var(--text-primary);">{{ e.vendor }}</td>
            <td class="pipeline-desktop">{{ e.description|truncatechars:60 }}</td>
            <td>
              <span class="ncc-badge {% if e.category == 'software' %}ncc-badge-open{% elif e.category == 'hardware' %}ncc-badge-approved{% elif e.category == 'formation' %}ncc-badge-review{% elif e.category == 'legal' %}ncc-badge-merged{% elif e.category == 'infrastructure' %}ncc-badge-review{% else %}ncc-badge-draft{% endif %}">{{ e.get_category_display }}</span>
            </td>
            <td style="text-align: right; font-weight: 500; {% if e.is_refund %}color: var(--color-danger);{% else %}color: var(--text-primary);{% endif %}">
              {% if e.is_refund %}-{% endif %}${{ e.total|floatformat:2 }}
            </td>
            <td style="text-align: right;" class="pipeline-desktop">${{ e.tax|floatformat:2 }}</td>
            <td class="pipeline-desktop" style="color: var(--text-muted);">{{ e.get_payment_method_display }}</td>
            <td style="text-align: center;">
              {% if e.receipt %}
              <a href="{{ e.receipt.url }}" target="_blank" title="View receipt: {{ e.receipt_filename }}" style="color: var(--text-muted); transition: color var(--transition-fast);" onmouseover="this.style.color='var(--accent-start)'" onmouseout="this.style.color='var(--text-muted)'">
                <i data-lucide="paperclip" style="width: 14px; height: 14px;"></i>
              </a>
              {% endif %}
            </td>
          </tr>
          {% empty %}
          <tr>
            <td colspan="8" style="text-align: center; padding: var(--space-8); color: var(--text-muted);">
              {% if has_expense_filters %}No expenses match the current filters.{% else %}No expenses yet. Run: python manage.py seed_expenses{% endif %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
        {% if expenses %}
        <tfoot>
          <tr style="border-top: 1px solid var(--bg-border);">
            <td colspan="4" class="font-semibold" style="color: var(--text-muted); text-transform: uppercase; font-size: 10px; letter-spacing: 0.08em;">
              {% if has_expense_filters %}Filtered Total{% else %}Net Total{% endif %}
            </td>
            <td style="text-align: right; font-weight: 700; color: var(--text-primary);">${{ filtered_totals.net|floatformat:2 }}</td>
            <td style="text-align: right;" class="pipeline-desktop">${{ filtered_totals.tax|floatformat:2 }}</td>
            <td class="pipeline-desktop"></td>
            <td></td>
          </tr>
        </tfoot>
        {% endif %}
      </table>
    </div>
  </div>

  <!-- Charts Row: Category + Monthly -->
  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-6); margin-bottom: var(--space-6);">
    <div class="ncc-chart-wrap ncc-stagger">
      <p class="ncc-chart-title">Spend by Category</p>
      <div style="height: 280px;" id="categoryChartWrap">
        <canvas id="categoryChart"></canvas>
      </div>
    </div>
    <div class="ncc-chart-wrap ncc-stagger">
      <p class="ncc-chart-title">Monthly Spending</p>
      <div style="height: 280px;" id="monthlyChartWrap">
        <canvas id="monthlyChart"></canvas>
      </div>
    </div>
  </div>

  <!-- Payment Method Chart -->
  <div class="ncc-chart-wrap ncc-stagger" style="margin-bottom: var(--space-6);">
    <p class="ncc-chart-title">Payment Method Breakdown</p>
    <div style="height: 250px;" id="paymentChartWrap">
      <canvas id="paymentChart"></canvas>
    </div>
  </div>

  <!-- API Usage Section -->
  <div style="display: grid; grid-template-columns: 2fr 1fr; gap: var(--space-6); margin-bottom: var(--space-6);">
    <div class="ncc-chart-wrap ncc-stagger">
      <p class="ncc-chart-title">API Daily Spend (30 days)</p>
      <div style="height: 250px;" id="dailySpendWrap">
        <canvas id="dailySpendChart"></canvas>
      </div>
    </div>
    <div class="ncc-chart-wrap ncc-stagger">
      <p class="ncc-chart-title">Model Breakdown (MTD)</p>
      <div style="height: 250px;" id="modelChartWrap">
        <canvas id="modelChart"></canvas>
      </div>
    </div>
  </div>

  <!-- API Daily Breakdown Table -->
  <div class="ncc-card ncc-stagger" style="padding: 0; overflow: hidden; margin-bottom: var(--space-6);">
    <div style="padding: var(--space-4); border-bottom: 1px solid var(--bg-border); display: flex; align-items: center; justify-content: space-between;">
      <span class="ncc-card-label">API Daily Breakdown</span>
      <form method="get" style="display: flex; align-items: center; gap: var(--space-2);">
        {% if expense_category %}<input type="hidden" name="expense_category" value="{{ expense_category }}">{% endif %}
        {% if expense_payment %}<input type="hidden" name="expense_payment" value="{{ expense_payment }}">{% endif %}
        <label for="filter-model" class="sr-only">Model</label>
        <select id="filter-model" name="model" class="ncc-select" style="width: auto; min-width: 140px;" onchange="this.form.submit()">
          <option value="">All Models</option>
          {% for m in models_list %}
          <option value="{{ m }}" {% if model_filter == m %}selected{% endif %}>{{ m }}</option>
          {% endfor %}
        </select>
      </form>
    </div>
    <div style="overflow-x: auto;">
      <table class="ncc-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Model</th>
            <th style="text-align: right;">Input</th>
            <th style="text-align: right;">Output</th>
            <th style="text-align: right;">Cache</th>
            <th style="text-align: right;">Reqs</th>
            <th style="text-align: right;">Cost</th>
          </tr>
        </thead>
        <tbody>
          {% for r in daily_table %}
          <tr>
            <td>{{ r.date }}</td>
            <td class="font-mono">{{ r.model|truncatechars:30 }}</td>
            <td style="text-align: right;">{{ r.input_tokens|default:"0" }}</td>
            <td style="text-align: right;">{{ r.output_tokens|default:"0" }}</td>
            <td style="text-align: right;">{{ r.cache_read_tokens|default:"0" }}</td>
            <td style="text-align: right;">{{ r.request_count|default:"0" }}</td>
            <td style="text-align: right; color: var(--text-primary); font-weight: 500;">${{ r.cost_usd|floatformat:4 }}</td>
          </tr>
          {% empty %}
          <tr>
            <td colspan="7" style="text-align: center; padding: var(--space-8); color: var(--text-muted);">
              {% if model_filter %}No API usage matches the current model filter.{% else %}No usage data yet. Run: python manage.py sync_spend{% endif %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</div>
{% endblock %}

{% block extra_scripts %}
<script>
const dailyData = {{ daily_chart_json|safe }};
const modelData = {{ model_chart_json|safe }};
const categoryData = {{ category_chart_json|safe }};
const paymentData = {{ payment_chart_json|safe }};
const monthlyData = {{ monthly_chart_json|safe }};

/* Design system chart colors */
const chartColors = ['#3B6FD4', '#7C5CFC', '#FBBF24', '#F87171', '#34D399', '#06B6D4', '#EC4899'];
const gridColor = 'rgba(30, 30, 46, 0.8)';
const tickColor = '#64748B';
const chartDefaults = { color: tickColor, font: { size: 10, family: "'DM Sans', sans-serif" } };

function showEmpty(wrapId, msg) {
    const el = document.getElementById(wrapId);
    if (el) { el.style.display = 'flex'; el.style.alignItems = 'center'; el.style.justifyContent = 'center'; el.style.color = '#64748B'; el.style.fontSize = '0.75rem'; el.textContent = msg; }
}

/* Category Donut */
const catEl = document.getElementById('categoryChart');
if (categoryData.length > 0 && catEl) {
    new Chart(catEl, {
        type: 'doughnut',
        data: { labels: categoryData.map(d => d.label), datasets: [{ data: categoryData.map(d => parseFloat(d.total)), backgroundColor: chartColors.slice(0, categoryData.length), borderWidth: 0 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { ...chartDefaults, padding: 10 } }, tooltip: { callbacks: { label: ctx => ' ' + ctx.label + ': $' + ctx.parsed.toFixed(2) } } } }
    });
} else { showEmpty('categoryChartWrap', 'No expense data'); }

/* Monthly Bar */
const monthEl = document.getElementById('monthlyChart');
if (monthlyData.length > 0 && monthEl) {
    new Chart(monthEl, {
        type: 'bar',
        data: { labels: monthlyData.map(d => d.month.slice(0, 7)), datasets: [{ label: 'Monthly Spend ($)', data: monthlyData.map(d => parseFloat(d.total)), backgroundColor: 'rgba(124, 92, 252, 0.6)', borderColor: '#7C5CFC', borderWidth: 1 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: chartDefaults, grid: { color: gridColor } }, y: { ticks: { ...chartDefaults, callback: v => '$' + v.toFixed(0) }, grid: { color: gridColor } } } }
    });
} else { showEmpty('monthlyChartWrap', 'No expense data'); }

/* Payment Horizontal Bar */
const pmEl = document.getElementById('paymentChart');
if (paymentData.length > 0 && pmEl) {
    new Chart(pmEl, {
        type: 'bar',
        data: { labels: paymentData.map(d => d.label), datasets: [{ label: 'Total Spend ($)', data: paymentData.map(d => parseFloat(d.total)), backgroundColor: chartColors.slice(0, paymentData.length), borderWidth: 0 }] },
        options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { ...chartDefaults, callback: v => '$' + v.toFixed(0) }, grid: { color: gridColor } }, y: { ticks: chartDefaults, grid: { display: false } } } }
    });
} else { showEmpty('paymentChartWrap', 'No expense data'); }

/* API Daily Spend */
const dateMap = {};
dailyData.forEach(d => { if (!dateMap[d.date]) dateMap[d.date] = 0; dateMap[d.date] += parseFloat(d.cost); });
const dates = Object.keys(dateMap).sort();
const costs = dates.map(d => dateMap[d]);
const dailyEl = document.getElementById('dailySpendChart');
if (dates.length > 0 && dailyEl) {
    new Chart(dailyEl, {
        type: 'bar',
        data: { labels: dates.map(d => d.slice(5)), datasets: [{ label: 'Daily Cost ($)', data: costs, backgroundColor: 'rgba(59, 111, 212, 0.6)', borderColor: '#3B6FD4', borderWidth: 1 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: chartDefaults, grid: { color: gridColor } }, y: { ticks: { ...chartDefaults, callback: v => '$' + v.toFixed(2) }, grid: { color: gridColor } } } }
    });
} else { showEmpty('dailySpendWrap', 'No API data yet'); }

/* Model Donut */
const modelEl = document.getElementById('modelChart');
if (modelData.length > 0 && modelEl) {
    new Chart(modelEl, {
        type: 'doughnut',
        data: { labels: modelData.map(d => d.model.split('-').slice(-2).join('-')), datasets: [{ data: modelData.map(d => parseFloat(d.cost)), backgroundColor: chartColors.slice(0, modelData.length), borderWidth: 0 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { ...chartDefaults, padding: 8 } } } }
    });
} else { showEmpty('modelChartWrap', 'No API data yet'); }
</script>
{% endblock %}
```

- [ ] **Step 2: Verify spend dashboard renders**

Run: Visit `/spend/` and confirm KPI cards, tables, charts, and filters all render correctly.

- [ ] **Step 3: Commit**

```bash
git add spend/templates/spend/dashboard.html
git commit -m "style: redesign Spend dashboard with KPI cards and styled tables"
```

---

### Task 5: Redesign CRM Pipeline

**Files:**
- Modify: `crm/templates/crm/pipeline.html`

- [ ] **Step 1: Rewrite CRM pipeline template**

Replace the entire content of `crm/templates/crm/pipeline.html`:

```html
{% extends "base.html" %}

{% block title %}CRM Pipeline — NockCC{% endblock %}

{% block content %}
<div>
  <!-- Page header -->
  <div class="ncc-page-header">
    <div>
      <h1 class="ncc-page-title">CRM Pipeline</h1>
      <p class="text-muted text-sm" style="margin-top: var(--space-1);">{{ total_deals }} deal{{ total_deals|pluralize }}</p>
    </div>
    <div style="display: flex; align-items: center; gap: var(--space-3);">
      <a href="{% url 'crm:deal-create' %}" class="ncc-btn ncc-btn-primary ncc-btn-sm">+ New Deal</a>
      <a href="{% url 'crm:contacts' %}" class="ncc-btn ncc-btn-ghost ncc-btn-sm">Contacts</a>
      <div class="ncc-view-toggle">
        <a href="?view=kanban" class="{% if view_mode == 'kanban' %}active{% endif %}">Kanban</a>
        <a href="?view=table" class="{% if view_mode == 'table' %}active{% endif %}">Table</a>
      </div>
    </div>
  </div>

  <!-- KPI Stats -->
  <div class="ncc-kpi-row">
    <div class="ncc-kpi-card ncc-stagger">
      <p class="ncc-kpi-label">Open Deals</p>
      <p class="ncc-kpi-value">{{ total_deals }}</p>
    </div>
    <div class="ncc-kpi-card ncc-stagger">
      <p class="ncc-kpi-label">Pipeline Value</p>
      <p class="ncc-kpi-value" style="color: var(--color-success);">${{ pipeline_value|floatformat:2 }}</p>
    </div>
    <div class="ncc-kpi-card ncc-stagger">
      <p class="ncc-kpi-label">Win Rate</p>
      <p class="ncc-kpi-value" style="color: var(--accent-start);">{{ win_rate }}%</p>
    </div>
    <div class="ncc-kpi-card ncc-stagger">
      <p class="ncc-kpi-label">Action This Week</p>
      <p class="ncc-kpi-value {% if action_needed > 0 %}text-warning{% else %}text-muted{% endif %}">{{ action_needed }}</p>
    </div>
  </div>

  {% if view_mode == 'kanban' %}
  <!-- Kanban Board -->
  <div class="ncc-kanban-board">
    {% for stage in stages %}
    <div class="ncc-kanban-col ncc-stagger">
      <div class="ncc-kanban-col-header">
        <span class="ncc-kanban-col-title">{{ stage.label }}</span>
        <span class="ncc-kanban-col-count">{{ stage.count }}</span>
      </div>
      {% for deal in stage.deals %}
      <a href="{% url 'crm:deal-detail' deal.pk %}" class="ncc-kanban-card" style="display: block; text-decoration: none;">
        <p class="text-sm font-medium" style="color: var(--text-primary); margin-bottom: var(--space-1);">{{ deal.title }}</p>
        {% if deal.contact %}
        <p class="text-xs text-secondary" style="margin-bottom: var(--space-1);">{{ deal.contact.name }}</p>
        {% endif %}
        {% if deal.display_value %}
        <p class="text-xs font-medium" style="color: var(--color-success);">${{ deal.display_value|floatformat:2 }}</p>
        {% endif %}
        {% if deal.next_action %}
        <p class="text-xs text-muted" style="margin-top: var(--space-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">Next: {{ deal.next_action }}</p>
        {% endif %}
      </a>
      {% empty %}
      <div class="ncc-kanban-empty">No deals</div>
      {% endfor %}
    </div>
    {% endfor %}
  </div>

  {% else %}
  <!-- Table View -->
  <div class="ncc-card ncc-stagger" style="padding: 0; overflow: hidden;">
    <div style="overflow-x: auto;">
      <table class="ncc-table">
        <thead>
          <tr>
            <th>Deal</th>
            <th>Contact</th>
            <th>Stage</th>
            <th>Source</th>
            <th style="text-align: right;">Value</th>
            <th class="pipeline-desktop">Next Action</th>
          </tr>
        </thead>
        <tbody>
          {% for deal in deals %}
          <tr class="ncc-stagger">
            <td>
              <a href="{% url 'crm:deal-detail' deal.pk %}" style="color: var(--accent-start); transition: color var(--transition-fast);" onmouseover="this.style.color='var(--accent-end)'" onmouseout="this.style.color='var(--accent-start)'">{{ deal.title }}</a>
            </td>
            <td>{{ deal.contact.name|default:"—" }}</td>
            <td>
              <span class="ncc-badge {% if deal.stage == 'closed_won' %}ncc-badge-approved{% elif deal.stage == 'closed_lost' %}ncc-badge-closed{% elif deal.stage == 'active' %}ncc-badge-open{% else %}ncc-badge-draft{% endif %}">{{ deal.get_stage_display }}</span>
            </td>
            <td>{{ deal.get_source_display }}</td>
            <td style="text-align: right; color: var(--color-success); font-weight: 500;">
              {% if deal.display_value %}${{ deal.display_value|floatformat:2 }}{% else %}—{% endif %}
            </td>
            <td class="pipeline-desktop" style="color: var(--text-muted);">{{ deal.next_action|default:"—"|truncatechars:30 }}</td>
          </tr>
          {% empty %}
          <tr>
            <td colspan="6" style="text-align: center; padding: var(--space-8); color: var(--text-muted);">No deals yet. Create your first deal.</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 2: Verify CRM page renders**

Run: Visit `/crm/` and confirm both kanban and table views work. Test `?view=kanban` and `?view=table` URL params.

- [ ] **Step 3: Commit**

```bash
git add crm/templates/crm/pipeline.html
git commit -m "style: redesign CRM pipeline with kanban layout"
```

---

### Task 6: Redesign Tasks Page

**Files:**
- Modify: `tasks/templates/tasks/feed.html`

- [ ] **Step 1: Rewrite tasks feed template**

Replace the entire content of `tasks/templates/tasks/feed.html`:

```html
{% extends "base.html" %}
{% block title %}Tasks — NockCC{% endblock %}
{% block content %}

<!-- Page header -->
<div class="ncc-page-header">
  <div>
    <h1 class="ncc-page-title">Tasks</h1>
    <p class="text-muted text-sm" style="margin-top: var(--space-1);">
      {% if overdue_count %}<span class="ncc-badge ncc-badge-closed">{{ overdue_count }} overdue</span>{% endif %}
    </p>
  </div>
  <div style="display: flex; align-items: center; gap: var(--space-3);">
    <a href="/handoffs/" class="ncc-card-link">Handoffs</a>
    <div class="ncc-view-toggle">
      <a href="?view=feed" class="{% if view_mode != 'dashboard' %}active{% endif %}">Feed</a>
      <a href="?view=dashboard" class="{% if view_mode == 'dashboard' %}active{% endif %}">Dashboard</a>
    </div>
  </div>
</div>

<!-- Project Summary Cards -->
{% if stats %}
<div style="display: flex; gap: var(--space-3); overflow-x: auto; margin-bottom: var(--space-5); padding-bottom: var(--space-1); -webkit-overflow-scrolling: touch;">
  {% for s in stats %}
  <div class="ncc-card ncc-stagger" style="flex-shrink: 0; min-width: 200px; padding: var(--space-3); border-left: 3px solid {% if s.project.color == 'blue' %}var(--accent-start){% elif s.project.color == 'green' %}var(--color-success){% elif s.project.color == 'purple' %}var(--accent-end){% elif s.project.color == 'orange' %}var(--color-warning){% else %}var(--text-muted){% endif %};">
    <p class="text-sm font-medium" style="color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ s.project.name }}</p>
    <div style="display: flex; align-items: center; gap: var(--space-3); margin-top: var(--space-1);">
      <span class="text-xs text-secondary">{{ s.done }}/{{ s.total }} complete</span>
      {% if s.overdue %}
      <span class="text-xs text-danger font-medium">{{ s.overdue }} overdue</span>
      {% endif %}
    </div>
    {% if s.last_activity %}
    <p class="text-xs text-muted" style="margin-top: var(--space-1);">Last activity: {{ s.last_activity|timesince }} ago</p>
    {% endif %}
  </div>
  {% endfor %}
</div>
{% endif %}

{% if view_mode == 'dashboard' %}
<!-- Dashboard View -->

{% if overdue_tasks %}
<div class="ncc-card ncc-stagger" style="padding: 0; overflow: hidden; margin-bottom: var(--space-6);">
  <div style="padding: var(--space-4); border-bottom: 1px solid var(--bg-border); display: flex; align-items: center; gap: var(--space-2);">
    <span class="ncc-dot ncc-dot-danger"></span>
    <span class="ncc-card-label" style="color: var(--color-danger);">Overdue</span>
    <span class="text-xs text-muted" style="margin-left: auto;">{{ overdue_tasks|length }} task{{ overdue_tasks|length|pluralize }}</span>
  </div>
  <table class="ncc-table">
    <tbody>
      {% for task in overdue_tasks %}
      <tr style="background-color: rgba(248, 113, 113, 0.04);">
        <td>
          {% if task.permalink_url %}
          <a href="{{ task.permalink_url }}" target="_blank" rel="noopener" style="color: var(--text-primary); transition: color var(--transition-fast);">{{ task.name|truncatechars:60 }}</a>
          {% else %}
          <span style="color: var(--text-secondary);">{{ task.name|truncatechars:60 }}</span>
          {% endif %}
        </td>
        <td>
          <span class="ncc-dot {% if task.project.color == 'blue' %}ncc-dot-info{% elif task.project.color == 'green' %}ncc-dot-success{% elif task.project.color == 'purple' %}ncc-dot-info{% else %}ncc-dot-muted{% endif %}" style="margin-right: var(--space-1);"></span>
          <span class="text-xs text-secondary">{{ task.project.name|truncatechars:20 }}</span>
        </td>
        <td class="text-danger font-medium">{{ task.due_on }}</td>
        <td style="color: var(--text-muted);">{{ task.assignee_name|default:"—" }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}

{% if due_this_week %}
<div class="ncc-card ncc-stagger" style="padding: 0; overflow: hidden; margin-bottom: var(--space-6);">
  <div style="padding: var(--space-4); border-bottom: 1px solid var(--bg-border);">
    <span class="ncc-card-label">Due This Week</span>
  </div>
  <table class="ncc-table">
    <tbody>
      {% for task in due_this_week %}
      <tr>
        <td>
          {% if task.permalink_url %}
          <a href="{{ task.permalink_url }}" target="_blank" rel="noopener" style="color: var(--text-primary); transition: color var(--transition-fast);">{{ task.name|truncatechars:60 }}</a>
          {% else %}<span style="color: var(--text-secondary);">{{ task.name|truncatechars:60 }}</span>{% endif %}
        </td>
        <td>
          <span class="ncc-dot {% if task.project.color == 'blue' %}ncc-dot-info{% elif task.project.color == 'green' %}ncc-dot-success{% else %}ncc-dot-muted{% endif %}" style="margin-right: var(--space-1);"></span>
          <span class="text-xs text-secondary">{{ task.project.name|truncatechars:20 }}</span>
        </td>
        <td class="{% if task.due_on == today %}text-warning font-medium{% endif %}">
          {% if task.due_on == today %}Today{% else %}{{ task.due_on }}{% endif %}
        </td>
        <td style="color: var(--text-muted);">{{ task.assignee_name|default:"—" }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}

{% if recent_completed %}
<div class="ncc-card ncc-stagger" style="padding: 0; overflow: hidden; margin-bottom: var(--space-6);">
  <div style="padding: var(--space-4); border-bottom: 1px solid var(--bg-border);">
    <span class="ncc-card-label">Recent Completions</span>
  </div>
  <table class="ncc-table">
    <tbody>
      {% for task in recent_completed %}
      <tr>
        <td><span style="color: var(--text-muted); text-decoration: line-through;">{{ task.name|truncatechars:60 }}</span></td>
        <td>
          <span class="ncc-dot {% if task.project.color == 'blue' %}ncc-dot-info{% elif task.project.color == 'green' %}ncc-dot-success{% else %}ncc-dot-muted{% endif %}" style="margin-right: var(--space-1);"></span>
          <span class="text-xs text-muted">{{ task.project.name|truncatechars:20 }}</span>
        </td>
        <td class="text-success">{% if task.completed_at %}{{ task.completed_at|timesince }} ago{% else %}Completed{% endif %}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}

{% if not overdue_tasks and not due_this_week and not recent_completed %}
<div style="padding: var(--space-12) 0; text-align: center;">
  <p class="text-sm text-secondary">No task data available in dashboard mode.</p>
  <a href="?view=feed" class="ncc-card-link" style="margin-top: var(--space-2); display: inline-block;">Switch to feed view</a>
</div>
{% endif %}

{% else %}
<!-- Feed View -->

<!-- Filters -->
<form method="get" class="ncc-filter-bar">
  <input type="hidden" name="view" value="feed">
  <select name="project" onchange="this.form.submit()" class="ncc-select">
    <option value="">All projects</option>
    {% for proj in projects %}
    <option value="{{ proj.pk }}" {% if filter.form.project.value|stringformat:"s" == proj.pk|stringformat:"s" %}selected{% endif %}>
      {{ proj.name|truncatechars:40 }}
    </option>
    {% endfor %}
  </select>
  <select name="priority" onchange="this.form.submit()" class="ncc-select">
    <option value="">All priorities</option>
    <option value="high" {% if filter.form.priority.value == 'high' %}selected{% endif %}>High</option>
    <option value="medium" {% if filter.form.priority.value == 'medium' %}selected{% endif %}>Medium</option>
    <option value="low" {% if filter.form.priority.value == 'low' %}selected{% endif %}>Low</option>
  </select>
  <select name="overdue" onchange="this.form.submit()" class="ncc-select">
    <option value="">All</option>
    <option value="yes" {% if filter.form.overdue.value == 'yes' %}selected{% endif %}>Overdue only</option>
    <option value="no" {% if filter.form.overdue.value == 'no' %}selected{% endif %}>Not overdue</option>
  </select>
  {% if request.GET.project or request.GET.priority or request.GET.overdue %}
  <a href="/tasks/?view=feed" class="ncc-btn ncc-btn-ghost ncc-btn-sm">Clear</a>
  {% endif %}
</form>

<!-- Task Table -->
<div class="ncc-card ncc-stagger" style="padding: 0; overflow: hidden;">
  {% if tasks %}
  <table class="ncc-table">
    <thead>
      <tr>
        <th><a href="?view=feed&{{ query_without_sort }}&sort={% if sort == 'name' %}-name{% else %}name{% endif %}" style="color: inherit;">Task</a></th>
        <th>Project</th>
        <th>Section</th>
        <th><a href="?view=feed&{{ query_without_sort }}&sort={% if sort == 'due_on' %}-due_on{% else %}due_on{% endif %}" style="color: inherit;">Due</a></th>
        <th>Priority</th>
        <th>PR</th>
        <th>Assignee</th>
      </tr>
    </thead>
    <tbody>
      {% for task in tasks %}
      <tr class="ncc-stagger" {% if task.is_overdue %}style="background-color: rgba(248, 113, 113, 0.04);"{% endif %}>
        <td>
          {% if task.permalink_url %}
          <a href="{{ task.permalink_url }}" target="_blank" rel="noopener" style="color: var(--text-primary); transition: color var(--transition-fast);">{{ task.name|truncatechars:70 }}</a>
          {% else %}<span style="color: var(--text-secondary);">{{ task.name|truncatechars:70 }}</span>{% endif %}
        </td>
        <td>
          <span class="ncc-dot {% if task.project.color == 'blue' %}ncc-dot-info{% elif task.project.color == 'green' %}ncc-dot-success{% elif task.project.color == 'purple' %}ncc-dot-info{% elif task.project.color == 'orange' %}ncc-dot-warning{% else %}ncc-dot-muted{% endif %}" style="margin-right: var(--space-1);"></span>
          <span class="text-xs text-secondary">{{ task.project.name|truncatechars:25 }}</span>
        </td>
        <td style="color: var(--text-muted);">{{ task.section_name|truncatechars:25|default:"—" }}</td>
        <td class="{% if task.is_overdue %}text-danger font-medium{% endif %}">
          {% if task.due_on %}{{ task.due_on }}{% if task.is_overdue %} &#9888;{% endif %}{% else %}—{% endif %}
        </td>
        <td>
          {% if task.priority == 'high' %}
          <span class="ncc-badge ncc-badge-closed">High</span>
          {% elif task.priority == 'medium' %}
          <span class="ncc-badge ncc-badge-review">Med</span>
          {% elif task.priority == 'low' %}
          <span class="ncc-badge ncc-badge-draft">Low</span>
          {% else %}<span class="text-muted">—</span>{% endif %}
        </td>
        <td>
          {% if task.linked_pr %}
          <a href="/pipeline/{{ task.linked_pr.repository.owner }}/{{ task.linked_pr.repository.name }}/{{ task.linked_pr.number }}/" style="color: var(--accent-start); transition: color var(--transition-fast);">#{{ task.linked_pr.number }}</a>
          {% else %}<span class="text-muted">—</span>{% endif %}
        </td>
        <td style="color: var(--text-muted);">{{ task.assignee_name|default:"—" }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div style="padding: var(--space-12) 0; text-align: center;">
    <p class="text-sm text-secondary">No tasks found</p>
    {% if request.GET.project or request.GET.priority or request.GET.overdue %}
    <a href="/tasks/?view=feed" class="ncc-card-link" style="margin-top: var(--space-2); display: inline-block;">Clear filters</a>
    {% else %}
    <p class="text-xs text-muted" style="margin-top: var(--space-2);">Run <code style="background: var(--bg-surface-hover); padding: 1px 4px; border-radius: var(--radius-sm);">python manage.py seed_asana_projects && python manage.py sync_asana</code> to load tasks</p>
    {% endif %}
  </div>
  {% endif %}
</div>
{% endif %}

{% endblock %}
```

- [ ] **Step 2: Verify tasks page renders**

Run: Visit `/tasks/` and test both feed and dashboard views. Confirm filters work.

- [ ] **Step 3: Commit**

```bash
git add tasks/templates/tasks/feed.html
git commit -m "style: polish Tasks page to match Pipeline design"
```

---

### Task 7: Redesign Vault Page

**Files:**
- Modify: `vault/templates/vault/list.html`

- [ ] **Step 1: Rewrite vault template**

Replace the entire content of `vault/templates/vault/list.html`:

```html
{% extends "base.html" %}

{% block title %}Document Vault — NockCC{% endblock %}

{% block content %}
<div>
  <!-- Page header -->
  <div class="ncc-page-header">
    <div>
      <h1 class="ncc-page-title">Document Vault</h1>
      <p class="text-muted text-sm" style="margin-top: var(--space-1);">{{ documents|length }} document{{ documents|length|pluralize }}</p>
    </div>
    <a href="{% url 'vault:upload' %}" class="ncc-btn ncc-btn-primary ncc-btn-sm">+ Upload Document</a>
  </div>

  <!-- Filters -->
  <form method="get" class="ncc-filter-bar">
    <label for="vault-category-filter" class="sr-only">Category</label>
    <select id="vault-category-filter" name="category" class="ncc-select" onchange="this.form.submit()">
      <option value="">All Categories</option>
      {% for val, label in categories %}
      <option value="{{ val }}" {% if selected_category == val %}selected{% endif %}>{{ label }}</option>
      {% endfor %}
    </select>
    <input type="text" name="q" value="{{ search }}" placeholder="Search title or tags..." class="ncc-input" style="width: auto; min-width: 200px;">
    <button type="submit" class="ncc-btn ncc-btn-ghost ncc-btn-sm">Search</button>
  </form>

  <!-- Document Grid -->
  <div class="ncc-doc-grid">
    {% for doc in documents %}
    <a href="{% url 'vault:detail' doc.pk %}" class="ncc-card ncc-stagger" style="display: block; text-decoration: none;">
      <div style="display: flex; align-items: flex-start; gap: var(--space-3);">
        <div style="flex-shrink: 0; width: 40px; height: 40px; border-radius: var(--radius-md); display: flex; align-items: center; justify-content: center;
          {% if doc.category == 'formation' %}background: rgba(251, 191, 36, 0.1); color: var(--color-warning);
          {% elif doc.category == 'legal' %}background: rgba(124, 92, 252, 0.1); color: var(--accent-end);
          {% elif doc.category == 'financial' %}background: rgba(52, 211, 153, 0.1); color: var(--color-success);
          {% elif doc.category == 'insurance' %}background: rgba(59, 111, 212, 0.1); color: var(--accent-start);
          {% elif doc.category == 'tax' %}background: rgba(248, 113, 113, 0.1); color: var(--color-danger);
          {% elif doc.category == 'trademark' %}background: rgba(6, 182, 212, 0.1); color: var(--color-info);
          {% else %}background: var(--bg-surface-hover); color: var(--text-muted);{% endif %}">
          <i data-lucide="file-text" style="width: 20px; height: 20px;"></i>
        </div>
        <div style="flex: 1; min-width: 0;">
          <p class="text-sm font-medium" style="color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ doc.title }}</p>
          <p class="text-xs text-secondary" style="margin-top: 2px;">{{ doc.get_category_display }}</p>
          {% if doc.description %}
          <p class="text-xs text-muted" style="margin-top: var(--space-1); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">{{ doc.description }}</p>
          {% endif %}
          <div style="display: flex; align-items: center; gap: var(--space-3); margin-top: var(--space-2);">
            <span class="text-xs text-muted">{{ doc.file_size_display }}</span>
            <span class="text-xs text-muted">{{ doc.uploaded_at|date:"M d, Y" }}</span>
          </div>
          {% if doc.tag_list %}
          <div style="display: flex; flex-wrap: wrap; gap: var(--space-1); margin-top: var(--space-2);">
            {% for tag in doc.tag_list %}
            <span class="ncc-badge ncc-badge-draft">{{ tag }}</span>
            {% endfor %}
          </div>
          {% endif %}
        </div>
      </div>
    </a>
    {% empty %}
    <div style="grid-column: 1 / -1; padding: var(--space-12) 0; text-align: center;">
      <i data-lucide="archive" style="width: 48px; height: 48px; color: var(--text-muted); margin: 0 auto var(--space-3); display: block; opacity: 0.3;"></i>
      <p class="text-sm text-secondary">No documents in the vault yet.</p>
      <a href="{% url 'vault:upload' %}" class="ncc-card-link" style="margin-top: var(--space-2); display: inline-block;">Upload your first document</a>
    </div>
    {% endfor %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Verify vault renders**

Run: Visit `/vault/` and confirm document cards, filters, and empty state render correctly.

- [ ] **Step 3: Commit**

```bash
git add vault/templates/vault/list.html
git commit -m "style: redesign Vault with document cards and session reports"
```

---

### Task 8: Redesign Notifications Page

**Files:**
- Modify: `notifications/templates/notifications/list.html`

- [ ] **Step 1: Rewrite notifications template**

Replace the entire content of `notifications/templates/notifications/list.html`:

```html
{% extends "base.html" %}

{% block title %}Notifications — NockCC{% endblock %}

{% block content %}
<div>
  <!-- Page header -->
  <div class="ncc-page-header">
    <div>
      <h1 class="ncc-page-title">Notifications</h1>
      <p class="text-muted text-sm" style="margin-top: var(--space-1);">Rules and channels</p>
    </div>
  </div>

  <div style="display: grid; grid-template-columns: 1fr 2fr; gap: var(--space-6); margin-bottom: var(--space-6);">

    <!-- Channels -->
    <div class="ncc-card ncc-stagger">
      <div class="ncc-card-header">
        <span class="ncc-card-label">Channels</span>
      </div>
      {% if channels %}
      <div style="display: flex; flex-direction: column; gap: var(--space-3);">
        {% for ch in channels %}
        <div style="display: flex; align-items: center; justify-content: space-between;">
          <div style="display: flex; align-items: center; gap: var(--space-2);">
            <span class="ncc-dot {% if ch.is_active %}ncc-dot-success{% else %}ncc-dot-muted{% endif %}"></span>
            <span class="text-sm" style="color: var(--text-primary);">{{ ch.name }}</span>
            <span class="text-xs text-muted">{{ ch.get_channel_type_display }}</span>
          </div>
          {% if ch.is_active %}
          <span class="ncc-badge ncc-badge-approved">Active</span>
          {% else %}
          <span class="ncc-badge ncc-badge-draft">Inactive</span>
          {% endif %}
        </div>
        {% endfor %}
      </div>
      {% else %}
      <p class="text-xs text-muted" style="text-align: center; padding: var(--space-4);">No channels configured</p>
      {% endif %}
    </div>

    <!-- Rules -->
    <div class="ncc-card ncc-stagger">
      <div class="ncc-card-header">
        <span class="ncc-card-label">Rules</span>
      </div>
      {% if rules %}
      <div style="display: flex; flex-direction: column; gap: var(--space-2);">
        {% for r in rules %}
        <div style="display: flex; align-items: center; justify-content: space-between; padding: var(--space-2) var(--space-3); background-color: var(--bg-base); border-radius: var(--radius-md);">
          <div style="display: flex; align-items: center; gap: var(--space-2);">
            <span class="text-sm" style="color: var(--text-primary);">{{ r.name }}</span>
            <span class="ncc-badge ncc-badge-draft">{{ r.get_trigger_event_display }}</span>
          </div>
          <div style="display: flex; align-items: center; gap: var(--space-2);">
            <span class="text-xs text-muted">&rarr; {{ r.channel.name }}</span>
            <span class="ncc-dot {% if r.is_active %}ncc-dot-success{% else %}ncc-dot-muted{% endif %}"></span>
          </div>
        </div>
        {% endfor %}
      </div>
      {% else %}
      <p class="text-xs text-muted" style="text-align: center; padding: var(--space-4);">No rules configured. Run: python manage.py seed_notifications</p>
      {% endif %}
    </div>
  </div>

  <!-- Notification Log -->
  <div class="ncc-card ncc-stagger" style="padding: 0; overflow: hidden;">
    <div style="padding: var(--space-4); border-bottom: 1px solid var(--bg-border);">
      <span class="ncc-card-label">Recent Notifications</span>
    </div>
    <div style="overflow-x: auto;">
      <table class="ncc-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Event</th>
            <th>Channel</th>
            <th>Status</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {% for log in logs %}
          <tr>
            <td>{{ log.sent_at|date:"M d, H:i" }}</td>
            <td>{{ log.event_type }}</td>
            <td>{{ log.channel.name }}</td>
            <td>
              {% if log.success %}
              <span class="ncc-badge ncc-badge-approved">Sent</span>
              {% else %}
              <span class="ncc-badge ncc-badge-closed">Failed</span>
              {% endif %}
            </td>
            <td style="color: var(--color-danger); max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ log.error_message|default:"—" }}</td>
          </tr>
          {% empty %}
          <tr>
            <td colspan="5" style="text-align: center; padding: var(--space-8); color: var(--text-muted);">No notifications sent yet</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Verify**

Run: Visit `/notifications/` and confirm channels, rules, and log table render correctly.

- [ ] **Step 3: Commit**

```bash
git add notifications/templates/notifications/list.html
git commit -m "style: redesign Notifications with rules and channels"
```

---

### Task 9: Redesign Context Page

**Files:**
- Modify: `context/templates/context/list.html`

- [ ] **Step 1: Rewrite context template**

Replace the entire content of `context/templates/context/list.html`:

```html
{% extends "base.html" %}

{% block title %}Context Map — NockCC{% endblock %}

{% block content %}
<div>
  <!-- Page header -->
  <div class="ncc-page-header">
    <div>
      <h1 class="ncc-page-title">Context Map</h1>
      <p class="text-muted text-sm" style="margin-top: var(--space-1);">{% if stats.last_sync %}Last sync: {{ stats.last_sync|timesince }} ago{% else %}Never synced{% endif %}</p>
    </div>
  </div>

  <!-- Stats -->
  <div class="ncc-kpi-row">
    <div class="ncc-kpi-card ncc-stagger">
      <p class="ncc-kpi-label">Total Docs</p>
      <p class="ncc-kpi-value">{{ stats.total }}</p>
    </div>
    <div class="ncc-kpi-card ncc-stagger">
      <p class="ncc-kpi-label">Healthy</p>
      <p class="ncc-kpi-value" style="color: var(--color-success);">{{ stats.healthy }}</p>
    </div>
    <div class="ncc-kpi-card ncc-stagger">
      <p class="ncc-kpi-label">Stale</p>
      <p class="ncc-kpi-value" style="color: {% if stats.stale %}var(--color-danger){% else %}var(--color-success){% endif %};">{{ stats.stale }}</p>
    </div>
    <div class="ncc-kpi-card ncc-stagger">
      <p class="ncc-kpi-label">Coverage</p>
      <p class="ncc-kpi-value" style="color: var(--accent-start);">
        {% if stats.total %}{{ stats.healthy|floatformat:0 }}/{{ stats.total }}{% else %}—{% endif %}
      </p>
    </div>
  </div>

  <!-- Filters -->
  <form method="get" class="ncc-filter-bar">
    <label for="filter-repo" class="sr-only">Repository</label>
    <select id="filter-repo" name="repo" class="ncc-select">
      <option value="">All Repos</option>
      {% for repo in repos %}
      <option value="{{ repo.name }}" {% if filters.repo == repo.name %}selected{% endif %}>{{ repo }}</option>
      {% endfor %}
    </select>
    <label for="filter-type" class="sr-only">Document Type</label>
    <select id="filter-type" name="type" class="ncc-select">
      <option value="">All Types</option>
      {% for value, label in doc_type_choices %}
      <option value="{{ value }}" {% if filters.type == value %}selected{% endif %}>{{ label }}</option>
      {% endfor %}
    </select>
    <label for="filter-stale" class="sr-only">Staleness</label>
    <select id="filter-stale" name="stale" class="ncc-select">
      <option value="">All</option>
      <option value="yes" {% if filters.stale == "yes" %}selected{% endif %}>Stale Only</option>
    </select>
    <button type="submit" class="ncc-btn ncc-btn-ghost ncc-btn-sm">Filter</button>
    {% if filters.repo or filters.type or filters.stale %}
    <a href="{% url 'context:list' %}" class="ncc-btn ncc-btn-ghost ncc-btn-sm">Clear</a>
    {% endif %}
  </form>

  <!-- Documents Table -->
  <div class="ncc-card ncc-stagger" style="padding: 0; overflow: hidden;">
    <div style="overflow-x: auto;">
      <table class="ncc-table">
        <thead>
          <tr>
            <th>Repo</th>
            <th>File Path</th>
            <th>Type</th>
            <th>Lines</th>
            <th>Last Modified</th>
            <th>Staleness</th>
          </tr>
        </thead>
        <tbody>
          {% for doc in documents %}
          <tr class="{% if doc.is_stale %}ncc-staleness-critical{% elif doc.days_since_modified is not None and doc.days_since_modified > 7 %}ncc-staleness-stale{% elif doc.days_since_modified is not None %}ncc-staleness-fresh{% endif %}">
            <td>{{ doc.repository.name }}</td>
            <td>
              <a href="{% url 'context:detail' doc.pk %}" class="font-mono" style="color: var(--text-primary); transition: color var(--transition-fast);">{{ doc.file_path }}</a>
            </td>
            <td>
              <span class="ncc-badge ncc-badge-draft">{{ doc.get_doc_type_display }}</span>
            </td>
            <td>{{ doc.line_count|default:"—" }}</td>
            <td style="color: var(--text-muted);">
              {% if doc.last_modified %}{{ doc.last_modified|timesince }} ago{% else %}Never{% endif %}
            </td>
            <td>
              {% if doc.days_since_modified is None %}
              <span class="ncc-badge ncc-badge-draft">Not synced</span>
              {% elif doc.is_stale %}
              <span class="ncc-badge ncc-badge-closed">{{ doc.days_since_modified }}d stale</span>
              {% elif doc.days_since_modified <= 3 %}
              <span class="ncc-badge ncc-badge-approved">Fresh</span>
              {% else %}
              <span class="ncc-badge ncc-badge-review">{{ doc.days_since_modified }}d</span>
              {% endif %}
            </td>
          </tr>
          {% empty %}
          <tr>
            <td colspan="6" style="text-align: center; padding: var(--space-8); color: var(--text-muted);">No documents tracked. Run: python manage.py register_context_docs</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Verify**

Run: Visit `/context/` and confirm stats, filters, table, and staleness indicators render correctly.

- [ ] **Step 3: Commit**

```bash
git add context/templates/context/list.html
git commit -m "style: redesign Context with staleness indicators"
```

---

### Task 10: Redesign Teams Page

**Files:**
- Modify: `teams/templates/teams/index.html`

The Teams page already uses some design system variables inline. The main changes are:
1. Replace `var(--border-subtle)` → `var(--bg-border)`, `var(--bg-raised)` → `var(--bg-surface-hover)`, `var(--text-tertiary)` → `var(--text-muted)`, `var(--border-hover)` → `var(--bg-border-hover)`, `var(--error)` → `var(--color-danger)`, `var(--success)` → `var(--color-success)`, `var(--warning)` → `var(--color-warning)`, `var(--accent-blue)` → `var(--accent-start)`, `var(--bg-void)` → `var(--bg-base)`
2. Replace `.ncc-accent-bg` inline usage with `ncc-btn ncc-btn-primary` classes
3. Replace custom `task-card` with `ncc-kanban-card` class
4. Replace `.ncc-card` (already correct) — keep as-is
5. Replace modal styling with `ncc-modal-overlay` and `ncc-modal` classes
6. Replace form inputs with `ncc-input` and `ncc-select` classes
7. Update page header to use `ncc-page-header` / `ncc-page-title`

- [ ] **Step 1: Rewrite teams template**

Replace the `<style>` block in `{% block extra_head %}` with updated CSS using design system variables. Replace the `{% block content %}` HTML with ncc-* classes. Preserve ALL Alpine.js x-data, x-model, x-for, @click bindings and the complete `teamsPage()` JavaScript function unchanged.

The key substitutions in the template HTML:
- `ncc-accent-bg hover:brightness-110 text-white` → `ncc-btn ncc-btn-primary ncc-btn-sm`
- `bg-[var(--bg-raised)] hover:bg-[var(--border-hover)] border border-[var(--border-subtle)]` → `ncc-btn ncc-btn-ghost ncc-btn-sm`
- `text-[var(--text-primary)]` → use `style="color: var(--text-primary);"`
- `text-[var(--text-secondary)]` → use `style="color: var(--text-secondary);"`
- `bg-[var(--bg-raised)]` → use `style="background-color: var(--bg-surface-hover);"`
- `border-[var(--border-subtle)]` → use `style="border-color: var(--bg-border);"`
- All modal containers → `ncc-modal-overlay` and `ncc-modal ncc-modal-md`
- All modal inputs → `ncc-input`
- All modal selects → `ncc-select`
- Page header: use `ncc-page-header` and `ncc-page-title`

**Important:** Keep all Alpine.js reactive bindings (x-data, x-model, x-for, x-show, x-if, @click, :class) EXACTLY as they are. Only change CSS classes and inline styles.

Write the complete new file. The `<style>` block should use design system variables:

```css
.kanban-col { min-height: 200px; }
.task-card {
    background: var(--bg-surface);
    border: 1px solid var(--bg-border);
    border-radius: var(--radius-lg);
    padding: 0.75rem;
    transition: border-color var(--transition-fast), transform var(--transition-fast);
}
.task-card:hover { border-color: var(--bg-border-hover); transform: translateY(-1px); }
.priority-critical { border-left: 3px solid var(--color-danger); }
.priority-high { border-left: 3px solid var(--color-warning); }
.priority-medium { border-left: 3px solid var(--accent-start); }
.priority-low { border-left: 3px solid var(--text-muted); }
.status-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.status-active { background: var(--color-success); box-shadow: 0 0 6px rgba(52,211,153,0.5); }
.status-idle { background: var(--color-warning); }
.status-offline { background: var(--text-muted); }
.kanban-header { border-top: 2px solid var(--text-muted); padding-top: 8px; }
.kanban-header[data-status="pending"] { border-color: var(--text-muted); }
.kanban-header[data-status="in_progress"] { border-color: var(--accent-start); }
.kanban-header[data-status="in_review"] { border-color: var(--accent-end); }
.kanban-header[data-status="blocked"] { border-color: var(--color-danger); }
.kanban-header[data-status="completed"] { border-color: var(--color-success); }
```

Then update all inline CSS variable references throughout the HTML from old names to design system names. The JavaScript `teamsPage()` function and `csrfHeaders()` function remain completely unchanged.

- [ ] **Step 2: Verify teams page renders**

Run: Visit `/teams/` and confirm team selector, agent roster, kanban board, activity feed, and all modals (new team, new task, task detail) work correctly.

- [ ] **Step 3: Commit**

```bash
git add teams/templates/teams/index.html
git commit -m "style: redesign Teams with agent cards and prompt queue"
```

---

### Task 11: Redesign Prompts Page

**Files:**
- Modify: `teams/templates/teams/prompts.html`

Apply the same variable renaming as Task 10. Replace custom CSS classes with design system equivalents:
- `.prompt-card` → keep custom but use design system variables
- `.status-badge` → use `ncc-badge` classes
- `.tag-pill` → use `ncc-badge ncc-badge-open`
- `.filter-pill` → use `ncc-tab`
- `.modal-overlay` → `ncc-modal-overlay`
- `.modal-content` → `ncc-modal ncc-modal-lg`
- Form inputs → `ncc-input`
- Form selects → `ncc-select`
- Page header → `ncc-page-header` / `ncc-page-title`
- Buttons → `ncc-btn ncc-btn-primary` / `ncc-btn ncc-btn-ghost`

The `promptLibrary()` JavaScript function remains completely unchanged.

- [ ] **Step 1: Update prompts template styles and classes**

Update the `<style>` block to use design system variables. Update HTML to use `ncc-*` classes where applicable. Keep all Alpine.js bindings unchanged.

- [ ] **Step 2: Verify prompts page renders**

Run: Visit `/prompts/` and confirm card grid, filters, create modal, and detail modal all work.

- [ ] **Step 3: Commit**

```bash
git add teams/templates/teams/prompts.html
git commit -m "style: redesign Prompts page with design system classes"
```

---

### Task 12: Redesign Remote Chat Page

**Files:**
- Modify: `remote/templates/remote/chat.html`

Match the AI Advisor (`intelligence/advisor.html`) visual style. Key changes:
1. Replace Tailwind classes with ncc-* classes and design system inline styles
2. Use `ncc-chat-container`, `ncc-chat-messages`, `ncc-chat-bubble-user`, `ncc-chat-bubble-assistant`, `ncc-chat-input-bar` classes
3. Use `ncc-select` for repo picker
4. Use `ncc-view-toggle` for chat/terminal toggle
5. Use `ncc-btn ncc-btn-ghost ncc-btn-sm` for control buttons
6. Use `ncc-btn ncc-btn-primary` for send button
7. Keep ALL JavaScript (`chatView()` function) completely unchanged
8. Keep the custom `.chat-md`, `.chat-terminal`, typing indicator, and tool-call CSS — these are chat-specific styles that don't have ncc-* equivalents

- [ ] **Step 1: Update chat template**

Update the HTML markup to use design system classes. Keep the `<style>` block for chat-specific CSS (markdown rendering, terminal view, typing indicators) but update colors to use design system variables. Replace Tailwind utility classes in HTML with ncc-* classes.

Key HTML changes:
- Top bar: use `ncc-page-header` layout, `ncc-select` for repo, `ncc-view-toggle` for chat/terminal
- Chat bubbles: replace `bg-brand-500/20 border border-brand-500/30` → `ncc-chat-bubble ncc-chat-bubble-user`
- Assistant bubbles: replace `bg-gray-800/80 border border-gray-700/50` → `ncc-chat-bubble ncc-chat-bubble-assistant`
- Input bar: replace inline classes → `ncc-chat-input-bar`, `ncc-input`, `ncc-btn ncc-btn-primary`
- History drawer: use `--bg-surface` background with `--bg-border`

- [ ] **Step 2: Verify chat renders**

Run: Visit `/remote/chat/` and confirm chat view, terminal view, conversation history, and input all work.

- [ ] **Step 3: Commit**

```bash
git add remote/templates/remote/chat.html
git commit -m "style: redesign Remote Chat to match Advisor style"
```

---

### Task 13: Responsive breakpoints for new pages

**Files:**
- Modify: `static/css/nockcc.css` (add responsive rules inside existing media queries)

- [ ] **Step 1: Add responsive rules for new components**

Add these rules inside the existing `@media (max-width: 1200px)` block:

```css
/* Charts: stack to 1 column on tablet */
.ncc-chart-wrap + .ncc-chart-wrap {
    margin-top: var(--space-4);
}
```

Add these rules inside the existing `@media (max-width: 767px)` block:

```css
/* Notifications: stack to 1 column */
/* Kanban: full width scroll */
.ncc-kanban-col {
    width: 200px;
    min-width: 200px;
}

/* Chart grid: single column */
```

- [ ] **Step 2: Test on mobile viewport**

Open Chrome DevTools, switch to mobile viewport (iPhone 14 Pro), and verify all redesigned pages are usable.

- [ ] **Step 3: Commit**

```bash
git add static/css/nockcc.css
git commit -m "style: add responsive breakpoints for remaining pages"
```

---

### Task 14: Documentation update and PR

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md` (if features changed)

- [ ] **Step 1: Update CHANGELOG.md**

Append entry for Phase 2:

```markdown
## [Unreleased] — 2026-04-06

### UI Reimagine Phase 2
- Redesigned Spend Dashboard with KPI cards, budget progress bar, styled tables, and design system chart colors
- Redesigned CRM Pipeline with kanban board and table view using ncc-* components
- Polished Tasks page with project summary cards, filter bar, priority dots, and overdue highlighting
- Redesigned Vault with document card grid, category icons, and tag badges
- Redesigned Teams page with design system variables and modal styling
- Redesigned Prompts page with design system badge and button classes
- Redesigned Remote Chat to match AI Advisor visual style
- Redesigned Notifications with channel status dots and rule cards
- Redesigned Context Map with staleness indicators and KPI stats
- Integrated actual Nock Technologies logo in sidebar and login page
- Added new CSS components: tabs, KPI row, kanban board, toggle switch, staleness indicators, chat bubbles, view toggle, filter bar, document grid, modals, chart wrappers
```

- [ ] **Step 2: Push branch and open PR**

```bash
git push -u origin feature/ui-reimagine-phase2
gh pr create --title "style: UI Reimagine Phase 2 — remaining pages" --body "$(cat <<'EOF'
## Summary
- Redesigned 9 remaining pages (Spend, CRM, Tasks, Vault, Teams, Prompts, Chat, Notifications, Context) to match Phase 1 design system
- Added 12 new CSS component classes to nockcc.css (tabs, kanban, toggles, chat, KPI, etc.)
- Integrated actual Nock logo in sidebar and login page
- No backend changes — pure frontend reskin

## Pages Redesigned
| Page | Key Changes |
|------|-------------|
| Spend | KPI cards, budget progress bar, styled tables, chart colors |
| CRM | Kanban board, view toggle, stage badges |
| Tasks | Project summary cards, filter bar, priority dots |
| Vault | Document card grid, category icons |
| Teams | Design system variables, modal styling |
| Prompts | Badge classes, button classes |
| Chat | Match Advisor style, chat bubbles |
| Notifications | Channel dots, rule cards |
| Context | Staleness indicators, KPI stats |

## Test plan
- [ ] Visual review of all 9 redesigned pages
- [ ] Verify sidebar logo renders (expanded + collapsed)
- [ ] Verify login page logo renders
- [ ] Test responsive layouts (mobile, tablet, desktop)
- [ ] Verify Alpine.js interactivity preserved (Teams kanban, Chat streaming, Prompts CRUD)
- [ ] Verify Chart.js renders with new colors (Spend page)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Commit CHANGELOG**

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for Phase 2 UI redesign"
git push
```
