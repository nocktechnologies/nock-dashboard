# brain/tests/test_research.py
"""
Tests for the Research Library: models, chunking, ingest command, and API.

Search tests mock out OpenAI embedding calls so they don't hit the network.
Vector similarity ranking is verified with a tiny dedicated test that writes
raw vectors to the DB and issues a CosineDistance query — this requires the
pgvector extension in the underlying PostgreSQL.
"""
from __future__ import annotations

import hashlib
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase

from brain.chunking import chunk_document
from brain.models import ResearchChunk, ResearchDocument

# Semantic-search tests use pgvector's CosineDistance, which is PostgreSQL-only.
# Skip those tests wholesale on other backends (e.g. SQLite) so the suite
# stays portable — the migration already gates pgvector setup the same way.
_PG_ONLY = skipUnless(
    getattr(connection, "vendor", None) == "postgresql",
    "pgvector semantic-search tests require PostgreSQL",
)

# ──────────────────────────────────────────────
# CHUNKING TESTS
# ──────────────────────────────────────────────


class ChunkDocumentTest(TestCase):

    def test_empty_document(self) -> None:
        self.assertEqual(chunk_document("", "t", "topic"), [])
        self.assertEqual(chunk_document("   \n\n  ", "t", "topic"), [])

    def test_short_document_single_chunk(self) -> None:
        content = "# Intro\n\nThis is a short document with not many words."
        chunks = chunk_document(content, "Intro Doc", "test-topic", max_words=100)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["chunk_index"], 0)
        self.assertEqual(chunks[0]["metadata"]["topic"], "test-topic")
        self.assertEqual(chunks[0]["metadata"]["title"], "Intro Doc")
        self.assertIn("short document", chunks[0]["content"])

    def test_chunk_includes_heading_in_metadata(self) -> None:
        content = "## Section One\n\nAlpha beta gamma."
        chunks = chunk_document(content, "Doc", "topic")
        self.assertEqual(chunks[0]["metadata"]["heading"], "Section One")

    def test_split_on_headers_produces_multiple_chunks(self) -> None:
        # Two sections, each just barely under max_words combined exceed it.
        section_a = "## Section A\n\n" + " ".join(["alpha"] * 60)
        section_b = "## Section B\n\n" + " ".join(["bravo"] * 60)
        chunks = chunk_document(
            section_a + "\n\n" + section_b,
            "Doc", "topic",
            max_words=80, overlap_words=10,
        )
        # 60 + 60 = 120 words; max 80 → at least 2 chunks
        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["chunk_index"], 0)
        self.assertEqual(chunks[1]["chunk_index"], 1)

    def test_overlap_between_chunks(self) -> None:
        words = " ".join([f"w{i}" for i in range(200)])
        content = f"# Doc\n\n{words}"
        chunks = chunk_document(content, "Doc", "topic", max_words=50, overlap_words=10)
        self.assertGreaterEqual(len(chunks), 2)
        # Each chunk after the first should contain at least some overlap
        # words from the tail of the prior chunk.
        first_tail_words = set(chunks[0]["content"].split()[-10:])
        second_head_words = set(chunks[1]["content"].split()[:15])
        overlap = first_tail_words & second_head_words
        self.assertTrue(overlap, "Expected some overlap between adjacent chunks")

    def test_chunk_indexes_are_sequential(self) -> None:
        words = " ".join([f"w{i}" for i in range(500)])
        chunks = chunk_document(words, "Doc", "topic", max_words=100, overlap_words=20)
        self.assertGreater(len(chunks), 1)
        for idx, chunk in enumerate(chunks):
            self.assertEqual(chunk["chunk_index"], idx)

    def test_chunk_word_count_matches_content(self) -> None:
        content = "# H\n\n" + " ".join(["word"] * 300)
        chunks = chunk_document(content, "Doc", "topic", max_words=100, overlap_words=20)
        for c in chunks:
            self.assertEqual(c["word_count"], len(c["content"].split()))

    def test_document_with_no_headers(self) -> None:
        content = " ".join(["apple"] * 20)
        chunks = chunk_document(content, "Plain Doc", "topic")
        self.assertEqual(len(chunks), 1)
        # Heading falls back to title when no header present.
        self.assertEqual(chunks[0]["metadata"]["heading"], "Plain Doc")

    def test_non_positive_max_words_raises(self) -> None:
        with self.assertRaises(ValueError):
            chunk_document("hello world", "Doc", "topic", max_words=0)
        with self.assertRaises(ValueError):
            chunk_document("hello world", "Doc", "topic", max_words=-5)


# ──────────────────────────────────────────────
# MODEL TESTS
# ──────────────────────────────────────────────


class ResearchDocumentModelTest(TestCase):

    def _make(self, **kwargs) -> ResearchDocument:
        defaults = {
            "slug": "test-doc",
            "title": "Test",
            "source_path": "raw/research/test.md",
            "source_type": "research",
            "topic": "test-topic",
            "content": "hello world",
            "word_count": 2,
            "file_hash": hashlib.sha256(b"hello world").hexdigest(),
        }
        defaults.update(kwargs)
        return ResearchDocument.objects.create(**defaults)

    def test_create_document(self) -> None:
        doc = self._make()
        self.assertEqual(doc.topic, "test-topic")
        self.assertFalse(doc.is_indexed)
        self.assertEqual(doc.word_count, 2)

    def test_slug_unique(self) -> None:
        from django.db import IntegrityError
        self._make(slug="unique")
        with self.assertRaises(IntegrityError):
            self._make(slug="unique")

    def test_ordering_by_topic_then_title(self) -> None:
        self._make(slug="b", topic="b-topic", title="B")
        self._make(slug="a2", topic="a-topic", title="Zeta")
        self._make(slug="a1", topic="a-topic", title="Alpha")
        docs = list(ResearchDocument.objects.all())
        self.assertEqual([d.slug for d in docs], ["a1", "a2", "b"])


class ResearchChunkModelTest(TestCase):

    def _make_doc(self) -> ResearchDocument:
        return ResearchDocument.objects.create(
            slug="d", title="D", source_path="p", source_type="research",
            topic="t", content="c", word_count=1, file_hash="h",
        )

    def test_create_chunk_without_embedding(self) -> None:
        doc = self._make_doc()
        chunk = ResearchChunk.objects.create(
            document=doc, chunk_index=0, content="hello", word_count=1,
            metadata={"heading": "H"},
        )
        self.assertIsNone(chunk.embedding)
        self.assertEqual(chunk.metadata["heading"], "H")

    def test_chunk_unique_per_document(self) -> None:
        from django.db import IntegrityError
        doc = self._make_doc()
        ResearchChunk.objects.create(document=doc, chunk_index=0, content="a")
        with self.assertRaises(IntegrityError):
            ResearchChunk.objects.create(document=doc, chunk_index=0, content="dup")

    def test_cascade_delete(self) -> None:
        doc = self._make_doc()
        ResearchChunk.objects.create(document=doc, chunk_index=0, content="a")
        ResearchChunk.objects.create(document=doc, chunk_index=1, content="b")
        doc.delete()
        self.assertEqual(ResearchChunk.objects.count(), 0)


# ──────────────────────────────────────────────
# INGEST COMMAND TESTS
# ──────────────────────────────────────────────


class IngestResearchCommandTest(TestCase):

    def _make_vault(self, tmp: str) -> Path:
        root = Path(tmp)
        (root / "raw" / "research" / "abl-underwriting").mkdir(parents=True)
        (root / "raw" / "research" / "abl-underwriting" / "overview.md").write_text(
            "# Overview\n\nContent A", encoding="utf-8",
        )
        (root / "raw" / "research" / "abl-underwriting" / "detail.md").write_text(
            "# Detail\n\nContent B", encoding="utf-8",
        )
        (root / "wiki" / "factoring-pricing").mkdir(parents=True)
        (root / "wiki" / "factoring-pricing" / "summary.md").write_text(
            "# Summary\n\nContent C", encoding="utf-8",
        )
        (root / "raw" / "articles").mkdir(parents=True)
        (root / "raw" / "articles" / "news.md").write_text(
            "# News\n\nContent D", encoding="utf-8",
        )
        return root

    def test_ingest_creates_documents(self) -> None:
        with TemporaryDirectory() as tmp:
            self._make_vault(tmp)
            out = StringIO()
            call_command("ingest_research", tmp, stdout=out)
        self.assertEqual(ResearchDocument.objects.count(), 4)
        # Topic derived from parent directory
        abl = ResearchDocument.objects.get(slug="raw-research-abl-underwriting-overview")
        self.assertEqual(abl.topic, "abl-underwriting")
        self.assertEqual(abl.source_type, "research")
        self.assertEqual(abl.title, "Overview")
        # Wiki source_type
        wiki = ResearchDocument.objects.get(slug="wiki-factoring-pricing-summary")
        self.assertEqual(wiki.source_type, "wiki")
        self.assertEqual(wiki.topic, "factoring-pricing")
        # Article source_type when file sits at the root of raw/articles (no intermediate topic dir)
        article = ResearchDocument.objects.get(slug="raw-articles-news")
        self.assertEqual(article.source_type, "article")

    def test_ingest_idempotent(self) -> None:
        with TemporaryDirectory() as tmp:
            self._make_vault(tmp)
            call_command("ingest_research", tmp, stdout=StringIO())
            self.assertEqual(ResearchDocument.objects.count(), 4)
            out = StringIO()
            call_command("ingest_research", tmp, stdout=out)
            self.assertEqual(ResearchDocument.objects.count(), 4)
            self.assertIn("unchanged", out.getvalue())

    def test_ingest_detects_changes(self) -> None:
        with TemporaryDirectory() as tmp:
            self._make_vault(tmp)
            call_command("ingest_research", tmp, stdout=StringIO())
            doc = ResearchDocument.objects.get(slug="raw-research-abl-underwriting-overview")
            original_hash = doc.file_hash

            # Mark the doc as already indexed to verify update resets that flag.
            doc.is_indexed = True
            doc.save()

            # Mutate the file so the hash differs.
            (Path(tmp) / "raw" / "research" / "abl-underwriting" / "overview.md").write_text(
                "# Overview\n\nCompletely new content", encoding="utf-8",
            )
            out = StringIO()
            call_command("ingest_research", tmp, stdout=out)
            doc.refresh_from_db()
            self.assertNotEqual(doc.file_hash, original_hash)
            self.assertFalse(doc.is_indexed)
            self.assertIn("UPDATE", out.getvalue())

    def test_ingest_dry_run_does_not_write(self) -> None:
        with TemporaryDirectory() as tmp:
            self._make_vault(tmp)
            call_command("ingest_research", tmp, "--dry-run", stdout=StringIO())
        self.assertEqual(ResearchDocument.objects.count(), 0)

    def test_ingest_strips_nul_bytes(self) -> None:
        """PostgreSQL text columns reject \\x00 bytes. Strip them from content
        before persisting so a single corrupted source file doesn't blow up
        the whole ingest.

        This regression was caught on the first prod run (PR #66): one vault
        file had 13,119 NUL bytes from a mis-decoded UTF-16 export, which
        crashed ingest with `DataError: PostgreSQL text fields cannot contain
        NUL (0x00) bytes` after 69 rows were already in the DB.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "raw" / "research" / "topic").mkdir(parents=True)
            corrupted_path = root / "raw" / "research" / "topic" / "corrupt.md"
            # Intersperse NUL bytes throughout valid markdown.
            corrupted_path.write_text(
                "# Title\x00\n\nParagraph\x00 with\x00 embedded\x00 nulls.",
                encoding="utf-8",
            )
            out = StringIO()
            call_command("ingest_research", tmp, stdout=out)

        # The document must still be created with the NULs stripped.
        self.assertEqual(ResearchDocument.objects.count(), 1)
        doc = ResearchDocument.objects.get(slug="raw-research-topic-corrupt")
        self.assertNotIn("\x00", doc.content)
        self.assertIn("Paragraph with embedded nulls.", doc.content)
        # The command must log the CLEAN action with the NUL count.
        log = out.getvalue()
        self.assertIn("CLEAN", log)
        self.assertIn("4 NUL bytes", log)

    def test_ingest_topic_filter(self) -> None:
        with TemporaryDirectory() as tmp:
            self._make_vault(tmp)
            call_command(
                "ingest_research", tmp, "--topic", "abl-underwriting",
                stdout=StringIO(),
            )
        slugs = set(ResearchDocument.objects.values_list("slug", flat=True))
        self.assertEqual(
            slugs,
            {
                "raw-research-abl-underwriting-overview",
                "raw-research-abl-underwriting-detail",
            },
        )

    def test_ingest_detects_rename_as_update(self) -> None:
        """Renaming a vault file updates the row in place, not as a duplicate."""
        with TemporaryDirectory() as tmp:
            self._make_vault(tmp)
            call_command("ingest_research", tmp, stdout=StringIO())
            before = ResearchDocument.objects.count()
            original = ResearchDocument.objects.get(
                slug="raw-research-abl-underwriting-overview",
            )
            original_pk = original.pk
            # Flag it so we can check the rename preserves embeddings.
            original.is_indexed = True
            original.save()

            # Rename the file on disk — same content, new path.
            old_path = Path(tmp) / "raw" / "research" / "abl-underwriting" / "overview.md"
            new_path = Path(tmp) / "raw" / "research" / "abl-underwriting" / "introduction.md"
            old_path.rename(new_path)

            out = StringIO()
            call_command("ingest_research", tmp, stdout=out)

        # Total row count unchanged (no duplicate row created).
        self.assertEqual(ResearchDocument.objects.count(), before)
        # The old slug is gone, the new slug points at the same underlying row.
        self.assertFalse(
            ResearchDocument.objects.filter(
                slug="raw-research-abl-underwriting-overview",
            ).exists(),
        )
        renamed = ResearchDocument.objects.get(
            slug="raw-research-abl-underwriting-introduction",
        )
        self.assertEqual(renamed.pk, original_pk)
        self.assertEqual(
            renamed.source_path,
            "raw/research/abl-underwriting/introduction.md",
        )
        # Rename preserves embeddings — content hash is unchanged.
        self.assertTrue(renamed.is_indexed)
        # Log must read "old → new", not "new → new".
        log = out.getvalue()
        self.assertIn("RENAME", log)
        self.assertIn("raw/research/abl-underwriting/overview.md", log)
        self.assertIn("raw/research/abl-underwriting/introduction.md", log)

    def test_ingest_orphan_cleanup_deletes_removed_files(self) -> None:
        """Files removed from the vault should be deleted from the DB."""
        with TemporaryDirectory() as tmp:
            self._make_vault(tmp)
            call_command("ingest_research", tmp, stdout=StringIO())
            self.assertEqual(ResearchDocument.objects.count(), 4)

            # Remove one file entirely.
            (Path(tmp) / "raw" / "research" / "abl-underwriting" / "detail.md").unlink()

            out = StringIO()
            call_command("ingest_research", tmp, stdout=out)

        self.assertEqual(ResearchDocument.objects.count(), 3)
        self.assertFalse(
            ResearchDocument.objects.filter(
                slug="raw-research-abl-underwriting-detail",
            ).exists(),
        )
        self.assertIn("DELETE", out.getvalue())
        self.assertIn("1 orphans deleted", out.getvalue())

    def test_rename_not_inferred_from_duplicate_content(self) -> None:
        """Two distinct files with identical content must not collapse into one.

        The old rename heuristic (hash match alone) would have overwritten the
        first row when the second file was ingested. The tightened heuristic
        requires the old file to no longer exist on disk AND the hash match
        to be unique, so both files coexist as separate rows.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "raw" / "research" / "topic-a").mkdir(parents=True)
            (root / "raw" / "research" / "topic-b").mkdir(parents=True)
            identical = "# Shared\n\nSame content in two places."
            (root / "raw" / "research" / "topic-a" / "note.md").write_text(
                identical, encoding="utf-8",
            )
            (root / "raw" / "research" / "topic-b" / "note.md").write_text(
                identical, encoding="utf-8",
            )
            call_command("ingest_research", tmp, stdout=StringIO())

        # Two distinct rows, not one rename-collapse.
        self.assertEqual(ResearchDocument.objects.count(), 2)
        slugs = set(ResearchDocument.objects.values_list("slug", flat=True))
        self.assertEqual(
            slugs,
            {
                "raw-research-topic-a-note",
                "raw-research-topic-b-note",
            },
        )

    def test_read_failure_does_not_trigger_orphan_deletion(self) -> None:
        """A file that fails to read must not be treated as an orphan.

        A transient OSError (or UnicodeDecodeError) during read_text() would
        previously skip adding the file's source_path to scanned_paths, so the
        orphan cleanup sweep at end-of-ingest would delete its ResearchDocument
        row. That's data loss from a transient filesystem error.
        """
        with TemporaryDirectory() as tmp:
            self._make_vault(tmp)
            # First pass: ingest normally so all 4 rows are in the DB.
            call_command("ingest_research", tmp, stdout=StringIO())
            self.assertEqual(ResearchDocument.objects.count(), 4)

            # Second pass: patch read_text to raise OSError for one specific
            # file, then re-run. The row for that file must survive.
            original_read_text = Path.read_text
            target_basename = "overview.md"

            def failing_read_text(self_path, *args, **kwargs):
                if self_path.name == target_basename:
                    raise OSError("simulated transient read failure")
                return original_read_text(self_path, *args, **kwargs)

            out = StringIO()
            with patch.object(Path, "read_text", failing_read_text):
                call_command("ingest_research", tmp, stdout=out)

        # All 4 rows must still be present — the failing file must not have
        # been swept as an orphan.
        self.assertEqual(ResearchDocument.objects.count(), 4)
        self.assertTrue(
            ResearchDocument.objects.filter(
                slug="raw-research-abl-underwriting-overview",
            ).exists(),
        )
        self.assertNotIn("0 orphans deleted", out.getvalue())

    def test_rename_not_inferred_when_old_file_still_exists(self) -> None:
        """If the old file is still on disk, it's a copy — not a rename."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "raw" / "research" / "topic").mkdir(parents=True)
            original = root / "raw" / "research" / "topic" / "original.md"
            original.write_text("# X\n\nContent", encoding="utf-8")
            call_command("ingest_research", tmp, stdout=StringIO())
            self.assertEqual(ResearchDocument.objects.count(), 1)

            # Add a second file with identical content; leave the original alone.
            (root / "raw" / "research" / "topic" / "copy.md").write_text(
                "# X\n\nContent", encoding="utf-8",
            )
            call_command("ingest_research", tmp, stdout=StringIO())

        # Both files should be present as separate rows.
        self.assertEqual(ResearchDocument.objects.count(), 2)

    def test_ingest_orphan_cleanup_skipped_with_topic_filter(self) -> None:
        """Topic filter must not delete docs outside the filtered topic."""
        with TemporaryDirectory() as tmp:
            self._make_vault(tmp)
            call_command("ingest_research", tmp, stdout=StringIO())
            self.assertEqual(ResearchDocument.objects.count(), 4)

            # Remove a file. With --topic=factoring-pricing we shouldn't scan
            # abl-underwriting at all, so orphan cleanup must stay off.
            (Path(tmp) / "wiki" / "factoring-pricing" / "summary.md").unlink()

            call_command(
                "ingest_research", tmp, "--topic", "factoring-pricing",
                stdout=StringIO(),
            )

        # All 4 docs should still be present — orphan cleanup was suppressed.
        self.assertEqual(ResearchDocument.objects.count(), 4)

    def test_ingest_concurrent_create_race_safe(self) -> None:
        """The IntegrityError fallback must actually recover, not crash.

        To exercise the `try: get_or_create ... except IntegrityError:` path
        we need a simulated race where another writer inserts the row in the
        gap between our `filter(slug=...).first()` check and `get_or_create`.
        We do that by patching `get_or_create` to:
          1. Insert a competing row (simulating the other writer)
          2. Raise IntegrityError (simulating the unique-constraint violation)

        The command should then catch the IntegrityError, re-fetch the row,
        and fall into the update branch. The row's content must end up as
        whatever came from the file on disk, with is_indexed reset.
        """
        from django.db import IntegrityError as DBIntegrityError

        from brain.models import ResearchDocument as RD

        original_get_or_create = RD.objects.get_or_create
        call_count = {"n": 0}

        def racing_get_or_create(**kwargs):
            call_count["n"] += 1
            # Only race on the first call; subsequent calls (for other files)
            # go through normally so the rest of the vault still imports.
            if call_count["n"] == 1:
                # Simulate another writer inserting the row in the gap.
                RD.objects.create(
                    slug=kwargs["slug"],
                    title="Injected by racing writer",
                    source_path=kwargs["defaults"]["source_path"],
                    source_type=kwargs["defaults"]["source_type"],
                    topic=kwargs["defaults"]["topic"],
                    content="race-injected content",
                    word_count=3,
                    file_hash="racehash",
                    is_indexed=True,
                )
                raise DBIntegrityError("UNIQUE constraint failed: brain_researchdocument.slug")
            return original_get_or_create(**kwargs)

        with TemporaryDirectory() as tmp:
            self._make_vault(tmp)
            with patch.object(RD.objects, "get_or_create", side_effect=racing_get_or_create):
                out = StringIO()
                # Must not raise — the IntegrityError must be caught and the
                # command must recover by updating the injected row.
                call_command("ingest_research", tmp, stdout=out)

        # The first slug scanned (sorted order → raw/articles/news.md) should
        # have been the one that hit the race. Verify that:
        #   a) The command completed and all 4 files are present.
        #   b) The racing row was updated from the file on disk (title
        #      rewritten, stale content replaced, is_indexed reset).
        self.assertEqual(ResearchDocument.objects.count(), 4)
        raced_doc = ResearchDocument.objects.get(slug="raw-articles-news")
        self.assertEqual(raced_doc.title, "News")  # from the file, not "Injected by racing writer"
        self.assertNotEqual(raced_doc.file_hash, "racehash")  # recomputed from file
        self.assertFalse(raced_doc.is_indexed)  # reset because content changed

    def test_ingest_invalid_path_raises(self) -> None:
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command("ingest_research", "/definitely/not/a/real/path", stdout=StringIO())

    def test_slugify_long_paths_stay_unique(self) -> None:
        """Two long paths sharing a prefix must not collapse to the same slug."""
        from pathlib import Path as _Path

        from brain.management.commands.ingest_research import (
            MAX_SLUG_LENGTH,
            _slugify_path,
        )

        # Build two paths that share the first ~210 characters after
        # normalization but diverge at the end.
        long_segment = "a" * 220
        p1 = _Path("raw/research") / long_segment / "overview-alpha.md"
        p2 = _Path("raw/research") / long_segment / "overview-beta.md"
        slug1 = _slugify_path(p1)
        slug2 = _slugify_path(p2)
        self.assertLessEqual(len(slug1), MAX_SLUG_LENGTH)
        self.assertLessEqual(len(slug2), MAX_SLUG_LENGTH)
        self.assertNotEqual(
            slug1, slug2,
            "Long paths with shared prefix must produce distinct slugs",
        )

    def test_slugify_short_paths_have_no_digest(self) -> None:
        from brain.management.commands.ingest_research import _slugify_path
        slug = _slugify_path(Path("raw/research/abl-underwriting/overview.md"))
        self.assertEqual(slug, "raw-research-abl-underwriting-overview")


# ──────────────────────────────────────────────
# EMBED COMMAND TESTS
# ──────────────────────────────────────────────


class EmbedResearchCommandTest(TestCase):
    """Tests for embed_research that don't require real OpenAI calls."""

    def _make_doc(self, **kwargs) -> ResearchDocument:
        defaults = {
            "slug": "d",
            "title": "Doc",
            "source_path": "p",
            "source_type": "research",
            "topic": "t",
            "content": "# Heading\n\nSome content here.",
            "word_count": 5,
            "file_hash": "h",
            "is_indexed": False,
        }
        defaults.update(kwargs)
        return ResearchDocument.objects.create(**defaults)

    def test_max_documents_zero_processes_nothing(self) -> None:
        """--max-documents=0 must be honored (not treated as "no limit")."""
        self._make_doc(slug="a")
        self._make_doc(slug="b")
        # If --max-documents=0 were ignored, the command would try to embed
        # both docs and explode because no OpenAI key is configured.
        out = StringIO()
        call_command("embed_research", "--max-documents", "0", stdout=out)
        # Neither document should have been indexed.
        self.assertEqual(
            ResearchDocument.objects.filter(is_indexed=True).count(), 0,
        )
        self.assertIn("Embedding 0 document(s)", out.getvalue())

    def test_no_unindexed_documents_is_noop(self) -> None:
        """Default (no --force) filters out already-indexed docs up front."""
        self._make_doc(slug="already", is_indexed=True)
        out = StringIO()
        call_command("embed_research", stdout=out)
        # Would have blown up on the missing OPENAI_API_KEY if it tried to embed.
        self.assertEqual(ResearchChunk.objects.count(), 0)
        self.assertIn("0 docs processed", out.getvalue())


# ──────────────────────────────────────────────
# API BASE
# ──────────────────────────────────────────────


class ResearchAPIBase(TestCase):

    def setUp(self) -> None:
        # Tests use force_login() and API-key auth — the user's password is
        # never checked. Pass password=None so Django stores an unusable
        # password (no literal secret in the tree, no Ruff S106 noise).
        self.user = User.objects.create_user(
            username="researchtest", password=None, is_staff=True,
        )
        self.client.force_login(self.user)
        cache.clear()

    def _make_doc(self, **kwargs) -> ResearchDocument:
        defaults = {
            "slug": "d",
            "title": "Doc",
            "source_path": "p",
            "source_type": "research",
            "topic": "t",
            "content": "hello world",
            "word_count": 2,
            "file_hash": "h",
            "is_indexed": True,
        }
        defaults.update(kwargs)
        return ResearchDocument.objects.create(**defaults)

    def _make_chunk(
        self, doc: ResearchDocument, chunk_index: int = 0,
        content: str = "body", embedding: list[float] | None = None,
        **kwargs,
    ) -> ResearchChunk:
        if embedding is None:
            embedding = [0.0] * 1536
        return ResearchChunk.objects.create(
            document=doc,
            chunk_index=chunk_index,
            content=content,
            word_count=len(content.split()),
            metadata=kwargs.get("metadata", {"heading": "H"}),
            embedding=embedding,
        )


# ──────────────────────────────────────────────
# DOCUMENTS LIST + DETAIL TESTS
# ──────────────────────────────────────────────


class DocumentsListTest(ResearchAPIBase):

    def test_list_empty(self) -> None:
        resp = self.client.get("/api/brain/research/documents/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["total"], 0)

    def test_list_excludes_content(self) -> None:
        self._make_doc(slug="x", content="This is the full body")
        resp = self.client.get("/api/brain/research/documents/")
        doc = resp.json()["data"]["documents"][0]
        self.assertNotIn("content", doc)
        self.assertIn("slug", doc)
        self.assertIn("topic", doc)

    def test_list_topic_filter(self) -> None:
        self._make_doc(slug="a", topic="alpha")
        self._make_doc(slug="b", topic="beta")
        resp = self.client.get("/api/brain/research/documents/?topic=alpha")
        slugs = [d["slug"] for d in resp.json()["data"]["documents"]]
        self.assertEqual(slugs, ["a"])

    def test_list_source_type_filter(self) -> None:
        self._make_doc(slug="r", source_type="research")
        self._make_doc(slug="w", source_type="wiki")
        resp = self.client.get("/api/brain/research/documents/?source_type=wiki")
        slugs = [d["slug"] for d in resp.json()["data"]["documents"]]
        self.assertEqual(slugs, ["w"])


class DocumentDetailTest(ResearchAPIBase):

    def test_detail_includes_content_and_chunks(self) -> None:
        doc = self._make_doc(slug="x", content="Full content here")
        self._make_chunk(doc, chunk_index=0, content="chunk 0 text")
        self._make_chunk(doc, chunk_index=1, content="chunk 1 text")
        resp = self.client.get("/api/brain/research/documents/x/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["content"], "Full content here")
        self.assertEqual(len(data["chunks"]), 2)
        self.assertEqual(data["chunks"][0]["chunk_index"], 0)
        self.assertTrue(data["chunks"][0]["has_embedding"])

    def test_detail_not_found(self) -> None:
        resp = self.client.get("/api/brain/research/documents/nope/")
        self.assertEqual(resp.status_code, 404)


# ──────────────────────────────────────────────
# TOPICS + STATS TESTS
# ──────────────────────────────────────────────


class TopicsEndpointTest(ResearchAPIBase):

    def test_topics_returns_counts(self) -> None:
        self._make_doc(slug="a1", topic="alpha")
        self._make_doc(slug="a2", topic="alpha")
        self._make_doc(slug="b1", topic="beta")
        resp = self.client.get("/api/brain/research/topics/")
        data = resp.json()["data"]
        counts = {row["topic"]: row["document_count"] for row in data["topics"]}
        self.assertEqual(counts, {"alpha": 2, "beta": 1})
        self.assertEqual(data["total"], 2)


class StatsEndpointTest(ResearchAPIBase):

    def test_stats_shape(self) -> None:
        doc1 = self._make_doc(slug="a", topic="alpha", word_count=100, is_indexed=True)
        self._make_doc(slug="b", topic="beta", word_count=50, is_indexed=False)
        self._make_chunk(doc1, chunk_index=0, content="x")
        resp = self.client.get("/api/brain/research/stats/")
        data = resp.json()["data"]
        self.assertEqual(data["total_documents"], 2)
        self.assertEqual(data["indexed_documents"], 1)
        self.assertEqual(data["indexed_percent"], 50.0)
        self.assertEqual(data["total_chunks"], 1)
        self.assertEqual(data["embedded_chunks"], 1)
        self.assertEqual(data["total_topics"], 2)
        self.assertEqual(data["total_words"], 150)


# ──────────────────────────────────────────────
# SEARCH TESTS
# ──────────────────────────────────────────────


@_PG_ONLY
class SearchEndpointTest(ResearchAPIBase):

    def _seed_chunks_with_distinct_embeddings(self) -> None:
        """Seed 3 docs with orthogonal-ish 1536-d vectors for ranking tests."""
        doc1 = self._make_doc(slug="d1", topic="finance", title="Doc One")
        doc2 = self._make_doc(slug="d2", topic="finance", title="Doc Two")
        doc3 = self._make_doc(slug="d3", topic="other", title="Doc Three")

        v1 = [0.0] * 1536
        v1[0] = 1.0
        v2 = [0.0] * 1536
        v2[1] = 1.0
        v3 = [0.0] * 1536
        v3[2] = 1.0
        self._make_chunk(doc1, content="finance one body", embedding=v1)
        self._make_chunk(doc2, content="finance two body", embedding=v2)
        self._make_chunk(doc3, content="other body", embedding=v3)

    def test_search_empty_query_returns_400(self) -> None:
        resp = self.client.get("/api/brain/research/search/?q=")
        self.assertEqual(resp.status_code, 400)

    def test_search_missing_query_returns_400(self) -> None:
        resp = self.client.get("/api/brain/research/search/")
        self.assertEqual(resp.status_code, 400)

    def test_search_returns_ranked_results(self) -> None:
        self._seed_chunks_with_distinct_embeddings()
        # Query vector most aligned with doc1's embedding (dim 0).
        query_vec = [0.0] * 1536
        query_vec[0] = 1.0
        with patch("brain.views_research.embeddings.generate_embedding", return_value=query_vec):
            resp = self.client.get("/api/brain/research/search/?q=finance")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertGreater(data["total_results"], 0)
        # Top result should be d1 because its embedding aligns with the query vector.
        self.assertEqual(data["results"][0]["document_slug"], "d1")
        self.assertEqual(data["results"][0]["heading"], "H")

    def test_search_topic_filter(self) -> None:
        self._seed_chunks_with_distinct_embeddings()
        query_vec = [0.0] * 1536
        query_vec[2] = 1.0
        with patch("brain.views_research.embeddings.generate_embedding", return_value=query_vec):
            resp = self.client.get("/api/brain/research/search/?q=q&topic=finance")
        results = resp.json()["data"]["results"]
        slugs = {r["document_slug"] for r in results}
        # Topic filter must exclude d3 even though it's the closest match.
        self.assertNotIn("d3", slugs)
        self.assertTrue(slugs.issubset({"d1", "d2"}))

    def test_search_limit(self) -> None:
        self._seed_chunks_with_distinct_embeddings()
        query_vec = [0.0] * 1536
        query_vec[0] = 1.0
        with patch("brain.views_research.embeddings.generate_embedding", return_value=query_vec):
            resp = self.client.get("/api/brain/research/search/?q=q&limit=1")
        self.assertEqual(resp.json()["data"]["total_results"], 1)

    def test_search_ignores_unindexed_documents(self) -> None:
        doc_unindexed = self._make_doc(slug="ux", is_indexed=False)
        self._make_chunk(doc_unindexed, embedding=[1.0] + [0.0] * 1535)
        doc_indexed = self._make_doc(slug="ix", is_indexed=True)
        self._make_chunk(doc_indexed, embedding=[1.0] + [0.0] * 1535)
        with patch(
            "brain.views_research.embeddings.generate_embedding",
            return_value=[1.0] + [0.0] * 1535,
        ):
            resp = self.client.get("/api/brain/research/search/?q=q")
        slugs = {r["document_slug"] for r in resp.json()["data"]["results"]}
        self.assertEqual(slugs, {"ix"})

    def test_search_ignores_chunks_without_embedding(self) -> None:
        doc = self._make_doc(slug="d", is_indexed=True)
        ResearchChunk.objects.create(
            document=doc, chunk_index=0, content="no embedding", embedding=None,
        )
        with patch(
            "brain.views_research.embeddings.generate_embedding",
            return_value=[1.0] + [0.0] * 1535,
        ):
            resp = self.client.get("/api/brain/research/search/?q=q")
        self.assertEqual(resp.json()["data"]["total_results"], 0)

    def test_search_embedding_upstream_failure_returns_502(self) -> None:
        """Upstream OpenAI errors (timeout, connection, rate limit) → 502."""
        from openai import APIConnectionError

        self._make_doc(slug="d", is_indexed=True)
        # APIConnectionError takes a `request` kwarg — an httpx.Request instance.
        import httpx
        dummy_request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
        with patch(
            "brain.views_research.embeddings.generate_embedding",
            side_effect=APIConnectionError(request=dummy_request),
        ):
            resp = self.client.get("/api/brain/research/search/?q=q")
        self.assertEqual(resp.status_code, 502)

    def test_search_embedding_missing_key_returns_500(self) -> None:
        self._make_doc(slug="d", is_indexed=True)
        with patch(
            "brain.views_research.embeddings.generate_embedding",
            side_effect=RuntimeError("OPENAI_API_KEY is not configured"),
        ):
            resp = self.client.get("/api/brain/research/search/?q=q")
        self.assertEqual(resp.status_code, 500)

    def test_search_embedding_value_error_returns_400(self) -> None:
        self._make_doc(slug="d", is_indexed=True)
        with patch(
            "brain.views_research.embeddings.generate_embedding",
            side_effect=ValueError("bad query"),
        ):
            resp = self.client.get("/api/brain/research/search/?q=q")
        self.assertEqual(resp.status_code, 400)


class SearchSQLiteGuardTest(ResearchAPIBase):
    """Search endpoint should 503 cleanly on non-Postgres backends.

    Not decorated with @_PG_ONLY — this test *specifically* exercises the
    non-Postgres code path via a mock so we can run it anywhere.
    """

    def test_search_on_non_postgres_returns_503(self) -> None:
        self._make_doc(slug="d", is_indexed=True)
        mock_conn = type("FakeConn", (), {"vendor": "sqlite"})()
        with patch("brain.views_research.connection", mock_conn):
            resp = self.client.get("/api/brain/research/search/?q=hello")
        self.assertEqual(resp.status_code, 503)
        body = resp.json()
        self.assertFalse(body["success"])
        self.assertIn("pgvector", body["message"])


# ──────────────────────────────────────────────
# AUTH TESTS
# ──────────────────────────────────────────────


class ResearchAuthTest(TestCase):

    def setUp(self) -> None:
        cache.clear()

    def test_all_endpoints_require_auth(self) -> None:
        endpoints = [
            "/api/brain/research/search/?q=test",
            "/api/brain/research/documents/",
            "/api/brain/research/documents/x/",
            "/api/brain/research/topics/",
            "/api/brain/research/stats/",
        ]
        for url in endpoints:
            resp = self.client.get(url)
            self.assertEqual(
                resp.status_code, 401,
                f"GET {url} should return 401 without auth, got {resp.status_code}",
            )

    def test_api_key_auth_works(self) -> None:
        User.objects.create_user(username="staff", password=None, is_staff=True)
        with self.settings(NOCKCC_API_KEY="test-key-123"):
            resp = self.client.get(
                "/api/brain/research/topics/",
                HTTP_X_API_KEY="test-key-123",
            )
        self.assertEqual(resp.status_code, 200)
