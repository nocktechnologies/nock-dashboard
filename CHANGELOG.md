# Changelog

All notable changes to Nock Dashboard (the product fork of NockCC) are
documented here. Organized by PR/merge to main.

---

# Nock Dashboard — Product Fork

The following entries describe work on `nocktechnologies/nock-dashboard`,
the multi-tenant SaaS product fork of NockCC. The product fork has its
own independent history starting 2026-04-11 and will **not** sync
upstream to `kkwills13/nock-command-center`. The NockCC inherited history
is preserved below the `--- Inherited from NockCC ---` separator for
archaeological reference, and will be progressively rewritten for the
product fork context in PR 6 (Docs + deployment).

---

## [PR 2] — 2026-04-11 — Auth: django-allauth + brute-force protection

### Added
- **`django-allauth[socialaccount]==65.15.1`** — email-first auth layer. Replaces the hand-rolled `accounts/` stub views (which only had an `index` redirect). Allauth owns signup, login, logout, password reset, email change, email verification, and account management. `socialaccount` extra pulled in now so the OAuth social-login path (PR 3 or later) requires only settings changes, not a schema migration.
- **`django.contrib.sites` + `SITE_ID = 1`** — required by allauth's email verification flow. Added to `INSTALLED_APPS` and the `sites` migration runs clean. The initial `Site` row (id=1) is created automatically by Django's `post_migrate` signal.
- **`allauth.account.middleware.AccountMiddleware`** — inserted between `AuthenticationMiddleware` and `MessageMiddleware` in `MIDDLEWARE`. Required by allauth 65.x; raises `ImproperlyConfigured` at boot if missing.
- **Full allauth settings block in `config/settings/base.py`**:
  - `ACCOUNT_LOGIN_METHODS = {"email"}` — email-only login; no username field on any form
  - `ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]` — allauth 65.x API (replaces deprecated `ACCOUNT_EMAIL_REQUIRED` + `ACCOUNT_USERNAME_REQUIRED`)
  - `ACCOUNT_USER_MODEL_USERNAME_FIELD = None` — decouples allauth from the `username` field
  - `ACCOUNT_EMAIL_VERIFICATION = "mandatory"` — new users cannot log in until they click the email link; the token is single-use and expires after 3 days (allauth default)
  - `ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"` — all generated links (verification, password reset) use https
  - `ACCOUNT_RATE_LIMITS` — six-bucket rate limit map covering `login_failed`, `signup`, `send_email`, `confirm_email`, `change_password`, `reset_password`, and `reset_password_from_key`. All set to allauth's sensible defaults (5/5m for most, 10/h for signup). This is in addition to axes brute-force lockout — two independent protection layers
  - SMTP env-var block (`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`, `EMAIL_BACKEND`) — provider-agnostic; any SMTP relay (Resend, SendGrid, Postmark) drops in by setting env vars. Dev default is `console.EmailBackend` so no mail config is needed locally
- **Dark-theme allauth template overrides** — 9 templates in `templates/account/` that override allauth's defaults with the product's circuit-board dark-theme design:
  - `base_auth.html` — shared base for all auth pages: animated conic-gradient card border, circuit-board SVG background, logo circle, Geist font, dark CSS. All other auth templates extend this via `{% block card_content %}`
  - `login.html`, `signup.html`, `logout.html` — primary auth flows
  - `password_reset.html`, `password_reset_done.html`, `password_reset_from_key.html`, `password_reset_from_key_done.html` — password reset funnel
  - `email_confirm.html` — email verification landing
- **`accounts/views.py` — profile view** — `@login_required` view at `/accounts/profile/` (name `account-profile`). Renders `accounts/profile.html` showing email, `date_joined`, `last_login`, and links to change-password + logout. This is a PR 2 placeholder; PR 3 extends it with `UserProfile` subscription data
- **`accounts/tests/` — 22 integration tests** across 7 files covering the full auth surface:
  - `test_login.py` — login page renders, valid creds log in and redirect, invalid creds show form errors (structural assertion — not version-pinned string), unverified user cannot log in
  - `test_signup.py` — signup page renders, valid signup creates user and sends verification email, duplicate email rejected (privacy-preserving redirect), weak password rejected, mismatched passwords rejected
  - `test_logout.py` — logout clears session, logout redirects to login
  - `test_password_reset.py` — reset page renders, valid email sends reset link, unknown email gets redirect (anti-enumeration — allauth intentionally sends to unknown addresses), done page renders
  - `test_email_verification.py` — signup sends verification email, valid HMAC key marks email verified, invalid key shows error (not 500)
  - `test_profile.py` — unauthenticated redirect to login with `next=`, authenticated user sees profile page with email content
  - `test_axes_integration.py` — 4 bad logins don't lock out, 5th bad login triggers axes lockout response (429), correct credentials blocked after lockout, successful login resets axes counter
- **`accounts/tests` added to `pytest.ini` testpaths** — accounts tests were collected locally but the testpaths entry makes the scope explicit for CI

### Changed
- **`config/urls.py`** — replaced the hand-rolled `include("accounts.urls")` with:
  ```python
  path("accounts/profile/", accounts_views.profile_view, name="account-profile"),
  path("accounts/", include("allauth.urls")),
  ```
  The profile path is declared before the allauth include so our view wins over any allauth catch-all at the same prefix
- **Allauth authentication backend** — added `allauth.account.auth_backends.AuthenticationBackend` between `AxesStandaloneBackend` and `ModelBackend` in `AUTHENTICATION_BACKENDS`. Order matters: axes intercepts first (to enforce lockout), allauth handles email→user lookup, Django's model backend provides the fallback

### Axes + allauth coexistence note

Axes 7.x + allauth 65.x interaction has a subtle behavior worth documenting: axes captures login failures via the `user_login_failed` Django signal. The 5th failure (at `AXES_FAILURE_LIMIT = 5`) triggers the lockout **on the same response** (signal fires inside the request cycle → `AxesSignalPermissionDenied` bubbles up → `AxesMiddleware.process_exception` returns a 429 with `accounts/locked.html`). Subsequent attempts (6th+) show the login form (200) rather than the lockout page because `AxesStandaloneBackend.authenticate()` raises `PermissionDenied` which Django's `authenticate()` silently converts to `None`; allauth re-renders the form with "invalid credentials". The lockout IS effective — the user cannot authenticate with correct or incorrect credentials after the 5th failure — but the HTTP response code changes from 429 back to 200 on attempt 6+. `AXES_RESET_ON_SUCCESS = True` clears the counter on successful login.

### Verification

- `python manage.py check` — 0 issues (3 deprecated-setting warnings from allauth 65.x migration fixed inline: `ACCOUNT_AUTHENTICATION_METHOD` → `ACCOUNT_LOGIN_METHODS`, `ACCOUNT_EMAIL_REQUIRED` + `ACCOUNT_USERNAME_REQUIRED` → `ACCOUNT_SIGNUP_FIELDS`)
- `python manage.py makemigrations --check --dry-run` — No changes detected
- `python manage.py migrate` — applies `account.*`, `sites.*`, `socialaccount.*` migrations cleanly
- `pytest accounts/tests/ -v` — **22 passed, 0 failed**
- Full suite — baseline maintained (pre-existing `pipeline/tests/test_review_alerts.py` TZ failures unchanged)

---

## [chore] — 2026-04-11 — Strip MCP / OAuth-shim refs

### Removed
- **`core/oauth/` OAuth 2.1 shim and its entire test suite** — The shim (`__init__.py`, `metadata.py`, `storage.py`, `urls.py`, `views.py` + `core/tests/test_oauth.py`, ~1512 lines total) was built upstream in NockCC to let claude.ai custom connectors authenticate against an MCP Streamable HTTP transport at `/mcp/`. The fork never had `mcp_server/`, so the shim was gating nothing — dead code with its own attack surface. Deleted outright. The `NOCKCC_OAUTH_ENABLED` + `OAUTH_ISSUER_URL` settings that configured it are also removed from `config/settings/base.py`. URL mounts at `/.well-known/` and `/oauth/` are removed from `config/urls.py`.
- **MCP references in `config/asgi.py`** — The upstream ASGI entry point wrapped Django inside a Starlette outer router to mount an MCP sub-app at `/mcp`, with a custom lifespan hook to drive the MCP session manager's `run()` task group. This fork never had the MCP sub-app to mount. The broken top-level `from mcp_server.http_app import build_http_app` was silently resolving to nock-command-center's project tree via a stale venv `sys.path` entry; on a clean venv, every boot failed with `ModuleNotFoundError`. Rewrote `config/asgi.py` as a plain Django + Channels ASGI app (`ProtocolTypeRouter` with `http` pointed at `django_asgi_app`, `websocket` pointed at the remote-agent WebSocket router). 107 lines → 36 lines.
- **`mcp>=1.23.0,<2.0.0` pin from `requirements.txt`** — was the first dep listed. Transitive pulls (`starlette`, `sse-starlette`, `pydantic`) are either still available from other deps (`pydantic` via `openai` + `anthropic` + `pydantic-settings`) or no longer needed (`starlette` and `sse-starlette` were exclusively used by the MCP sub-app). Uvicorn is pinned independently and stays.
- **`mcp_server/tests` from `pytest.ini` `testpaths`** — latent gotcha flagged during PR 1 baseline. The directory never existed in the fork; pytest was silently skipping the missing path. Entry removed.

### Changed
- **`.claude/lessons/asgi-deployment.md` → `.claude/lessons/archived/asgi-deployment.md`** — the lesson doc describes Daphne 4.1.2's broken ASGI lifespan implementation and why production must run uvicorn. The specific failure mode it captured (MCP session manager task group never starting under Daphne) is obsolete for the product fork, but the underlying Daphne lifespan bug is a real piece of ASGI tribal knowledge that future fork work may need. Moved to `archived/` rather than deleted so the lesson stays discoverable.
- **Uvicorn pin comment in `requirements.txt`** simplified — removed the MCP-specific framing ("the MCP session manager's task group never starts under Daphne"), kept the generic Daphne-lacks-lifespan-protocol note with a cross-reference to the archived lesson doc.

### Why this chore PR exists (inherited fork bug discovery)

This cleanup was triggered by PR 2 (django-allauth) baseline verification. The local dev `.venv` on `nock-dashboard` was a file-level copy of `nock-command-center/.venv` with the internal `pyvenv.cfg` still pointing at the nock-cc path — so every `pip install`, every `python -c "import ..."`, and every Django test run was silently resolving modules through nock-cc's `sys.path` as a fall-through. This masked the entire class of "fork references code that doesn't exist in the fork" bugs.

When the venv was recreated from scratch as part of CP0 of PR 2, the masking stopped and the `ModuleNotFoundError` on `config.asgi` import surfaced immediately. That meant **the fork has never been deployable** — production `uvicorn config.asgi:application --lifespan on` would have failed at boot, `manage.py runserver` would have failed (Daphne is first in `INSTALLED_APPS`, so Django uses the channels runserver override which also loads the ASGI app). No one had noticed because the broken venv + the "we haven't deployed the fork yet" status were hiding each other.

This is the third bug in the fork bestiary that surfaced from the initial `cp -r` fork (PR 0 was the missing `notifications`/`remote`/`vault` apps; PR 2 CP0 was the broken venv; this PR is the ASGI / OAuth shim dead code). Better to find them now than after customers are on the thing.

### Verification

- `python -c "import config.asgi"` — **loads successfully** (this was broken on fresh venv before the strip)
- `python manage.py check` — clean (0 issues)
- `python manage.py makemigrations --check --dry-run` — No changes detected
- `python manage.py runserver 0.0.0.0:8765 --noreload` — boots, `/accounts/login/` returns HTTP 200 (the existing hand-rolled login view still works)
- `pytest` full suite — **728 passed, 2 failed** (the 2 failures are the pre-existing TZ-related failures in `pipeline/tests/test_review_alerts.py` that have been baseline-red since PR 0). Net delta from the fresh-venv PR 2 CP0 baseline: −32 tests total (all 32 were in `core/tests/test_oauth.py` — 28 passing tests that tested the deleted shim, 4 failing tests that imported `mcp_server.http_app`)
- `grep -rn "mcp_server" --include="*.py" --include="*.ini" --include="*.txt" --include="*.toml" --include="*.sh"` excluding `.venv/` — **zero hits**

### Notes

- Docs (`README.md`, `ROADMAP.md`, `ARCHITECTURE.md`, `CHANGELOG.md`'s "Inherited from NockCC" section) all still reference MCP. PR 6 (Docs + deployment) owns that rewrite; this chore PR is code + config only.
- `railway.toml` has a historical comment block mentioning MCP in the context of a past Railpack bug. Comment, not active code. Left untouched for PR 6.
- The `.venv` recreation is a local-machine-only operation (`.venv` is gitignored). PR 6 will add the recreation procedure to the `README.md` so future fork operators don't hit the same trap.

---

## [Unreleased] — 2026-04-11

### Changed
- **Strip personal layers** (in progress, `feature/strip-personal-layers`) — delete the diary / identity-document / Mara-Kevin-specific continuity surface from the fork so the remaining code becomes a generic multi-tenant product base for PR 2 (auth) and PR 3 (data isolation). Layered execution with one commit per checkpoint; see `.claude/decisions/PR-1-strip-personal-layers.md` for the full plan and per-checkpoint rationale.
  - **Models deleted**: `DiaryEntry`, `IdentityDocument`, `IdentityDocumentVersion` (and their associated `Category`/`Source`/`DOCUMENT_TYPES` choices) removed from `brain/models.py`. `MemoryEntry`, `ConsolidationLog`, `MorningNoteSent`, `HandoffEntry`, `HandoffVersion`, `ResearchDocument`, `ResearchChunk` all kept as-is — they are product-grade features
  - **URLs / routing**: 5 `/api/brain/diary/*` routes and 4 `/api/brain/identity/*` routes deleted from `config/urls.py`; `/brain/diary/` page route deleted from `brain/urls.py`; `diary_views` and `views_identity` imports removed
  - **View modules deleted**: `brain/diary_views.py` (446 lines, all diary API + browser), `brain/views_identity.py` (identity CRUD + `/boot` endpoint)
  - **Templates deleted**: `brain/templates/brain/diary.html`
  - **Management commands deleted**: `brain/management/commands/migrate_diary_from_asana.py`, `brain/management/commands/seed_identity.py` (the MARA_CORE / KEVIN_CORE / FUZZY seed)
  - **Tests deleted**: `brain/tests/test_diary.py` (636 lines, 57 tests), `brain/tests/test_identity.py` (614 lines, 50 tests)
  - **Tests retargeted**: `brain/tests/test_security.py` now targets `/api/brain/entries/` (MemoryEntry endpoint) instead of the removed diary endpoint. Preserves the 10 auth / CORS / rate-limit / CSRF assertions; the 4 date-parameter-validation tests were dropped because the memory endpoint has no date filter equivalent. Net: 14 → 10 security tests
  - **Tests cleaned up for seed no-ops**: `brain/tests/test_continuity.py::ContinuitySeedTest` and `brain/tests/test_views.py::SeedDataTest` deleted — they asserted the presence of personal seed data that the 0002 and 0004 migrations no longer install
  - **Dashboard sidebar test**: `dashboard/tests/test_pm_views.py::SidebarNavTests::test_sidebar_includes_diary_research_projects` renamed to `test_sidebar_includes_research_projects` and the `/brain/diary/` assertion dropped
  - **Dashboard home card**: the "Mara's Diary" stats sub-section removed from `dashboard/templates/dashboard/index.html` (including the `diary` Alpine state + `refreshDiary()` method + corresponding `fetch()` calls). It was a sub-section inside the Brain card rather than a standalone grid cell, so removing it just shortens the card — no grid hole, no replacement needed
  - **Sidebar nav**: the Diary link removed from `templates/base.html`
  - **Branding sweep across code**: `brain/apps.py` verbose_name `"Mara's Brain"` → `"Brain"`; `brain/templates/brain/index.html` page title; `brain/templates/brain/handoffs.html` empty-state helper text; `brain/services.py::MorningNoteGenerator` docstring + header string (`"Mara's Morning Note"` → `"Morning Note"`); `brain/services.py` `"diary"` source filter drops out of the confidence-promotion logic; `brain/views_research.py` docstring; `brain/management/commands/ingest_research.py` docstring and usage examples; `brain/models.py` `ResearchDocument` docstring; `config/settings/base.py` celery-beat schedule comment; `tasks/views_api.py` module docstring
  - **Intelligence layer prompts generalized**: `intelligence/services.py::generate_morning_question` no longer says "You are Mara, generating a question for Kevin's morning commute"; `intelligence/tasks.py::generate_weekly_memo` no longer opens with "Chief of Staff for Nock Technologies...Kevin Wills"; `intelligence/views.py::_build_advisor_system_prompt` no longer says "AI Business Advisor for Nock Technologies founded by Kevin Wills". All three now use generic "user's business" framing while preserving the same memory query + six-section memo structure
  - **Teams overflow notifications**: `teams/views.py` and `teams/signals.py` Telegram alerts `"exceeded max review cycles — needs Kevin"` → `"needs review"`
  - **Claude project doc deleted**: `.claude/SKILL_IN_CHAT_HANDOFF.md` (142-line Mara-specific handoff skill). The product uses the `HandoffEntry` model for operational state tracking; this doc has no meaning in the fork
  - **Migration chain rewrite**: the 10-migration brain chain collapses to 7. `0006_diary_entry`, `0007_fix_diary_entry_indexes`, and `0008_identity_documents` are deleted. `0002_seed_memory_entries` and `0004_seed_continuity_entries` are replaced with empty no-op content at the same migration numbers (preserves chain linearity, no renumbering cascade). `0009_research_library` is renamed to `0006_research_library` and its dependency retargeted to `0005_morning_note_sent`. `0010_handoffentry_handoffversion` is renamed to `0007_handoffentry_handoffversion` and its dependency retargeted to `0006_research_library`. **Safe** because there is no production database for nock-dashboard yet (fresh Railway project comes in PR 6) and the local dev DB was switched off the shared `nockcc_db` before the rewrite. **Anyone checking out the fork must run `dropdb nock_dashboard_dev && createdb nock_dashboard_dev && python manage.py migrate` once** to pick up the rewritten chain

### Known issues (not fixed in PR 1 — flagged for follow-up)

- `pytest.ini` `testpaths` includes `brain/tests` implicitly only when `pytest brain/tests` is invoked explicitly. Default `pytest` runs skip the brain test suite entirely. Latent CI coverage hole, present at baseline, scope for a later cleanup PR
- `pytest.ini` `testpaths` lists `mcp_server/tests` but the `mcp_server/` directory does not exist in the fork (pre-existing gap — the MCP server was not copied from nock-cc at fork time). pytest silently skips the missing path. The MCP server is scoped for a later PR when we decide whether the product fork gets the MCP transport at launch or as a post-launch feature
- The two timezone-dependent pre-existing test failures in `pipeline/tests/test_review_alerts.py::TelegramNotifierTests::{test_not_quiet_hours,test_quiet_hours_midnight_crossing}` continue to fail on this branch. They were failing at baseline on `main@40045de` and are unrelated to the strip. Out of scope
- Docs deliberately deferred: `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `CODEX.md`, `DESIGN_CLAUDE_COMMAND_CENTER.md`, and `docs/superpowers/**` all still reference Mara/Kevin/diary in historical and design content. Rewriting them in PR 1 would explode the diff. **PR 6 (Docs + deployment) owns all of these**. The CHANGELOG (this file) is the only doc that gets updated in PR 1
- `remote/management/commands/create_agent_token.py:18` has a placeholder CLI help example string `"Kevin's MacBook"` that came over from PR 0's verbatim app copy. Flagged during PR 0 for the strip to address; the string is benign (just a CLI example placeholder) and kept intentionally unchanged here — PR 6 will sanitize it as part of the branding sweep

## [0.1 — 2026-04-11] — Fork Backfill + Pipeline Tracking

### Added
- **`chore(fork)`: backfill `notifications/`, `remote/`, `vault/`** — these three Django apps were listed in `INSTALLED_APPS` but their directories were never copied from `nock-command-center/` during the initial fork. Until this PR, every Django runtime in nock-dashboard was resolving those imports to `/Users/kevin/Dev/nock-command-center/` on the local filesystem, so the fork was partially running on the source repo. Discovered during PR 1's baseline verification. rsynced verbatim from nock-cc, then migrations + tests confirmed against a fresh Postgres database. Also generated two missing migrations for pre-existing model drift that was hidden by the wrong-module resolution (`context/0002_alter_contextsnapshot_options.py`, `notifications/0002_alter_notificationrule_trigger_event.py`). Fixed one inherited stale test (`remote/tests/test_pages.py::BaseTemplateTest::test_mobile_bottom_nav_present` was asserting a Tailwind class that pre-dated a template refactor). See nocktechnologies/nock-dashboard#1 for the full walkthrough and the gemini+coderabbit review artifacts
- **`nocktechnologies/nock-dashboard` registered in NockCC pipeline tracking** — GitHub webhook created on the repo (hook id 605029736 → `https://cc.nocktechnologies.io/webhooks/github/`, shared `GITHUB_WEBHOOK_SECRET`, events: `check_run, check_suite, pull_request, pull_request_review, pull_request_review_comment, push`), corresponding `Repository` row written to the striking-serenity production database, and `pipeline/management/commands/register_repos.py` updated in nock-command-center (PR kkwills13/nock-command-center#75) to keep the source of truth in sync with reality. CodeRabbit, Claude GitHub App, and Gemini all auto-apply to the new repo via org-level GitHub App install with `repository_selection: "all"` — no additional review-tool setup required

### Changed
- **`chore`: remove nested nock-command-center submodule from fork working tree** — the initial fork commit had an accidental `nock-command-center` gitlink (mode 160000) pointing at nock-cc's latest commit, which would have shown up in every diff until it was untracked. `git rm --cached nock-command-center` + `.gitignore` entry for `nock-command-center/`

---

*--- Inherited from NockCC ---*

*The entries below describe work on the upstream `kkwills13/nock-command-center` personal command center prior to the 2026-04-11 product fork. They are preserved for archaeological context and will be rewritten or trimmed in PR 6 (Docs + deployment) as part of the product fork documentation sweep.*

## [Unreleased] — 2026-04-10

### Changed
- **Terminal Electron hardening pass** (`terminal-electron/`) — closed the Electron-side security and dead-code issues from the April 11 review.
  - Main-process settings writes are now validated and sanitized before persistence; `devRoots` no longer trusts renderer input blindly
  - File access checks now resolve real paths and block sibling-prefix escapes and symlink escapes before `read`, `write`, `stat`, `gitStatus`, or file watching proceeds
  - Session-discovered project roots are granted explicitly so the sidebar file tree still works without widening the filesystem sandbox globally
  - Prompt-library execution is now wired into the AI chat panel, cross-platform context-file detection works on macOS/Linux, and file-tree "Copy Content" now copies actual file text
  - Removed dead code (`src/utils/ipc.js`, unused editor save helper, unused theme exports, unused `png-to-ico` dependency) and added Node regression tests for the path policy
  - Upgraded the Terminal Electron toolchain (`electron` 41.2.0, `electron-builder` 26.8.1, `vite` 8.0.8, `@vitejs/plugin-react` 6.0.1, `wait-on` 9.0.5, explicit `esbuild`) and pinned patched `axios`/`dompurify` via `overrides`
  - Verification: `npm test`, `npm audit --json`, `npm audit --omit=dev --json`, `npx knip --no-progress`, and `npm run build` all complete successfully; both audit passes now report 0 vulnerabilities

### Added
- **OAuth 2.1 shim for the MCP Streamable HTTP transport** (`core/oauth/`) — claude.ai custom connectors refuse to talk to a plain bearer-token MCP server, they require OAuth 2.1 per MCP spec 2025-03-26. This single-user shim runs just enough of the protocol to let claude.ai complete its handshake and walk away with `NOCKCC_API_KEY` as the access token.
  - **Discovery**: `/.well-known/oauth-protected-resource/mcp` (RFC 9728) and `/.well-known/oauth-authorization-server` (RFC 8414) served as static JSON. The 401 on `/mcp/` now includes a `resource_metadata="…"` attribute in the `WWW-Authenticate` header so claude.ai can discover the OAuth server automatically.
  - **Dynamic client registration** (`POST /oauth/register`, RFC 7591) auto-accepts any well-formed client with real `http://` or `https://` redirect URIs and returns a fresh `client_id`. No secrets — public clients only, PKCE S256 enforced.
  - **Authorize endpoint** (`GET /oauth/authorize`) auto-approves every request because this is a single-user instance (no consent screen), validates PKCE S256 (`plain` rejected — OAuth 2.1 deprecates it), mints a 60-second authorization code in Redis, and 302s to the registered redirect URI preserving `state`.
  - **Token endpoint** (`POST /oauth/token`) pops the code atomically so it can't be reused, validates `client_id`, `redirect_uri`, PKCE verifier (SHA-256 constant-time compare), and returns `NOCKCC_API_KEY` as the access token. The existing `BearerAuthMiddleware` on `/mcp/` accepts it with zero changes.
  - **Storage**: direct `redis-py` with 60s TTLs for auth codes and 30d TTLs for registered clients. `StorageUnavailable` exceptions are caught in the view layer and converted to clean OAuth `server_error` 503 responses instead of 500 tracebacks.
  - **Enable flag**: `NOCKCC_OAUTH_ENABLED=1`. When off, every OAuth endpoint returns 404 and the shim is dormant — no discovery advertising, no endpoints exposed.
  - **Rate limits**: `django-ratelimit` at 20/min per IP on register/authorize/token.
  - **Security note**: single-user only. Anyone who completes the OAuth dance gets the master API key. The flag and rate limits exist specifically because of this. Do not copy the pattern into a multi-tenant service.
  - 23 new tests in `core/tests/test_oauth.py` — discovery JSON shape, register validation, authorize PKCE+client+redirect_uri rejection, token exchange happy path + every failure mode (wrong verifier / code reuse / client mismatch / redirect mismatch / wrong grant_type / API key missing), full end-to-end register → authorize → token flow, `/mcp` bare-path 308 redirect, `WWW-Authenticate: resource_metadata` toggling with the enable flag.
- **`/mcp` trailing-slash redirect** (`config/asgi.py`) — Starlette's `Mount("/mcp", ...)` only matches `/mcp/` and `/mcp/foo`, so a bare `/mcp` used to 404. claude.ai probes the bare path during discovery, so this was silently breaking connector setup. An explicit `Route("/mcp")` now 308s to `/mcp/` preserving method and body.
- **MCP Streamable HTTP transport** (`mcp_server/http_app.py`) — the same 42 tools Mara has via stdio are now reachable over HTTP at `/mcp` for claude.ai custom connectors and any other remote MCP client.
  - Streamable HTTP transport per the 2025-03-26 MCP spec (the replacement for deprecated HTTP+SSE) via `StreamableHTTPSessionManager` from the MCP SDK
  - Mounted inside the existing Django ASGI app — one deploy, one domain, one TLS cert, no new service on Railway
  - Bearer-token auth (`Authorization: Bearer <NOCKCC_API_KEY>`) with `X-API-Key` fallback so the same secret works across every NockCC surface; constant-time comparison via `secrets.compare_digest`
  - Unauthenticated `/mcp/health` liveness route for Railway health checks and uptime monitors
  - Shared tool registry (`mcp_server/registry.py`) — stdio (`mcp_server/server.py`) and HTTP (`mcp_server/http_app.py`) both import the same `ALL_TOOLS`, `TOOL_MODULES`, and `dispatch_tool_call()`, so new tools land in both transports automatically
  - Lifespan wiring in `config/asgi.py` hoists `session_manager.run()` to the outer Starlette router because `Mount` drops lifespan events for sub-apps (caveat documented in `mcp_server/README.md`)
  - 25 new tests: 10 auth-middleware unit tests (health exemption, missing/wrong token, wrong scheme, case-insensitive bearer, X-API-Key fallback, bearer precedence, missing server key), 4 end-to-end tests using the MCP SDK's own `streamable_http_client` pointed at the in-process ASGI app (health, missing/wrong auth, full `initialize`→`tools/list` handshake), 11 registry invariant tests (no duplicate names, schema shape, back-compat aliases)
  - `pytest.ini` now includes `mcp_server/tests` in `testpaths`, so every MCP test (93 total, including the previously-orphaned tests from PRs #70 and #71) runs in CI for the first time
  - `mcp_server/README.md` updated with the full claude.ai custom-connector setup walkthrough
- **PM plugin UI polish** — dashboard/pm_project_detail.html now a real daily-driver workspace.
  - Inline task detail panel (click any task row) — edit name, description, priority, status, due date, assignee, section, tags; Save / Complete / Reopen / Delete buttons
  - Row-level complete checkbox that strike-throughs the task and sinks completed items to the bottom of their section
  - Inline "+ Add Section" form — type name, hit Enter, section appears
  - Collapsible section groups with live task counts (click section header to toggle)
  - Enriched task rows: colored priority badges (urgent=red, high=orange, medium=yellow, low=gray), status badges, assignee pill, due-date text
  - Overdue tasks get red left border + red due-date text
  - Double-click task name for inline rename
  - New-task modal extended with Description (textarea), Status (dropdown), and Assignee fields
- **Cross-project Tasks dashboard** (`/pm/tasks/`) — single page showing every task across every project, backed by `/api/pm/api/tasks/?ordering=-priority`
  - Client-side filters: project, priority, status, completion state, overdue-only toggle
  - Per-row: complete checkbox, project link, task name, priority badge, due date, assignee, status badge
  - Sidebar "Tasks" nav link now points here
- **MCP Handoff tools** (`mcp_server/tools/handoffs.py`) — 3 new tools wired through `/api/brain/handoffs/`
  - `nockcc_handoff_read` — fetch current handoff for a context (cortextos-agent / claude-chat / kit-session / codex-session)
  - `nockcc_handoff_write` — create or overwrite; archives the prior version automatically
  - `nockcc_handoff_list` — summary of all active handoffs (no content)
  - 11 new tests in `mcp_server/tests/test_handoffs.py` covering context validation, endpoint routing, body shape, and defaults
  - Total MCP tool count now 42 across 12 groups (was 39/11)
- **Projects app** (`projects/`) — standalone reusable Django REST app for lightweight project management.
  - Models: `Project`, `Section`, `Task`, `TaskComment`
  - API endpoints for project CRUD, section CRUD/reorder, task CRUD/filtering, comments, dashboard, overdue/today/upcoming views
  - Management commands: `import_from_asana`, `task_stats`
  - 66 tests covering models, filters, API auth/CRUD/actions, dashboard views, and import idempotency
  - App README at `projects/README.md`
- **Asana two-way sync** (`tasks/`) — NockCC becomes a read/write proxy so Mara and the MCP server can create, update, complete, move, comment on, and delete Asana tasks through the NockCC API. Asana remains the source of truth.
  - New write helpers in `tasks/asana_client.py`: `create_task`, `update_task`, `complete_task`, `uncomplete_task`, `delete_task`, `add_task_to_section`, `add_comment`, `get_sections`. Shared `_request_with_retry` handles 429 backoff and surfaces Asana's `errors[].message` envelope.
  - New `AsanaSection` model (cached per project) + `AsanaTask.deleted_at` for soft delete. Migration `0003_asanatask_deleted_at_asanasection`.
  - New write endpoints under `/api/tasks/` — all gated by `require_brain_access`:
    - `POST /api/tasks/create/`
    - `PUT /api/tasks/<gid>/update/`
    - `POST /api/tasks/<gid>/complete/` + `/uncomplete/`
    - `POST /api/tasks/<gid>/move/` (same-project only — cross-project moves rejected)
    - `POST /api/tasks/<gid>/comment/`
    - `DELETE /api/tasks/<gid>/delete/` (soft-deletes locally, hard-deletes in Asana)
  - New cross-project read endpoints that hit local DB only (fast path for morning briefs / heartbeat crons):
    - `GET /api/tasks/all/` (filters: `project_gid`, `priority`, `due_before`, `due_after`, `overdue`, `completed`, `limit`)
    - `GET /api/tasks/overdue/` — sorted by days overdue
    - `GET /api/tasks/today/`
    - `GET /api/tasks/summary/` — total / incomplete / completed / overdue, by priority, by project
    - `GET /api/tasks/sections/<project_gid>/` (optional `?refresh=true` forces a fresh pull from Asana)
  - **Asana-first write discipline** — every write follows validate → call Asana → mirror to local DB. Local DB is never mutated if the Asana call fails (prevents sync drift). Covered by regression tests.
  - **Priority stays local** — Asana free tier lacks a native priority custom field, so `AsanaTask.priority` is never forwarded to Asana. Local-only updates (priority alone) skip the Asana round-trip entirely.
  - Celery sync (`sync_asana_projects`) now also pulls project sections into `AsanaSection` and skips soft-deleted rows during orphan cleanup so deleted tasks don't resurrect themselves.
  - 32 new tests in `tasks/tests/test_write_api.py` covering create / update / complete / move / comment / delete, cross-project reads, auth, Asana failure rollback, retry/backoff, and priority isolation.
- **Research Library** (`brain/`) — semantic search over Mara's 413-file Obsidian research vault via pgvector
  - `ResearchDocument` + `ResearchChunk` models with pgvector `VectorField(dimensions=1536)` and ivfflat cosine index
  - Chunking strategy (`brain/chunking.py`) — splits on markdown headers, ~500-word chunks with 100-word overlap, preserves parent heading in metadata
  - OpenAI `text-embedding-3-small` integration (`brain/embeddings.py`) with batch support
  - Management commands: `ingest_research` (idempotent vault import via SHA-256 hash), `embed_research` (chunk + embed unindexed docs), `search_research` (CLI test)
  - API endpoints under `/api/brain/research/`: `search/`, `documents/`, `documents/<slug>/`, `topics/`, `stats/` — all gated by `require_brain_access` with rate limiting
  - Database migration `0009_research_library` with conditional `CREATE EXTENSION vector` (PostgreSQL only, no-op on SQLite)
  - Added `pgvector==0.3.6` and `openai==1.54.4` to requirements; added `OPENAI_API_KEY` setting
  - 38 tests covering chunking, models, ingestion idempotency, API endpoints, vector ranking, topic filtering, auth
  - Estimated corpus embedding cost: ~$0.08 for the full 22MB vault
- **MCP Server** (`mcp_server/`) — gives Mara native read/write access to NockCC from any Claude session via the Model Context Protocol
  - 39 tools across 11 groups: diary, memory, pipeline, sessions, spend, tasks, CRM, teams, prompts, alerts, research
  - `nockcc_diary_recent` + `nockcc_diary_brief` at session start → context reconstitution in seconds
  - `nockcc_prompts_create` → Mara queues work for Kit directly
  - Graceful handling of unimplemented endpoints (404/501) — all 39 tools defined, backend-ready
  - Auth via `NOCKCC_API_KEY` env var, API key never logged or exposed in errors
  - Rate limit (429), 401, 403, 501, connection error, and timeout handling with clear messages
  - 53 unit tests (all passing): API helper, diary, memory, pipeline, sessions, server routing, security
  - `mcp_server/requirements.txt` (`mcp>=1.23.0,<2.0.0`, `httpx>=0.27.0`)
  - `mcp_server/README.md` with setup instructions for Claude Code and claude.ai MCP connector

## [2026-04-08]

### Security
- **HIGH-1 (Broken Access Control):** Replaced `require_api_key` on all Brain endpoints with new `require_brain_access` decorator that enforces `is_staff=True` for session auth. Non-staff authenticated users now receive 401.
- **HIGH-2 (Wildcard CORS):** Replaced `CORS_ALLOW_ALL_ORIGINS = True` with explicit `CORS_ALLOWED_ORIGINS` allowlist (`cc.nocktechnologies.io`, `nocktechnologies.io`, `nocktechnologies.com`).
- **HIGH-3 (No Rate Limiting):** Added `django-ratelimit` decorators to all 11 Brain API endpoints: 100/m reads, 10/m writes, 5/m AI endpoints (`diary_brief`, `generate_brief`, `consolidate`, `send_test_morning_note`). Exceeded limit returns 429 + `Retry-After: 60`.
- **MEDIUM-4 (CSRF Exempt on Session Writes):** Removed `@csrf_exempt` from all Brain views. `require_brain_access` enforces CSRF via `CsrfViewMiddleware.process_view()` for session auth; API key requests are exempt programmatically. CSRF failure returns JSON envelope (not HTML).
- **MEDIUM-5 (Invalid Date 500s):** Added `_parse_date_param()` helper in `diary_views.py` — validates `date_from`, `date_to`, and `session_date` (query params + POST body) before ORM use. Invalid formats return 400 with YYYY-MM-DD guidance.

### Added
- `require_brain_access` decorator in `core/auth.py` — Brain-specific auth with staff gate, conditional CSRF, and 429 rate limit handling
- 14 new security tests in `brain/tests/test_security.py` covering all 5 findings
- `DiaryEntry` model in `brain` app — permanent storage for Mara's diary with 6 categories (work/personal/private/design/handoff/in_chat), 5 sources, word count tracking, tags, and Asana migration tracking
- 7 diary API endpoints at `/api/brain/diary/`: list+create, detail+PATCH, stats, recent, brief (AI synthesis)
- Diary browser page at `/brain/diary/` — filterable, searchable, expandable entry cards with new entry modal (Alpine.js)
- Diary stats widget in Nerve Center Brain panel — total entries, total words, entries this week
- `migrate_diary_from_asana` management command — infrastructure for migrating Asana Volume 1 & 2 into NockCC (future use by Mara)
- `get_task_stories_paginated` in `tasks/asana_client.py` — paginated comment fetching for large Asana tasks
- 57 new tests (10 model, 31 API, 3 UI, 10 parsing, 3 integration)

### Changed (Phase 2 Design)
- Completed emerald design system migration across all 11 remaining app templates
- Removed Phase 1 backwards-compat `--accent-start`/`--accent-end` CSS aliases — all templates now reference `--color-accent` directly
- Pipeline: open PRs → emerald border, merged PRs → neutral gray (semantic distinction)
- CRM: negotiation stage → amber (`--color-warning`), active stage → emerald
- Vault: legal documents → cyan (`--color-info`), insurance → amber (`--color-warning`)
- Teams: standard complexity → emerald, deep complexity → cyan; in-review kanban → cyan; hardcoded purple/gray hex replaced with design tokens
- Extended palette tokens (`--color-blue`, `--color-purple`, `--color-orange` and their dim variants) added to nockcc.css — removes last hardcoded hex from all HTML templates
- Desktop/desktop-win loader gradient updated to emerald to match Phase 2 brand
- Design system migrated from blue-purple gradient to emerald (#10B981) brand accent
- Font swapped from DM Sans → Geist (UI) + Geist Mono (code/technical), loaded from Google Fonts
- Card depth system upgraded to Supabase-level layered shadows with inset highlights
- Sidebar active states now use emerald color + emerald-dim background (replaced blue gradient pill)
- Primary buttons now solid emerald with darker hover and scale-on-press feedback
- Button/card hover states gated behind `@media (hover: hover)` — no sticky hover on touch devices
- Emil Kowalski animation tokens added (cubic-bezier ease-out, dur-fast/default/slow)
- `prefers-reduced-motion` block added — all transform animations disabled for accessibility

### Fixed
- Android keyboard no longer covers input fields (`interactive-widget=resizes-content` viewport meta)
- Spend dashboard showing $0 on mobile — service worker now handles `/spend/api/` as network-first
- Agent status `Cache-Control: no-store` set — prevents stale offline readings on mobile
- Service worker cache bumped to v2 to force update on existing installations

---

## 2026-04-07

### Repo Standardization — .claude/ Architecture
- Slimmed CLAUDE.md to lean index (~110 lines) pointing to `.claude/` subdirectories
- Created `.claude/diagrams/` with 4 Mermaid diagrams: models, API map, data flow, Celery tasks
- Created `.claude/design/DESIGN.md` with dark theme brand tokens (pitch black, emerald, Geist)
- Created `.claude/review/PIPELINE.md` with 7-phase review pipeline + priority hierarchy
- Created `.claude/lessons/` with 3 lesson files: data safety, API conventions, Celery gotchas
- Created `.claude/decisions/` with 3 ADRs: Django monolith, WebSocket agent control, pseudo-signals
- Added `.claude/` directory reference to ARCHITECTURE.md

---

## 2026-04-06

### UI Reimagine Phase 2 — Remaining Pages
- Redesigned Spend Dashboard with KPI cards, budget progress bar, styled tables, and design system chart colors
- Redesigned CRM Pipeline with kanban board, view toggle, and stage badges
- Polished Tasks page with project summary cards, filter bar, priority badges, and overdue highlighting
- Redesigned Vault with document card grid, category icons, and tag badges
- Redesigned Teams page with design system variables, modal styling, and ncc-* classes
- Redesigned Prompts page with design system badge and button classes
- Redesigned Remote Chat to match AI Advisor visual style with chat bubbles and terminal view
- Redesigned Notifications with channel status dots, rule cards, and notification log
- Redesigned Context Map with staleness indicators (green/yellow/red borders) and KPI stats
- Integrated actual Nock Technologies logo in sidebar and login page
- Added 12 new CSS component sections to nockcc.css: tabs, KPI row, kanban board, toggle switch, staleness indicators, chat components, view toggle, filter bar, document grid, modals, chart wrappers

---

## 2026-04-04

### NockCC Desktop — Windows Electron App
- Native Windows Electron app wrapping cc.nocktechnologies.io
- Frameless window with custom title bar (minimize/maximize/close)
- System tray icon with right-click menu (Show, navigation, Quit)
- Left-click tray icon toggles window visibility
- Global shortcut: Ctrl+Shift+N toggles window
- Keyboard shortcuts (Ctrl+1-7 for sections, plus Chat/Advisor/Executive)
- Single instance lock — prevents multiple windows
- Minimize to tray on close
- Native Windows notifications via IPC bridge
- Offline handling with retry screen
- Window state persistence via electron-store
- Build scripts: PowerShell (.ps1) and batch (.bat)
- Icon generation: SVG → .ico + .png via sharp + to-ico
- electron-builder config for portable .exe and NSIS installer

---

## 2026-04-03

### Prompt Queue — Autonomous Agent Pipeline (#43)
- `PromptFile` and `PromptExecution` models for managed prompt lifecycle
- Prompt queue UI and API endpoints (`/api/prompts/`)
- Execute prompts via remote agent with status tracking
- Dependency ordering between prompts
- Branch-based PR linking on execution

### Smart Watch — Proactive Observation Loop (#42)
- `SmartWatchRule` and `SmartWatchEvent` models
- 5 default rules: PR waiting, long sessions, task due, context high, brain stale
- `smart_watch_tick` Celery task (every 15 minutes) with cooldown logic
- Telegram notifications on triggered alerts
- REST API for rule CRUD and manual tick
- `seed_smart_watch` management command

## 2026-04-02

### NockCC Desktop — Electron Mac App (#40)
- Native macOS app wrapping NockCC dashboard
- Hidden inset title bar, pitch-black theme
- Menu bar tray icon with quick navigation
- Global shortcut: Cmd+Shift+N toggles window
- Keyboard shortcuts (Cmd+1-7 for sections)
- Native macOS notifications via IPC bridge
- Offline handling with retry screen
- Window state persistence via electron-store
- Build scripts for .app, .dmg, .zip distribution

### Nav Tab Fix (#41)
- Fix clickable nav tabs under hidden title bar

## 2026-04-01

### Design Polish — Pitch Black Command Center (#38)
- Full dark theme redesign across all pages
- Pitch-black cockpit aesthetic

### Mobile Layout Polish (#37)
- Improved tap targets, card layouts, bottom nav
- Mobile-first responsive refinements

### Stale Session Cleanup (#36)
- Auto-cleanup of stale sessions (configurable timeout)
- Manual cleanup option via management

## 2026-03-31

### Agent Teams — Multi-Agent Orchestration (#35)
- `AgentTeam`, `TeamMember`, `TeamTask`, `TeamEvent` models
- Team dashboard at `/teams/teams/`
- Full REST API for teams, members, tasks
- Pipeline signal integration: `on_pr_opened`, `on_pr_merged`, `on_review_alert`
- Task dependencies with blocking/unblocking
- Telegram notifications on PR events

## 2026-03-30

### Continuity Layer + Brain Consolidation + Morning Note (#34)
- `MemoryEntry` and `ConsolidationLog` models in brain app
- Brain consolidation process with three-gate trigger
- Mara's Morning Note via Telegram (daily maintenance task)
- Brain context brief API

### Webhook Review Parser + Telegram Notifications (#33)
- CodeRabbit review status parsing from webhooks
- Telegram notification channel integration

### Brain App + Nerve Center Homepage (#32)
- New `brain/` Django app
- Nerve Center as homepage replacing old dashboard
- Memory entry CRUD API
- Category-based brain organization

## 2026-03-29

### Terminal Bridge — Phase 8 (#31)
- `TerminalHeartbeat` and `SessionReport` models
- 5 bridge API endpoints at `/api/terminal/`
- Dashboard executive API includes terminal status
- 15 new tests (494 total passing)

### Register New Repositories
- Added Forge, jobcost, and claude-terminal to tracked repos
- Auto-register repos on deploy via `register_repos`

## 2026-03-28

### Railway Service Routing Fix (#30)
- SERVICE_ROLE-based entrypoint for web/worker/beat processes
- Fixed Railway multi-service deployment

## 2026-03-27

### Auth Sweep + Real-Time Track Streaming (#29)
- Comprehensive auth audit across all endpoints
- Real-time session output streaming fixes

### Terminal Output View + cc --track Mode (#28)
- Terminal-style session output viewer
- `cc --track` CLI flag for live session monitoring

### API Key Auth Migration (#27)
- All API endpoints switched to X-API-Key auth for mobile app compatibility

### CORS + Mobile API Endpoints
- CORS support for mobile app
- Mobile-specific API endpoints

## 2026-03-16

### Phase 5 — AI Intelligence Layer (#26)
- `intelligence/` Django app
- `BusinessSnapshot`, `AdvisorConversation`, `AdvisorMessage`, `PredictiveAlert`, `WeeklyMemo` models
- Executive dashboard (4-quadrant Bloomberg-style) at `/intelligence/executive/`
- AI Business Advisor chat with Claude Sonnet tool use
- Predictive alerts: 7 alert types checked every 6 hours
- Weekly strategy memo (Sunday 6 PM CST) saved to vault + Slack
- Business snapshot generation (daily 6 AM CST)

### Phase 3 — Business Operations Platform (#25)
- `crm/` app: Contact, Deal, DealNote models
- `vault/` app: Document model with file upload
- Deal pipeline kanban view
- Contact directory
- Document storage with category filtering

### Expense Tracking (#24)
- Expense model added to spend app
- Redesigned spend dashboard with expense table
- Net tax calculation includes refund tax
- Monthly chart nets refunds to match summary totals

## 2026-03-16

### Chat Interface (#23)
- Chat-style conversation interface for remote Claude Code control
- `ConversationThread` model with follow-up prompts
- Session output streaming fixes
- Alpine proxy issue fix for session IDs

## 2026-03-15

### Phase 2 — Remote Mac Agent (PRs #12–#22)
- `remote/` Django app with 6 models
- WebSocket server (Django Channels consumer)
- Mac agent daemon with auto-reconnect
- Command queue REST API with HMAC signing
- SSE output streaming
- Mobile-optimized UI + PWA manifest
- Web Push notifications with VAPID
- Security hardening: session timeout, audit log, token rotation
- Agent subprocess management (no shell injection)
- Kill switch for emergency process termination

### Railway Deployment
- Production deployment to Railway (Daphne + Celery + Beat)
- Custom domain: cc.nocktechnologies.io
- PostgreSQL + Redis managed services
- WhiteNoise static file serving

## 2026-03-14

### Phase 1 — Foundation (PRs #1–#9)
- Django project scaffold (8 apps, split settings, Celery, Channels)
- Pipeline: GitHub webhooks, PR tracking, CI status, 4 Celery tasks
- Sessions: AgentSession model, REST API, CLI tool (`nockcc`)
- Context: CLAUDE.md inventory, GitHub sync, staleness detection
- Spend: Anthropic API polling, budget alerts, Chart.js dashboards
- Tasks: Asana sync, task↔PR fuzzy linkage
- Notifications: Slack/Discord webhooks, alert rules engine
- Dark/light theme, responsive layout, custom error pages
- Login/logout with django-axes brute-force protection
- 175 tests passing at phase completion
