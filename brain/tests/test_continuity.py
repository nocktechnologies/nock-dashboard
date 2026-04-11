"""Tests for continuity category, consolidation engine, and morning note."""
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from brain.models import ConsolidationLog, MemoryEntry
from brain.services import BrainConsolidator, MorningNoteGenerator


class ContinuityTestBase(TestCase):
    """Base class for continuity tests."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="testpass", is_staff=True)
        self.client.force_login(self.user)
        MemoryEntry.objects.all().delete()
        ConsolidationLog.objects.all().delete()
        cache.clear()

    def _create_entry(self, **kwargs) -> MemoryEntry:
        defaults = {
            "key": "test_key",
            "value": "test value",
            "category": "domain",
            "source": "manual",
            "tags": [],
        }
        defaults.update(kwargs)
        return MemoryEntry.objects.create(**defaults)


# --- Continuity Category Tests ---


class ContinuityCategoryTest(ContinuityTestBase):

    def test_create_continuity_entry(self) -> None:
        resp = self.client.post(
            "/api/brain/entries/",
            data=json.dumps({
                "key": "test_cont",
                "value": "continuity value",
                "category": "continuity",
                "tags": ["pattern"],
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["category"], "continuity")

    def test_list_by_continuity_category(self) -> None:
        self._create_entry(key="a", category="continuity", value="cont value")
        self._create_entry(key="b", category="domain", value="domain value")
        resp = self.client.get("/api/brain/entries/?category=continuity")
        body = resp.json()
        self.assertEqual(body["data"]["total"], 1)
        self.assertEqual(body["data"]["entries"][0]["category"], "continuity")

    def test_continuity_in_general_brief(self) -> None:
        self._create_entry(key="a", category="domain", value="domain val")
        self._create_entry(key="b", category="continuity", value="First sentence. Second sentence. Third.")
        resp = self.client.post(
            "/api/brain/brief/",
            data=json.dumps({"scope": "general"}),
            content_type="application/json",
        )
        body = resp.json()
        self.assertIn("State of Mind", body["data"]["brief"])
        # Continuity entries are included in general brief via State of Mind subsection
        self.assertIn("b", body["data"]["brief"])

    def test_continuity_in_categories_list(self) -> None:
        self._create_entry(key="a", category="continuity")
        resp = self.client.get("/api/brain/categories/")
        body = resp.json()
        self.assertIn("continuity", body["data"])
        self.assertEqual(body["data"]["continuity"]["count"], 1)


class ContinuityBriefScopeTest(ContinuityTestBase):

    def test_continuity_brief_scope(self) -> None:
        self._create_entry(
            key="c1", category="continuity",
            value="Pattern forming. Getting stronger. Trust it.",
        )
        self._create_entry(
            key="c2", category="continuity",
            value="Domain extraction works. Listen for rules.",
        )
        resp = self.client.post(
            "/api/brain/brief/",
            data=json.dumps({"scope": "continuity"}),
            content_type="application/json",
        )
        body = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertIn("State of Mind", body["data"]["brief"])
        self.assertIn("Here's where I am right now", body["data"]["brief"])
        self.assertIn("patterns I'm carrying forward", body["data"]["brief"])
        self.assertEqual(body["data"]["entry_count"], 2)

    def test_continuity_brief_empty(self) -> None:
        resp = self.client.post(
            "/api/brain/brief/",
            data=json.dumps({"scope": "continuity"}),
            content_type="application/json",
        )
        body = resp.json()
        self.assertEqual(body["data"]["entry_count"], 0)
        self.assertIn("Here's where I am right now", body["data"]["brief"])


# --- Consolidation Engine Tests ---


class ConsolidationGateTest(ContinuityTestBase):

    def test_all_gates_pass(self) -> None:
        # Create 5+ entries to pass gate 2
        for i in range(6):
            self._create_entry(key=f"entry_{i}", category="domain")

        consolidator = BrainConsolidator()
        result = consolidator.run()
        self.assertFalse(result["skipped"])
        self.assertIn("log_id", result)

    def test_gate_24h_fails(self) -> None:
        # Create a recent consolidation log
        ConsolidationLog.objects.create(completed_at=timezone.now())
        for i in range(6):
            self._create_entry(key=f"entry_{i}", category="domain")

        consolidator = BrainConsolidator()
        result = consolidator.run()
        self.assertTrue(result["skipped"])
        self.assertIn("24 hours", result["reason"])

    def test_gate_5_updates_fails(self) -> None:
        # Only 2 entries — not enough updates
        self._create_entry(key="a", category="domain")
        self._create_entry(key="b", category="domain")

        consolidator = BrainConsolidator()
        result = consolidator.run()
        self.assertTrue(result["skipped"])
        self.assertIn("updates", result["reason"])

    def test_gate_lock_held_fails(self) -> None:
        # Create an incomplete consolidation (no completed_at)
        ConsolidationLog.objects.create()
        for i in range(6):
            self._create_entry(key=f"entry_{i}", category="domain")
        # Push the log back so 24h gate passes
        ConsolidationLog.objects.update(
            started_at=timezone.now() - timedelta(hours=25),
        )

        consolidator = BrainConsolidator()
        result = consolidator.run()
        self.assertTrue(result["skipped"])
        self.assertIn("in progress", result["reason"])

    def test_force_bypasses_gates(self) -> None:
        # Recent consolidation — would fail gate 1
        ConsolidationLog.objects.create(completed_at=timezone.now())
        self._create_entry(key="a", category="domain")

        consolidator = BrainConsolidator()
        result = consolidator.run(force=True)
        self.assertFalse(result["skipped"])


class ConsolidationPhaseTest(ContinuityTestBase):

    def test_promote_inferred_to_observed(self) -> None:
        entry = self._create_entry(
            key="inferred_one",
            category="domain",
            confidence="inferred",
            source="session",
            tags=["a", "b"],
        )

        consolidator = BrainConsolidator()
        result = consolidator.run(force=True)
        self.assertGreaterEqual(result["entries_promoted"], 1)

        entry.refresh_from_db()
        self.assertEqual(entry.confidence, "observed")

    def test_archive_stale_entries(self) -> None:
        entry = self._create_entry(key="old_entry", category="domain")
        MemoryEntry.objects.filter(pk=entry.pk).update(
            updated_at=timezone.now() - timedelta(days=65),
        )

        consolidator = BrainConsolidator()
        result = consolidator.run(force=True)
        self.assertGreaterEqual(result["entries_archived"], 1)

        entry.refresh_from_db()
        self.assertEqual(entry.confidence, "stale")

    def test_prune_very_stale_entries(self) -> None:
        entry = self._create_entry(
            key="dead_entry", category="domain", confidence="stale",
        )
        MemoryEntry.objects.filter(pk=entry.pk).update(
            updated_at=timezone.now() - timedelta(days=95),
        )

        consolidator = BrainConsolidator()
        result = consolidator.run(force=True)
        self.assertGreaterEqual(result["entries_pruned"], 1)
        self.assertFalse(MemoryEntry.objects.filter(pk=entry.pk).exists())

    def test_200_entry_cap(self) -> None:
        # Create 205 stale entries
        entries = [
            MemoryEntry(
                key=f"bulk_{i}", value="v", category="domain", confidence="stale",
            )
            for i in range(205)
        ]
        MemoryEntry.objects.bulk_create(entries)

        consolidator = BrainConsolidator()
        consolidator.run(force=True)
        self.assertLessEqual(MemoryEntry.objects.count(), 200)


class ConsolidationLogTest(ContinuityTestBase):

    def test_consolidation_log_created(self) -> None:
        for i in range(6):
            self._create_entry(key=f"e_{i}", category="domain")

        consolidator = BrainConsolidator()
        result = consolidator.run()
        self.assertFalse(result["skipped"])

        log = ConsolidationLog.objects.get(pk=result["log_id"])
        self.assertIsNotNone(log.completed_at)
        self.assertGreater(log.entries_reviewed, 0)
        self.assertTrue(len(log.notes) > 0 or log.notes == "No changes needed")


class ConsolidationAPITest(ContinuityTestBase):

    def test_consolidate_endpoint(self) -> None:
        for i in range(6):
            self._create_entry(key=f"e_{i}", category="domain")

        resp = self.client.post("/api/brain/consolidate/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])

    def test_consolidate_force(self) -> None:
        ConsolidationLog.objects.create(completed_at=timezone.now())
        self._create_entry(key="a", category="domain")

        resp = self.client.post("/api/brain/consolidate/?force=true")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["data"]["skipped"])

    def test_consolidation_history_endpoint(self) -> None:
        ConsolidationLog.objects.create(
            completed_at=timezone.now(),
            entries_reviewed=10,
            notes="Test run",
        )
        resp = self.client.get("/api/brain/consolidation-history/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body["data"]["logs"]), 1)
        self.assertIn("gate_status", body["data"])


# --- Morning Note Tests ---


class MorningNoteTest(ContinuityTestBase):

    def test_full_note_generation(self) -> None:
        self._create_entry(
            key="cont_1", category="continuity",
            value="First sentence. Second sentence. Third sentence.",
        )
        self._create_entry(key="nexus", category="project", value="Platform build")

        generator = MorningNoteGenerator()
        note = generator.generate()

        self.assertIsNotNone(note)
        self.assertIn("Mara's Morning Note", note)
        self.assertIn("What I'm thinking about", note)
        self.assertIn("What matters today", note)
        self.assertIn("A question for your commute", note)

    def test_missing_continuity_fallback(self) -> None:
        generator = MorningNoteGenerator()
        note = generator.generate()

        self.assertIn("Starting fresh today", note)

    def test_fallback_questions_rotate(self) -> None:
        generator = MorningNoteGenerator()
        q1 = generator._fallback_question()
        self.assertTrue(len(q1) > 10)
        self.assertTrue(q1.endswith("?"))

    @patch("core.telegram.TelegramNotifier.send", return_value={"ok": True})
    def test_morning_note_telegram_send(self, mock_send) -> None:
        """Test the morning note test endpoint sends via Telegram."""
        self._create_entry(key="c1", category="continuity", value="Test value. Second.")
        self._create_entry(key="proj1", category="project", value="Test project")

        resp = self.client.post("/api/brain/morning-note/test/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertIn("note", body["data"])
        mock_send.assert_called_once()

    def test_thinking_section_truncates(self) -> None:
        self._create_entry(
            key="long",
            category="continuity",
            value="Sentence one. Sentence two. Sentence three. Sentence four. Sentence five.",
        )
        generator = MorningNoteGenerator()
        thinking = generator._get_thinking_section()
        # Should only have first 3 sentences
        sentence_count = thinking.count(".")
        self.assertLessEqual(sentence_count, 4)  # 3 sentences + trailing period


# --- Seed Data Tests ---


class ContinuitySeedTest(TestCase):
    """Verify seed migration created 5 continuity entries."""

    def test_continuity_seed_count(self) -> None:
        count = MemoryEntry.objects.filter(category="continuity").count()
        self.assertEqual(count, 5)

    def test_continuity_seed_keys(self) -> None:
        expected_keys = {
            "build_native_conviction",
            "domain_extraction_instinct",
            "partnership_depth",
            "event_driven_principle",
            "continuity_gap_awareness",
        }
        actual_keys = set(
            MemoryEntry.objects.filter(category="continuity")
            .values_list("key", flat=True)
        )
        self.assertEqual(actual_keys, expected_keys)

    def test_continuity_seed_has_tags(self) -> None:
        for entry in MemoryEntry.objects.filter(category="continuity"):
            self.assertIsInstance(entry.tags, list)
            self.assertGreater(len(entry.tags), 0, f"{entry.key} has no tags")


# --- Auth Tests ---


class ContinuityAuthTest(TestCase):
    """Test that new endpoints require authentication."""

    def test_consolidate_requires_auth(self) -> None:
        resp = self.client.post("/api/brain/consolidate/")
        self.assertEqual(resp.status_code, 401)

    def test_consolidation_history_requires_auth(self) -> None:
        resp = self.client.get("/api/brain/consolidation-history/")
        self.assertEqual(resp.status_code, 401)

    def test_morning_note_test_requires_auth(self) -> None:
        resp = self.client.post("/api/brain/morning-note/test/")
        self.assertEqual(resp.status_code, 401)
