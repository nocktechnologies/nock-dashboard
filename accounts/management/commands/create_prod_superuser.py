import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Create a superuser from environment variables (non-interactive, idempotent)."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not all([username, email, password]):
            self.stdout.write(
                self.style.WARNING(
                    "Skipping superuser creation: "
                    "DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL, "
                    "and DJANGO_SUPERUSER_PASSWORD must all be set."
                )
            )
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.SUCCESS(f"Superuser '{username}' already exists — skipping.")
            )
            return

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' created."))
