# PR 1 — Strip Personal Layers from Nock Dashboard

**Status:** EXECUTED 2026-04-11 — checkpoints 0-8 complete, PR opened as nocktechnologies/nock-dashboard#2

## Actual counts (post-execution, captured at checkpoint 8)

| Metric | Before | After | Delta |
|---|---|---|---|
| Files deleted entirely | — | 10 | — |
| Files edited surgically | — | ~20 | — |
| Brain migration chain length | 10 | 7 | −3 |
| Brain test count (explicit) | 281 | 165 | −116 (57 diary + 50 identity + 4 security date + 2 continuity seed + 2 views seed + 1 vacuous continuity-seed-has-tags removed during re-review) |
| Main pytest suite | 760 passed / 2 failed | 760 passed / 2 failed | 0 (matches PR 0 baseline; the 2 failures are the pre-existing TZ issues) |
| Mara strings in hard-target files | 6 files with refs | 0 | all clean |
| DiaryEntry / IdentityDocument code refs | present | 0 in code (docs-only meta-references in CHANGELOG, plan doc, test_security docstring) | all clean |
| manage.py check | clean | clean | — |
| makemigrations --check --dry-run | 2 pending (pre-existing drift, resolved in PR 0) | No changes detected | clean |

**Checkpoint commits (on `feature/strip-personal-layers`, on top of `main@4298a1b`):**
- `f15b26b` docs(pr-1): add PR 1 plan
- `c2c711b` checkpoint 0: baseline captured
- `64a7059` checkpoint 1: unroute diary/identity endpoints
- `e3d3308` checkpoint 2: delete view modules
- `db1d34e` checkpoint 3: delete/rewrite tests
- `5ae9c0c` checkpoint 4: strip Mara branding + branding sweep
- `e0a74e3` checkpoint 5: generic AI prompts in intelligence layer
- `e6dd221` checkpoint 6: delete DiaryEntry + IdentityDocument models, rewrite migration chain
- `f2fa02d` checkpoint 7: CHANGELOG product-fork section
- `(this commit)` checkpoint 8: verification
**Review outcomes (all 7 questions from §5):**
1. Delete `.claude/SKILL_IN_CHAT_HANDOFF.md` (Mara-specific, product has `HandoffEntry`)
2. Rewrite `brain/tests/test_security.py` against `/api/brain/memory/` (preserve security coverage)
3. Migration renumbering approved — document `rm db.sqlite3 && migrate` requirement in CHANGELOG + README
4. Dashboard layout hole: fill the slot with an existing card (Kit's judgment call during checkpoint 1)
5. Docs deferred to PR 6 — only CHANGELOG entry lands in PR 1
6. `.claude/review/PIPELINE.md` "Mara reviews" stays — in the product context Mara is the AI architecture reviewer role, not a personal artifact
7. Code-level brand stays "NockCC" until PR 5/6 — no display-brand changes in PR 1
**Owner:** Kit (Claude)
**Branch:** `feature/strip-personal-layers` (created 2026-04-11, 10 checkpoint commits pushed, PR open as nocktechnologies/nock-dashboard#2)
**Depends on:** `main` at `4298a1b` (the merge commit for PR 0 — `chore(fork): backfill notifications, remote, vault`). The original plan referenced `40045de` but that base was superseded mid-execution by the fork-backfill work; feature/strip-personal-layers was rebased onto PR 0's merge commit before checkpoint 6 landed.
**Target:** First real feature PR in the product-fork pipeline. Full 7-phase engineering standards apply.

---

## 1. Goal

Cut the personal-continuity surface (diary, identity documents, Mara/Kevin-specific framing) out of the nock-dashboard codebase while leaving every product-grade feature (pipeline, sessions, spend, tasks, research library, handoffs, AI advisor shell, morning note shell, weekly memo shell, CRM, teams, prompt queue, remote agent, notifications) functional for a generic customer.

The AI advisor, morning note, and weekly memo become **generic "here's your project status"** surfaces. No diary, no identity docs, no FUZZY. Clean cut, no feature flags, no backward-compat shims.

The output of this PR is a codebase that **builds, migrates, passes tests, and renders** — but is still single-tenant (auth + tenancy come in PR 2 and PR 3). Nothing in this PR touches auth, billing, or multi-tenant data isolation.

---

## 2. Deletion Inventory

Scanned at 2026-04-11. `terminal-electron/node_modules/**` and `docs/superpowers/**` excluded from the code surface (docs get touched in PR 6; node_modules is vendored JS junk). MCP server references are N/A — `mcp_server/` does not exist in the current fork snapshot (fork was taken before MCP server was merged to NockCC; that's a gap for a later PR, not this one).

### 2a. Models — `brain/models.py`

| Model | Action | Notes |
|---|---|---|
| `MemoryEntry` | **Keep** | Product-grade; used by advisor context, morning note continuity section |
| `ConsolidationLog` | **Keep** | Operational — tracks MemoryEntry consolidation runs |
| `MorningNoteSent` | **Keep** | Atomic per-day claim for morning note idempotency |
| `DiaryEntry` | **DELETE** | Personal continuity layer |
| `IdentityDocument` | **DELETE** | Identity docs (MARA_CORE, KEVIN_CORE) |
| `IdentityDocumentVersion` | **DELETE** | Version history for IdentityDocument |
| `HandoffEntry` | **Keep** | Operational state tracking — product feature |
| `HandoffVersion` | **Keep** | Version history for HandoffEntry |
| `ResearchDocument` | **Keep** | Research library feature |
| `ResearchChunk` | **Keep** | pgvector chunks |

**Note on `MemoryEntry.CATEGORY_CHOICES`:** contains `("identity", "Identity")`. This is a general category (e.g., "who is this customer") not tied to the deleted `IdentityDocument` model. **Keep the choice** — it's still a valid memory category for a generic user. Same for `("personal", "Personal")` and `("relationship", "Relationship")`.

**Scan for `is_private` flag:** zero real hits in code (only node_modules false positives). The flag the spec mentions does **not exist** in this fork. Nothing to remove.

**Scan for `FUZZY`, `MARA_CORE`, `KEVIN_CORE` symbols:** zero real hits in code (only node_modules + `seed_identity.py` + `test_identity.py` + `SKILL_IN_CHAT_HANDOFF.md`). All three go with the deletions below.

### 2b. Files to delete entirely

```text
brain/diary_views.py                                   # 446+ lines, all diary API views
brain/views_identity.py                                # identity CRUD + /boot endpoint
brain/management/commands/migrate_diary_from_asana.py  # one-shot Asana importer
brain/management/commands/seed_identity.py             # MARA_CORE / KEVIN_CORE / FUZZY seeds
brain/templates/brain/diary.html                       # "Mara's Diary" browser page
brain/tests/test_diary.py                              # diary API test suite (~500+ lines)
brain/tests/test_identity.py                           # identity API test suite (~600+ lines)
brain/migrations/0006_diary_entry.py                   # DiaryEntry creation
brain/migrations/0007_fix_diary_entry_indexes.py       # DiaryEntry index tweak
brain/migrations/0008_identity_documents.py            # IdentityDocument + Version creation
.claude/SKILL_IN_CHAT_HANDOFF.md                       # Mara-specific handoff skill doc
```

**Note on migrations:** deleting migration files is safe here because nock-dashboard has no production DB yet (fresh Railway project comes in PR 6). Local `db.sqlite3` is throwaway and will be deleted in this PR. A new squashed migration chain (or a replacement `0006_drop_personal_models.py`) will rewrite the schema without the personal tables. See §4 for strategy.

### 2c. Files to modify (surgical deletions within)

**`brain/models.py`**
- Delete `DiaryEntry`, `IdentityDocument`, `IdentityDocumentVersion` classes
- Keep everything else as-is

**`brain/admin.py`**
- Delete `DiaryEntryAdmin`, `IdentityDocumentAdmin`, `IdentityDocumentVersionAdmin` registrations
- Delete `DiaryEntry`, `IdentityDocument`, `IdentityDocumentVersion` imports
- Keep everything else

**`brain/urls.py`**
- Delete `diary_views` import
- Delete `path("diary/", diary_views.diary_browser, ...)` line
- Result: brain app serves `/brain/`, `/brain/handoffs/`, `/brain/research/` only

**`config/urls.py`**
- Delete `diary_views` and `views_identity` from the `from brain import ...` line
- Delete the `path("api/brain/diary/...", ...)` block (5 routes)
- Delete the `path("api/brain/identity/...", ...)` block (4 routes)
- Keep handoffs, research, and memory routes

**`brain/apps.py`**
- Change `verbose_name = "Mara's Brain"` → `verbose_name = "Brain"`

**`brain/templates/brain/index.html`**
- Change `<h1 class="ncc-page-title">Mara's Brain</h1>` → `<h1 class="ncc-page-title">Brain</h1>`
- Review page title and any other Mara-specific strings

**`brain/templates/brain/handoffs.html`**
- Change `"Mara's evening-wrap cron writes the first handoff."` → generic equivalent ("The evening-wrap cron writes the first handoff." or remove if low-value)

**`brain/services.py`**
- `MorningNoteGenerator.__doc__`: `"Generate Mara's Morning Note for Telegram."` → `"Generate the daily morning note for Telegram."`
- Line 249: `"\u2600\ufe0f *Mara's Morning Note* ..."` → `"\u2600\ufe0f *Morning Note* ..."` (or configurable brand string from settings)
- Line 153 inside `_should_promote_entry`: `entry.source in ("session", "diary")` → `entry.source in ("session",)`. The `"diary"` source was a signal from the (now-deleted) diary ingestion path; sessions is the only surviving structured source.

**`intelligence/services.py`** (`generate_morning_question`)
- System prompt `"You are Mara, generating a single thoughtful question for Kevin's morning commute..."` → strip Mara/Kevin framing, make it a generic "Generate one reflective morning question based on recent project context." The function continues to pull from `MemoryEntry` (continuity/project/decision categories) which remains valid.
- Docstring references to "Kevin's morning commute" → generic "the user's morning".

**`intelligence/tasks.py`** (`generate_weekly_memo`)
- System prompt `"You are the Chief of Staff for Nock Technologies, a bootstrapped commercial finance technology company. You produce a weekly strategy memo for the founder, Kevin Wills..."` → generic "You are an executive assistant generating a weekly strategy memo from the user's business data." The sections list (WEEK IN REVIEW, FINANCIAL SNAPSHOT, PIPELINE UPDATE, DEVELOPMENT PROGRESS, ATTENTION REQUIRED, PRIORITIES FOR NEXT WEEK) is generic and stays.

**`intelligence/views.py`** (`_build_advisor_system_prompt`)
- `"You are the AI Business Advisor for Nock Technologies, a bootstrapped commercial finance technology company founded by Kevin Wills..."` → generic "You are the AI Business Advisor for this user's business. You have access to real business data..." The guidelines bullet list stays unchanged.

**`teams/views.py` (line 992) and `teams/signals.py` (line 215)**
- `f"⚠️ PR #{pr_number} exceeded max review cycles — needs Kevin"` → `f"⚠️ PR #{pr_number} exceeded max review cycles — needs review"`. These fire in Telegram overflow alerts.

**`brain/management/commands/ingest_research.py`** (line 2)
- Docstring `"walk Mara's vault directory and import markdown files..."` → `"walk a research vault directory and import markdown files..."`

**`brain/views_research.py`** (line 3)
- Docstring `"Research Library API — semantic search over Mara's research corpus."` → `"Research Library API — semantic search over the user's research corpus."`

**`dashboard/templates/dashboard/index.html`**
- Delete the "Mara's Diary" stats card block (lines 272–295 area — the diary panel with `total_entries`, `total_words`, `entries_this_week`)
- Delete the `diary: { total_entries: 0, ... }` state and `refreshDiary()` method in the Alpine component (lines 611, 633, 687–706)
- Delete the two `fetch('/api/brain/diary/...')` calls
- Verify the dashboard still renders a full grid without a hole where the diary card was — may need a layout adjustment (e.g., one less column on that row)

**`templates/base.html`**
- Delete the sidebar nav link for Diary (lines 88–91 — the `<a href="/brain/diary/">` block with Diary label)

**`dashboard/tests/test_pm_views.py`**
- Inspect for diary-related assertions; remove/adjust

**`brain/tests/test_security.py`**
- This file asserts diary API auth behavior (API key, CORS). Since the diary endpoints are gone, either delete the whole file or rewrite the tests against a surviving endpoint (e.g., memory or handoffs) to preserve the security contract coverage. **Proposal:** rewrite `test_security.py` to target `/api/brain/memory/` — that's the cleanest product-value-preserving path.

**`brain/tests/test_continuity.py`**
- Test `"Mara's Morning Note"` string assertion (line 306). Update to whatever the new morning note header becomes (likely `"Morning Note"` or from settings).

**`brain/tests/test_tasks.py`**
- Check for DiaryEntry references (appeared in `Mara` grep); update or delete as appropriate.

**`brain/migrations/0002_seed_memory_entries.py`**
- This is a data migration that seeds Mara-specific MemoryEntries ("Mara. Senior developer + project manager partner to Kevin Wills", etc.). Options:
  - **A.** Convert to a no-op (empty forward, empty reverse). Preserves the migration number so the chain stays linear.
  - **B.** Delete the file and renumber. Risks breaking the linear migration chain and invalidating `django_migrations` in any DB that has this applied.
  - **Proposal: option A.** Replace the file's content with an empty forward/reverse, keep the number 0002. Safe, reversible, no renumbering cascade.

**`brain/migrations/0004_seed_continuity_entries.py`**
- Same situation as 0002 — personal continuity entries. **Proposal: option A (empty no-op).**

### 2d. Local database

- Delete `/Users/kevin/Dev/nock-dashboard/db.sqlite3` entirely. New fresh DB for dev. The throwaway dev data (the fork's copy of Mara's diary) goes with it. Real data lives in NockCC striking-serenity Postgres and is untouched.

---

## 3. Execution order (layered)

The order minimizes broken-state windows so `manage.py check`, `migrate`, and the test suite stay meaningful at each checkpoint.

**Checkpoint 0 — Baseline**
- `git checkout -b feature/strip-personal-layers`
- Delete `db.sqlite3`
- Run `python manage.py check` — capture baseline (expect clean)
- Run `python manage.py migrate --run-syncdb` against a fresh sqlite to confirm migrations apply cleanly
- Run full test suite `pytest` — capture baseline pass/fail. This is **our reference**; anything that was green and is now red because of our changes is a regression, anything that was red before is pre-existing.

**Checkpoint 1 — URL layer (no code deletion yet; just route removal)**
- Edit `config/urls.py`: remove `diary_views`, `views_identity` imports + route registrations
- Edit `brain/urls.py`: remove `diary_views` import + `/brain/diary/` route
- Edit `templates/base.html`: remove Diary nav link
- Edit `dashboard/templates/dashboard/index.html`: remove diary stats card + JS
- Run `python manage.py check` — should pass (views still exist; they're just unrouted)
- Run `pytest brain/tests/test_diary.py brain/tests/test_identity.py` — expect failures (404s now). **Note: we'll delete these test files in checkpoint 3, so red here is fine.**
- Run remaining brain tests — should pass

**Checkpoint 2 — Views and templates**
- `rm brain/diary_views.py brain/views_identity.py brain/templates/brain/diary.html`
- Run `python manage.py check` — expect `NameError` / `ModuleNotFoundError` if anything still imports these. Fix any surviving imports (should be zero after checkpoint 1). Re-run until green.
- `rm brain/management/commands/migrate_diary_from_asana.py brain/management/commands/seed_identity.py`

**Checkpoint 3 — Tests**
- `rm brain/tests/test_diary.py brain/tests/test_identity.py`
- Rewrite `brain/tests/test_security.py` to target `/api/brain/memory/` instead of `/api/brain/diary/` (preserves security contract coverage)
- Fix `brain/tests/test_continuity.py` (morning note header string) and `brain/tests/test_tasks.py` (DiaryEntry references) as needed.
- Run `pytest brain/tests/` — all green

**Checkpoint 4 — Admin, apps, templates (surgical edits)**
- Edit `brain/admin.py`: remove DiaryEntry / IdentityDocument registrations + imports
- Edit `brain/apps.py`: verbose_name "Mara's Brain" → "Brain"
- Edit `brain/templates/brain/index.html`: "Mara's Brain" → "Brain"
- Edit `brain/templates/brain/handoffs.html`: Mara wording
- Edit `brain/services.py`: MorningNoteGenerator docstring + header string + `"diary"` source filter
- Edit `brain/views_research.py`: docstring
- Edit `brain/management/commands/ingest_research.py`: docstring
- Run `python manage.py check` — expect clean

**Checkpoint 5 — Intelligence layer (advisor/memo/morning question)**
- Edit `intelligence/services.py`: generic system prompt for morning question
- Edit `intelligence/tasks.py`: generic system prompt for weekly memo
- Edit `intelligence/views.py`: generic system prompt for AI advisor
- Edit `teams/views.py` and `teams/signals.py`: "needs Kevin" → "needs review"
- Run `pytest intelligence/ teams/` — should pass

**Checkpoint 6 — Models and migrations**
- Edit `brain/models.py`: delete `DiaryEntry`, `IdentityDocument`, `IdentityDocumentVersion`
- `rm brain/migrations/0006_diary_entry.py brain/migrations/0007_fix_diary_entry_indexes.py brain/migrations/0008_identity_documents.py`
- Replace `brain/migrations/0002_seed_memory_entries.py` and `brain/migrations/0004_seed_continuity_entries.py` with no-op content (empty forward, empty reverse, same migration number + dependencies)
- **Add a new migration** `brain/migrations/0006_drop_personal_models.py` with `DeleteModel` operations for DiaryEntry, IdentityDocument, IdentityDocumentVersion. This is the replacement for the three deleted migrations — Django will see the deletion and generate the DROP TABLE. Actually since we deleted the source migrations this is only needed if any environment has them applied. Since there's no prod DB yet, we can just **rewrite the chain**: renumber to keep 0006 linear.
  - **Cleaner plan:** renumber the surviving migrations so 0005 (morning_note_sent) stays, 0006 becomes `0006_research_library.py` (was 0009), 0007 becomes `0007_handoffentry_handoffversion.py` (was 0010). Delete the three personal-model migrations. Update `dependencies` arrays accordingly.
  - **Risk:** renumbering breaks any DB that has the old chain applied. We have no such DB in the product fork (no prod, throwaway dev). Safe.
- Delete `db.sqlite3`, run `python manage.py makemigrations --check --dry-run brain` — expect "No changes detected" if the chain is consistent
- Run `python manage.py migrate` against fresh sqlite — should apply cleanly
- Run full test suite — all green

**Checkpoint 7 — Docs housekeeping (minimal)**
- Update `CHANGELOG.md` with a new entry documenting the strip (what was removed, why, forward plan)
- Leave `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `CODEX.md`, `DESIGN_CLAUDE_COMMAND_CENTER.md`, `docs/superpowers/**` for **PR 6 (Docs + deployment)**. They're still accurate descriptions of the NockCC source; rewriting them now would explode this PR's scope.
- Leave `.claude/review/PIPELINE.md` as-is for now (Mara reference is in a review-pipeline doc, not code)

**Checkpoint 8 — Full verification (Phase 3 of the 7-phase pipeline)**
- `python manage.py check` — clean
- `python manage.py makemigrations --check --dry-run` — no pending
- `python manage.py migrate` against fresh sqlite — clean
- `pytest` full suite — all green (or documented pre-existing failures from baseline)
- `grep -ri "diary\|identity document\|MARA_CORE\|KEVIN_CORE\|FUZZY" --include="*.py" --include="*.html"` excluding node_modules — should return zero hits
- `grep -r "Mara\|Kevin" --include="*.py"` excluding node_modules — should return only: code comments that still make sense as historical context, test fixture strings that don't assert personal identity, docs that PR 6 will handle. **Hard targets:** `intelligence/services.py`, `intelligence/tasks.py`, `intelligence/views.py`, `brain/services.py`, `teams/views.py`, `teams/signals.py` should have **zero** Mara/Kevin strings.

Then the PR heads into Phase 4 (Codex gate), Phase 5 (push + auto-review), Phase 6 (human review), Phase 7 (merge + deploy).

---

## 4. Migration strategy — detailed

The trick: we want a clean linear migration chain with no dangling references to deleted models, and no prod-DB to worry about.

**Current chain:**
```text
0001_initial             → MemoryEntry
0002_seed_memory_entries → data: seeds Mara-specific memories (delete content → no-op)
0003_add_continuity_and_consolidation_log → continuity category + ConsolidationLog
0004_seed_continuity_entries → data: seeds continuity (delete content → no-op)
0005_morning_note_sent   → MorningNoteSent
0006_diary_entry         → DiaryEntry (DELETE ENTIRE FILE)
0007_fix_diary_entry_indexes → index tweak on DiaryEntry (DELETE ENTIRE FILE)
0008_identity_documents  → IdentityDocument + IdentityDocumentVersion (DELETE ENTIRE FILE)
0009_research_library    → ResearchDocument + ResearchChunk (RENAME → 0006)
0010_handoffentry_handoffversion → HandoffEntry + HandoffVersion (RENAME → 0007)
```

**Target chain:**
```text
0001_initial                            → unchanged
0002_seed_memory_entries                → content replaced with empty no-op, number kept
0003_add_continuity_and_consolidation_log → unchanged
0004_seed_continuity_entries            → content replaced with empty no-op, number kept
0005_morning_note_sent                  → unchanged
0006_research_library                   → renamed from 0009, dependencies updated
0007_handoffentry_handoffversion        → renamed from 0010, dependencies updated
```

**Why empty no-op instead of delete-and-renumber for 0002 and 0004:** renumbering data migrations that might have been applied in a dev DB (even throwaway) creates `django_migrations` drift. Keeping the number and emptying the content is bulletproof and costs zero runtime. The no-op file:

```python
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [("brain", "0001_initial")]   # same deps as before
    operations = []  # personal seeds removed in the product fork
```

**Why renumber 0009 and 0010 instead of leaving gaps:** a chain with holes (0005 → 0009) looks broken to anyone reading it. Renumbering is a one-time cost with no runtime downside since no DB has the old numbers applied in prod. The local `db.sqlite3` gets deleted at the start of the PR.

---

## 5. Risks and open questions

1. **Migration chain rewrite is destructive to local dev DBs.** Anyone with a `db.sqlite3` from pre-fork will need to `rm db.sqlite3 && python manage.py migrate` after this PR. Since the dev DB is throwaway and already scheduled for deletion in checkpoint 0, this is fine — but worth a CHANGELOG note.

2. **`brain/tests/test_security.py` rewrite is non-trivial.** The file currently asserts auth/CORS behavior against `/api/brain/diary/`. Rewriting it against `/api/brain/memory/` preserves the security coverage but requires understanding the memory endpoint's auth decorators. I'll read `brain/views.py` memory endpoints before executing this step and flag if the auth shape differs enough that the rewrite is non-mechanical.

3. **Dashboard layout hole.** Removing the diary stats card from `dashboard/templates/dashboard/index.html` leaves a grid slot empty. The layout is a CSS grid — we'll need to either re-flow (one-less-column on that row) or fill the slot with another existing card. I'll visually verify in a local browser render before marking checkpoint 1 done.

4. **`.claude/SKILL_IN_CHAT_HANDOFF.md` deletion.** This skill doc is Mara-specific (handoff format referencing Asana volumes, MARA_CORE session state, etc.). It's a Claude Code project skill, not application code. **Proposal: delete in this PR** — it has no meaning in the product fork. Flag if you'd rather keep it around as a reference for now.

5. **Docs deliberately out of scope.** README.md, ARCHITECTURE.md, ROADMAP.md, CODEX.md, DESIGN_CLAUDE_COMMAND_CENTER.md, `docs/superpowers/**` all contain Mara/Kevin/diary references. They get rewritten in PR 6. This PR's CHANGELOG entry will document that doc rewrites are intentionally deferred.

6. **Branding strings.** `config/settings/base.py` has one `# NockCC API key for session tracking endpoints` comment. Branding to "Nock Dashboard" comes in PR 5 (landing page) / PR 6 (docs). For now, code-level branding stays as "NockCC" and there's no hardcoded display-brand string to change in this PR.

7. **Seed data from migrations.** After the 0002 and 0004 no-op rewrite, a fresh migrate produces an **empty** MemoryEntry table. That's intentional — the product has no pre-seeded personal memories. The AI advisor, morning question, and weekly memo will gracefully handle an empty MemoryEntry table (they already do — `.order_by("-updated_at").first()` returns `None` and the advisor returns a fallback).

8. **`brain/views.py` line 291** has `categories = ["identity", "relationship", "personal"]`. These are **MemoryEntry category labels**, not references to the deleted `IdentityDocument` model. Keep as-is.

---

## 5a. Baseline captured — 2026-04-11 (checkpoint 0)

Branch: `feature/strip-personal-layers` from `main@40045de`
Python: 3.12.12, Django 5.0.4, venv at `.venv/`

**`python manage.py check`:** clean (0 issues)

**`python manage.py migrate` against fresh sqlite:** clean — all 10 brain migrations apply (0001..0010), other apps also apply without errors. Confirms the baseline chain is self-consistent before I start rewriting it.

**Main test suite** (pytest.ini testpaths): **586 passed, 2 failed in 62s**
- `pipeline/tests/test_review_alerts.py::TelegramNotifierTests::test_not_quiet_hours`
- `pipeline/tests/test_review_alerts.py::TelegramNotifierTests::test_quiet_hours_midnight_crossing`
- Both are pre-existing time/TZ-dependent failures unrelated to PR 1 scope. **Treat as baseline-red** — any state where these are the only failures after my changes is still green for PR 1 purposes.

**Brain test suite** (run explicitly — see gotcha #1 below): **281 passed in 45s**
- test_continuity: 30, test_diary: 57 (will delete), test_handoffs: 36, test_identity: 50 (will delete), test_research: 54, test_security: 14 (will rewrite), test_tasks: 7, test_views: 33
- Post-strip expected count: **281 − 57 − 50 = 174 passing brain tests**, plus the rewritten security test file against `/api/brain/memory/` (target: keep the 14 count, same assertions, different URL)

### Gotchas discovered during baseline (latent — NOT PR 1 scope to fix)

1. **`pytest.ini` does not include `brain/tests` in `testpaths`.** Brain app tests are invisible to default `pytest` invocations — they only run when you explicitly `pytest brain/tests`. This means the brain app has had a silent test-coverage hole in CI for however long this has been the case. **Logging this in CHANGELOG as a known issue** and fixing it should be a separate cleanup PR (or folded into PR 6 docs/deployment). Adding `brain/tests` to `testpaths` in this PR would cause the 2 diary test failures from my own deletions to show up in the main `pytest` run before checkpoint 3 completes — which is fine actually, but it's still scope creep I'd rather avoid in PR 1.

2. **`pytest.ini` lists `mcp_server/tests` in `testpaths` but the directory does not exist in this fork.** pytest silently skips missing testpaths. Not PR 1 scope — the MCP server itself is absent from the fork and adding it is future work.

Neither gotcha blocks PR 1. Both get mentioned in the PR description as "known issues observed during baseline, out of scope."

## 6. Out of scope for PR 1

- Multi-tenant auth (PR 2 — django-allauth)
- User profile + data isolation (PR 3)
- Stripe billing (PR 4)
- Public landing page + pricing (PR 5)
- Docs + deployment + README rewrite + Railway setup (PR 6)
- MCP server (not present in fork snapshot; future work)
- Any code-quality refactor beyond what's strictly needed to keep the app running after the strip

---

## 7. Verification checklist (Phase 3 — executed at checkpoint 8)

- [x] `python manage.py check` — clean (0 issues)
- [x] `python manage.py makemigrations --check --dry-run` — No changes detected
- [x] `python manage.py migrate` against fresh `nock_dashboard_dev` postgres — all apps applied, no errors
- [x] `pytest` full suite — 760 passed, 2 failed (only the 2 pre-existing TZ failures in `pipeline/tests/test_review_alerts.py`, unchanged from baseline)
- [x] `grep -ri "DiaryEntry\|IdentityDocument\|MARA_CORE\|KEVIN_CORE\|FUZZY" --include="*.py" --include="*.html"` in `brain/ intelligence/ dashboard/ teams/ config/ templates/` — zero hits (3 remaining hits in `CHANGELOG.md`, the plan doc itself, and `brain/tests/test_security.py` docstring are documentation meta-references explaining the deletions)
- [x] `grep -r "Mara" intelligence/ brain/services.py teams/` — zero hits
- [x] `grep -r "Kevin" intelligence/ brain/services.py teams/` — zero hits
- [x] Hard targets (`intelligence/services.py`, `intelligence/tasks.py`, `intelligence/views.py`, `brain/services.py`, `teams/views.py`, `teams/signals.py`) contain zero Mara/Kevin strings — confirmed via dedicated grep at checkpoint 8
- [x] `/brain/` renders, `/brain/diary/` returns 404, `/brain/handoffs/` and `/brain/research/` still route correctly
- [x] `/api/brain/entries/*` (memory) and `/api/brain/research/*` endpoints still route (retargeted security test suite at 10 tests passes against the entries endpoint)
- [ ] Security plugin review (deferred — being handled via the CodeRabbit + Gemini + Copilot auto-review triad on the PR itself, per PR 0's org-level install decisions)
- [ ] Code-simplifier plugin (deferred — same as above; the auto-review triad is the Phase 3-5 mechanism for the product fork)
- [ ] Code-review plugin (deferred — same as above)
- [x] PR description follows the structured format (see nocktechnologies/nock-dashboard#2)

---

## 8. Execution record

1. **Branched** `feature/strip-personal-layers` from `main@40045de` and committed the approved plan doc as the branch's first commit (`f15b26b`). Mid-execution (between checkpoints 5 and 6), the branch was rebased onto `main@4298a1b` to pick up PR 0's fork-backfill (see §5a for the PR 0 discovery and decision).
2. **Worked through 8 layered checkpoints** (0 through 8), one commit per checkpoint so the review diff is readable one layer at a time. Final checkpoint commits:
   - `c2c711b` checkpoint 0: baseline captured (760+281 passing)
   - `64a7059` checkpoint 1: unroute diary/identity endpoints
   - `e3d3308` checkpoint 2: delete view modules (5 files)
   - `db1d34e` checkpoint 3: delete/rewrite tests (2 test files deleted, security test retargeted)
   - `5ae9c0c` checkpoint 4: strip Mara branding from brain app + cross-app branding sweep + delete SKILL_IN_CHAT_HANDOFF.md
   - `e0a74e3` checkpoint 5: generic AI prompts in intelligence layer + teams "needs Kevin" → "needs review"
   - `e6dd221` checkpoint 6: delete DiaryEntry + IdentityDocument + IdentityDocumentVersion models, rewrite migration chain 10 → 7
   - `f2fa02d` checkpoint 7: CHANGELOG product-fork section
   - `737b730` checkpoint 8: final verification pass
3. **Verification checklist executed** at checkpoint 8 — see §7 above. Results: `manage.py check` clean, `makemigrations --check --dry-run` clean, fresh migrate clean, full pytest 760 passed / 2 failed (pre-existing TZ), zero Mara/Kevin in hard-target files.
4. **Plan doc updated in-place** with actual counts and per-checkpoint commit list, committed separately as `737b730` (part of checkpoint 8) so the PR review has the design record alongside the code.
5. **Pushed the branch and opened the PR** as nocktechnologies/nock-dashboard#2, with a structured description covering summary, checkpoint-by-checkpoint layers, deletions inventory, branding sweep, hard targets, verification results, and known-issues deferred to PR 6.
6. **Two review cycles** via the CodeRabbit + Gemini + Copilot auto-review triad. First cycle surfaced 8 findings; 5 were fixed in commit `2e8225a` ("review: address findings from PR #2 auto-review"), 3 were deferred with Kevin's approval (teams/*.py DRY refactor, Docstring Coverage pre-merge warning, Copilot custom-instructions link). Second cycle surfaced 5 more findings on the design record itself + 1 missed branding scrub (`ingest_research.py:121` `Command.help` string still said "mara-vault"), all fixed in a follow-up commit.

**Divergences from the original plan:** One significant divergence — PR 0 (`chore(fork): backfill notifications, remote, vault`) was discovered mid-execution when `manage.py check` surfaced that three apps listed in `INSTALLED_APPS` were physically absent from the fork directory tree and were resolving to nock-command-center via Python import path. The fork-backfill was landed as a separate PR #1 (merged at `4298a1b`) before this branch rebased and resumed checkpoint 6. See §5a for the full story.
