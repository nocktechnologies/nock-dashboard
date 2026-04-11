# PR 2 — Multi-Tenant Auth (django-allauth)

**Status:** APPROVED 2026-04-11 — executing

### Review outcomes (all 10 decision points from §3)

Kevin approved all 10 recommendations verbatim:

1. **Q1 — Delete stub views, repurpose `accounts/` as profile/billing UI host** (option C)
2. **Q2 — Port existing dark-theme login into `templates/account/login.html`** (option A)
3. **Q3 — Defer prod email to PR 6, env-var-driven `EMAIL_BACKEND`** (option A) — **refined**: use Django's SMTP backend with generic env vars `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` so any SMTP provider (Resend / SendGrid / Postmark / Mailgun / SES) can drop in at PR 6 without code changes. Do NOT hardcode a provider name.
4. **Q4 — `"mandatory"` email verification everywhere + `verified_user` test fixture** (option A)
5. **Q5 — Keep both axes and allauth rate limits, add integration test** (option C)
6. **Q6 — Install `allauth.socialaccount`, configure zero providers** (option A)
7. **Q7 — Keep default `User` model, extend via `UserProfile` in PR 3**
8. **Q8 — Lightweight profile page in PR 2, extended in PR 3** (option A)
9. **Q9 — No `ACCOUNT_ADAPTER` override in PR 2, add in PR 3**
10. **Q10 — 22 tests across 7 files targeting the integration layer**

### Timeline posture

Kevin: "Go slower on this one. More verification cycles. This is auth — the thing that stands between the public internet and customer data. Take the time. Run the security self-check twice if you need to. No rush."

Translation for execution:
- Run `manage.py check` + `pytest` after **every** checkpoint, not just the code-changing ones
- Manual browser test after CP3 (routing) AND after CP4 (templates) AND after CP5 (profile) — three visual verifications, not one at the end
- Security self-check runs **twice** at CP8: once when I think I'm done, then again after any discovered fixes
- Run the axes-allauth coexistence test in isolation before running the full suite, to make sure the two rate-limit mechanisms don't hide each other's failures
- When in doubt about a security-adjacent decision, stop and flag, don't guess
**Owner:** Kit (Claude)
**Branch:** `feature/django-allauth` (not yet created)
**Depends on:** `main` at `3a15f68` (PR 3 merge) — which sits on top of PR 2 strip-personal-layers at `71368bb`
**Target:** Second real feature PR in the product-fork pipeline. Full 7-phase engineering standards apply. **This is the most security-sensitive PR in the 6-PR sequence** — allauth configuration, email verification, password reset flows, session cookie scope, CSRF. Security review is not optional.

---

## 1. Goal

Replace the minimal hand-rolled `accounts/` app (40-line login + logout only, no registration, no password reset, no email verification) with `django-allauth` to get a production-grade multi-tenant auth surface for the product fork. Output of this PR is a codebase where:

- Anyone can `POST /accounts/signup/` to create a new account (email + password, no username)
- Login / logout / password reset / email verification all work
- The existing dark-theme login visual (circuit-board background, radial glow, Nock brand) is preserved via template overrides
- The existing `require_brain_access` API decorator (X-API-Key / DRF Token / staff session) continues to work unchanged
- `django-axes` brute-force lockout continues to work through the allauth backend
- Everything in PR 1's strip (brain, intelligence, dashboard, teams) still renders and the test suite stays green
- The full pytest suite passes (target: 760 main + 165 brain + ~15 new allauth integration tests, 2 pre-existing TZ failures unchanged)

**Not in scope:** multi-tenant **data isolation** (owner FK on every data model, queryset filtering, cross-user isolation tests). That's PR 3. PR 2 gives us accounts; PR 3 makes sure users can't see each other's data. They are separate concerns and separate PRs.

---

## 2. Current auth state (researched at 2026-04-11)

### 2a. Existing `accounts/` app

```
accounts/
├── __init__.py
├── admin.py         # only imports TokenAdmin — no actual admin registrations
├── apps.py          # AccountsConfig
├── models.py        # empty (just `from django.db import models`)
├── management/      # empty
├── tests/           # just __init__.py — ZERO tests for the auth flow
├── urls.py          # 2 routes: /login/, /logout/
└── views.py         # 40 lines: login_view + logout_view using AuthenticationForm
```

**What the existing views do:**
- `login_view`: uses `django.contrib.auth.forms.AuthenticationForm`, `django_ratelimit` at 5/m POST, renders `templates/accounts/login.html`, redirects to `next` param or `/`
- `logout_view`: calls `django.contrib.auth.logout`, redirects to `/accounts/login/`
- **NO registration, NO password reset, NO email verification, NO profile page**

### 2b. Existing settings (`config/settings/base.py`)

```python
# Auth
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# django-axes brute-force protection
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_TEMPLATE = "accounts/locked.html"  # template exists at templates/accounts/locked.html
AXES_RESET_ON_SUCCESS = True
```

- **No `AUTH_USER_MODEL` override** — using default `django.contrib.auth.User`
- **No `django.contrib.sites`** in `INSTALLED_APPS` — allauth requires it
- **No `SITE_ID`** set
- **No `EMAIL_BACKEND`** in base.py; `dev.py` has `django.core.mail.backends.console.EmailBackend`
- **No `DEFAULT_FROM_EMAIL`** configured
- **DRF configured** with `TokenAuthentication` + `SessionAuthentication` as default classes

### 2c. Existing templates

- `templates/accounts/login.html` — **full standalone login page** with its own `<html>` tag (does NOT extend `base.html`). ~200 lines of custom dark-theme CSS + SVG circuit-board background + radial glow effects. Quality design worth preserving.
- `templates/accounts/locked.html` — django-axes lockout template (exists, not inspected yet)

### 2d. Auth consumers across the codebase

- **`@login_required`** is imported and used in 14 view modules: pipeline, tasks, context, intelligence, crm, dashboard, sessions, teams, spend, brain, notifications, vault, remote, dashboard/tests/test_pm_views.py. All of these redirect unauthenticated users to `LOGIN_URL`.
- **`require_brain_access`** (`core/auth.py`) — decorator that gates the Brain API on: API key (X-API-Key header) OR DRF Token (Authorization: Token ...) OR authenticated staff session. Orthogonal to web login — continues to work without modification.
- **Pipeline webhook** — HMAC signature verification, not user auth. Unchanged.
- **Remote agent** — `AgentToken` scheme, not user auth. Unchanged.
- **Django admin** — `/admin/login/` with its own form. allauth doesn't touch it.

### 2e. Dependencies

- **`django-allauth` is NOT in `requirements.txt`.** Needs to be added.
- `rest_framework.authtoken` is installed for API tokens — orthogonal, unchanged.
- `django-axes` is installed and configured — must continue to work through the allauth backend.
- `django-ratelimit` is installed — will be dropped from the login view (replaced by allauth's `ACCOUNT_RATE_LIMITS` and axes' failure limit).

---

## 3. Decision points — I need Kevin's answers before writing code

### Q1: Delete the existing `accounts/` app entirely, or mount allauth at a different URL?

**Options:**
- **A. Delete the stub.** Remove `accounts/views.py`, `accounts/urls.py`, `accounts/tests/`, `accounts/templates/` references, and unregister from `INSTALLED_APPS`. Let django-allauth fully own `/accounts/`. `accounts/apps.py`, `accounts/models.py`, `accounts/admin.py` either go or stay depending on whether we want the namespace reservation.
- **B. Keep the stub app, mount allauth at `/auth/`.** Two parallel auth surfaces — the hand-rolled one at `/accounts/` and allauth at `/auth/`. Confusing for users, extra maintenance.
- **C. Repurpose `accounts/` as the "profile + billing UI" layer.** Keep the app, empty out views/urls, let allauth own `/accounts/*` for auth, and in PR 3 add `/accounts/profile/` custom views in this app that extend allauth.

**My recommendation: C.** It preserves the `accounts` namespace for future non-allauth views (profile, subscription management, team invites) without the stub's confusing parallel login. PR 3 will add `UserProfile` and `/accounts/profile/` lives naturally inside `accounts/views.py`. The existing `login_view` and `logout_view` get deleted; the app becomes a host for profile + billing UI in PR 3/4/5.

---

### Q2: What happens to the existing dark-theme login template?

The current `templates/accounts/login.html` is a polished standalone login page (circuit-board SVG background, radial glow, Nock brand, custom CSS) that does NOT extend `base.html`. Allauth's default templates are plain and ugly.

**Options:**
- **A. Port the existing visual into `templates/account/login.html`** (allauth's template path). Keeps the dark-theme design. Allauth expects a specific form-field rendering pattern; we'd need to swap `AuthenticationForm` rendering for allauth's `{{ form.as_p }}` or Django form rendering.
- **B. Start fresh with allauth's defaults**, layer on dark-theme styling later in PR 5 (public landing + pricing). Fast to ship, ugly in the meantime.
- **C. Extend `base.html`** so the login page fits into the sidebar-shell look. Doesn't match the current standalone design but is faster to implement.

**My recommendation: A.** The existing template is high-quality visual work worth preserving. The form-rendering swap is mechanical (3-4 fields, error messages, submit button). I'll adapt it in place. Signup / password reset / email verification pages get lightweight variations of the same template.

---

### Q3: Email backend for dev vs production?

**Current state:**
- Dev: `django.core.mail.backends.console.EmailBackend` — prints emails to stdout
- Prod: NOT CONFIGURED

**The constraint:** `ACCOUNT_EMAIL_VERIFICATION = "mandatory"` means new users cannot log in until they verify via email. In dev, console output works (copy the verification link from stdout). In prod, we need a real transactional email provider.

**Options:**
- **A. Defer prod email to PR 6 (deployment).** PR 2 ships with `EMAIL_BACKEND` configurable via env var, production value blank until PR 6 picks a provider. Staging deploy would fail at email send; that's acceptable for a staging environment.
- **B. Pick a provider now** (Mailgun, Postmark, SendGrid, Amazon SES, Resend) and wire it up in PR 2. Provides confidence that the end-to-end flow works on a staging environment immediately.
- **C. Use Django's SMTP backend pointed at a provider.** Requires `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_PORT`, `EMAIL_USE_TLS` env vars.

**My recommendation: A, with `EMAIL_BACKEND` driven by an env var.** Local dev continues to use console backend. Production env var is blank until PR 6 picks a provider. PR 2 is about the auth infrastructure, not email infrastructure. Document the blank-prod-email state in the PR 2 known-issues.

**Refinement per Kevin (2026-04-11):** Structure the env vars generically so any SMTP provider drops in. Use Django's built-in SMTP backend with:

```python
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@localhost")
```

At PR 6 deploy time, set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` + the SMTP credentials for whichever provider is chosen (Resend, SendGrid, Postmark, Mailgun, SES — all speak SMTP). No code changes required at PR 6. Do **not** hardcode a provider name anywhere in settings or docs.

---

### Q4: Email verification in dev — mandatory or optional?

**The trade-off:** `ACCOUNT_EMAIL_VERIFICATION = "mandatory"` in dev means every self-test requires copying a verification link from stdout. Fast to forget, slow to iterate. But if dev is `"optional"` and prod is `"mandatory"`, we're testing different behavior in dev vs prod.

**Options:**
- **A. `"mandatory"` everywhere.** Same behavior dev and prod. Pay the dev friction cost. Write a helper test fixture that auto-verifies users for test flows.
- **B. Override to `"optional"` in `config/settings/dev.py`.** Dev iteration is fast, prod is correct. Risk: missing a bug that only shows up under the mandatory gate.
- **C. `"mandatory"` with a `MANAGE_EMAIL_VERIFICATION_BYPASS` env var** that lets dev bypass the mandatory gate when explicitly set.

**My recommendation: A with a test fixture.** One `verified_user` fixture in `conftest.py` that creates a user and pre-verifies them via allauth's `EmailAddress` model. All tests use the fixture; manual dev testing is unavoidable but the console backend makes it survivable. Consistency between dev and prod beats dev iteration speed.

---

### Q5: `django-axes` coexistence with allauth

**Current state:** django-axes wraps `AUTHENTICATION_BACKENDS` and captures failed logins at the backend level. Allauth uses its own backend (`allauth.account.auth_backends.AuthenticationBackend`). The question is whether axes will correctly capture failures through allauth's backend.

**Axes documentation says:** axes hooks via `authenticate()` signals and works with any backend that uses `django.contrib.auth.authenticate()`. Allauth's backend does use it.

**Options:**
- **A. Keep axes as-is, verify integration with a dedicated test.** Add allauth's backend to `AUTHENTICATION_BACKENDS` BEFORE `ModelBackend` and AFTER `AxesStandaloneBackend`. Write a test that fails login 5 times and asserts a lockout.
- **B. Drop axes, rely on allauth's `ACCOUNT_RATE_LIMITS` (allauth 0.58+).** Less coverage overlap, but losing the 15-minute cooloff behavior axes provides.
- **C. Both.** Axes for IP-based brute-force lockout (long cooloff), allauth rate limits for per-user throttling (short window). Belt and suspenders.

**My recommendation: C.** Both mechanisms run at different granularities and costs. Test that they coexist without double-counting failures.

---

### Q6: `allauth.socialaccount` — install or skip?

CLAUDE.md's PR 2 spec says install both `allauth.account` AND `allauth.socialaccount`. No social providers (Google / GitHub / etc.) are configured in the spec.

**Options:**
- **A. Install both, configure zero providers.** Ready for future Google/GitHub/Microsoft sign-in without another migration.
- **B. Skip `socialaccount` entirely.** Less schema, less surface. Add later when we need it.

**My recommendation: A (follows the spec).** Installing `socialaccount` creates a handful of DB tables (`socialaccount_socialaccount`, `socialaccount_socialapp`, `socialaccount_socialtoken`) that are empty until a provider is configured. Zero runtime cost, ready for PR 7 or whenever social sign-in is needed.

---

### Q7: `AUTH_USER_MODEL` — keep default or swap now?

**The long view:** Multi-tenant SaaS typically wants extra fields on User (company name, Stripe customer ID, subscription plan, trial end date). Django strongly recommends setting `AUTH_USER_MODEL` at project start because swapping it later is extremely painful.

**But:** The fork is already post-start. The `User` table has existing rows (admin users, test data). Swapping `AUTH_USER_MODEL` now would require a full data migration and is higher risk than it's worth.

**The CLAUDE.md spec says** to use a `UserProfile` OneToOneField approach in PR 3, which is the recommended pattern for "extend User without swapping it."

**My recommendation: keep default `User`, add `UserProfile` OneToOneField in PR 3.** Confirmed by the CLAUDE.md spec. No action needed in PR 2 besides documenting the decision here.

---

### Q8: Profile page in PR 2 vs PR 3?

CLAUDE.md PR 2 spec lists `/accounts/profile/` as an auth page. But the `UserProfile` model (with `company_name`, `stripe_customer_id`, `subscription_plan`, etc.) doesn't land until PR 3.

**Options:**
- **A. Lightweight profile in PR 2.** Display `email`, `username`, `date_joined`, `last_login` from the default User model. PR 3 extends it with UserProfile fields.
- **B. Skip profile in PR 2, add it in PR 3** alongside UserProfile.

**My recommendation: A.** Gives users a visible "I'm logged in" landing page + lays the template + URL plumbing PR 3 will extend. One lightweight view + one template. ~30 lines.

---

### Q9: `ACCOUNT_ADAPTER` — override the default?

allauth has `ACCOUNT_ADAPTER` for customizing signup/email/URL generation logic. The default is fine for most cases.

**Potential reason to override:** we might want to enforce that new signups get a default `subscription_plan = "free_trial"` with `trial_ends_at = now + 14 days`. But that's PR 3/PR 4 scope (UserProfile + billing), not PR 2.

**My recommendation: don't override in PR 2.** Add a custom `ACCOUNT_ADAPTER` in PR 3 when the UserProfile is added, at which point the signup hook can set the trial defaults.

---

### Q10: Test coverage scope

CLAUDE.md spec: "Registration, login, logout, password reset, email verification, redirect after login."

**Proposed test count:**
- `test_signup.py` (5 tests): signup page renders, valid signup creates user + sends verification email, duplicate email rejected, weak password rejected, signup redirects to email-sent page
- `test_login.py` (4 tests): login page renders, valid credentials log in + redirect, invalid credentials show error, unverified user cannot log in (allauth blocks)
- `test_logout.py` (2 tests): logout clears session, redirect to `/accounts/login/`
- `test_password_reset.py` (4 tests): reset page renders, submitting email sends reset link, reset link form validates, new password takes effect
- `test_email_verification.py` (3 tests): new user gets verification email, verification link works, expired/bad token rejected
- `test_profile.py` (2 tests): authenticated user sees profile page, unauthenticated redirect to login
- `test_axes_integration.py` (2 tests): 5 failed logins locks out, successful login resets counter

**Total: 22 tests.** Target coverage is the integration layer (URL routing, template rendering, form handling, email sending, session behavior) — NOT re-testing allauth's internal views. That's allauth's job.

---

## 4. Execution plan — layered checkpoints

Same pattern as PR 1: one commit per checkpoint for reviewability.

**Checkpoint 0 — Baseline**
- `git checkout -b feature/django-allauth` from `main@3a15f68`
- Capture baseline: `manage.py check`, `pytest` (target: 760 main + 165 brain, 2 pre-existing TZ failures), `showmigrations`

**Checkpoint 1 — Install allauth + contrib.sites**
- `pip install django-allauth[socialaccount]` and pin version in `requirements.txt`
- Add `django.contrib.sites` to `DJANGO_APPS`, add `SITE_ID = 1`
- Add `allauth`, `allauth.account`, `allauth.socialaccount` to `THIRD_PARTY_APPS`
- Add `allauth.account.middleware.AccountMiddleware` to `MIDDLEWARE` (allauth 0.56+)
- Add allauth backend to `AUTHENTICATION_BACKENDS` between `AxesStandaloneBackend` and `ModelBackend`
- Run `manage.py migrate` → creates `allauth_*`, `socialaccount_*`, `django_site` tables. Confirm migration succeeds on fresh DB
- Run `pytest` — should still pass (no routing changes yet)

**Checkpoint 2 — Settings for allauth behavior**
- Add allauth settings block: `ACCOUNT_EMAIL_REQUIRED = True`, `ACCOUNT_USERNAME_REQUIRED = False`, `ACCOUNT_AUTHENTICATION_METHOD = "email"`, `ACCOUNT_EMAIL_VERIFICATION = "mandatory"`, `ACCOUNT_USER_MODEL_USERNAME_FIELD = None`, `ACCOUNT_EMAIL_NOTIFICATIONS = True`, `ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"` (for production URL generation), `ACCOUNT_RATE_LIMITS = {...}` (login throttle)
- Add `EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")` + `DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@localhost")`
- Keep existing `LOGIN_URL`, `LOGIN_REDIRECT_URL`, `LOGOUT_REDIRECT_URL` (they already match allauth's defaults)
- Run `manage.py check`

**Checkpoint 3 — Route allauth URLs, delete stub accounts views**
- Swap `path("accounts/", include("accounts.urls", namespace="accounts"))` → `path("accounts/", include("allauth.urls"))` in `config/urls.py`
- **Delete `accounts/urls.py`, `accounts/views.py`** (the 40-line hand-rolled login + logout stubs)
- Keep `accounts/apps.py`, `accounts/models.py`, `accounts/admin.py`, `accounts/tests/` (empty shell for PR 3's UserProfile + /accounts/profile/ to land into)
- Run `manage.py check` — allauth's URL conf should load
- Test: `curl http://localhost:8000/accounts/login/` renders allauth's login (with our template override)

**Checkpoint 4 — Template overrides for the dark theme**
- Create `templates/account/login.html` (allauth's convention is `account/` not `accounts/`) — adapt the existing `templates/accounts/login.html` standalone dark-theme design to render allauth's form fields
- Create `templates/account/signup.html` — variation of login with extra email confirmation + password2 fields
- Create `templates/account/password_reset.html` + `password_reset_done.html` + `password_reset_from_key.html` + `password_reset_from_key_done.html`
- Create `templates/account/email_confirm.html` + `email_confirmation_sent.html` + `verification_sent.html` + `verified_email_required.html`
- Create `templates/account/logout.html` — lightweight confirm-logout page
- Delete `templates/accounts/login.html` (superseded by `templates/account/login.html`)
- Keep `templates/accounts/locked.html` (still used by django-axes)
- Run `manage.py runserver` locally and visually verify each page renders correctly

**Checkpoint 5 — Lightweight profile view**
- Add `accounts/urls.py` back with a single route: `path("profile/", views.profile_view, name="profile")`
- Add `accounts/views.py` with `profile_view` — `@login_required`, renders `templates/accounts/profile.html` with `user.email`, `user.username`, `user.date_joined`, `user.last_login`
- Update `config/urls.py` to mount BOTH allauth and the stub accounts routes: allauth for `/accounts/login/`, `/accounts/signup/`, etc., and `accounts.urls` for `/accounts/profile/`. Note: URL ordering matters — allauth's `include` handles everything under `/accounts/` that it knows about, then falls through to the local accounts/urls.py for /profile/. Actually: cleaner to mount the profile at a separate path like `path("accounts/profile/", views.profile_view)` directly in config/urls.py to avoid include-ordering fragility. Decision in the doc's commit.
- Create `templates/accounts/profile.html` extending `base.html` — shows email, join date, last login, placeholder for PR 3 subscription info
- Run `manage.py check` + smoke test locally

**Checkpoint 6 — Tests**
- Write the 22 tests outlined in §3 Q10, organized into 7 test files under `accounts/tests/`
- Add a `verified_user` fixture to `accounts/tests/conftest.py` for post-verification test flows
- Run `pytest accounts/tests` — all green
- Run full `pytest` — 760 main + 165 brain + 22 new = 947 passing, 2 pre-existing TZ failures

**Checkpoint 7 — CHANGELOG + docs housekeeping**
- Add a new `## [Unreleased] — 2026-04-1X` entry under the "Nock Dashboard — Product Fork" section of CHANGELOG.md documenting:
  - The allauth install + allauth.account + allauth.socialaccount
  - The settings changes
  - The deleted `accounts/views.py` stub
  - The template override convention (`templates/account/*.html` for allauth, `templates/accounts/*.html` for non-allauth views)
  - The "one-time `dropdb && createdb && migrate`" requirement for dev environments (because allauth + socialaccount + sites tables are net-new)
  - Known issues: prod email backend still blank (deferred to PR 6)
- Do NOT touch README / ARCHITECTURE / ROADMAP / CODEX (PR 6 owns the big doc sweep)

**Checkpoint 8 — Full verification**
- `manage.py check` — clean
- `makemigrations --check --dry-run` — No changes detected
- `migrate` against a fresh `nock_dashboard_dev` postgres — clean
- `pytest` full suite — 760 main + 165 brain + 22 new accounts, 2 pre-existing TZ failures
- `grep -r "AuthenticationForm\|django_ratelimit" accounts/` — zero hits (replaced by allauth + axes)
- Manual browser test: signup → verify email from console output → login → see profile → logout → hit a protected page → redirected back to login
- Security self-check per the CLAUDE.md "security-guidance plugin MANDATORY on every PR" clause:
  - CSRF tokens present on every POST form
  - Session cookies have `HttpOnly` + `Secure` (prod) + `SameSite=Lax`
  - Password reset links expire (allauth default: 3 days — acceptable)
  - Email verification links are single-use
  - Rate limits present on signup, login, password reset
  - No PII in logs
  - Axes lockout still works

---

## 5. Known risks & open questions (beyond the 10 decision points)

1. **URL-ordering fragility if both `allauth.urls` and `accounts.urls` are mounted at `/accounts/`.** `allauth.urls` catches `/accounts/login/`, `/accounts/signup/`, etc. The stub `accounts.urls` would catch `/accounts/profile/` only. If allauth's include has a broad `path("", ...)` catch-all, the stub profile route might never fire. Mitigation: mount `/accounts/profile/` as a direct `path()` in `config/urls.py` (not via include), order before `allauth.urls` include.

2. **The existing `templates/accounts/login.html` does NOT extend `base.html`.** It's a standalone page. allauth's default templates DO extend a base template (allauth uses `account/base.html` as its own). We either need to make the new `templates/account/login.html` fully standalone (copy the design verbatim) OR have it extend a new `templates/account/base.html` that in turn extends nothing (to match the current look). Easier: standalone.

3. **django-axes captures failed authenticate() calls.** allauth does `authenticate()` internally, so axes should capture it. But the interaction between allauth's own rate limits (`ACCOUNT_RATE_LIMITS`) and axes' failure lockout needs a dedicated test — both mechanisms could be active simultaneously and the user-visible behavior should be well-defined. Hit axes first (5 failures → 15 min lockout) OR allauth's limit (typically 5/5min) — whichever triggers first wins.

4. **Admin superuser compatibility.** The existing Kevin admin superuser has a username and an email. allauth with `ACCOUNT_USERNAME_REQUIRED = False` + `ACCOUNT_AUTHENTICATION_METHOD = "email"` means new signups are created with `username=""` (or allauth generates a UUID-ish username internally). The existing superuser has both — login via Django admin should still work (it uses its own form), and login via allauth should work if we use email. Verify with a manual test.

5. **`django-axes` `AxesStandaloneBackend` vs the `axes.backends.AxesBackend` dual backend.** The current setup uses `AxesStandaloneBackend` which is a distinct backend that intercepts authenticate() calls. Compatibility with allauth is good, but the axes documentation is worth re-reading to confirm.

6. **Password validators.** `AUTH_PASSWORD_VALIDATORS` is configured (line 108 in base.py). allauth uses these by default. No change needed.

7. **Sessions vs DRF tokens coexistence.** `require_brain_access` decorator already handles this (API key → DRF token → session). No changes needed. Verified by reading `core/auth.py`.

8. **`pytest.ini` does NOT include `accounts/tests/` in testpaths.** Same latent gotcha as `brain/tests` in PR 1. I'll explicitly add `accounts/tests` to `testpaths` in this PR since the tests are net-new and there's no "inherited drift" concern — the fix is scope-appropriate here.

---

## 5a. Baseline captured — 2026-04-11 (checkpoint 0)

Branch: `feature/django-allauth` from `main@3a15f68`
Python: 3.12.12, Django 5.0.4, venv at `.venv/`, local dev DB: `nock_dashboard_dev` (postgres, reset fresh before baseline run)

**`python manage.py check`:** clean (0 issues)

**`python manage.py migrate` against fresh `nock_dashboard_dev` postgres:** clean — all apps apply including the 3 backfilled apps from PR 0 (`notifications`, `remote`, `vault`) and the rewritten brain chain (`0001`..`0007`) from PR 1.

**`python manage.py makemigrations --check --dry-run`:** No changes detected (confirms the fork is self-consistent after PR 1 + PR 3 merged to main).

**Main test suite** (`pytest` with default `testpaths`): **760 passed, 2 failed in 215s**
- `pipeline/tests/test_review_alerts.py::TelegramNotifierTests::test_not_quiet_hours`
- `pipeline/tests/test_review_alerts.py::TelegramNotifierTests::test_quiet_hours_midnight_crossing`
- Both are pre-existing timezone-dependent failures inherited from PR 0 / PR 1 baselines. Treat as baseline-red — any state where these are the only failures after PR 2 is still green for PR 2 purposes.

**Brain test suite** (explicit `pytest brain/tests` — still not in default `testpaths` per the latent gotcha from PR 1): **165 passed, 0 failed in 73s**

**Accounts test suite** (explicit `pytest accounts/tests`): **0 collected** — expected, the existing accounts/ stub has no tests. PR 2 adds 22 tests across 7 files at CP6.

### Expected post-PR-2 test counts (to be verified at CP8)

- Main: 760 passed / 2 failed (unchanged — no new test failures from allauth integration)
- Brain: 165 passed (unchanged — PR 2 doesn't touch brain)
- Accounts: **22 passed** (new, the 7 files from §3 Q10)
- Grand total: **947 passed / 2 failed**

### Baseline gotchas (carried forward from PR 1, not fixed in PR 2)

1. `brain/tests` still not in `pytest.ini` `testpaths`. Still a latent coverage gap. Scope for a dedicated cleanup PR (not PR 2)
2. ~~`mcp_server/tests` still listed in `testpaths` but directory doesn't exist.~~ **RESOLVED by `chore/strip-mcp-refs` (nocktechnologies/nock-dashboard#4, merged as `1e78ae5`).** See §5b below for the post-strip baseline refresh.
3. `accounts/tests` ALSO not currently in `testpaths`. **PR 2 WILL add `accounts/tests` to `testpaths`** at CP6 because the tests are net-new and there's no inherited-drift concern. This is the only `testpaths` change that's scope-appropriate in PR 2

## 5b. Baseline refresh — 2026-04-11 (checkpoint 0b, post chore/strip-mcp-refs merge)

Branch: `feature/django-allauth` rebased onto `main@1e78ae5` (the merge commit for `chore: strip MCP / OAuth-shim references from fork` — PR #4).

### Why CP0b exists

CP0 was captured against `main@3a15f68` with a **broken local venv** (`pyvenv.cfg` copied from nock-command-center, `sys.path` fall-through resolving `mcp_server` to nock-cc's project tree). That venv was masking two latent bugs:

1. **Broken ASGI entry point** — `config/asgi.py` did a top-level `from mcp_server.http_app import build_http_app`, which raised `ModuleNotFoundError` on a clean venv. Production uvicorn would have failed to boot. `manage.py runserver` (via Daphne's channels override) would have failed to boot.
2. **32 dead tests** — `core/tests/test_oauth.py` had 28 passing tests + 4 failing tests, all testing the OAuth 2.1 shim at `core/oauth/` that existed solely to gate the absent MCP server.

Rebuilding the venv from scratch at CP0 exposed both issues. Rather than bloat PR 2's diff with an unrelated 1605-line deletion, a separate chore PR (`chore/strip-mcp-refs` → #4) landed the MCP + OAuth shim cleanup. CP0b refreshes the baseline numbers on top of that merged chore. Per Kevin's instruction: clean append, CP0 is NOT rewritten.

### Post-strip baseline (captured 2026-04-11)

Branch: `feature/django-allauth` at HEAD, rebased onto `main@1e78ae5`
Python: 3.12.12, Django 5.0.4, venv at `.venv/` (freshly created via `python3.12 -m venv .venv && pip install -r requirements.txt` during the CP0 venv rebuild)
Local dev DB: `nock_dashboard_dev` (postgres, fresh)

**`python -c "import config.asgi"`:** **loads successfully** (was ModuleNotFoundError on fresh venv before PR #4 landed)

**`python manage.py check`:** clean (0 issues)

**`python manage.py makemigrations --check --dry-run`:** No changes detected

**Main test suite** (`pytest` with `pytest.ini` default `testpaths` — now without `mcp_server/tests`): **728 passed, 2 failed in 188s**
- `pipeline/tests/test_review_alerts.py::TelegramNotifierTests::test_not_quiet_hours`
- `pipeline/tests/test_review_alerts.py::TelegramNotifierTests::test_quiet_hours_midnight_crossing`
- Both are pre-existing timezone-dependent failures. Root cause: the tests `mock.patch` a `core.telegram.dj_timezone` attribute that doesn't exist on the module. Unchanged from PR 0/PR 1 baselines; continues as baseline-red for PR 2.

**Brain test suite** (explicit `pytest brain/tests`): **165 passed, 0 failed in 52s** — unchanged from CP0 (PR #4 didn't touch brain).

**Accounts test suite** (explicit `pytest accounts/tests`): **0 collected** — still the stub app with no tests. PR 2 adds 22 tests at CP6.

### Delta vs. CP0 (stale broken-venv baseline)

| Metric | CP0 (broken venv) | CP0b (post-strip, fresh venv) | Delta |
|---|---|---|---|
| Main pytest passed | 760 | 728 | −32 |
| Main pytest failed | 2 | 2 | 0 |
| Brain pytest passed | 165 | 165 | 0 |
| `config.asgi` imports | ✗ (hidden by fall-through) | ✓ | fixed |
| `runserver` boots | ✗ (hidden by fall-through) | ✓ | fixed |

The −32 in main pytest is entirely the deleted `core/tests/test_oauth.py` (28 passing + 4 failing). Not a regression — all 32 were testing dead code for a non-existent MCP server.

### Updated expected post-PR-2 counts (supersedes §5a's final grand-total line)

- Main: **728 passed / 2 failed** (unchanged — PR 2 doesn't add to the main suite)
- Brain: **165 passed** (unchanged)
- Accounts: **22 passed** (new at CP6)
- **Grand total: 915 passed / 2 failed**

## 6. Out of scope for PR 2

- Multi-tenant data isolation (owner FK, queryset filtering, cross-user tests) → PR 3
- Stripe billing + subscription gate → PR 4
- Public landing page + pricing → PR 5
- Production email provider (Mailgun / Postmark / SES / Resend) → PR 6
- Social auth providers (Google, GitHub, Microsoft) → post-launch feature
- Two-factor auth (TOTP via `allauth.mfa` or `django-otp`) → post-launch feature
- Team / organization accounts (multi-user orgs sharing a workspace) → post-launch feature, possibly part of the "Team" subscription tier
- User impersonation for support → post-launch ops feature
- Account deletion / GDPR data export → PR 5 or later (compliance-driven timing)

---

## 7. Verification checklist (Phase 3 — to be executed at checkpoint 8)

- [ ] `python manage.py check` — clean
- [ ] `python manage.py makemigrations --check --dry-run` — No changes detected
- [ ] `python manage.py migrate` against fresh `nock_dashboard_dev` postgres — clean
- [ ] Full `pytest` — 760 main + 165 brain + 22 new accounts tests = 947 passing, 2 pre-existing TZ failures
- [ ] `grep -r "AuthenticationForm\|django_ratelimit" accounts/` — zero hits
- [ ] Manual browser walk-through: signup → verify email from console → login → profile → logout → protected page → redirect
- [ ] CSRF tokens present on every POST form (inspect rendered HTML)
- [ ] Session cookies: `HttpOnly`, `Secure` (prod), `SameSite=Lax`
- [ ] Password reset link expires per allauth defaults (3 days)
- [ ] Email verification link is single-use
- [ ] Rate limits present on signup, login, password reset (test by hitting them)
- [ ] django-axes lockout still works (test: 5 failed logins → locked)
- [ ] `/admin/login/` still works for the Kevin superuser
- [ ] `require_brain_access` decorator still gates `/api/brain/entries/` (test with API key, DRF token, session, unauth — 4 cases)

---

## 8. How I'll execute

After Kevin answers the 10 decision points in §3:

1. Create branch `feature/django-allauth` from `main@3a15f68`
2. Work through checkpoints 0–7 one at a time, committing per checkpoint
3. Run checkpoint 8 verification
4. Update this plan doc with actual counts + commit as the design record
5. Push, open PR on nocktechnologies/nock-dashboard, wait for the auto-review triad + Kevin
6. Apply review fixes, merge when clean

**No code until Kevin signs off on §3 decision points.**
