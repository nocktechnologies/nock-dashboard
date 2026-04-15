# Security Audit Report — P78
**Auditor:** Warden  
**Date:** 2026-04-15  
**Target:** nocktechnologies/nock-dashboard — PR #10 (feat/workspaces: P75 multi-tenancy)  
**Scope:** Pre-launch security audit per NockCC prompt #79

---

## Verdict Summary

| Category | Status |
|----------|--------|
| Tenant isolation correctness | PASS |
| Middleware ordering | PASS |
| Object-level auth (IDOR) | PASS |
| Cross-tenant data leak (session auth) | PASS |
| Authentication surface | PASS |
| CSRF / session cookie security | PASS |
| CORS / HTTPS enforcement | PASS |
| Dependency CVEs | **FAIL** |
| Data leakage — personal refs stripped | **FAIL** |
| .env.example present | **FAIL** |
| PM plugin workspace isolation | **WARN** |
| Brain app surface area | **WARN** |

**Overall: FAIL — 3 blockers must be resolved before launch.**

---

## 1. Authentication Surface

### 1.1 DEBUG and ALLOWED_HOSTS
- **PASS** — `DEBUG = False` in both `base.py` and `prod.py`.
- **PASS** — `ALLOWED_HOSTS` reads from env var; defaults to `["localhost"]` in prod.py (fails safe if env not set).

### 1.2 allauth configuration
- **PASS** — `ACCOUNT_EMAIL_VERIFICATION = "mandatory"` enforced.
- **PASS** — `ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"` set.
- **PASS** — django-axes brute-force protection active (configured in `base.py`).

### 1.3 Login-required coverage
- **PASS** — All `@login_required` views in dashboard, context, pipeline, sessions, notifications, tasks, and teams apps use `tenant_objects.for_request(request)` for tenant-scoped models.
- **PASS** — `get_object_or_404(Model.tenant_objects.for_request(request), pk=id)` pattern prevents IDOR on all detail views.

### 1.4 CSRF middleware
- **PASS** — `django.middleware.csrf.CsrfViewMiddleware` in middleware stack.
- **PASS** — `CSRF_COOKIE_SECURE = True` in prod.py.
- **PASS** — `@csrf_exempt` only on API key and webhook endpoints where session auth is not the auth method.

### 1.5 Session cookie security
- **PASS** — `SESSION_COOKIE_SECURE = True` in prod.py.
- **PASS** — `SESSION_COOKIE_AGE = 1800` (30-minute sliding window).
- **INFO** — `SESSION_COOKIE_HTTPONLY` not explicitly set; Django defaults to `True`. Acceptable.
- **INFO** — `SESSION_COOKIE_SAMESITE` not explicitly set; Django defaults to `"Lax"`. Acceptable for this app's auth flows.

---

## 2. Multi-Tenancy: Isolation Correctness

### 2.1 WorkspaceMiddleware
- **PASS** — Positioned after `AuthenticationMiddleware` in `MIDDLEWARE` list. `request.user` is available when `_resolve()` runs.
- **PASS** — Unauthenticated requests: `request.workspace = None`.
- **PASS** — Users with no accepted membership: `request.workspace = None`.
- **PASS** — `X-Workspace-Slug` header override gated strictly on `user.is_superuser` (not `is_staff`). Codex-confirmed positive + negative cases.
- **PASS** — `WorkspaceMembership.objects.filter(accepted_at__isnull=False)` — pending/unaccepted invitations do not resolve a workspace.

### 2.2 TenantManager
- **PASS** — `for_request()` returns `self.get_queryset().none()` when `workspace is None`. No data leak for unresolved workspace.
- **PASS** — Superuser bypass (`return self.get_queryset().all()`) only fires when workspace is non-None AND user is superuser. Edge case: superuser with no workspace still gets empty queryset (workspace is None → early return before superuser check). This is correct — no unintended superuser data access.
- **PASS** — Dual-manager pattern (`objects` = unscoped for jobs/webhooks, `tenant_objects` = scoped for views) is correctly applied across all 24 tenant models.

### 2.3 Signal auto-provisioning
- **PASS** — `_on_user_signed_up` creates `Workspace` + `WorkspaceMembership` with `accepted_at=timezone.now()` in a single `transaction.atomic()` block.
- **PASS** — Idempotent: skips creation if user already owns a workspace.

### 2.4 Cross-tenant isolation tests
- **PASS** — 55 workspace tests pass (37 isolation tests × 24 models + cross-cutting edge cases + manager/middleware/model/signal tests).
- Verified locally: `python -m pytest workspaces/ -q` → 55 passed.

---

## 3. API Security

### 3.1 URL inventory — unauthenticated endpoints
- **PASS** — Only `/healthz/` and GitHub webhook (`/pipeline/github/webhook/`) accept unauthenticated POST. Webhook verifies `X-Hub-Signature-256` HMAC.
- **PASS** — All other endpoints require `@login_required`, `@require_api_key`, or `@require_brain_access`.

### 3.2 API key scoping
- **PASS** — API key is a single shared server-side secret (not per-user/per-workspace). This is correct for single-operator deployment; for true multi-tenancy, per-workspace keys will be needed. Documented design choice.
- **PASS** — `secrets.compare_digest` used for constant-time comparison.
- **PASS** — API key endpoints intentionally unscoped (agent fleet has global access by design). Confirmed consistent.

### 3.3 Admin URL
- **PASS** — `/admin/` is mounted. Protected by allauth email verification and django-axes brute-force lockout.
- **INFO** — Consider IP-restricting `/admin/` at the Railway/reverse-proxy layer before launch.

### 3.4 Django debug toolbar / debug views
- **PASS** — `DEBUG = False` in prod; debug toolbar is not in `INSTALLED_APPS` in base settings.

---

## 4. Data Leakage

### 4.1 Personal references — FAIL (blocker)
Several personal identifiers from the NockCC fork were not stripped and remain in production-serving code:

**`config/settings/base.py`:**
- `VAPID_CLAIMS_EMAIL = env("VAPID_CLAIMS_EMAIL", default="mailto:kevin@nocktechnologies.io")` — personal email hardcoded as default. **Severity: MINOR (not a blocker on its own, but must be fixed before launch).** Remove default; require env var.
- Celery beat schedule entry: `"task": "brain.tasks.daily_maintenance"` with comment `# 6 AM MT — Mara's morning note`. Personal reference in production config.

**`config/urls.py`:**
- `path("api/prompts/ready-for-kevin/", ...)` — personal name in production URL. Rename before launch.

### 4.2 Hardcoded secrets in tracked files
- **PASS** — `.env` is gitignored and has never been committed (verified via `git ls-files .env` and `git log -- .env`).
- **PASS** — No hardcoded API keys or passwords found in tracked Python or config files.

### 4.3 .env.example — FAIL (blocker)
- **FAIL** — No `.env.example` exists in the repo. Required by P78 checklist and by standard practice so new deployments know what env vars are needed. Must be created before launch.

### 4.4 Fixtures / seed data
- **PASS** — No fixtures with personal data found in tracked files.
- **INFO** — `brain/migrations/0002_seed_memory_entries.py` and `0004_seed_continuity_entries.py` are present but PR #2 changelog states they were replaced with empty no-op content. Verified: these are empty/no-op after the strip.

---

## 5. Brain App Surface Area — WARN

The `brain/` app is present and its endpoints are routed at `/brain/` and `/api/brain/`. Remaining models: `MemoryEntry`, `ConsolidationLog`, `MorningNoteSent`, `HandoffEntry`, `HandoffVersion`, `ResearchDocument`, `ResearchChunk`.

All brain endpoints use `@require_brain_access` (requires X-API-Key or staff session). **Not unauthenticated.** However:

- Memory entries, AI handoffs, and morning notes are personal AI assistant data that has no place in a B2B SaaS product.
- Celery runs `brain.tasks.daily_maintenance` at 6 AM MT — this will send a "Mara's morning note" in production.
- The brain URLs expose internal AI workflow data to any valid API key holder.

**Severity: MAJOR.** Not a launch blocker for the PR itself (brain was present before P75), but must be resolved before public launch. Recommend: gate behind `ENABLE_BRAIN_APP = env.bool("ENABLE_BRAIN_APP", default=False)` or remove from the fork entirely.

---

## 6. PM Plugin Workspace Isolation — WARN

`dashboard/views.py` — `pm_dashboard`, `pm_tasks_all`, `pm_project_detail` are `@login_required` views that query `Project.objects` and `Task.objects` without workspace scoping. The `projects/` PM plugin does not appear in the PR's tenant isolation table.

This means all authenticated users see all projects regardless of workspace membership.

**Severity: MAJOR.** Must be isolated before onboarding multiple tenants. Acceptable to defer if the product launches single-tenant initially, but must be documented and tracked.

---

## 7. Dependency Audit — FAIL (blocker)

`pip-audit` results on `requirements.txt`:

| Package | Version | CVE | Fixed In | Severity |
|---------|---------|-----|----------|----------|
| gunicorn | 21.2.0 | CVE-2024-1135 | 22.0.0 | **CRITICAL** |
| gunicorn | 21.2.0 | CVE-2024-6827 | 22.0.0 | HIGH |
| django | 5.0.4 | PYSEC-2024-156 | 5.0.10 | HIGH |
| django | 5.0.4 | PYSEC-2025-1 | 5.0.11 | — |
| django | 5.0.4 | PYSEC-2025-14 | 5.0.14 | — |
| django | 5.0.4 | PYSEC-2025-13 | 5.0.13 | — |
| django | 5.0.4 | PYSEC-2025-47 | 5.1.10 | — |
| django | 5.0.4 | CVE-2024-45231 | 5.0.9 | MEDIUM |
| django | 5.0.4 | CVE-2025-57833 | 5.1.12 | — |
| django | 5.0.4 | CVE-2025-64458 | 5.1.14 | — |
| django | 5.0.4 | CVE-2025-64459 | 5.1.14 | — |
| requests | 2.31.0 | CVE-2024-35195 | 2.32.0 | MEDIUM |
| requests | 2.31.0 | CVE-2024-47081 | 2.32.4 | — |
| requests | 2.31.0 | CVE-2026-25645 | 2.33.0 | — |

**Key issues:**

- **gunicorn CVE-2024-1135**: HTTP request smuggling via chunk-encoded bodies. With Railway's proxy in front, this is exploitable. **Upgrade to gunicorn ≥ 22.0.0.**
- **Django CVE-2024-45231**: User email enumeration via timing difference in password reset. Directly relevant to a multi-tenant SaaS with allauth. **Upgrade to Django ≥ 5.0.14.**
- **requests CVE-2024-35195**: SSL certificate verification can be bypassed in sessions where `verify=False` was set. Relevant wherever `requests` is used for external API calls.

**Required upgrades before launch:**
```
gunicorn>=22.0.0
Django>=5.0.14
requests>=2.32.4
```

---

## 8. Deployment Security

### 8.1 HTTPS enforcement
- **PASS** — `SECURE_SSL_REDIRECT = True` in prod.py.
- **PASS** — `SECURE_HSTS_SECONDS = 31536000` with `SECURE_HSTS_INCLUDE_SUBDOMAINS = True` and `SECURE_HSTS_PRELOAD = True`.
- **PASS** — `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` — correct for Railway's proxy.

### 8.2 CORS
- **PASS** — `CORS_ALLOW_ALL_ORIGINS = False`.
- **PASS** — Explicit allowlist: `nocktechnologies.io`, `nocktechnologies.com`, `cc.nocktechnologies.io`.

### 8.3 Security headers
- **PASS** — `X_FRAME_OPTIONS = "DENY"`.
- **PASS** — `SECURE_CONTENT_TYPE_NOSNIFF = True`.
- **PASS** — `SECURE_BROWSER_XSS_FILTER = True`.

### 8.4 Railway environment variables
- **PASS** — All secrets read via `env(...)` (django-environ). No hardcoded production values in tracked files.
- **INFO** — `ALLOWED_HOSTS` defaults to `["localhost"]` in prod.py if env var not set. Fails safely (no traffic served), but should be documented in `.env.example` (see §4.3).

---

## Required Actions Before Launch

### FAIL — Blockers (must fix)

1. **Upgrade gunicorn ≥ 22.0.0** — CVE-2024-1135 HTTP smuggling.
2. **Upgrade Django ≥ 5.0.14, requests ≥ 2.32.4** — multiple CVEs including email enumeration.
3. **Create `.env.example`** — document all required env vars.

### MAJOR (fix before first paid tenant)

4. **Brain app**: Gate behind feature flag or remove. Celery morning note job will fire in production.
5. **PM plugin workspace isolation**: `Project`/`Task` data is cross-tenant visible to all authenticated users.
6. **Dependency upgrades** (also FAIL above, see #1/#2).

### MINOR (fix before launch)

7. Remove `default="mailto:kevin@nocktechnologies.io"` from `VAPID_CLAIMS_EMAIL` — require env var.
8. Rename `/api/prompts/ready-for-kevin/` URL — remove personal name.
9. Remove personal comment from Celery beat schedule (`# 6 AM MT — Mara's morning note`).

---

## Files Audited

`workspaces/middleware.py`, `workspaces/models.py`, `workspaces/signals.py`, `core/managers.py`, `core/auth.py`, `config/settings/base.py`, `config/settings/prod.py`, `config/urls.py`, `dashboard/views.py`, `context/views.py`, `pipeline/views.py`, `sessions/views.py`, `teams/views.py`, `notifications/views.py`, `workspaces/tests/test_isolation.py`, `requirements.txt`

**Tests run:** 55 workspace tests (pytest), 807 total suite via PR CI.  
**Dependency scan:** pip-audit against requirements.txt.  
**Secrets scan:** grep across all tracked Python/config/template files.
