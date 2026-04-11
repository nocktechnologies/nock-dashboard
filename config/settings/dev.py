from .base import *  # noqa: F403

DEBUG = True

CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS += ["django_extensions"]  # noqa: F405

# Use in-memory channel layer for dev if Redis not available
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Run Celery tasks synchronously in dev (no Redis/worker required)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
