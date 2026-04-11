# Design Refresh Phase 2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the emerald design system migration across all remaining app templates, remove the Phase 1 backwards-compat CSS aliases, and apply semantic color decisions for status states (pipeline open/merged, CRM stages, vault document types).

**Architecture:** Three categories of work: (1) bulk `sed` for templates where `var(--accent-start)` → `var(--color-accent)` is the correct replacement verbatim, (2) surgical edits for templates with semantic distinctions (open vs merged, active vs done), (3) CSS alias removal once all template inline styles are clean. No new dependencies.

**Tech Stack:** Django templates, vanilla CSS custom properties, Alpine.js. All changes are HTML/CSS — no Python changes needed.

**Branch:** `design/phase2-token-cleanup` (from `main`)
**Phase 1 plan:** `docs/superpowers/plans/2026-04-08-design-refresh-phase1.md`
**Design spec:** `docs/superpowers/specs/2026-04-08-design-refresh-design.md`
**Design context:** `.impeccable.md`

---

## Semantic Color Decisions

Before starting, internalize these replacements for status-bearing elements:

| Context | Old | New |
|---|---|---|
| Active / open / in-progress states | `var(--accent-start)` | `var(--color-accent)` (#10B981 emerald) |
| Done / merged / closed states | `var(--accent-end)` | `rgba(148, 163, 184, 0.15)` bg + `var(--text-secondary)` text |
| CRM negotiation stage | `var(--accent-end)` purple | `var(--color-warning)` (#FBBF24 amber) |
| CRM active stage | `var(--accent-start)` blue | `var(--color-accent)` (emerald) |
| Vault legal documents | `var(--accent-end)` purple | `var(--color-info)` (#06B6D4 cyan) |
| Vault insurance documents | `var(--accent-start)` blue | `var(--color-warning)` (#FBBF24 amber) |
| Teams complexity: standard | `var(--accent-start)` | `var(--color-accent)` (emerald) |
| Teams complexity: deep | `var(--accent-end)` | `var(--color-info)` (#06B6D4 cyan) |
| Raw `rgba(59, 111, 212,` (blue) | any opacity | replace with emerald equivalent |
| Raw `rgba(124, 92, 252,` (purple) | any opacity | replace with neutral/semantic color |

---

## File Map

**Bulk sed (simple swap only):**
- `brain/templates/brain/index.html` — 2 uses (filter button border-color)
- `context/templates/context/list.html` — 1 use (text color in style block)
- `intelligence/templates/intelligence/advisor.html` — 2 uses (AI bubble border-left)
- `remote/templates/remote/chat.html` — 5 uses (chat bubbles, links, terminal tool)
- `tasks/templates/tasks/feed.html` — 1 use (PR link color)
- `spend/templates/spend/dashboard.html` — 3 uses (KPI value colors)

**Semantic edits (surgical):**
- `pipeline/templates/pipeline/detail.html` — 3 uses (open=emerald, merged=neutral)
- `pipeline/templates/pipeline/list.html` — 5 uses (accent borders + repo/PR colors)
- `crm/templates/crm/pipeline.html` — 3 uses (negotiation=warning, active=emerald)
- `vault/templates/vault/list.html` — 2 uses (legal=info, insurance=warning)
- `teams/templates/teams/index.html` — 6 uses (PR numbers, kanban in-progress border)
- `teams/templates/teams/prompts.html` — 8 uses (standard=emerald, deep=info)

**CSS (alias removal):**
- `static/css/nockcc.css` lines 29-30 — remove `--accent-start` and `--accent-end`

---

## Task 1: Bulk Token Swap — 6 Simple Templates

**Files:**
- Modify: `brain/templates/brain/index.html`
- Modify: `context/templates/context/list.html`
- Modify: `intelligence/templates/intelligence/advisor.html`
- Modify: `remote/templates/remote/chat.html`
- Modify: `tasks/templates/tasks/feed.html`
- Modify: `spend/templates/spend/dashboard.html`

All of these use `var(--accent-start)` or `var(--accent-end)` in contexts where emerald is the correct replacement — no semantic distinction needed.

- [ ] **Step 1: Run sed across the 6 simple templates**

```bash
for f in \
  brain/templates/brain/index.html \
  context/templates/context/list.html \
  intelligence/templates/intelligence/advisor.html \
  remote/templates/remote/chat.html \
  tasks/templates/tasks/feed.html \
  spend/templates/spend/dashboard.html
do
  sed -i '' 's/var(--accent-start)/var(--color-accent)/g' "$f"
  sed -i '' 's/var(--accent-end)/var(--color-accent)/g' "$f"
done
```

- [ ] **Step 2: Verify — no remaining references in those 6 files**

```bash
grep -l "accent-start\|accent-end" \
  brain/templates/brain/index.html \
  context/templates/context/list.html \
  intelligence/templates/intelligence/advisor.html \
  remote/templates/remote/chat.html \
  tasks/templates/tasks/feed.html \
  spend/templates/spend/dashboard.html
```

Expected: empty output (no files listed).

- [ ] **Step 3: Commit**

```bash
git add \
  brain/templates/brain/index.html \
  context/templates/context/list.html \
  intelligence/templates/intelligence/advisor.html \
  remote/templates/remote/chat.html \
  tasks/templates/tasks/feed.html \
  spend/templates/spend/dashboard.html
git commit -m "style: swap accent-start/end → color-accent in 6 simple templates"
```

---

## Task 2: Pipeline Templates — Semantic Open/Merged Colors

**Files:**
- Modify: `pipeline/templates/pipeline/detail.html`
- Modify: `pipeline/templates/pipeline/list.html`

Open PRs → emerald. Merged/done PRs → neutral gray.

- [ ] **Step 1: Fix `pipeline/templates/pipeline/detail.html`**

This file has:
- Line 27: `.timeline-dot-open { border-color: var(--accent-start); background: rgba(59, 111, 212, 0.15); }`
- Line 28: `.timeline-dot-merged { border-color: var(--accent-end); background: rgba(124, 92, 252, 0.15); }`
- Line 74: `style="color:var(--accent-end);"` on merged timestamp

Read the file, then make these exact replacements:

Replace the two timeline dot classes:
```css
.timeline-dot-open    { border-color: var(--color-accent); background: var(--color-accent-dim); }
.timeline-dot-merged  { border-color: var(--bg-border-hover); background: rgba(148, 163, 184, 0.1); }
```

Replace the merged timestamp inline style:
```html
<span style="color:var(--text-secondary);">merged {{ pr.merged_at|timesince }} ago</span>
```

- [ ] **Step 2: Fix `pipeline/templates/pipeline/list.html`**

This file has:
- Lines 8-9: `.pr-accent-open` and `.pr-accent-merged` border-left classes
- Lines 107, 180: repo name color (emerald is correct — these are active navigation)
- Line 184: `onmouseover="this.style.color='var(--accent-start)'"` — inline JS hover

Replace lines 8-9:
```css
.pr-accent-open    { border-left: 3px solid var(--color-accent); }
.pr-accent-merged  { border-left: 3px solid var(--bg-border-hover); }
```

Replace all `var(--accent-start)` in the file with `var(--color-accent)`:
```bash
sed -i '' 's/var(--accent-start)/var(--color-accent)/g' pipeline/templates/pipeline/list.html
sed -i '' "s/this.style.color='var(--accent-start)'/this.style.color='var(--color-accent)'/g" pipeline/templates/pipeline/list.html
```

Then replace `var(--accent-end)` (merged) with neutral:
```bash
sed -i '' 's/var(--accent-end)/var(--text-secondary)/g' pipeline/templates/pipeline/list.html
```

- [ ] **Step 3: Verify no remaining old tokens in pipeline templates**

```bash
grep -n "accent-start\|accent-end\|rgba(59, 111\|rgba(124, 92" \
  pipeline/templates/pipeline/detail.html \
  pipeline/templates/pipeline/list.html
```

Expected: empty output.

- [ ] **Step 4: Commit**

```bash
git add pipeline/templates/pipeline/detail.html pipeline/templates/pipeline/list.html
git commit -m "style: pipeline templates — emerald open PRs, neutral merged PRs"
```

---

## Task 3: CRM, Vault, Teams — Semantic Stage Colors

**Files:**
- Modify: `crm/templates/crm/pipeline.html`
- Modify: `vault/templates/vault/list.html`
- Modify: `teams/templates/teams/index.html`
- Modify: `teams/templates/teams/prompts.html`

- [ ] **Step 1: Fix `crm/templates/crm/pipeline.html`**

This file has 3 uses:
- Line 18: `.ncc-badge-negotiation { background-color: rgba(124, 92, 252, 0.15); color: var(--accent-end); }` → amber (negotiation = high stakes)
- Line 19: `.ncc-badge-active { background-color: rgba(59, 111, 212, 0.15); color: var(--accent-start); }` → emerald (active = in progress)
- Line 106: `style="color:var(--accent-start);"` on deal title → emerald

Make these exact replacements:

```css
.ncc-badge-negotiation { background-color: rgba(251, 191, 36, 0.12); color: var(--color-warning); }
.ncc-badge-active      { background-color: var(--color-accent-dim); color: var(--color-accent); }
```

For line 106 deal title:
```bash
sed -i '' 's/style="color:var(--accent-start);"/style="color:var(--color-accent);"/g' crm/templates/crm/pipeline.html
```

- [ ] **Step 2: Fix `vault/templates/vault/list.html`**

This file has 2 uses in a style block:
- Line 10: `.vault-icon-legal { background: rgba(124, 92, 252, 0.12); color: var(--accent-end); }` → cyan/info
- Line 12: `.vault-icon-insurance { background: rgba(59, 111, 212, 0.12); color: var(--accent-start); }` → amber/warning

Replace:
```css
.vault-icon-legal      { background: rgba(6, 182, 212, 0.12); color: var(--color-info); }
.vault-icon-insurance  { background: rgba(251, 191, 36, 0.12); color: var(--color-warning); }
```

- [ ] **Step 3: Fix `teams/templates/teams/index.html`**

This file has 6 uses — all are `var(--accent-start)` for PR number links and the in-progress kanban column border. All should be emerald:

```bash
sed -i '' 's/var(--accent-start)/var(--color-accent)/g' teams/templates/teams/index.html
sed -i '' 's/var(--accent-end)/var(--color-accent)/g' teams/templates/teams/index.html
```

Also fix raw hardcoded blue rgba if present:
```bash
sed -i '' 's/rgba(59, 111, 212,/rgba(16, 185, 129,/g' teams/templates/teams/index.html
```

- [ ] **Step 4: Fix `teams/templates/teams/prompts.html`**

This file uses both standard (emerald) and deep (cyan/info) complexity levels:

```bash
# Standard complexity → emerald
sed -i '' 's/var(--accent-start)/var(--color-accent)/g' teams/templates/teams/prompts.html
```

Then for deep complexity badges specifically — read the file to find lines 20-31 (the style block) and replace:

Find:
```css
.complexity-deep { border-left: 3px solid var(--accent-end); }
.complexity-badge.standard { background: rgba(59,111,212,0.1); color: var(--accent-start); }
.complexity-badge.deep { background: rgba(124,92,252,0.1); color: var(--accent-end); }
```

Replace with:
```css
.complexity-deep { border-left: 3px solid var(--color-info); }
.complexity-badge.standard { background: var(--color-accent-dim); color: var(--color-accent); }
.complexity-badge.deep { background: rgba(6, 182, 212, 0.1); color: var(--color-info); }
```

- [ ] **Step 5: Verify — no remaining old tokens in these 4 files**

```bash
grep -n "accent-start\|accent-end\|rgba(59, 111\|rgba(124, 92" \
  crm/templates/crm/pipeline.html \
  vault/templates/vault/list.html \
  teams/templates/teams/index.html \
  teams/templates/teams/prompts.html
```

Expected: empty output.

- [ ] **Step 6: Commit**

```bash
git add \
  crm/templates/crm/pipeline.html \
  vault/templates/vault/list.html \
  teams/templates/teams/index.html \
  teams/templates/teams/prompts.html
git commit -m "style: semantic colors for CRM stages, vault doc types, team complexity badges"
```

---

## Task 4: Remove CSS Compat Aliases

**Files:**
- Modify: `static/css/nockcc.css:29-30`

The Phase 1 backwards-compat aliases were only needed while templates still referenced the old tokens. Once Tasks 1-3 are complete, these aliases are dead code.

- [ ] **Step 1: Verify zero remaining template references**

```bash
grep -rn "var(--accent-start)\|var(--accent-end)" --include="*.html" .
```

Expected: empty output. If any files appear, go fix them before continuing.

- [ ] **Step 2: Remove the compat alias lines from nockcc.css**

Find and remove these exact lines from the `:root` block in `static/css/nockcc.css`:
```css
  /* Phase 1 backwards-compat aliases — templates using these inline
     will now render emerald instead of blue-purple.
     Remove these in Phase 2 when all template inline styles are cleaned up. */
  --accent-start: var(--color-accent);
  --accent-end:   var(--color-accent);
```

After removal, verify the `:root` block no longer contains either alias:
```bash
grep "accent-start\|accent-end" static/css/nockcc.css
```

Expected: empty output.

- [ ] **Step 3: Commit**

```bash
git add static/css/nockcc.css
git commit -m "style: remove Phase 1 accent-start/end compat aliases — all templates migrated"
```

---

## Task 5: Final Verification + CHANGELOG + PR

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Ruff lint**

```bash
/Users/kevin/Dev/nock-command-center/.venv/bin/ruff check . --fix
```

Expected: `All checks passed!` Fix anything that appears.

- [ ] **Step 2: Full test suite**

```bash
DJANGO_SETTINGS_MODULE=config.settings.dev \
  /Users/kevin/Dev/nock-command-center/.venv/bin/pytest -q 2>&1 | tail -5
```

Expected: `3 failed, 677+ passed` — only the 3 pre-existing failures (`test_not_quiet_hours`, `test_quiet_hours_midnight_crossing`, `test_mobile_bottom_nav_present`). No new failures.

- [ ] **Step 3: Global grep — no old tokens anywhere**

```bash
echo "=== HTML templates ===" && \
grep -rn "accent-start\|accent-end\|rgba(59, 111, 212\|rgba(124, 92, 252" --include="*.html" . || echo "CLEAN"

echo "=== CSS ===" && \
grep -n "accent-start\|accent-end\|rgba(59, 111\|rgba(124, 92\|3B6FD4\|7C5CFC" static/css/nockcc.css || echo "CLEAN"
```

Expected: both show CLEAN.

- [ ] **Step 4: Update CHANGELOG.md**

Prepend this entry at the top of `CHANGELOG.md`:

```markdown
## [Unreleased] — 2026-04-08

### Changed (Phase 2)
- Completed emerald design system migration across all 11 remaining app templates
- Removed Phase 1 backwards-compat `--accent-start`/`--accent-end` CSS aliases
- Pipeline: open PRs → emerald border, merged PRs → neutral gray (semantic distinction)
- CRM: negotiation stage → amber, active stage → emerald (semantic distinction)
- Vault: legal documents → cyan, insurance documents → amber (type-coded icons)
- Teams: standard complexity → emerald, deep complexity → cyan (complexity scale)
- All templates now use canonical `--color-accent` token directly

```

- [ ] **Step 5: Commit CHANGELOG**

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for Phase 2 design migration"
```

- [ ] **Step 6: Push and open PR**

```bash
git push origin design/phase2-token-cleanup
```

```bash
gh pr create \
  --title "style: Phase 2 design refresh — complete token migration, remove compat aliases" \
  --body "$(cat <<'EOF'
## Summary
- Completes emerald design system migration across all remaining 11 app templates
- Removes the Phase 1 `--accent-start`/`--accent-end` backwards-compat aliases — all templates now use `--color-accent` directly
- Applies semantic color decisions: pipeline open/merged, CRM stages, vault doc types, teams complexity badges

## Semantic color choices
- **Pipeline**: open PRs → emerald border, merged → neutral gray
- **CRM**: negotiation → amber, active → emerald
- **Vault**: legal → cyan (`--color-info`), insurance → amber (`--color-warning`)
- **Teams complexity**: standard → emerald, deep → cyan

## Test plan
- [ ] `pytest -q` — only 3 pre-existing failures
- [ ] `ruff check .` — clean
- [ ] `grep "accent-start\|accent-end" --include="*.html" -r .` → empty
- [ ] `grep "accent-start\|accent-end" static/css/nockcc.css` → empty
- [ ] Pipeline list: open PRs have emerald left border, merged have gray
- [ ] CRM pipeline: negotiation cards have amber badge, active have emerald
- [ ] Vault list: legal icon is cyan, insurance icon is amber

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
