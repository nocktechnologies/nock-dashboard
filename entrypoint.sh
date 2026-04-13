#!/usr/bin/env bash
set -euo pipefail

# Shared setup for all services
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py create_prod_superuser || true
python manage.py setup_production || true

# Route to the correct process based on SERVICE_ROLE
case "${SERVICE_ROLE:-web}" in
  web)
    exec uvicorn config.asgi:application \
        --host 0.0.0.0 \
        --port "${PORT:-8000}" \
        --lifespan on \
        --ws websockets
    ;;
  worker)
    exec celery -A config worker -l info --concurrency=2
    ;;
  beat)
    exec celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    ;;
  *)
    echo "Unknown SERVICE_ROLE: ${SERVICE_ROLE}" >&2
    exit 1
    ;;
esac
