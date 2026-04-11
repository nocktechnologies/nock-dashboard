"""GitHub API sync for context documents — polls file content and detects changes."""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import ContextDocument, ContextSnapshot

logger = logging.getLogger(__name__)


def _github_headers() -> dict[str, str]:
    token = getattr(settings, "GITHUB_PAT", "") or ""
    headers: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def _fetch_file(owner: str, repo: str, path: str) -> dict[str, Any] | None:
    """Fetch a file from GitHub REST API. Returns parsed JSON or None on error."""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    try:
        resp = requests.get(url, headers=_github_headers(), timeout=15)
        if resp.status_code == 404:
            logger.info("File not found on GitHub: %s/%s/%s", owner, repo, path)
            return None
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.warning("GitHub API error for %s/%s/%s: %s", owner, repo, path, exc)
        return None


def _content_hash(content: str) -> str:
    """SHA-256 hash of file content."""
    return hashlib.sha256(content.encode()).hexdigest()


def sync_document(doc: ContextDocument) -> bool:
    """Sync a single context document from GitHub.

    Returns True if the document was updated (content changed), False otherwise.
    """
    repo = doc.repository
    data = _fetch_file(repo.owner, repo.name, doc.file_path)

    now = timezone.now()

    if data is None:
        # File not found — mark inactive but don't delete
        if doc.is_active:
            doc.is_active = False
            doc.last_synced = now
            doc.save(update_fields=["is_active", "last_synced"])
            logger.info("Marked %s as inactive (file not found)", doc)
        return False

    # Decode base64 content
    try:
        raw_content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
    except (ValueError, KeyError) as exc:
        logger.warning("Could not decode content for %s: %s", doc, exc)
        doc.last_synced = now
        doc.save(update_fields=["last_synced"])
        return False

    new_hash = _content_hash(raw_content)
    new_line_count = len(raw_content.splitlines())

    if new_hash != doc.last_content_hash:
        # Content changed — create snapshot and update doc atomically
        old_line_count = doc.line_count
        diff_summary = f"Changed from {old_line_count} to {new_line_count} lines"

        with transaction.atomic():
            ContextSnapshot.objects.create(
                document=doc,
                content_hash=new_hash,
                commit_sha=data.get("sha", "")[:40],
                line_count=new_line_count,
                diff_summary=diff_summary,
            )

            doc.last_content_hash = new_hash
            doc.last_modified = now
            doc.line_count = new_line_count
            doc.last_synced = now
            doc.is_active = True
            doc.update_staleness()
            doc.save(update_fields=[
                "last_content_hash", "last_modified", "line_count",
                "last_synced", "is_active", "is_stale",
            ])
        logger.info("Updated %s — %s", doc, diff_summary)
        return True

    # Content unchanged — just update sync time and staleness
    doc.last_synced = now
    doc.is_active = True
    doc.update_staleness()
    doc.save(update_fields=["last_synced", "is_active", "is_stale"])
    return False


def sync_context_documents() -> dict[str, int]:
    """Sync all active context documents. Returns counts."""
    docs = ContextDocument.objects.filter(is_active=True).select_related("repository")
    updated = 0
    unchanged = 0
    errors = 0

    for doc in docs:
        try:
            changed = sync_document(doc)
            if changed:
                updated += 1
            else:
                unchanged += 1
        except Exception:
            logger.exception("Error syncing %s", doc)
            errors += 1

    return {"updated": updated, "unchanged": unchanged, "errors": errors}
