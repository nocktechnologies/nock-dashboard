"""Run all idempotent seed/setup commands in sequence.

Safe to run on every deploy — each sub-command uses get_or_create.
Failures are logged but do not halt the remaining commands.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

SETUP_COMMANDS: list[tuple[str, list[str]]] = [
    # Seed static data
    ("register_repos", []),
    ("backfill_prs", ["--days", "30"]),
    ("seed_subscriptions", []),
    ("seed_asana_projects", ["--confirm"]),
    ("register_context_docs", []),
    ("seed_notifications", []),
    # Sync live data from external APIs
    ("sync_asana", []),
    ("sync_context", []),
]


class Command(BaseCommand):
    help = "Run all production seed/setup commands in sequence."

    def handle(self, *args, **options):
        for name, extra_args in SETUP_COMMANDS:
            self.stdout.write(f"\n--- {name} ---")
            try:
                call_command(name, *extra_args, stdout=self.stdout, stderr=self.stderr)
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"  {name} failed: {exc}"))
                continue

        self.stdout.write(self.style.SUCCESS("\nsetup_production complete."))
