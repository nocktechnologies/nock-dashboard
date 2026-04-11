import argparse
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from tasks.models import AsanaProject


class Command(BaseCommand):
    help = "Seed the 4 Nock Technologies Asana projects"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
        parser.add_argument("--verbose", action="store_true", dest="verbose_output", help="Verbose output")
        parser.add_argument("--confirm", action="store_true", help="Confirm writes")

    def handle(self, *args: object, **options: Any) -> None:
        dry_run: bool = options["dry_run"]
        verbose: bool = options["verbose_output"]
        confirm: bool = options["confirm"]

        if not confirm and not dry_run:
            self.stdout.write(self.style.WARNING(
                "Run with --confirm to write, or --dry-run to preview."
            ))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes saved."))

        projects = [
            ("1213385963010586", "Project Nexus — Development Roadmap", "blue"),
            ("1213654268728162", "Nock Academy", "green"),
            ("1213659188123153", "Claude Command Center — Development Roadmap", "purple"),
            ("1213660356472624", "Nock Verticals — Exploration & Strategy", "orange"),
        ]

        for gid, name, color in projects:
            if verbose:
                self.stdout.write(f"  Processing: {name}")
            if dry_run:
                exists = AsanaProject.objects.filter(asana_gid=gid).exists()
                action = "Update" if exists else "Create"
                self.stdout.write(f"  Would {action}: {name}")
                continue
            with transaction.atomic():
                try:
                    obj = AsanaProject.objects.select_for_update().get(asana_gid=gid)
                    obj.name = name
                    obj.color = color
                    obj.save(update_fields=["name", "color"])
                    status = "Updated"
                except AsanaProject.DoesNotExist:
                    AsanaProject.objects.create(
                        asana_gid=gid, name=name, color=color, is_active=True
                    )
                    status = "Created"
            self.stdout.write(self.style.SUCCESS(f"  {status}: {name}"))

        if not dry_run:
            self.stdout.write(self.style.SUCCESS("Done. 4 Asana projects seeded."))
