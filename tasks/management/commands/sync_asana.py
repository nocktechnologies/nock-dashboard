from typing import Any

from django.core.management.base import BaseCommand, CommandError

from tasks.asana_client import AsanaClientError
from tasks.tasks import sync_asana_projects


class Command(BaseCommand):
    help = "Manually trigger Asana sync for all active projects"

    def handle(self, *args: object, **options: Any) -> None:
        self.stdout.write("Syncing Asana projects...")
        try:
            sync_asana_projects()
            self.stdout.write(self.style.SUCCESS("Sync complete."))
        except ValueError as exc:
            raise CommandError(f"Configuration error: {exc}") from exc
        except AsanaClientError as exc:
            raise CommandError(f"Asana API error: {exc}") from exc
