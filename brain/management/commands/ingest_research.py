"""
ingest_research — walk a research vault directory and import markdown files
into the ResearchDocument table.

Usage:
    python manage.py ingest_research /path/to/research-vault
    python manage.py ingest_research /path/to/research-vault --dry-run
    python manage.py ingest_research /path/to/research-vault --topic abl-underwriting

Idempotency:
    Each file's SHA-256 hash is compared against the stored hash. Unchanged
    files are skipped, changed files update the row (and reset is_indexed so
    embeddings will be regenerated), new files are created.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from brain.models import ResearchDocument

# (vault subdir, source_type) — only these directories get scanned.
SCAN_TARGETS: list[tuple[str, str]] = [
    ("raw/research", "research"),
    ("raw/articles", "article"),
    ("raw/transcripts", "transcript"),
    ("wiki", "wiki"),
]


@dataclass
class IngestStats:
    created: int = 0
    updated: int = 0
    renamed: int = 0
    unchanged: int = 0
    skipped: int = 0
    orphans_deleted: int = 0
    scanned_paths: set[str] = field(default_factory=set)


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


MAX_SLUG_LENGTH = 200
# Reserved for "-" + 12 hex chars of SHA-256 when we need a collision suffix.
SLUG_HASH_SUFFIX_LENGTH = 13


def _slugify_path(rel_path: Path) -> str:
    """
    Convert a relative vault path to a unique, URL-safe slug.

    Example: raw/research/abl-underwriting/overview.md
          -> raw-research-abl-underwriting-overview

    When the normalized slug exceeds the database column's max length, we
    append a short SHA-256 digest of the full path so two long paths that
    share a normalized prefix never collapse onto the same slug.
    """
    parts = list(rel_path.with_suffix("").parts)
    slug = "-".join(parts)
    # SlugField accepts [A-Za-z0-9_-], so swap any stray characters for '-'.
    cleaned = []
    for ch in slug.lower():
        if ch.isalnum() or ch in "-_":
            cleaned.append(ch)
        else:
            cleaned.append("-")
    slug = "".join(cleaned)
    # Collapse consecutive dashes and trim.
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")

    if len(slug) <= MAX_SLUG_LENGTH:
        return slug

    # Truncation needed — append a deterministic digest so paths that share
    # the first N characters after normalization remain distinguishable.
    digest = hashlib.sha256(str(rel_path).encode("utf-8")).hexdigest()[:12]
    head_limit = MAX_SLUG_LENGTH - SLUG_HASH_SUFFIX_LENGTH
    return f"{slug[:head_limit].rstrip('-')}-{digest}"


def _title_from_file(rel_path: Path, content: str) -> str:
    """Prefer the first H1 in the file; fall back to the filename."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.lstrip("#").strip()[:500]
    return rel_path.stem.replace("_", " ").replace("-", " ").title()[:500]


def _topic_from_path(rel_path: Path, source_root: Path) -> str:
    """
    Derive the topic from the first directory under the scan target.

    For raw/research/abl-underwriting/overview.md with source_root=raw/research,
    this returns "abl-underwriting".
    For wiki/factoring-pricing/summary.md with source_root=wiki, returns
    "factoring-pricing".
    If the file sits directly in source_root, returns the source_root name.
    """
    try:
        inside = rel_path.relative_to(source_root)
    except ValueError:
        return source_root.name
    parts = inside.parts
    if len(parts) > 1:
        return parts[0][:200]
    return source_root.name[:200]


class Command(BaseCommand):
    help = "Walk a mara-vault directory and import markdown files into ResearchDocument."

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument("vault_path", type=str, help="Absolute path to the vault root")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing to the database",
        )
        parser.add_argument(
            "--topic",
            type=str,
            default=None,
            help="Only ingest files whose derived topic matches this value",
        )

    def handle(self, *args, **options) -> None:  # type: ignore[no-untyped-def]
        vault_root = Path(options["vault_path"]).expanduser().resolve()
        dry_run: bool = options["dry_run"]
        topic_filter: str | None = options["topic"]

        if not vault_root.exists() or not vault_root.is_dir():
            raise CommandError(f"Vault path does not exist or is not a directory: {vault_root}")

        stats = IngestStats()

        for subdir, source_type in SCAN_TARGETS:
            source_root = vault_root / subdir
            if not source_root.exists():
                self.stdout.write(f"  SKIP  {subdir}/ (not present in vault)")
                continue

            for md_path in sorted(source_root.rglob("*.md")):
                rel_path = md_path.relative_to(vault_root)
                source_path_str = str(rel_path)
                topic = _topic_from_path(md_path, source_root)
                if topic_filter and topic != topic_filter:
                    stats.skipped += 1
                    continue

                # Record the path as "scanned" BEFORE attempting any I/O.
                # Transient read failures (OSError, UnicodeDecodeError,
                # empty files) would otherwise leave the file's existing
                # ResearchDocument row out of scanned_paths and the orphan
                # sweep would delete valid corpus rows on a temporary error.
                stats.scanned_paths.add(source_path_str)

                try:
                    content = md_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as exc:
                    self.stdout.write(
                        self.style.WARNING(f"  SKIP  {rel_path} ({exc})")
                    )
                    stats.skipped += 1
                    continue

                # Strip NUL bytes — PostgreSQL text columns reject \x00.
                # Corrupted source files (bad downloads, mis-decoded UTF-16,
                # binary contamination) sometimes contain NUL bytes inside
                # what otherwise looks like a valid markdown file. Drop them
                # silently so one bad file doesn't blow up the whole ingest.
                if "\x00" in content:
                    nul_count = content.count("\x00")
                    content = content.replace("\x00", "")
                    self.stdout.write(
                        self.style.WARNING(
                            f"  CLEAN  {rel_path} (stripped {nul_count} NUL bytes)"
                        )
                    )

                if not content.strip():
                    stats.skipped += 1
                    continue

                file_hash = _sha256(content)
                slug = _slugify_path(rel_path)
                title = _title_from_file(rel_path, content)
                word_count = len(content.split())

                # Fast path: slug + hash match → nothing to do.
                existing_by_slug = ResearchDocument.objects.filter(slug=slug).first()
                if existing_by_slug and existing_by_slug.file_hash == file_hash:
                    stats.unchanged += 1
                    continue

                # Rename detection: no slug match, but some other row has the
                # same content hash at a different source_path AND that old
                # source_path no longer exists on disk. Both conditions matter:
                #
                # - Hash alone is too weak. Two legitimately different files
                #   with the same content (e.g. an empty stub, a duplicated
                #   boilerplate in two topic dirs) would otherwise make the
                #   second file's ingest overwrite the first row and silently
                #   drop the first document from the corpus.
                # - Requiring the hash match to be unique (exactly one row)
                #   avoids picking an arbitrary row when several legitimately
                #   share content.
                # - Requiring the old file to be gone from disk confirms this
                #   is a real move/rename, not a copy.
                rename_candidate = None
                if existing_by_slug is None:
                    hash_matches = list(
                        ResearchDocument.objects
                        .filter(file_hash=file_hash)
                        .exclude(source_path=source_path_str)
                        .order_by("pk")[:2]
                    )
                    if len(hash_matches) == 1:
                        candidate = hash_matches[0]
                        candidate_disk_path = vault_root / candidate.source_path
                        if not candidate_disk_path.exists():
                            rename_candidate = candidate

                if dry_run:
                    if existing_by_slug:
                        tag = "UPDATE"
                        stats.updated += 1
                    elif rename_candidate:
                        tag = "RENAME"
                        stats.renamed += 1
                        stats.scanned_paths.add(rename_candidate.source_path)
                    else:
                        tag = "CREATE"
                        stats.created += 1
                    self.stdout.write(f"  {tag}  {rel_path}")
                    continue

                # --- Rename branch -------------------------------------
                if rename_candidate is not None:
                    with transaction.atomic():
                        try:
                            locked = (
                                ResearchDocument.objects
                                .select_for_update()
                                .get(pk=rename_candidate.pk)
                            )
                        except ResearchDocument.DoesNotExist:
                            # Deleted between the unlocked check and now —
                            # fall through to the normal create-or-update.
                            locked = None

                        if locked is not None:
                            # If another run already moved this row to the
                            # new source_path, nothing to do.
                            if locked.source_path == source_path_str:
                                stats.unchanged += 1
                                continue
                            # If another run grabbed the new slug for a
                            # different row, fall through to normal path so
                            # we don't trip the unique constraint.
                            conflict = (
                                ResearchDocument.objects
                                .filter(slug=slug)
                                .exclude(pk=locked.pk)
                                .exists()
                            )
                            if not conflict:
                                # Capture the prior path BEFORE overwriting
                                # so the log message reads "old → new", not
                                # "new → new".
                                old_source_path = locked.source_path
                                locked.slug = slug
                                locked.source_path = source_path_str
                                locked.title = title
                                locked.source_type = source_type
                                locked.topic = topic
                                # Hash is already equal, so content is
                                # identical — leave chunks and is_indexed
                                # alone to avoid needlessly re-embedding.
                                locked.save()
                                stats.renamed += 1
                                # The old source_path no longer exists on
                                # disk; add the new path to scanned_paths
                                # so the orphan sweep doesn't delete this
                                # row on the next ingest step.
                                stats.scanned_paths.add(source_path_str)
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f"  RENAME  {old_source_path} → {rel_path}"
                                    )
                                )
                                continue

                # --- Normal create-or-update branch --------------------
                defaults = {
                    "title": title,
                    "source_path": source_path_str,
                    "source_type": source_type,
                    "topic": topic,
                    "content": content,
                    "word_count": word_count,
                    "file_hash": file_hash,
                    "is_indexed": False,
                }
                with transaction.atomic():
                    try:
                        doc, created = ResearchDocument.objects.get_or_create(
                            slug=slug,
                            defaults=defaults,
                        )
                    except IntegrityError:
                        # Race: another writer created the row between our
                        # unlocked check and the atomic block. Re-fetch and
                        # fall into the update branch.
                        doc = ResearchDocument.objects.get(slug=slug)
                        created = False

                    if created:
                        stats.created += 1
                        self.stdout.write(self.style.SUCCESS(f"  CREATE  {rel_path}"))
                        continue

                    # Existing row — lock and update.
                    locked = (
                        ResearchDocument.objects.select_for_update().get(pk=doc.pk)
                    )
                    if locked.file_hash == file_hash:
                        stats.unchanged += 1
                        continue
                    for field_name, value in defaults.items():
                        setattr(locked, field_name, value)
                    # Content changed — embeddings are stale.
                    locked.chunks.all().delete()
                    locked.save()
                    stats.updated += 1
                    self.stdout.write(self.style.WARNING(f"  UPDATE  {rel_path}"))

        # --- Orphan cleanup ---------------------------------------------------
        # A file that was in the vault on a previous run but no longer exists
        # (or was renamed — handled above) leaves a ResearchDocument row with
        # a source_path that wasn't scanned this run. Delete those rows so the
        # search index, document list, topic counts, and stats stay aligned
        # with the actual vault. Only run when we scanned the full corpus —
        # never under a topic filter (we'd delete docs we never looked at).
        if topic_filter is None and not dry_run and stats.scanned_paths:
            orphans = ResearchDocument.objects.exclude(
                source_path__in=stats.scanned_paths,
            )
            orphan_paths = list(
                orphans.order_by("source_path").values_list("source_path", flat=True)
            )
            if orphan_paths:
                # Count the documents ourselves — QuerySet.delete() returns
                # the total of ALL deleted rows including cascaded
                # ResearchChunks, which would over-report the orphan count
                # once chunks exist.
                stats.orphans_deleted = len(orphan_paths)
                orphans.delete()
                for path in orphan_paths:
                    self.stdout.write(self.style.WARNING(f"  DELETE  {path}"))

        summary_parts = [
            f"{stats.created} created",
            f"{stats.updated} updated",
            f"{stats.renamed} renamed",
            f"{stats.unchanged} unchanged",
            f"{stats.skipped} skipped",
        ]
        if stats.orphans_deleted:
            summary_parts.append(f"{stats.orphans_deleted} orphans deleted")
        summary = "\nDone — " + ", ".join(summary_parts)
        if dry_run:
            summary = "[DRY RUN] " + summary.lstrip()
        self.stdout.write(self.style.SUCCESS(summary))
