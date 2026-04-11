"""Backfill PullRequest records from the GitHub API."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from pipeline.models import PullRequest, Repository

logger = logging.getLogger(__name__)


def _parse_dt(value: str | None):
    """Parse an ISO-8601 datetime string from GitHub, or return None."""
    if not value:
        return None
    from django.utils.dateparse import parse_datetime
    return parse_datetime(value)


def _gh_state_to_model(pr_data: dict) -> str:
    """Map GitHub API state + merged flag to our State choices."""
    if pr_data.get("merged_at"):
        return PullRequest.State.MERGED
    if pr_data.get("state") == "closed":
        return PullRequest.State.CLOSED
    return PullRequest.State.OPEN


class Command(BaseCommand):
    help = "Backfill PullRequest records from the GitHub API."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Only import PRs updated within this many days (default: 30).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        token = getattr(settings, "GITHUB_PAT", "") or ""
        if not token:
            self.stderr.write(self.style.ERROR("GITHUB_PAT is not set — cannot call GitHub API."))
            return

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {token}",
        }

        cutoff = timezone.now() - timedelta(days=options["days"])
        repos = Repository.objects.filter(is_active=True)
        total_created = 0
        total_updated = 0

        for repo in repos:
            self.stdout.write(f"\n--- {repo.owner}/{repo.name} ---")
            created, updated = self._backfill_repo(repo, headers, cutoff)
            total_created += created
            total_updated += updated

        total = total_created + total_updated
        self.stdout.write(self.style.SUCCESS(
            f"\nBackfilled {total} PRs across {repos.count()} repos "
            f"({total_created} created, {total_updated} updated)."
        ))

    def _backfill_repo(
        self, repo: Repository, headers: dict, cutoff
    ) -> tuple[int, int]:
        created = 0
        updated = 0
        page = 1

        while True:
            url = (
                f"https://api.github.com/repos/{repo.owner}/{repo.name}/pulls"
                f"?state=all&sort=updated&direction=desc&per_page=100&page={page}"
            )
            try:
                resp = requests.get(url, headers=headers, timeout=30)
                resp.raise_for_status()
            except requests.RequestException as exc:
                self.stderr.write(self.style.ERROR(f"  API error: {exc}"))
                break

            pulls = resp.json()
            if not pulls:
                break

            for pr_data in pulls:
                updated_at = _parse_dt(pr_data.get("updated_at"))
                if updated_at and updated_at < cutoff:
                    return created, updated

                c, u = self._upsert_pr(repo, pr_data)
                created += c
                updated += u

            # Stop if this was the last page
            if "next" not in resp.links:
                break
            page += 1

        return created, updated

    def _upsert_pr(self, repo: Repository, pr_data: dict) -> tuple[int, int]:
        number = pr_data["number"]
        defaults = {
            "github_pr_id": pr_data["id"],
            "title": pr_data.get("title", "")[:500],
            "branch": (pr_data.get("head") or {}).get("ref", "unknown"),
            "author": (pr_data.get("user") or {}).get("login", "unknown"),
            "state": _gh_state_to_model(pr_data),
            "opened_at": _parse_dt(pr_data.get("created_at")) or timezone.now(),
            "merged_at": _parse_dt(pr_data.get("merged_at")),
            "closed_at": _parse_dt(pr_data.get("closed_at")),
            "additions": pr_data.get("additions", 0),
            "deletions": pr_data.get("deletions", 0),
            "files_changed": pr_data.get("changed_files", 0),
        }

        obj, was_created = PullRequest.objects.get_or_create(
            repository=repo,
            number=number,
            defaults=defaults,
        )

        if was_created:
            self.stdout.write(f"  + PR #{number}: {defaults['title'][:60]}")
            return 1, 0

        # Update existing record
        changed = False
        for field, value in defaults.items():
            if getattr(obj, field) != value:
                setattr(obj, field, value)
                changed = True
        if changed:
            obj.save()
            self.stdout.write(f"  ~ PR #{number}: {defaults['title'][:60]}")
            return 0, 1

        return 0, 0
