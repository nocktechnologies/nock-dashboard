# brain/tests/test_handoffs.py
import json

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from brain.models import HandoffEntry, HandoffVersion

# ──────────────────────────────────────────────
# MODEL TESTS
# ──────────────────────────────────────────────


class HandoffEntryModelTest(TestCase):

    def _make(self, **kwargs) -> HandoffEntry:
        defaults = {
            "context": HandoffEntry.Context.CORTEXTOS_AGENT,
            "title": "Test Handoff",
            "content": "Narrative goes here",
            "action_items": [],
            "updated_by": "test",
        }
        defaults.update(kwargs)
        return HandoffEntry.objects.create(**defaults)

    def test_create_handoff(self) -> None:
        h = self._make()
        self.assertEqual(h.title, "Test Handoff")
        self.assertEqual(h.version, 1)
        self.assertFalse(h.previous_items_resolved)
        self.assertEqual(h.context, "cortextos-agent")

    def test_context_unique(self) -> None:
        from django.db import IntegrityError

        self._make(context=HandoffEntry.Context.KIT_SESSION)
        with self.assertRaises(IntegrityError):
            self._make(context=HandoffEntry.Context.KIT_SESSION)

    def test_action_item_counts(self) -> None:
        h = self._make(action_items=[
            {"description": "ship X", "status": "completed", "reason": None},
            {"description": "polish Y", "status": "open", "reason": None},
            {"description": "fix Z", "status": "open", "reason": None},
            {"description": "deferred bug", "status": "deferred", "reason": "needs Kevin"},
        ])
        self.assertEqual(h.open_items_count, 2)
        self.assertEqual(h.completed_items_count, 1)
        self.assertEqual(h.deferred_items_count, 1)

    def test_str_format(self) -> None:
        h = self._make(title="April 10 evening")
        self.assertIn("cortextos-agent", str(h))
        self.assertIn("v1", str(h))


class HandoffVersionModelTest(TestCase):

    def _make_handoff(self, **kwargs) -> HandoffEntry:
        defaults = {
            "context": HandoffEntry.Context.CORTEXTOS_AGENT,
            "title": "Test",
            "content": "Original",
            "action_items": [],
            "updated_by": "test",
        }
        defaults.update(kwargs)
        return HandoffEntry.objects.create(**defaults)

    def test_create_version(self) -> None:
        h = self._make_handoff()
        v = HandoffVersion.objects.create(
            handoff=h,
            version=1,
            title=h.title,
            content=h.content,
            action_items=h.action_items,
            updated_by=h.updated_by,
        )
        self.assertEqual(v.version, 1)
        self.assertEqual(v.content, "Original")

    def test_version_unique_together(self) -> None:
        from django.db import IntegrityError

        h = self._make_handoff()
        HandoffVersion.objects.create(
            handoff=h, version=1, title="t", content="c", updated_by="x",
        )
        with self.assertRaises(IntegrityError):
            HandoffVersion.objects.create(
                handoff=h, version=1, title="dup", content="c2", updated_by="x",
            )

    def test_versions_ordered_newest_first(self) -> None:
        h = self._make_handoff()
        v1 = HandoffVersion.objects.create(
            handoff=h, version=1, title="v1", content="c1", updated_by="x",
        )
        v2 = HandoffVersion.objects.create(
            handoff=h, version=2, title="v2", content="c2", updated_by="x",
        )
        versions = list(h.versions.all())
        self.assertEqual(versions[0].pk, v2.pk)
        self.assertEqual(versions[1].pk, v1.pk)

    def test_cascade_delete(self) -> None:
        h = self._make_handoff()
        HandoffVersion.objects.create(
            handoff=h, version=1, title="v1", content="c1", updated_by="x",
        )
        h.delete()
        self.assertEqual(HandoffVersion.objects.count(), 0)


# ──────────────────────────────────────────────
# API BASE
# ──────────────────────────────────────────────


class HandoffAPIBase(TestCase):

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="testhandoff", password="testpass", is_staff=True,
        )
        self.client.force_login(self.user)
        cache.clear()

    def _make(self, **kwargs) -> HandoffEntry:
        defaults = {
            "context": HandoffEntry.Context.CORTEXTOS_AGENT,
            "title": "Test Handoff",
            "content": "Narrative",
            "action_items": [],
            "updated_by": "test",
        }
        defaults.update(kwargs)
        return HandoffEntry.objects.create(**defaults)


# ──────────────────────────────────────────────
# LIST TESTS
# ──────────────────────────────────────────────


class HandoffListTest(HandoffAPIBase):

    def test_list_empty(self) -> None:
        resp = self.client.get("/api/brain/handoffs/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["total"], 0)
        self.assertEqual(data["data"]["handoffs"], [])

    def test_list_returns_one_per_context(self) -> None:
        self._make(context=HandoffEntry.Context.CORTEXTOS_AGENT)
        self._make(context=HandoffEntry.Context.KIT_SESSION, title="Kit handoff")
        resp = self.client.get("/api/brain/handoffs/")
        data = resp.json()["data"]
        self.assertEqual(data["total"], 2)
        contexts = {h["context"] for h in data["handoffs"]}
        self.assertEqual(contexts, {"cortextos-agent", "kit-session"})

    def test_list_excludes_content(self) -> None:
        self._make(content="Long narrative that should not appear in list")
        resp = self.client.get("/api/brain/handoffs/")
        h = resp.json()["data"]["handoffs"][0]
        self.assertNotIn("content", h)
        self.assertIn("title", h)
        self.assertIn("open_items_count", h)
        self.assertIn("completed_items_count", h)
        self.assertIn("deferred_items_count", h)

    def test_list_ordered_by_updated_desc(self) -> None:
        self._make(context=HandoffEntry.Context.CORTEXTOS_AGENT, title="oldest")
        self._make(context=HandoffEntry.Context.KIT_SESSION, title="middle")
        self._make(context=HandoffEntry.Context.CODEX_SESSION, title="newest")
        resp = self.client.get("/api/brain/handoffs/")
        titles = [h["title"] for h in resp.json()["data"]["handoffs"]]
        self.assertEqual(titles, ["newest", "middle", "oldest"])


# ──────────────────────────────────────────────
# DETAIL / GET BY CONTEXT TESTS
# ──────────────────────────────────────────────


class HandoffDetailTest(HandoffAPIBase):

    def test_get_includes_content_and_action_items(self) -> None:
        self._make(
            context=HandoffEntry.Context.CORTEXTOS_AGENT,
            content="full narrative",
            action_items=[{"description": "x", "status": "open", "reason": None}],
        )
        resp = self.client.get("/api/brain/handoffs/cortextos-agent/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["content"], "full narrative")
        self.assertEqual(data["context"], "cortextos-agent")
        self.assertEqual(len(data["action_items"]), 1)
        self.assertEqual(data["action_items"][0]["status"], "open")

    def test_get_nonexistent_returns_404(self) -> None:
        resp = self.client.get("/api/brain/handoffs/cortextos-agent/")
        self.assertEqual(resp.status_code, 404)

    def test_get_invalid_context_returns_400(self) -> None:
        resp = self.client.get("/api/brain/handoffs/not-a-context/")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("context", resp.json()["message"].lower())


# ──────────────────────────────────────────────
# PUT / UPDATE TESTS (with version archiving)
# ──────────────────────────────────────────────


class HandoffUpdateTest(HandoffAPIBase):

    def test_put_creates_when_missing(self) -> None:
        resp = self.client.put(
            "/api/brain/handoffs/cortextos-agent/",
            data=json.dumps({
                "title": "First handoff",
                "content": "starting state",
                "action_items": [],
                "previous_items_resolved": False,
                "updated_by": "mara-cron",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["title"], "First handoff")
        self.assertEqual(HandoffEntry.objects.count(), 1)
        # No version archived because there was no prior content
        self.assertEqual(HandoffVersion.objects.count(), 0)

    def test_put_increments_version_and_archives(self) -> None:
        self._make(
            context=HandoffEntry.Context.CORTEXTOS_AGENT,
            title="v1 title",
            content="v1 content",
            action_items=[{"description": "x", "status": "open", "reason": None}],
        )
        resp = self.client.put(
            "/api/brain/handoffs/cortextos-agent/",
            data=json.dumps({
                "title": "v2 title",
                "content": "v2 content",
                "action_items": [{"description": "y", "status": "open", "reason": None}],
                "previous_items_resolved": True,
                "updated_by": "mara-cron",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["version"], 2)
        self.assertEqual(data["title"], "v2 title")
        self.assertEqual(data["content"], "v2 content")

        # Old version archived
        versions = HandoffVersion.objects.filter(handoff__context="cortextos-agent")
        self.assertEqual(versions.count(), 1)
        v1 = versions.first()
        self.assertEqual(v1.version, 1)
        self.assertEqual(v1.title, "v1 title")
        self.assertEqual(v1.content, "v1 content")
        self.assertEqual(len(v1.action_items), 1)
        self.assertEqual(v1.action_items[0]["description"], "x")

    def test_put_preserves_chain_across_multiple_updates(self) -> None:
        for content in ["v1", "v2", "v3"]:
            self.client.put(
                "/api/brain/handoffs/cortextos-agent/",
                data=json.dumps({
                    "title": content,
                    "content": content,
                    "action_items": [],
                    "previous_items_resolved": True,
                }),
                content_type="application/json",
            )
        h = HandoffEntry.objects.get(context="cortextos-agent")
        self.assertEqual(h.version, 3)
        self.assertEqual(h.content, "v3")
        versions = list(h.versions.all().order_by("version"))
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0].content, "v1")
        self.assertEqual(versions[1].content, "v2")

    def test_put_one_per_context_constraint(self) -> None:
        # Two different contexts each have their own active handoff.
        self.client.put(
            "/api/brain/handoffs/cortextos-agent/",
            data=json.dumps({"title": "agent", "content": "a", "action_items": []}),
            content_type="application/json",
        )
        self.client.put(
            "/api/brain/handoffs/kit-session/",
            data=json.dumps({"title": "kit", "content": "k", "action_items": []}),
            content_type="application/json",
        )
        self.assertEqual(HandoffEntry.objects.count(), 2)
        # Updating one does not affect the other
        self.client.put(
            "/api/brain/handoffs/cortextos-agent/",
            data=json.dumps({"title": "agent v2", "content": "av2", "action_items": []}),
            content_type="application/json",
        )
        self.assertEqual(HandoffEntry.objects.count(), 2)
        self.assertEqual(
            HandoffEntry.objects.get(context="cortextos-agent").content, "av2",
        )
        self.assertEqual(
            HandoffEntry.objects.get(context="kit-session").content, "k",
        )

    def test_put_invalid_context_returns_400(self) -> None:
        resp = self.client.put(
            "/api/brain/handoffs/bogus/",
            data=json.dumps({"title": "x", "content": "y", "action_items": []}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_put_missing_title_returns_400(self) -> None:
        resp = self.client.put(
            "/api/brain/handoffs/cortextos-agent/",
            data=json.dumps({"content": "y", "action_items": []}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_put_missing_content_returns_400(self) -> None:
        resp = self.client.put(
            "/api/brain/handoffs/cortextos-agent/",
            data=json.dumps({"title": "x", "action_items": []}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_put_invalid_action_item_status_returns_400(self) -> None:
        resp = self.client.put(
            "/api/brain/handoffs/cortextos-agent/",
            data=json.dumps({
                "title": "t", "content": "c",
                "action_items": [{"description": "x", "status": "weird", "reason": None}],
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("status", resp.json()["message"].lower())

    def test_put_action_item_missing_description_returns_400(self) -> None:
        resp = self.client.put(
            "/api/brain/handoffs/cortextos-agent/",
            data=json.dumps({
                "title": "t", "content": "c",
                "action_items": [{"status": "open"}],
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_put_action_items_must_be_list(self) -> None:
        resp = self.client.put(
            "/api/brain/handoffs/cortextos-agent/",
            data=json.dumps({"title": "t", "content": "c", "action_items": "not a list"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


# ──────────────────────────────────────────────
# ACTION ITEM STATUS TRACKING
# ──────────────────────────────────────────────


class HandoffActionItemTest(HandoffAPIBase):

    def test_action_items_persist_with_full_shape(self) -> None:
        items = [
            {"description": "ship feature", "status": "completed", "reason": None},
            {"description": "review PR", "status": "open", "reason": None},
            {
                "description": "rewrite auth",
                "status": "deferred",
                "reason": "needs Kevin's input",
            },
        ]
        resp = self.client.put(
            "/api/brain/handoffs/cortextos-agent/",
            data=json.dumps({"title": "t", "content": "c", "action_items": items}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["open_items_count"], 1)
        self.assertEqual(data["completed_items_count"], 1)
        self.assertEqual(data["deferred_items_count"], 1)
        # Round-trip
        resp = self.client.get("/api/brain/handoffs/cortextos-agent/")
        action_items = resp.json()["data"]["action_items"]
        deferred = next(i for i in action_items if i["status"] == "deferred")
        self.assertEqual(deferred["reason"], "needs Kevin's input")


# ──────────────────────────────────────────────
# HISTORY TESTS
# ──────────────────────────────────────────────


class HandoffHistoryTest(HandoffAPIBase):

    def test_history_empty_for_new_handoff(self) -> None:
        self._make(context=HandoffEntry.Context.CORTEXTOS_AGENT)
        resp = self.client.get("/api/brain/handoffs/cortextos-agent/history/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["current_version"], 1)

    def test_history_after_updates(self) -> None:
        for n, content in enumerate(["v1", "v2", "v3"], start=1):
            self.client.put(
                "/api/brain/handoffs/cortextos-agent/",
                data=json.dumps({
                    "title": f"title {n}", "content": content, "action_items": [],
                }),
                content_type="application/json",
            )
        resp = self.client.get("/api/brain/handoffs/cortextos-agent/history/")
        data = resp.json()["data"]
        self.assertEqual(data["current_version"], 3)
        self.assertEqual(data["total"], 2)
        # Newest archived version first
        self.assertEqual(data["versions"][0]["version"], 2)
        self.assertEqual(data["versions"][0]["content"], "v2")
        self.assertEqual(data["versions"][1]["version"], 1)
        self.assertEqual(data["versions"][1]["content"], "v1")

    def test_history_nonexistent_returns_404(self) -> None:
        resp = self.client.get("/api/brain/handoffs/cortextos-agent/history/")
        self.assertEqual(resp.status_code, 404)

    def test_history_invalid_context_returns_400(self) -> None:
        resp = self.client.get("/api/brain/handoffs/bogus/history/")
        self.assertEqual(resp.status_code, 400)


# ──────────────────────────────────────────────
# LATEST TESTS
# ──────────────────────────────────────────────


class HandoffLatestTest(HandoffAPIBase):

    def test_latest_empty_returns_null(self) -> None:
        resp = self.client.get("/api/brain/handoffs/latest/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertIsNone(data["handoff"])

    def test_latest_returns_most_recent_across_contexts(self) -> None:
        self._make(context=HandoffEntry.Context.CORTEXTOS_AGENT, title="agent first")
        self._make(context=HandoffEntry.Context.KIT_SESSION, title="kit second")
        # Touch the kit one to make it "latest"
        h = HandoffEntry.objects.get(context="kit-session")
        h.title = "kit updated"
        h.save()
        resp = self.client.get("/api/brain/handoffs/latest/")
        data = resp.json()["data"]
        self.assertIsNotNone(data["handoff"])
        self.assertEqual(data["handoff"]["context"], "kit-session")
        self.assertEqual(data["handoff"]["title"], "kit updated")
        # Latest must include open count for the Nerve Center card
        self.assertIn("open_items_count", data["handoff"])


# ──────────────────────────────────────────────
# AUTH TESTS
# ──────────────────────────────────────────────


class HandoffAuthTest(TestCase):

    def setUp(self) -> None:
        cache.clear()

    def test_unauthenticated_list_returns_401(self) -> None:
        resp = self.client.get("/api/brain/handoffs/")
        self.assertEqual(resp.status_code, 401)

    def test_all_endpoints_require_auth(self) -> None:
        endpoints = [
            ("/api/brain/handoffs/", "get"),
            ("/api/brain/handoffs/latest/", "get"),
            ("/api/brain/handoffs/cortextos-agent/", "get"),
            ("/api/brain/handoffs/cortextos-agent/history/", "get"),
        ]
        for url, method in endpoints:
            resp = getattr(self.client, method)(url)
            self.assertEqual(
                resp.status_code, 401,
                f"{method.upper()} {url} should return 401 without auth, got {resp.status_code}",
            )

    def test_put_requires_auth(self) -> None:
        resp = self.client.put(
            "/api/brain/handoffs/cortextos-agent/",
            data=json.dumps({"title": "x", "content": "y", "action_items": []}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_api_key_auth_works(self) -> None:
        User.objects.create_user(username="staffuser", password="p", is_staff=True)
        with self.settings(NOCKCC_API_KEY="test-key-123"):
            resp = self.client.get(
                "/api/brain/handoffs/",
                HTTP_X_API_KEY="test-key-123",
            )
        self.assertEqual(resp.status_code, 200)
