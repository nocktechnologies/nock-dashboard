import logging
import re

import requests
from celery import shared_task
from django.db import transaction
from django.utils import timezone

from pipeline.models import PullRequest

from .asana_client import (
    AsanaClientError,
    get_project_tasks,
    get_sections,
    get_task_stories,
    parse_task,
)
from .models import AsanaProject, AsanaSection, AsanaTask

logger = logging.getLogger(__name__)

_STOP_WORDS = frozenset(
    {"feat", "fix", "chore", "add", "update", "the", "a", "an", "and", "or", "for",
     "to", "of", "in", "on", "with", "from", "via", "wip"}
)


def _words(text: str) -> set[str]:
    """Normalise text -> meaningful lowercase words."""
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    return {w for w in text.split() if len(w) > 2 and w not in _STOP_WORDS}


@shared_task
def sync_asana_projects() -> None:
    """Sync all active AsanaProject records from Asana API."""
    projects = list(AsanaProject.objects.filter(is_active=True))
    if not projects:
        logger.info("No active Asana projects to sync")
        return

    for project in projects:
        try:
            raw_tasks = get_project_tasks(project.asana_gid)
        except AsanaClientError as exc:
            logger.error("Failed to sync project %s: %s", project.name, exc)
            continue

        # Sync sections first so tasks can reference them by local cache.
        # Section fetch failures are non-fatal — tasks still sync.
        _sync_sections(project)

        synced_gids: set[str] = set()
        for raw in raw_tasks:
            parsed = parse_task(raw)
            gid = parsed.pop("asana_gid")
            synced_gids.add(gid)
            with transaction.atomic():
                AsanaTask.objects.update_or_create(
                    asana_gid=gid,
                    defaults={"project": project, **parsed},
                )

        # Only remove incomplete tasks no longer present in Asana.
        # Skip soft-deleted rows so we don't resurrect-then-re-delete them
        # (deleted_at is set by the write-back API delete endpoint).
        AsanaTask.objects.filter(
            project=project, completed=False, deleted_at__isnull=True,
        ).exclude(asana_gid__in=synced_gids).delete()

        with transaction.atomic():
            project.last_synced = timezone.now()
            project.save(update_fields=["last_synced"])

        logger.info("Synced %d tasks for %s", len(synced_gids), project.name)

    # Check for new comments on incomplete tasks
    _check_new_comments()

    # Call inline — works whether running in a Celery worker or management command
    link_tasks_to_prs()


def _sync_sections(project: AsanaProject) -> None:
    """Upsert Asana sections for a project into the local cache.

    Non-fatal: logs and returns on any client error so the main task sync
    isn't held up by a transient sections API failure.
    """
    try:
        raw_sections = get_sections(project.asana_gid)
    except AsanaClientError as exc:
        logger.warning("Failed to sync sections for %s: %s", project.name, exc)
        return
    except ValueError as exc:
        # ASANA_PAT missing — already logged elsewhere, don't spam.
        logger.debug("Skipping section sync for %s: %s", project.name, exc)
        return

    synced_gids: set[str] = set()
    for idx, raw in enumerate(raw_sections):
        gid = raw.get("gid")
        if not gid:
            continue
        synced_gids.add(gid)
        with transaction.atomic():
            AsanaSection.objects.update_or_create(
                asana_gid=gid,
                defaults={
                    "project": project,
                    "name": str(raw.get("name", ""))[:255],
                    "order": idx,
                },
            )

    # Drop sections that no longer exist in Asana
    AsanaSection.objects.filter(project=project).exclude(
        asana_gid__in=synced_gids,
    ).delete()


def _check_new_comments() -> None:
    """Poll incomplete, live Asana tasks for new comments and send notifications.

    Soft-deleted tasks (deleted_at__isnull=False) are skipped — otherwise the
    poller would keep pinging Asana for a gid that no longer exists and
    potentially surface stale comments for deleted tasks.
    """
    task_pks = list(
        AsanaTask.objects.filter(completed=False, deleted_at__isnull=True)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    for pk in task_pks:
        try:
            task = AsanaTask.objects.select_related("project").get(pk=pk)
        except AsanaTask.DoesNotExist:
            continue

        try:
            stories = get_task_stories(task.asana_gid)
        except (AsanaClientError, requests.RequestException, ValueError) as exc:
            logger.debug("Failed to fetch stories for task %s: %s", task.asana_gid, exc)
            continue
        if not stories:
            continue

        latest = max(stories, key=lambda s: s.get("created_at", ""))
        latest_gid = latest["gid"]

        # Lock the row and re-read the marker to prevent races
        with transaction.atomic():
            locked = AsanaTask.objects.select_for_update().get(pk=pk)

            if latest_gid == locked.last_comment_gid:
                continue

            # First observation — initialise the marker without notifying
            if not locked.last_comment_gid:
                locked.last_comment_gid = latest_gid
                locked.save(update_fields=["last_comment_gid"])
                continue

        # New comment — notify outside the lock, then advance marker
        author = (latest.get("created_by") or {}).get("name", "Someone")
        text_preview = (latest.get("text") or "")[:120]

        _notify_asana_comment(
            task_name=task.name,
            project_name=task.project.name,
            author=author,
            text_preview=text_preview,
            permalink=task.permalink_url,
        )

        # Only advance marker after successful notification
        with transaction.atomic():
            AsanaTask.objects.select_for_update().filter(pk=pk).update(
                last_comment_gid=latest_gid,
            )


_MD_ESCAPE_CHARS = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")


def _escape_md(text: str) -> str:
    """Escape Telegram MarkdownV1 special characters in user-generated text."""
    return _MD_ESCAPE_CHARS.sub(r"\\\1", text)


def _notify_asana_comment(
    task_name: str,
    project_name: str,
    author: str,
    text_preview: str,
    permalink: str,
) -> None:
    """Send Slack + Telegram notification for an Asana comment."""
    try:
        from notifications.notifier import trigger_event
        trigger_event("asana_comment", {
            "title": f"Comment on: {task_name[:60]}",
            "message": f"*{author}* commented on _{task_name[:60]}_\n> {text_preview}",
            "project": project_name,
            "task": task_name[:80],
            "author": author,
        })
    except (ImportError, OSError) as exc:
        logger.warning("Asana comment notification dispatch failed: %s", exc)

    try:
        from core.telegram import TelegramNotifier
        esc_author = _escape_md(author)
        esc_task = _escape_md(task_name[:60])
        esc_project = _escape_md(project_name)
        esc_preview = _escape_md(text_preview)
        lines = [
            f"\U0001f4ac *{esc_author}* commented on Asana task",
            f"_{esc_task}_ ({esc_project})",
        ]
        if esc_preview:
            lines.append(f"> {esc_preview}")
        if permalink:
            lines.append(f"[View task]({permalink})")
        TelegramNotifier.send("\n".join(lines))
    except (ImportError, OSError) as exc:
        logger.warning("Asana comment Telegram failed: %s", exc)


@shared_task
def link_tasks_to_prs() -> None:
    """Fuzzy-match unlinked AsanaTasks to PullRequests by name similarity."""
    # Skip soft-deleted tasks — they should never accrue new PR links.
    unlinked = AsanaTask.objects.filter(
        linked_pr__isnull=True,
        completed=False,
        deleted_at__isnull=True,
    ).select_related("project")
    recent_prs = list(
        PullRequest.objects.order_by("-opened_at")[:200]
    )

    for task in unlinked:
        task_words = _words(task.name)
        if len(task_words) < 2:
            continue

        best_pr = None
        best_score = 0

        for pr in recent_prs:
            pr_words = _words(pr.title) | _words(pr.branch)
            overlap = task_words & pr_words
            if len(overlap) >= 2 and len(overlap) > best_score:
                best_score = len(overlap)
                best_pr = pr

        if best_pr:
            with transaction.atomic():
                updated = (
                    AsanaTask.objects.select_for_update()
                    .filter(pk=task.pk, linked_pr__isnull=True)
                    .update(linked_pr=best_pr)
                )
                if updated:
                    logger.debug("Linked task '%s' → PR #%d", task.name[:50], best_pr.number)
