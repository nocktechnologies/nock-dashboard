from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Reset django_celery_beat schedule state after timezone change"

    def handle(self, *args: object, **options: object) -> None:
        from django_celery_beat.models import PeriodicTask, PeriodicTasks

        updated = PeriodicTask.objects.update(last_run_at=None)
        PeriodicTasks.update_changed()
        self.stdout.write(f"Reset last_run_at on {updated} periodic tasks")
        self.stdout.write("Marked beat schedule as changed.")
        self.stdout.write(
            self.style.SUCCESS("Done. Restart the beat service on Railway.")
        )
