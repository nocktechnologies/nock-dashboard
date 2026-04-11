import os

from .base import *  # noqa: F403

DEBUG = False

ALLOWED_HOSTS = env.list(  # noqa: F405
    "ALLOWED_HOSTS",
    default=["web-production-b0528.up.railway.app"],
)

# Security headers
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True

# Session timeout: 30 min sliding window
SESSION_COOKIE_AGE = 1800
SESSION_SAVE_EVERY_REQUEST = True

# Static files
STATIC_ROOT = BASE_DIR / "staticfiles"  # noqa: F405
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
        },
        "pipeline": {
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}

# Celery: use REDIS_URL from environment, no localhost fallback in production
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = "django-db"

# CSRF trusted origins (Railway production domain)
CSRF_TRUSTED_ORIGINS = env.list(  # noqa: F405
    "CSRF_TRUSTED_ORIGINS",
    default=["https://web-production-b0528.up.railway.app"],
)

# Channels: same Redis for WebSocket layer
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [os.environ.get("REDIS_URL", "redis://localhost:6379/0")],
        },
    },
}
