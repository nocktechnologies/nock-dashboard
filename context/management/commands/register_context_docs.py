"""Register known context files for tracked repositories."""

from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from context.models import ContextDocument
from pipeline.models import Repository

logger = logging.getLogger(__name__)

# Known context files per repo
KNOWN_DOCS: dict[str, list[dict[str, str]]] = {
    "kkwills13/project-nexus": [
        {"file_path": "CLAUDE.md", "doc_type": "claude_md", "title": "CLAUDE.md"},
        {"file_path": "PROJECT_NEXUS_ARCHITECTURE.md", "doc_type": "architecture", "title": "Architecture"},
        {"file_path": "CHANGELOG.md", "doc_type": "changelog", "title": "Changelog"},
        {"file_path": ".claude/skills/nexus/credit_decisioning.md", "doc_type": "skill_file", "title": "Credit Decisioning Skill"},
        {"file_path": ".claude/skills/nexus/factoring_operations.md", "doc_type": "skill_file", "title": "Factoring Operations Skill"},
    ],
    "kkwills13/nock-command-center": [
        {"file_path": "CLAUDE.md", "doc_type": "claude_md", "title": "CLAUDE.md"},
        {"file_path": "DESIGN_CLAUDE_COMMAND_CENTER.md", "doc_type": "design_doc", "title": "Design Document"},
    ],
}


def _github_headers() -> dict[str, str]:
    token = getattr(settings, "GITHUB_PAT", "") or ""
    headers: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def _discover_skill_files(owner: str, repo_name: str) -> list[dict[str, str]]:
    """Scan .claude/skills/ directory via GitHub API for .md files."""
    url = f"https://api.github.com/repos/{owner}/{repo_name}/contents/.claude/skills"
    discovered: list[dict[str, str]] = []
    try:
        resp = requests.get(url, headers=_github_headers(), timeout=15)
        if resp.status_code != 200:
            return discovered
        items = resp.json()
        if not isinstance(items, list):
            return discovered
        for item in items:
            if item.get("type") == "dir":
                # Recurse into subdirectory
                sub_url = item.get("url", "")
                if sub_url:
                    try:
                        sub_resp = requests.get(sub_url, headers=_github_headers(), timeout=15)
                        if sub_resp.status_code == 200:
                            sub_items = sub_resp.json()
                            if isinstance(sub_items, list):
                                for sub in sub_items:
                                    if sub.get("name", "").endswith(".md"):
                                        discovered.append({
                                            "file_path": sub["path"],
                                            "doc_type": "skill_file",
                                            "title": sub["name"].replace(".md", "").replace("_", " ").title(),
                                        })
                    except requests.RequestException:
                        pass
            elif item.get("name", "").endswith(".md"):
                discovered.append({
                    "file_path": item["path"],
                    "doc_type": "skill_file",
                    "title": item["name"].replace(".md", "").replace("_", " ").title(),
                })
    except requests.RequestException as exc:
        logger.warning("Could not scan skills directory for %s/%s: %s", owner, repo_name, exc)
    return discovered


class Command(BaseCommand):
    help = "Register known context files for tracked repositories."

    def handle(self, *args: Any, **options: Any) -> None:
        total_created = 0
        total_existing = 0

        for repo_slug, docs in KNOWN_DOCS.items():
            owner, _, name = repo_slug.partition("/")
            try:
                repo = Repository.objects.get(owner=owner, name=name)
            except Repository.DoesNotExist:
                self.stderr.write(self.style.WARNING(f"  Repository {repo_slug} not found — skipping"))
                continue

            for doc_def in docs:
                _, created = ContextDocument.objects.get_or_create(
                    repository=repo,
                    file_path=doc_def["file_path"],
                    defaults={
                        "doc_type": doc_def["doc_type"],
                        "title": doc_def["title"],
                    },
                )
                if created:
                    total_created += 1
                    self.stdout.write(f"  + {repo_slug}/{doc_def['file_path']}")
                else:
                    total_existing += 1

            # Auto-discover skill files
            discovered = _discover_skill_files(owner, name)
            for skill in discovered:
                _, created = ContextDocument.objects.get_or_create(
                    repository=repo,
                    file_path=skill["file_path"],
                    defaults={
                        "doc_type": skill["doc_type"],
                        "title": skill["title"],
                    },
                )
                if created:
                    total_created += 1
                    self.stdout.write(f"  + {repo_slug}/{skill['file_path']} (discovered)")
                else:
                    total_existing += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. {total_created} created, {total_existing} already existed."
        ))
