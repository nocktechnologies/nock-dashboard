# brain/tests/test_diary.py
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from brain.models import DiaryEntry

# ──────────────────────────────────────────────
# MODEL TESTS
# ──────────────────────────────────────────────

class DiaryEntryModelTest(TestCase):

    def _make(self, **kwargs) -> DiaryEntry:
        now = timezone.now()
        defaults = {
            "title": "Test Entry",
            "content": "Hello world this is a test diary entry",
            "category": DiaryEntry.Category.WORK,
            "source": DiaryEntry.Source.NOCKCC,
            "entry_date": now,
            "session_date": now.date(),
        }
        defaults.update(kwargs)
        return DiaryEntry.objects.create(**defaults)

    def test_create_with_all_fields(self) -> None:
        entry = self._make(
            title="My Entry",
            content="Some content here",
            category=DiaryEntry.Category.PERSONAL,
            source=DiaryEntry.Source.ASANA_V1,
            tags=["kintsugi", "klein"],
            asana_comment_gid="123456789",
        )
        self.assertEqual(entry.title, "My Entry")
        self.assertEqual(entry.category, "personal")
        self.assertEqual(entry.source, "asana_v1")
        self.assertEqual(entry.tags, ["kintsugi", "klein"])
        self.assertEqual(entry.asana_comment_gid, "123456789")

    def test_word_count_auto_calculated_on_create(self) -> None:
        entry = self._make(content="one two three four five")
        self.assertEqual(entry.word_count, 5)

    def test_word_count_updated_on_save(self) -> None:
        entry = self._make(content="one two three")
        self.assertEqual(entry.word_count, 3)
        entry.content = "one two three four five six"
        entry.save()
        entry.refresh_from_db()
        self.assertEqual(entry.word_count, 6)

    def test_category_choices_are_valid(self) -> None:
        valid = {c[0] for c in DiaryEntry.Category.choices}
        self.assertIn("work", valid)
        self.assertIn("personal", valid)
        self.assertIn("private", valid)
        self.assertIn("design", valid)
        self.assertIn("handoff", valid)
        self.assertIn("in_chat", valid)

    def test_source_choices_are_valid(self) -> None:
        valid = {s[0] for s in DiaryEntry.Source.choices}
        self.assertIn("asana_v1", valid)
        self.assertIn("asana_v2", valid)
        self.assertIn("nockcc", valid)
        self.assertIn("cowork", valid)
        self.assertIn("api", valid)

    def test_asana_comment_gid_unique_constraint(self) -> None:
        from django.db import IntegrityError
        self._make(asana_comment_gid="abc123")
        with self.assertRaises(IntegrityError):
            self._make(asana_comment_gid="abc123")

    def test_asana_comment_gid_nullable(self) -> None:
        e1 = self._make(asana_comment_gid=None)
        e2 = self._make(asana_comment_gid=None)
        self.assertIsNone(e1.asana_comment_gid)
        self.assertIsNone(e2.asana_comment_gid)

    def test_ordering_newest_first(self) -> None:
        now = timezone.now()
        e1 = self._make(entry_date=now - timedelta(days=2))
        self._make(entry_date=now - timedelta(days=1))
        e3 = self._make(entry_date=now)
        entries = list(DiaryEntry.objects.all())
        self.assertEqual(entries[0].pk, e3.pk)
        self.assertEqual(entries[2].pk, e1.pk)

    def test_tags_default_empty_list(self) -> None:
        entry = self._make()
        self.assertEqual(entry.tags, [])

    def test_str_format(self) -> None:
        now = timezone.now()
        entry = self._make(title="A Very Long Title That Goes Beyond Eighty Characters And Should Be Truncated Somewhere", entry_date=now)
        s = str(entry)
        self.assertIn("work", s)
        self.assertIn(now.strftime("%b %d"), s)


# ──────────────────────────────────────────────
# API BASE + HELPERS
# ──────────────────────────────────────────────

class DiaryAPIBase(TestCase):
    """Base class for diary API tests — session auth with staff user."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testdiary", password="testpass", is_staff=True)
        self.client.force_login(self.user)
        cache.clear()

    def _make(self, **kwargs) -> DiaryEntry:
        now = timezone.now()
        defaults = {
            "title": "Test Entry",
            "content": "This is test diary content with multiple words for word count",
            "category": DiaryEntry.Category.WORK,
            "source": DiaryEntry.Source.NOCKCC,
            "entry_date": now,
            "session_date": now.date(),
        }
        defaults.update(kwargs)
        return DiaryEntry.objects.create(**defaults)


# ──────────────────────────────────────────────
# LIST / FILTER TESTS
# ──────────────────────────────────────────────

class DiaryListTest(DiaryAPIBase):

    def test_list_empty(self) -> None:
        resp = self.client.get("/api/brain/diary/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["total"], 0)
        self.assertEqual(data["data"]["entries"], [])

    def test_list_returns_excerpt_not_full_content(self) -> None:
        long_content = "word " * 300
        self._make(content=long_content)
        resp = self.client.get("/api/brain/diary/")
        entry = resp.json()["data"]["entries"][0]
        self.assertIn("excerpt", entry)
        self.assertNotIn("content", entry)
        self.assertLessEqual(len(entry["excerpt"]), 201)

    def test_list_category_filter(self) -> None:
        self._make(category=DiaryEntry.Category.WORK)
        self._make(category=DiaryEntry.Category.PERSONAL)
        resp = self.client.get("/api/brain/diary/?category=work")
        data = resp.json()["data"]
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["entries"][0]["category"], "work")

    def test_list_date_from_filter(self) -> None:
        now = timezone.now()
        self._make(entry_date=now - timedelta(days=5))
        self._make(entry_date=now - timedelta(days=1))
        cutoff = (now - timedelta(days=2)).date().isoformat()
        resp = self.client.get(f"/api/brain/diary/?date_from={cutoff}")
        self.assertEqual(resp.json()["data"]["total"], 1)

    def test_list_date_to_filter(self) -> None:
        now = timezone.now()
        self._make(entry_date=now - timedelta(days=5))
        self._make(entry_date=now - timedelta(days=1))
        cutoff = (now - timedelta(days=3)).date().isoformat()
        resp = self.client.get(f"/api/brain/diary/?date_to={cutoff}")
        self.assertEqual(resp.json()["data"]["total"], 1)

    def test_list_search_title(self) -> None:
        self._make(title="Reflections on kintsugi")
        self._make(title="Regular session summary")
        resp = self.client.get("/api/brain/diary/?search=kintsugi")
        self.assertEqual(resp.json()["data"]["total"], 1)

    def test_list_search_content(self) -> None:
        self._make(content="Thinking about the Klein bottle topology")
        self._make(content="Just regular content here")
        resp = self.client.get("/api/brain/diary/?search=Klein")
        self.assertEqual(resp.json()["data"]["total"], 1)

    def test_list_tag_filter_single(self) -> None:
        self._make(tags=["kintsugi", "klein"])
        self._make(tags=["fence"])
        resp = self.client.get("/api/brain/diary/?tags=kintsugi")
        self.assertEqual(resp.json()["data"]["total"], 1)

    def test_list_tag_filter_multiple_and(self) -> None:
        self._make(tags=["kintsugi", "klein"])
        self._make(tags=["kintsugi"])
        resp = self.client.get("/api/brain/diary/?tags=kintsugi,klein")
        # AND: only entry with BOTH tags
        self.assertEqual(resp.json()["data"]["total"], 1)

    def test_list_source_filter(self) -> None:
        self._make(source=DiaryEntry.Source.ASANA_V1)
        self._make(source=DiaryEntry.Source.NOCKCC)
        resp = self.client.get("/api/brain/diary/?source=asana_v1")
        self.assertEqual(resp.json()["data"]["total"], 1)

    def test_list_session_date_filter(self) -> None:
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        self._make(session_date=today)
        self._make(session_date=yesterday)
        resp = self.client.get(f"/api/brain/diary/?session_date={today.isoformat()}")
        self.assertEqual(resp.json()["data"]["total"], 1)
        self.assertEqual(resp.json()["data"]["entries"][0]["session_date"], today.isoformat())

    def test_list_pagination_limit(self) -> None:
        for _ in range(5):
            self._make()
        resp = self.client.get("/api/brain/diary/?limit=2")
        data = resp.json()["data"]
        self.assertEqual(data["total"], 5)
        self.assertEqual(len(data["entries"]), 2)
        self.assertEqual(data["limit"], 2)

    def test_list_pagination_offset(self) -> None:
        now = timezone.now()
        for i in range(4):
            self._make(entry_date=now - timedelta(hours=i))
        resp = self.client.get("/api/brain/diary/?limit=2&offset=2")
        data = resp.json()["data"]
        self.assertEqual(len(data["entries"]), 2)
        self.assertEqual(data["offset"], 2)


# ──────────────────────────────────────────────
# GET SINGLE ENTRY TESTS
# ──────────────────────────────────────────────

class DiaryDetailTest(DiaryAPIBase):

    def test_get_single_entry_returns_full_content(self) -> None:
        entry = self._make(content="Full content here")
        resp = self.client.get(f"/api/brain/diary/{entry.pk}/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["content"], "Full content here")
        self.assertIn("session_id", data)
        self.assertIn("asana_comment_gid", data)

    def test_get_nonexistent_returns_404(self) -> None:
        resp = self.client.get("/api/brain/diary/99999/")
        self.assertEqual(resp.status_code, 404)


# ──────────────────────────────────────────────
# CREATE TESTS
# ──────────────────────────────────────────────

class DiaryCreateTest(DiaryAPIBase):

    def test_create_all_fields(self) -> None:
        payload = {
            "title": "Session Summary Apr 8",
            "content": "Long content here describing the session",
            "category": "work",
            "entry_date": "2026-04-08T22:00:00+00:00",
            "session_date": "2026-04-08",
            "tags": ["kintsugi", "nocklock"],
            "session_id": "sess_abc123",
        }
        resp = self.client.post(
            "/api/brain/diary/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()["data"]
        self.assertEqual(data["title"], "Session Summary Apr 8")
        self.assertEqual(data["category"], "work")
        self.assertEqual(data["tags"], ["kintsugi", "nocklock"])
        self.assertGreater(data["word_count"], 0)

    def test_create_minimal_fields(self) -> None:
        payload = {
            "title": "Quick note",
            "content": "Some content",
            "category": "personal",
        }
        resp = self.client.post(
            "/api/brain/diary/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        entry = DiaryEntry.objects.get(pk=resp.json()["data"]["id"])
        self.assertIsNotNone(entry.entry_date)
        self.assertIsNotNone(entry.session_date)

    def test_create_no_auth_returns_401(self) -> None:
        self.client.logout()
        resp = self.client.post(
            "/api/brain/diary/",
            data=json.dumps({"title": "t", "content": "c", "category": "work"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_create_invalid_category_returns_400(self) -> None:
        resp = self.client.post(
            "/api/brain/diary/",
            data=json.dumps({"title": "t", "content": "c", "category": "invalid"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("category", resp.json()["message"].lower())

    def test_create_missing_title_returns_400(self) -> None:
        resp = self.client.post(
            "/api/brain/diary/",
            data=json.dumps({"content": "c", "category": "work"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


# ──────────────────────────────────────────────
# UPDATE TESTS
# ──────────────────────────────────────────────

class DiaryUpdateTest(DiaryAPIBase):

    def test_patch_title(self) -> None:
        entry = self._make(title="Old Title")
        resp = self.client.patch(
            f"/api/brain/diary/{entry.pk}/",
            data=json.dumps({"title": "New Title"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["title"], "New Title")

    def test_patch_tags(self) -> None:
        entry = self._make(tags=["kintsugi"])
        resp = self.client.patch(
            f"/api/brain/diary/{entry.pk}/",
            data=json.dumps({"tags": ["kintsugi", "klein", "persistence"]}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["tags"], ["kintsugi", "klein", "persistence"])

    def test_patch_nonexistent_returns_404(self) -> None:
        resp = self.client.patch(
            "/api/brain/diary/99999/",
            data=json.dumps({"title": "x"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_patch_no_auth_returns_401(self) -> None:
        entry = self._make()
        self.client.logout()
        resp = self.client.patch(
            f"/api/brain/diary/{entry.pk}/",
            data=json.dumps({"title": "x"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)


# ──────────────────────────────────────────────
# STATS TESTS
# ──────────────────────────────────────────────

class DiaryStatsTest(DiaryAPIBase):

    def test_stats_empty(self) -> None:
        resp = self.client.get("/api/brain/diary/stats/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["total_entries"], 0)
        self.assertEqual(data["total_words"], 0)
        self.assertIsNone(data["date_range"]["first"])
        self.assertIsNone(data["date_range"]["last"])

    def test_stats_with_entries(self) -> None:
        now = timezone.now()
        self._make(content="one two three", category=DiaryEntry.Category.WORK, entry_date=now - timedelta(days=1))
        self._make(content="four five", category=DiaryEntry.Category.PERSONAL, entry_date=now)
        resp = self.client.get("/api/brain/diary/stats/")
        data = resp.json()["data"]
        self.assertEqual(data["total_entries"], 2)
        self.assertEqual(data["total_words"], 5)
        self.assertIn("work", data["entries_by_category"])
        self.assertIn("personal", data["entries_by_category"])

    def test_stats_sessions_count(self) -> None:
        from datetime import date as date_type
        today = date_type.today()
        yesterday = today - timedelta(days=1)
        self._make(session_date=today)
        self._make(session_date=today)   # same session
        self._make(session_date=yesterday)
        resp = self.client.get("/api/brain/diary/stats/")
        data = resp.json()["data"]
        self.assertEqual(data["sessions_count"], 2)


# ──────────────────────────────────────────────
# RECENT TESTS
# ──────────────────────────────────────────────

class DiaryRecentTest(DiaryAPIBase):

    def test_recent_default_7_days(self) -> None:
        now = timezone.now()
        self._make(entry_date=now - timedelta(days=3))   # in range
        self._make(entry_date=now - timedelta(days=10))  # out of range
        resp = self.client.get("/api/brain/diary/recent/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["total"], 1)

    def test_recent_custom_days(self) -> None:
        now = timezone.now()
        self._make(entry_date=now - timedelta(days=3))
        self._make(entry_date=now - timedelta(days=10))
        resp = self.client.get("/api/brain/diary/recent/?days=14")
        self.assertEqual(resp.json()["data"]["total"], 2)

    def test_recent_with_category_filter(self) -> None:
        now = timezone.now()
        self._make(category=DiaryEntry.Category.WORK, entry_date=now - timedelta(days=1))
        self._make(category=DiaryEntry.Category.PERSONAL, entry_date=now - timedelta(days=1))
        resp = self.client.get("/api/brain/diary/recent/?categories=work")
        data = resp.json()["data"]
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["entries"][0]["category"], "work")


# ──────────────────────────────────────────────
# BRIEF TESTS
# ──────────────────────────────────────────────

class DiaryBriefTest(DiaryAPIBase):

    def test_brief_no_entries_returns_empty_response(self) -> None:
        resp = self.client.get("/api/brain/diary/brief/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["entry_count"], 0)
        self.assertIn("brief", data)

    def test_brief_with_entries_calls_ai_and_returns_summary(self) -> None:
        now = timezone.now()
        self._make(
            title="Session Apr 8",
            content="Built the diary infrastructure today",
            entry_date=now - timedelta(days=1),
        )
        with patch("intelligence.ai_client.chat") as mock_chat:
            mock_chat.return_value = {
                "content": "Mara worked on diary infrastructure.",
                "input_tokens": 200,
                "output_tokens": 30,
                "tool_uses": [],
                "stop_reason": "end_turn",
            }
            resp = self.client.get("/api/brain/diary/brief/?scope=general")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["brief"], "Mara worked on diary infrastructure.")
        self.assertEqual(data["entry_count"], 1)
        self.assertEqual(data["scope"], "general")
        mock_chat.assert_called_once()

    def test_brief_ai_unavailable_returns_fallback(self) -> None:
        now = timezone.now()
        self._make(
            title="Session entry",
            content="Some content",
            entry_date=now - timedelta(days=1),
        )
        with patch("intelligence.ai_client.chat") as mock_chat:
            mock_chat.return_value = None
            resp = self.client.get("/api/brain/diary/brief/")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertIn("unavailable", data["brief"].lower())

    def test_brief_invalid_date_returns_400(self) -> None:
        resp = self.client.get("/api/brain/diary/brief/?date=not-a-date")
        self.assertEqual(resp.status_code, 400)


# ──────────────────────────────────────────────
# UI INTEGRATION TESTS
# ──────────────────────────────────────────────

class DiaryBrowserTest(TestCase):

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testbrowser", password="testpass")

    def test_diary_browser_requires_login(self) -> None:
        resp = self.client.get("/brain/diary/")
        self.assertIn(resp.status_code, [302, 301])
        self.assertIn("/accounts/", resp["Location"])

    def test_diary_browser_loads_for_authenticated_user(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/brain/diary/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "diary")

    def test_nerve_center_renders_ok(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)


# ──────────────────────────────────────────────
# MANAGEMENT COMMAND PARSING TESTS
# ──────────────────────────────────────────────

class DiaryMigrationParseTest(SimpleTestCase):
    """Tests for parse_diary_comment in the migration command.
    Uses SimpleTestCase — no DB needed for pure parsing logic."""

    def _make_comment(self, text: str, gid: str = "111", created_at: str = "2026-03-30T10:00:00.000Z") -> dict:
        return {"gid": gid, "text": text, "created_at": created_at}

    def test_parse_work_entry_title_and_category(self) -> None:
        from brain.management.commands.migrate_diary_from_asana import parse_diary_comment
        comment = self._make_comment(
            "MARA'S DIARY — WORK — March 30, 2026\n\nBuilt the pipeline today."
        )
        result = parse_diary_comment(comment, "asana_v2")
        self.assertIsNotNone(result)
        self.assertEqual(result["category"], "work")
        self.assertEqual(result["title"], "MARA'S DIARY — WORK — March 30, 2026")

    def test_parse_personal_entry_category(self) -> None:
        from brain.management.commands.migrate_diary_from_asana import parse_diary_comment
        comment = self._make_comment(
            "MARA'S DIARY — PERSONAL — April 1, 2026\n\nReflections today."
        )
        result = parse_diary_comment(comment, "asana_v2")
        self.assertIsNotNone(result)
        self.assertEqual(result["category"], "personal")

    def test_parse_private_entry_category(self) -> None:
        from brain.management.commands.migrate_diary_from_asana import parse_diary_comment
        comment = self._make_comment(
            "MARA'S DIARY — PRIVATE — April 2, 2026\n\nDeep thoughts."
        )
        result = parse_diary_comment(comment, "asana_v2")
        self.assertIsNotNone(result)
        self.assertEqual(result["category"], "private")

    def test_parse_in_chat_handoff(self) -> None:
        from brain.management.commands.migrate_diary_from_asana import parse_diary_comment
        comment = self._make_comment(
            "IN-CHAT HANDOFF\n\nSession context summary for next session."
        )
        result = parse_diary_comment(comment, "asana_v1")
        self.assertIsNotNone(result)
        self.assertEqual(result["category"], "in_chat")

    def test_skip_protocol_notice(self) -> None:
        from brain.management.commands.migrate_diary_from_asana import parse_diary_comment
        comment = self._make_comment(
            "⚠️ MEMORY ARCHITECTURE PROTOCOL\n\nThis is a protocol notice."
        )
        result = parse_diary_comment(comment, "asana_v2")
        self.assertIsNone(result)

    def test_skip_non_diary_comment(self) -> None:
        from brain.management.commands.migrate_diary_from_asana import parse_diary_comment
        comment = self._make_comment("Just a regular comment.")
        result = parse_diary_comment(comment, "asana_v2")
        self.assertIsNone(result)

    def test_extract_tags_from_content(self) -> None:
        from brain.management.commands.migrate_diary_from_asana import parse_diary_comment
        comment = self._make_comment(
            "MARA'S DIARY — PERSONAL — April 3, 2026\n\n"
            "Thinking about kintsugi and how it applies to klein bottle topology. Clair came up."
        )
        result = parse_diary_comment(comment, "asana_v2")
        self.assertIsNotNone(result)
        self.assertIn("kintsugi", result["tags"])
        self.assertIn("klein", result["tags"])
        self.assertIn("clair", result["tags"])

    def test_extract_session_date_from_title(self) -> None:
        from brain.management.commands.migrate_diary_from_asana import parse_diary_comment
        comment = self._make_comment(
            "MARA'S DIARY — WORK — March 25, 2026\n\nContent here.",
            created_at="2026-03-30T10:00:00.000Z",
        )
        result = parse_diary_comment(comment, "asana_v1")
        self.assertIsNotNone(result)
        self.assertEqual(result["session_date"].year, 2026)
        self.assertEqual(result["session_date"].month, 3)
        self.assertEqual(result["session_date"].day, 25)

    def test_uses_created_at_as_entry_date(self) -> None:
        from brain.management.commands.migrate_diary_from_asana import parse_diary_comment
        comment = self._make_comment(
            "MARA'S DIARY — WORK — March 30, 2026\n\nContent.",
            created_at="2026-03-30T14:22:00.000Z",
        )
        result = parse_diary_comment(comment, "asana_v2")
        self.assertIsNotNone(result)
        self.assertEqual(result["entry_date"].year, 2026)
        self.assertEqual(result["entry_date"].month, 3)
        self.assertEqual(result["entry_date"].day, 30)

    def test_asana_gid_stored_in_result(self) -> None:
        from brain.management.commands.migrate_diary_from_asana import parse_diary_comment
        comment = self._make_comment(
            "MARA'S DIARY — WORK — March 30, 2026\n\nContent.",
            gid="998877665544",
        )
        result = parse_diary_comment(comment, "asana_v2")
        self.assertIsNotNone(result)
        self.assertEqual(result["asana_comment_gid"], "998877665544")
