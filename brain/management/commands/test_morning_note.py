from django.core.management.base import BaseCommand

from brain.tasks import daily_maintenance


class Command(BaseCommand):
    help = "Manually trigger the morning note for testing"

    def handle(self, *args: object, **options: object) -> None:
        self.stdout.write("Triggering morning note...")
        result = daily_maintenance.delay()
        self.stdout.write(
            self.style.SUCCESS(f"Morning note task queued: {result.id}")
        )
