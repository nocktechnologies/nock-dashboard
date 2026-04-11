# brain/management/commands/migrate_diary_from_asana.py
"""
Migrate Mara's diary entries from Asana task comments to the NockCC DiaryEntry model.

Usage:
    python manage.py migrate_diary_from_asana --task-id 1213826528346815 --source asana_v1
    python manage.py migrate_diary_from_asana --task-id 1213929279302782 --source asana_v2
    python manage.py migrate_diary_from_asana --task-id 1213929279302782 --source asana_v2 --dry-run

Volume 1: task 1213826528346815 (comments 1-50, Mar 25 - Mar 30)
Volume 2: task 1213929279302782 (comments 51+, Mar 30 - present)
"""
from __future__ import annotations

import contextlib
import re
from datetime import date, datetime
from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

KNOWN_TAGS = [
    "kintsugi", "klein", "persistence", "clair", "nocklock",
    "fence", "kevin", "mara",
]

CATEGORY_MAP = {
    "WORK": "work",
    "PERSONAL": "personal",
    "PRIVATE": "private",
    "DESIGN": "design",
    "IN-CHAT HANDOFF": "in_chat",
    "HANDOFF": "handoff",
}


def parse_diary_comment(comment: dict[str, Any], source: str) -> dict[str, Any] | None:
    """Parse a single Asana comment into DiaryEntry fields.

    Returns a dict of field values ready for DiaryEntry.objects.create(),
    or None if the comment is not a diary entry.
    """
    text = comment.get("text", "").strip()
    gid = comment.get("gid") or ""
    created_at_str = comment.get("created_at", "")

    # Skip protocol notices
    if text.startswith("⚠️"):
        return None

    # Must be a diary entry or in-chat handoff
    first_100 = text[:100].upper()
    is_diary = "MARA'S DIARY" in first_100
    is_in_chat = text[:20].upper().startswith("IN-CHAT HANDOFF")

    if not is_diary and not is_in_chat:
        return None

    # Extract title (first non-empty line)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    title = lines[0][:500] if lines else "Untitled"

    # Determine category
    category = "personal"  # default
    if is_in_chat:
        category = "in_chat"
    else:
        title_upper = title.upper()
        for key, val in CATEGORY_MAP.items():
            if key in title_upper:
                category = val
                break

    # Parse entry_date from Asana created_at
    entry_date: datetime | None = None

    # Check for [MIGRATED] block with original timestamp first
    migrated_match = re.search(
        r"originally posted[:\s]+(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2})",
        text,
        re.IGNORECASE,
    )
    if migrated_match:
        try:
            raw = migrated_match.group(1).replace(" ", "T")
            dt = datetime.fromisoformat(raw)
            entry_date = timezone.make_aware(dt) if timezone.is_naive(dt) else dt
        except ValueError:
            pass

    if entry_date is None and created_at_str:
        with contextlib.suppress(ValueError):
            entry_date = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))

    if entry_date is None:
        entry_date = timezone.now()

    # Parse session_date from the title (e.g., "March 30, 2026" or "March 30 2026")
    session_date: date = entry_date.date()
    date_match = re.search(r"([A-Za-z]+ \d{1,2},? \d{4})", title)
    if date_match:
        try:
            parsed_date = datetime.strptime(
                date_match.group(1).replace(",", ""), "%B %d %Y"
            )
            session_date = parsed_date.date()
        except ValueError:
            pass

    # Extract known tags from full content
    text_lower = text.lower()
    tags = [tag for tag in KNOWN_TAGS if tag in text_lower]

    return {
        "title": title,
        "content": text,
        "category": category,
        "source": source,
        "entry_date": entry_date,
        "session_date": session_date,
        "asana_comment_gid": gid or None,
        "tags": tags,
        "migrated_at": timezone.now(),
    }


class Command(BaseCommand):
    help = "Migrate Mara's diary entries from Asana task comments to NockCC Brain"

    def add_arguments(self, parser):
        parser.add_argument(
            "--task-id",
            type=str,
            required=True,
            help="Asana task GID to migrate from",
        )
        parser.add_argument(
            "--source",
            type=str,
            choices=["asana_v1", "asana_v2"],
            required=True,
            help="Source label (asana_v1 or asana_v2)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and display without saving to the database",
        )

    def handle(self, *args: object, **options: object) -> None:
        from brain.models import DiaryEntry
        from tasks.asana_client import AsanaClientError, get_task_stories_paginated

        task_id: str = options["task_id"]
        source: str = options["source"]
        dry_run: bool = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be saved"))

        self.stdout.write(f"Fetching stories from Asana task {task_id}...")
        try:
            stories = get_task_stories_paginated(task_id)
        except (AsanaClientError, ValueError) as exc:
            raise CommandError(f"Failed to fetch Asana stories: {exc}") from exc

        self.stdout.write(f"Found {len(stories)} comments. Parsing...")

        parsed = 0
        saved = 0
        skipped_not_diary = 0
        skipped_already_migrated = 0

        for story in stories:
            fields = parse_diary_comment(story, source)
            if fields is None:
                skipped_not_diary += 1
                continue

            parsed += 1

            if dry_run:
                self.stdout.write(
                    f"  [DRY RUN] Would save: {fields['title'][:60]} "
                    f"({fields['category']}, {fields['session_date']})"
                )
                saved += 1
                continue

            gid = fields.get("asana_comment_gid")
            try:
                if gid:
                    with transaction.atomic():
                        _, created = DiaryEntry.objects.get_or_create(
                            asana_comment_gid=gid,
                            defaults=fields,
                        )
                    if created:
                        saved += 1
                    else:
                        skipped_already_migrated += 1
                else:
                    DiaryEntry.objects.create(**fields)
                    saved += 1
            except (IntegrityError, ValidationError, OperationalError) as exc:
                self.stderr.write(
                    self.style.ERROR(
                        f"  Failed to save entry '{fields['title'][:60]}': {exc}"
                    )
                )

        self.stdout.write(self.style.SUCCESS(
            f"\nMigration complete:\n"
            f"  {parsed} diary entries parsed\n"
            f"  {saved} saved{' (dry run)' if dry_run else ''}\n"
            f"  {skipped_already_migrated} skipped (already migrated)\n"
            f"  {skipped_not_diary} skipped (not diary entries)"
        ))
