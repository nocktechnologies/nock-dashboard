web: python manage.py migrate && python manage.py collectstatic --noinput && python manage.py create_prod_superuser && python manage.py setup_production && uvicorn config.asgi:application --host 0.0.0.0 --port $PORT --lifespan on --ws websockets
worker: celery -A config worker -l info --concurrency=2
beat: celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
