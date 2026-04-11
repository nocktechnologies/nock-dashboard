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
]

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

# OAuth 2.1 shim for the MCP Streamable HTTP transport
# ----------------------------------------------------
# claude.ai custom connectors require OAuth 2.1 per the MCP spec
# 2025-03-26 (RFC 9728 resource metadata + RFC 8414 auth server metadata
# + RFC 7591 dynamic client registration + RFC 7636 PKCE). This single-
# user instance runs a minimal OAuth shim that auto-approves every
# authorize request and issues NOCKCC_API_KEY as the access token, so
# the existing BearerAuthMiddleware on /mcp/ keeps working unchanged.
#
# OAUTH_ISSUER_URL is the absolute base URL that appears in the OAuth
# discovery metadata — must match what claude.ai sees in the browser.
# Defaults to the production host so local dev can leave it blank.
NOCKCC_OAUTH_ENABLED = env.bool("NOCKCC_OAUTH_ENABLED", default=False)
OAUTH_ISSUER_URL = env("OAUTH_ISSUER_URL", default="https://cc.nocktechnologies.io")

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
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# django-axes: brute-force login protection
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
