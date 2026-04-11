"""Tests for the context app — models, views, sync, and management commands."""

import base64
import hashlib
import os
import secrets
from datetime import timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from context.github_sync import _content_hash, sync_document
from context.models import ContextDocument, ContextSnapshot
from pipeline.models import Repository

_TEST_FERNET_KEYS = [os.environ.get("TEST_FERNET_KEY", "")]
_TEST_WEBHOOK_SECRET = secrets.token_hex(16)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class ContextDocumentModelTests(TestCase):
    def setUp(self) -> None:
        self.repo = Repository.objects.create(
            name="project-nexus",
            owner="kkwills13",
            github_id=300001,
            webhook_secret=_TEST_WEBHOOK_SECRET,
        )

    def test_create_document(self) -> None:
        doc = ContextDocument.objects.create(
            repository=self.repo,
            doc_type="claude_md",
            file_path="CLAUDE.md",
            title="CLAUDE.md",
        )
        self.assertEqual(str(doc), "project-nexus/CLAUDE.md")
        self.assertFalse(doc.is_stale)
        self.assertTrue(doc.is_active)

    def test_unique_constraint(self) -> None:
        ContextDocument.objects.create(
            repository=self.repo,
            doc_type="claude_md",
            file_path="CLAUDE.md",
            title="CLAUDE.md",
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            ContextDocument.objects.create(
                repository=self.repo,
                doc_type="claude_md",
                file_path="CLAUDE.md",
                title="Duplicate",
            )

    def test_days_since_modified_none_when_never_modified(self) -> None:
        doc = ContextDocument.objects.create(
            repository=self.repo,
            doc_type="claude_md",
            file_path="CLAUDE.md",
            title="CLAUDE.md",
        )
        self.assertIsNone(doc.days_since_modified)

    def test_days_since_modified_fresh(self) -> None:
        doc = ContextDocument.objects.create(
            repository=self.repo,
            doc_type="claude_md",
            file_path="CLAUDE.md",
            title="CLAUDE.md",
            last_modified=timezone.now() - timedelta(days=2),
        )
        self.assertEqual(doc.days_since_modified, 2)

    def test_staleness_detection_fresh(self) -> None:
        doc = ContextDocument.objects.create(
            repository=self.repo,
            doc_type="claude_md",
            file_path="CLAUDE.md",
            title="CLAUDE.md",
            last_modified=timezone.now() - timedelta(days=3),
            staleness_threshold_days=7,
        )
        doc.update_staleness()
        self.assertFalse(doc.is_stale)

    def test_staleness_detection_stale(self) -> None:
        doc = ContextDocument.objects.create(
            repository=self.repo,
            doc_type="claude_md",
            file_path="CLAUDE.md",
            title="CLAUDE.md",
            last_modified=timezone.now() - timedelta(days=10),
            staleness_threshold_days=7,
        )
        doc.update_staleness()
        self.assertTrue(doc.is_stale)

    def test_staleness_warning_zone(self) -> None:
        """5 days old with 7 day threshold — not stale yet."""
        doc = ContextDocument.objects.create(
            repository=self.repo,
            doc_type="claude_md",
            file_path="CLAUDE.md",
            title="CLAUDE.md",
            last_modified=timezone.now() - timedelta(days=5),
            staleness_threshold_days=7,
        )
        doc.update_staleness()
        self.assertFalse(doc.is_stale)
        self.assertEqual(doc.days_since_modified, 5)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class ContextSnapshotTests(TestCase):
    def setUp(self) -> None:
        self.repo = Repository.objects.create(
            name="project-nexus",
            owner="kkwills13",
            github_id=300002,
            webhook_secret=_TEST_WEBHOOK_SECRET,
        )
        self.doc = ContextDocument.objects.create(
            repository=self.repo,
            doc_type="claude_md",
            file_path="CLAUDE.md",
            title="CLAUDE.md",
        )

    def test_snapshot_creation(self) -> None:
        snap = ContextSnapshot.objects.create(
            document=self.doc,
            content_hash="abc123",
            line_count=100,
            diff_summary="Initial snapshot",
        )
        self.assertEqual(str(snap), f"CLAUDE.md @ {snap.captured_at}")

    def test_snapshot_on_hash_change(self) -> None:
        """Simulates sync detecting a content change."""
        old_hash = _content_hash("old content")
        new_hash = _content_hash("new content")
        self.assertNotEqual(old_hash, new_hash)

        self.doc.last_content_hash = old_hash
        self.doc.save()

        ContextSnapshot.objects.create(
            document=self.doc,
            content_hash=new_hash,
            line_count=5,
            diff_summary="Changed from 3 to 5 lines",
        )
        self.assertEqual(self.doc.snapshots.count(), 1)

    def test_no_snapshot_on_unchanged(self) -> None:
        """If hash matches, no snapshot should be created."""
        content_hash = _content_hash("same content")
        self.doc.last_content_hash = content_hash
        self.doc.save()
        # Simulate sync — hash matches, no snapshot
        self.assertEqual(self.doc.snapshots.count(), 0)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, GITHUB_PAT="test-pat")
class GitHubSyncTests(TestCase):
    def setUp(self) -> None:
        self.repo = Repository.objects.create(
            name="project-nexus",
            owner="kkwills13",
            github_id=300003,
            webhook_secret=_TEST_WEBHOOK_SECRET,
        )
        self.doc = ContextDocument.objects.create(
            repository=self.repo,
            doc_type="claude_md",
            file_path="CLAUDE.md",
            title="CLAUDE.md",
            last_content_hash="",
        )

    @patch("context.github_sync.requests.get")
    def test_sync_changed_file(self, mock_get: MagicMock) -> None:
        content = "# CLAUDE.md\nLine 2\nLine 3\n"
        encoded = base64.b64encode(content.encode()).decode()
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "content": encoded,
            "sha": "abc123def456",
        }
        mock_get.return_value.raise_for_status = MagicMock()

        changed = sync_document(self.doc)
        self.assertTrue(changed)

        self.doc.refresh_from_db()
        self.assertEqual(self.doc.line_count, 3)
        self.assertIsNotNone(self.doc.last_synced)
        self.assertIsNotNone(self.doc.last_modified)
        expected_hash = hashlib.sha256(content.encode()).hexdigest()
        self.assertEqual(self.doc.last_content_hash, expected_hash)
        self.assertEqual(self.doc.snapshots.count(), 1)

    @patch("context.github_sync.requests.get")
    def test_sync_unchanged_file(self, mock_get: MagicMock) -> None:
        content = "# Same content\n"
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        self.doc.last_content_hash = content_hash
        self.doc.save()

        encoded = base64.b64encode(content.encode()).decode()
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"content": encoded, "sha": "abc"}
        mock_get.return_value.raise_for_status = MagicMock()

        changed = sync_document(self.doc)
        self.assertFalse(changed)
        self.assertEqual(self.doc.snapshots.count(), 0)

    @patch("context.github_sync.requests.get")
    def test_sync_404_file(self, mock_get: MagicMock) -> None:
        mock_get.return_value.status_code = 404

        changed = sync_document(self.doc)
        self.assertFalse(changed)

        self.doc.refresh_from_db()
        self.assertFalse(self.doc.is_active)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class ContextViewTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(self.user)
        self.repo = Repository.objects.create(
            name="project-nexus",
            owner="kkwills13",
            github_id=300004,
            webhook_secret=_TEST_WEBHOOK_SECRET,
        )

    def test_context_list_returns_200(self) -> None:
        resp = self.client.get("/context/")
        self.assertEqual(resp.status_code, 200)

    def test_context_list_shows_documents(self) -> None:
        ContextDocument.objects.create(
            repository=self.repo,
            doc_type="claude_md",
            file_path="CLAUDE.md",
            title="CLAUDE.md",
        )
        resp = self.client.get("/context/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "CLAUDE.md")

    def test_context_list_filter_by_repo(self) -> None:
        ContextDocument.objects.create(
            repository=self.repo,
            doc_type="claude_md",
            file_path="CLAUDE.md",
            title="CLAUDE.md",
        )
        resp = self.client.get("/context/?repo=project-nexus")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "CLAUDE.md")

    def test_context_detail_returns_200(self) -> None:
        doc = ContextDocument.objects.create(
            repository=self.repo,
            doc_type="claude_md",
            file_path="CLAUDE.md",
            title="CLAUDE.md",
        )
        resp = self.client.get(f"/context/{doc.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "CLAUDE.md")

    def test_context_detail_shows_snapshots(self) -> None:
        doc = ContextDocument.objects.create(
            repository=self.repo,
            doc_type="claude_md",
            file_path="CLAUDE.md",
            title="CLAUDE.md",
        )
        ContextSnapshot.objects.create(
            document=doc,
            content_hash="abc123",
            line_count=50,
            diff_summary="Changed from 0 to 50 lines",
        )
        resp = self.client.get(f"/context/{doc.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Changed from 0 to 50 lines")


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class ContextHealthAPITests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(self.user)
        self.repo = Repository.objects.create(
            name="project-nexus",
            owner="kkwills13",
            github_id=300005,
            webhook_secret=_TEST_WEBHOOK_SECRET,
        )

    def test_health_api_returns_expected_keys(self) -> None:
        resp = self.client.get("/context/api/health/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        data = body["data"]
        expected_keys = {"total_docs", "healthy_count", "stale_count", "stale_docs", "last_sync"}
        self.assertEqual(set(data.keys()), expected_keys)

    def test_health_api_correct_counts(self) -> None:
        ContextDocument.objects.create(
            repository=self.repo,
            doc_type="claude_md",
            file_path="CLAUDE.md",
            title="CLAUDE.md",
            is_stale=False,
            last_modified=timezone.now(),
        )
        ContextDocument.objects.create(
            repository=self.repo,
            doc_type="design_doc",
            file_path="DESIGN.md",
            title="Design",
            is_stale=True,
            last_modified=timezone.now() - timedelta(days=14),
        )
        resp = self.client.get("/context/api/health/")
        data = resp.json()["data"]
        self.assertEqual(data["total_docs"], 2)
        self.assertEqual(data["healthy_count"], 1)
        self.assertEqual(data["stale_count"], 1)
        self.assertEqual(len(data["stale_docs"]), 1)
        self.assertEqual(data["stale_docs"][0]["title"], "Design")


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class RegisterContextDocsCommandTests(TestCase):
    def setUp(self) -> None:
        Repository.objects.create(
            name="project-nexus",
            owner="kkwills13",
            github_id=300006,
            webhook_secret=_TEST_WEBHOOK_SECRET,
        )
        Repository.objects.create(
            name="nock-command-center",
            owner="kkwills13",
            github_id=300007,
            webhook_secret=_TEST_WEBHOOK_SECRET,
        )

    @patch("context.management.commands.register_context_docs._discover_skill_files", return_value=[])
    def test_register_creates_records(self, mock_discover: MagicMock) -> None:
        out = StringIO()
        call_command("register_context_docs", stdout=out)
        self.assertEqual(ContextDocument.objects.count(), 7)  # 5 nexus + 2 nockcc
        self.assertIn("Done", out.getvalue())

    @patch("context.management.commands.register_context_docs._discover_skill_files", return_value=[])
    def test_register_idempotent(self, mock_discover: MagicMock) -> None:
        call_command("register_context_docs", stdout=StringIO())
        call_command("register_context_docs", stdout=StringIO())
        self.assertEqual(ContextDocument.objects.count(), 7)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, GITHUB_PAT="test")
class SyncContextCommandTests(TestCase):
    def setUp(self) -> None:
        self.repo = Repository.objects.create(
            name="test-repo",
            owner="kkwills13",
            github_id=300008,
            webhook_secret=_TEST_WEBHOOK_SECRET,
        )

    @patch("context.github_sync.requests.get")
    def test_sync_command_triggers_sync(self, mock_get: MagicMock) -> None:
        ContextDocument.objects.create(
            repository=self.repo,
            doc_type="claude_md",
            file_path="CLAUDE.md",
            title="CLAUDE.md",
        )
        content = "# Test\n"
        encoded = base64.b64encode(content.encode()).decode()
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"content": encoded, "sha": "abc"}
        mock_get.return_value.raise_for_status = MagicMock()

        out = StringIO()
        call_command("sync_context", stdout=out)
        self.assertIn("Done", out.getvalue())
        self.assertEqual(ContextSnapshot.objects.count(), 1)
