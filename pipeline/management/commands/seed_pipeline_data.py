import argparse
import secrets
from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from pipeline.models import Branch, PREvent, PullRequest, Repository


class Command(BaseCommand):
    help = "Seed pipeline with demo repositories, PRs, and events for visual testing"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without saving to database",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            dest="verbose_output",
            help="Show detailed progress output",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Confirm destructive operations (deletes existing PR events)",
        )

    def handle(self, *args: object, **options: Any) -> None:
        dry_run: bool = options["dry_run"]
        verbose: bool = options["verbose_output"]
        confirm: bool = options["confirm"]

        if not confirm and not dry_run:
            self.stdout.write(self.style.WARNING(
                "This command deletes existing PR events. Run with --confirm to proceed, "
                "or --dry-run to preview."
            ))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be saved."))

        self.stdout.write("Seeding pipeline data...")

        now = timezone.now()

        # Repos
        repo_defs = [
            ("kkwills13", "project-nexus", 100001, secrets.token_urlsafe(32)),
            ("kkwills13", "nock-command-center", 100002, secrets.token_urlsafe(32)),
        ]
        repos: dict[str, Repository] = {}
        for owner, name, github_id, secret in repo_defs:
            if verbose:
                self.stdout.write(f"  Repo: {owner}/{name}")
            if not dry_run:
                repo, _ = Repository.objects.get_or_create(
                    owner=owner, name=name,
                    defaults={"github_id": github_id, "webhook_secret": secret, "is_active": True},
                )
                repos[name] = repo

        if dry_run:
            self.stdout.write("Would create: 2 repos, 10 PRs, ~43 events, 4 branches.")
            return

        nexus = repos["project-nexus"]
        nockcc = repos["nock-command-center"]

        # PR data: (repo, number, title, branch, author, state, ci, cr, files, add, del,
        #           days_ago, merged_days_ago, agent, tests_passed, tests_failed)
        prs_data = [
            # Open PRs
            (nexus, 201, "feat: invoice-centric migration phase 1", "feature/invoice-centric", "kev", "open", "passed", "approved", 12, 340, 45, 2, None, "claude-code", 2181, 0),
            (nexus, 202, "fix: over_advance race condition", "fix/oa-race", "kev", "open", "failed", "changes_requested", 3, 28, 5, 1, None, "claude-code", 2150, 31),
            (nockcc, 3, "feat: sessions app models", "feature/sessions-models", "kev", "open", "pending", "pending", 5, 120, 0, 0, None, "claude-code", None, None),
            # Merged PRs
            (nexus, 198, "feat: reporting module — 6 operational reports", "feature/reporting", "kev", "merged", "passed", "approved", 18, 890, 120, 5, 4, "claude-code", 2181, 0),
            (nexus, 199, "fix: P1 hardening + dead code cleanup", "fix/p1-hardening", "kev", "merged", "passed", "approved", 22, 450, 380, 4, 3, "claude-code", 2143, 0),
            (nexus, 200, "fix: Opus re-audit findings", "fix/opus-reaudit", "kev", "merged", "passed", "approved", 8, 95, 40, 3, 2, "claude-code", 2181, 0),
            (nockcc, 1, "feat: pipeline models", "feature/pipeline-models", "kev", "merged", "passed", "approved", 9, 263, 2, 7, 6, "claude-code", 27, 0),
            (nockcc, 2, "feat: GitHub webhook receiver + PR event processing", "feature/github-webhooks", "kev", "merged", "passed", "approved", 5, 794, 3, 6, 5, "claude-code", 27, 0),
            # Closed PRs
            (nexus, 196, "WIP: pipeline redesign draft", "wip/pipeline-redesign", "kev", "closed", "failed", "not_applicable", 4, 55, 10, 10, None, "", None, None),
            (nockcc, 0, "chore: initial project scaffold exploration", "chore/explore", "kev", "closed", "pending", "not_applicable", 2, 20, 5, 14, None, "", None, None),
        ]

        created_prs: list[PullRequest] = []
        for (repo, number, title, branch, author, state, ci, cr, files, add, dlt,
             days_ago, merged_days, agent, tp, tf) in prs_data:
            if verbose:
                self.stdout.write(f"  PR: {repo.name}#{number} — {title[:50]}")
            opened_at = now - timedelta(days=days_ago, hours=3)
            merged_at = (now - timedelta(days=merged_days, hours=1)) if merged_days is not None and state == "merged" else None
            closed_at = (now - timedelta(days=days_ago - 1)) if state == "closed" else None
            pr, _ = PullRequest.objects.update_or_create(
                repository=repo,
                number=number,
                defaults={
                    "github_pr_id": repo.github_id * 100 + number,
                    "title": title,
                    "branch": branch,
                    "author": author,
                    "state": state,
                    "ci_status": ci,
                    "coderabbit_status": cr,
                    "files_changed": files,
                    "additions": add,
                    "deletions": dlt,
                    "opened_at": opened_at,
                    "merged_at": merged_at,
                    "closed_at": closed_at,
                    "generating_agent": agent,
                    "tests_passed": tp,
                    "tests_failed": tf,
                },
            )
            created_prs.append(pr)

        # Events
        event_delivery_counter = 9000
        for pr in created_prs:
            pr.events.all().delete()

            def make_event(etype: str, actor: str, payload: dict, delta_minutes: int, _pr: PullRequest = pr) -> None:
                nonlocal event_delivery_counter
                event_delivery_counter += 1
                delivery = f"seed-del-{event_delivery_counter}"
                ts = timezone.now() - timedelta(minutes=delta_minutes)
                if verbose:
                    self.stdout.write(f"    Event: {etype} by {actor}")
                PREvent.objects.create(
                    pull_request=_pr,
                    event_type=etype,
                    actor=actor,
                    delivery_id=delivery,
                    created_at=ts,
                    payload={**payload, "delivery_id": delivery},
                )

            make_event("opened", pr.author, {"action": "opened"}, 0)
            make_event("review_submitted", "coderabbitai[bot]", {"state": "commented", "body": "CodeRabbit initial review."}, 30)

            if pr.ci_status == "passed":
                make_event("ci_completed", "github-actions", {"conclusion": "success", "name": "pytest", "status": "completed"}, 60)
                make_event("review_submitted", "coderabbitai[bot]", {"state": "approved", "body": "LGTM."}, 90)
            elif pr.ci_status == "failed":
                make_event("ci_completed", "github-actions", {"conclusion": "failure", "name": "pytest", "status": "completed"}, 60)
                make_event("review_submitted", "coderabbitai[bot]", {"state": "changes_requested", "body": "Please fix failing tests."}, 90)

            if pr.state == "merged":
                make_event("closed", pr.author, {"merged": True}, 120)
            elif pr.state == "closed":
                make_event("closed", pr.author, {"merged": False}, 60)

        # Branches
        for repo in [nexus, nockcc]:
            Branch.objects.get_or_create(
                repository=repo, name="main",
                defaults={"last_commit_sha": "abc123def456abc123def456abc123def456abc1", "last_commit_message": "Initial commit", "is_active": True},
            )
            Branch.objects.get_or_create(
                repository=repo, name="feature/pipeline-dashboard",
                defaults={"last_commit_sha": "def456abc123def456abc123def456abc123def4", "last_commit_message": "feat: pipeline dashboard", "is_active": True},
            )

        pr_count = PullRequest.objects.count()
        event_count = PREvent.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f"Done. {Repository.objects.count()} repos, {pr_count} PRs, {event_count} events, {Branch.objects.count()} branches."
        ))
