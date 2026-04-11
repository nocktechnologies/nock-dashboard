"""Clear seed/demo data from the database while preserving real records."""

from typing import Any

from django.core.management.base import BaseCommand

from pipeline.models import Branch, BranchEvent, PREvent, PullRequest


class Command(BaseCommand):
    help = "Clear seed/demo data. Preserves repositories, Asana, context, and spend records."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--confirm", action="store_true",
            help="Required to actually delete. Without this, shows a dry-run preview.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        confirm = options["confirm"]

        if not confirm:
            self.stdout.write(self.style.WARNING("DRY RUN — pass --confirm to actually delete."))

        # Seed pipeline data uses delivery_id starting with "seed-del-"
        seed_events = PREvent.objects.filter(delivery_id__startswith="seed-del-")
        seed_event_count = seed_events.count()

        # Seed PRs: linked to seed events, or github_pr_id matches seed pattern
        # seed_pipeline_data computes github_pr_id = repo.github_id * 100 + number
        # For github_id 100001: 10000100-10000199, for 100002: 10000200-10000299
        seed_prs = PullRequest.objects.filter(
            github_pr_id__gte=10000000, github_pr_id__lt=10100000
        )
        seed_pr_count = seed_prs.count()

        # Seed branches created by seed_pipeline_data (check for known seed patterns)
        seed_branches = Branch.objects.filter(
            last_commit_sha="abc123def456abc123def456abc123def456abc1"
        ) | Branch.objects.filter(
            last_commit_sha="def456abc123def456abc123def456abc123def4"
        )
        seed_branch_count = seed_branches.count()

        # Seed branch events
        seed_branch_events = BranchEvent.objects.filter(delivery_id__startswith="seed-")
        seed_branch_event_count = seed_branch_events.count()

        # Sessions from seed_sessions command (all seed sessions have no repository FK)
        # Since sessions are already 0, this is a safety net
        from sessions.models import AgentSession, SessionLog
        seed_sessions = AgentSession.objects.filter(repository__isnull=True)
        seed_session_count = seed_sessions.count()
        seed_log_count = SessionLog.objects.filter(session__in=seed_sessions).count()

        self.stdout.write(f"  Seed PREvents:      {seed_event_count}")
        self.stdout.write(f"  Seed PullRequests:  {seed_pr_count}")
        self.stdout.write(f"  Seed Branches:      {seed_branch_count}")
        self.stdout.write(f"  Seed BranchEvents:  {seed_branch_event_count}")
        self.stdout.write(f"  Seed Sessions:      {seed_session_count}")
        self.stdout.write(f"  Seed SessionLogs:   {seed_log_count}")

        total = seed_event_count + seed_pr_count + seed_branch_count + seed_branch_event_count + seed_session_count + seed_log_count

        if total == 0:
            self.stdout.write(self.style.SUCCESS("No seed data found. Database is clean."))
            return

        if not confirm:
            self.stdout.write(f"\n  Total to delete: {total} records")
            self.stdout.write("  Run with --confirm to delete.")
            return

        # Delete in dependency order
        seed_events.delete()
        seed_prs.delete()
        seed_branches.delete()
        seed_branch_events.delete()
        SessionLog.objects.filter(session__in=seed_sessions).delete()
        seed_sessions.delete()

        self.stdout.write(self.style.SUCCESS(f"Deleted {total} seed records."))
