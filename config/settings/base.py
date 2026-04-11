from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")

# django-fernet-fields: field-level encryption for sensitive model data
FERNET_KEYS = env.list("FERNET_KEYS", default=[])
if not FERNET_KEYS or not FERNET_KEYS[0]:
    raise ImproperlyConfigured(
        "FERNET_KEYS must be set. Generate a key with: "
        "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    )

DEBUG = False

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

DJANGO_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",  # required by django-allauth
]

SITE_ID = 1  # required by django-allauth (used in email links + social auth)

THIRD_PARTY_APPS = [
    "channels",
    "corsheaders",
    "django_celery_beat",
    "django_celery_results",
    "django_tables2",
    "django_filters",
    "axes",
    "rest_framework",
    "rest_framework.authtoken",
    # django-allauth: multi-tenant web auth (registration, login, password
    # reset, email verification). socialaccount is installed but no providers
    # are configured — table surface is created now, providers enabled later.
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
]

LOCAL_APPS = [
    "core.apps.CoreConfig",
    "accounts.apps.AccountsConfig",
    "dashboard.apps.DashboardConfig",
    "pipeline.apps.PipelineConfig",
    "sessions.apps.AgentSessionsConfig",
    "context.apps.ContextConfig",
    "spend.apps.SpendConfig",
    "notifications.apps.NotificationsConfig",
    "tasks.apps.TasksConfig",
    "remote.apps.RemoteConfig",
    "vault.apps.VaultConfig",
    "crm.apps.CrmConfig",
    "intelligence.apps.IntelligenceConfig",
    "brain.apps.BrainConfig",
    "teams.apps.TeamsConfig",
    "projects.apps.ProjectsConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",  # allauth 0.56+ requirement
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL", default="sqlite:///db.sqlite3")
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Denver"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Channels
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [env("REDIS_URL", default="redis://localhost:6379/0")],
        },
    },
}

# Celery
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = "django-db"
CELERY_CACHE_BACKEND = "django-cache"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "America/Denver"

CELERY_BEAT_SCHEDULE = {
    "sync-asana-projects": {
        "task": "tasks.tasks.sync_asana_projects",
        "schedule": crontab(minute="*/5"),
    },
    "sync-context-docs": {
        "task": "context.tasks.sync_context_docs_task",
        "schedule": crontab(minute="*/30"),
    },
    "sync-anthropic-usage": {
        "task": "spend.tasks.sync_anthropic_usage",
        "schedule": crontab(minute="*/15"),
    },
    "daily-usage-backfill": {
        "task": "spend.tasks.daily_usage_backfill",
        "schedule": crontab(hour=3, minute=0),  # 3 AM MT
    },
    "check-budget-alerts": {
        "task": "spend.tasks.check_budget_alerts",
        "schedule": crontab(minute=0),
    },
    "daily-digest": {
        "task": "notifications.tasks.send_daily_digest",
        "schedule": crontab(hour=9, minute=0),  # 9 AM MT
        "options": {"expires": 3600},
    },
    "generate-business-snapshot": {
        "task": "intelligence.tasks.generate_business_snapshot",
        "schedule": crontab(hour=6, minute=30),  # 6:30 AM MT (offset from morning note)
    },
    "check-predictive-alerts": {
        "task": "intelligence.tasks.check_predictive_alerts",
        "schedule": crontab(minute=0, hour="*/6"),  # Every 6 hours
    },
    "generate-weekly-memo": {
        "task": "intelligence.tasks.generate_weekly_memo",
        "schedule": crontab(hour=7, minute=0, day_of_week=1),  # Monday 7 AM MT
        "options": {"expires": 7200},
    },
    "daily-maintenance": {
        "task": "brain.tasks.daily_maintenance",
        "schedule": crontab(hour=6, minute=0),  # 6 AM MT — Mara's morning note
        "options": {"expires": 3600},
    },
    "cleanup-stale-sessions": {
        "task": "sessions.tasks.cleanup_stale_sessions",
        "schedule": crontab(minute="*/30"),
    },
    "smart-watch-tick": {
        "task": "intelligence.tasks.smart_watch_tick",
        "schedule": crontab(minute="*/15"),
    },
}

# GitHub
GITHUB_WEBHOOK_SECRET = env("GITHUB_WEBHOOK_SECRET", default="")
GITHUB_PAT = env("GITHUB_PAT", default="")

# Anthropic
ANTHROPIC_ADMIN_API_KEY = env("ANTHROPIC_ADMIN_API_KEY", default="")
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")

# OpenAI — used for Research Library embeddings (text-embedding-3-small)
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")

# Slack / Discord
SLACK_WEBHOOK_URL = env("SLACK_WEBHOOK_URL", default="")
DISCORD_WEBHOOK_URL = env("DISCORD_WEBHOOK_URL", default="")

# NockCC API key for session tracking endpoints
NOCKCC_API_KEY = env("NOCKCC_API_KEY", default="")

# Telegram notifications (server-side, always-on via Railway)
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", default="")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID", default="")
TELEGRAM_ENABLED = env.bool("TELEGRAM_ENABLED", default=False)
TELEGRAM_QUIET_START = env.int("TELEGRAM_QUIET_START", default=23)
TELEGRAM_QUIET_END = env.int("TELEGRAM_QUIET_END", default=7)

# Morning Note
MORNING_NOTE_ENABLED = env.bool("MORNING_NOTE_ENABLED", default=True)
MORNING_NOTE_HOUR_UTC = env.int("MORNING_NOTE_HOUR_UTC", default=11)
MORNING_NOTE_AI_QUESTIONS = env.bool("MORNING_NOTE_AI_QUESTIONS", default=True)

# Remote Agent
AGENT_HMAC_KEY = env("AGENT_HMAC_KEY", default="")
ALLOWED_COMMAND_IPS = env.list("ALLOWED_COMMAND_IPS", default=[])

# Web Push (VAPID)
VAPID_PUBLIC_KEY = env("VAPID_PUBLIC_KEY", default="")
VAPID_PRIVATE_KEY = env("VAPID_PRIVATE_KEY", default="")
VAPID_CLAIMS_EMAIL = env("VAPID_CLAIMS_EMAIL", default="mailto:kevin@nocktechnologies.io")

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
}

# Authentication
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

AUTHENTICATION_BACKENDS = [
    # axes must be first — it intercepts authenticate() calls and enforces
    # brute-force lockout BEFORE credentials are checked.
    "axes.backends.AxesStandaloneBackend",
    # allauth handles email-based authentication (login, social, etc.)
    "allauth.account.auth_backends.AuthenticationBackend",
    # Django's built-in backend as the final fallback (admin, API tokens)
    "django.contrib.auth.backends.ModelBackend",
]

# ── django-allauth configuration ────────────────────────────────────────────
# Authentication method: email-only (no usernames). New accounts get a
# system-generated username internally via allauth's username adapter;
# we don't expose it anywhere in the UI.
# allauth 65.x renamed several settings; using the current API here:
ACCOUNT_LOGIN_METHODS = {"email"}          # replaces ACCOUNT_AUTHENTICATION_METHOD
ACCOUNT_SIGNUP_FIELDS = [                  # replaces ACCOUNT_EMAIL_REQUIRED +
    "email*",                              #   ACCOUNT_USERNAME_REQUIRED
    "password1*",
    "password2*",
]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None   # suppress allauth's username field
ACCOUNT_EMAIL_VERIFICATION = "mandatory"   # user must verify before first login

# Always use HTTPS for password-reset and email-verification links.
# Set to "http" for local dev if you prefer, but prod must be "https".
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"

# Allauth-side rate limits (belt-and-suspenders alongside django-axes).
# These throttle allauth's own views; axes handles IP lockout afterward.
# Values are "<count>/<window>" strings; None disables a specific limit.
ACCOUNT_RATE_LIMITS = {
    "login_failed": "5/5m",           # 5 failed logins per 5 minutes per IP
    "signup": "10/h",                  # 10 signups per hour per IP
    "manage_email": "5/5m",            # 5 email-management actions per 5 min
    "confirm_email": "10/m",           # 10 email-confirm attempts per minute
    "change_password": "5/5m",         # 5 password-change attempts per 5 min
    "reset_password": "5/5m",          # 5 password-reset requests per 5 min
    "reset_password_from_key": "5/5m", # 5 password-reset-from-key attempts per 5 min
}

# Behind Railway's reverse proxy — tell allauth to trust one hop so
# rate-limiting sees the real client IP rather than Railway's proxy IP.
ALLAUTH_TRUSTED_PROXY_COUNT = 1

# Email backend — env-var driven so any SMTP provider drops in at PR 6.
# Dev uses the console backend (prints emails to stdout; copy the
# verification link from runserver logs). Prod sets EMAIL_BACKEND to
# "django.core.mail.backends.smtp.EmailBackend" + the SMTP credentials
# for whichever provider is chosen (Resend / SendGrid / Postmark /
# Mailgun / SES — all speak SMTP, all drop in here with zero code
# changes). See CHANGELOG for the provider-selection decision.
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
# Some providers (e.g. port 465) use implicit TLS — set EMAIL_USE_SSL=True
# and EMAIL_USE_TLS=False. Mutually exclusive with EMAIL_USE_TLS.
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@localhost")
# Note: a fail-fast guard against the console backend in production belongs
# in a Django system check (accounts/checks.py), not at module level here —
# module-level code in base.py runs before child settings override DEBUG.
# PR 6 (production settings) will add accounts.E001 via @register().

# ── django-axes: brute-force login protection ────────────────────────────────
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_TEMPLATE = "accounts/locked.html"
AXES_RESET_ON_SUCCESS = True

# CSRF trusted origins (set to Railway domain in production)
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# CORS — explicit allowlist (wildcard was a security risk)
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    "https://cc.nocktechnologies.io",
    "https://nocktechnologies.io",
    "https://nocktechnologies.com",
]
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "x-api-key",
]
