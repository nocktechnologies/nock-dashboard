"""Manual trigger for context document sync."""

from typing import Any

from django.core.management.base import BaseCommand

from context.github_sync import sync_context_documents


class Command(BaseCommand):
    help = "Sync all active context documents from GitHub."

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write("Syncing context documents...")
        result = sync_context_documents()
        self.stdout.write(self.style.SUCCESS(
            f"Done. {result['updated']} updated, {result['unchanged']} unchanged, {result['errors']} errors."
        ))
