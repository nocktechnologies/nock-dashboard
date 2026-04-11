import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from brain.models import MemoryEntry


class BrainAPITestBase(TestCase):
    """Base class for brain API tests — uses session auth."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="testpass", is_staff=True)
        self.client.force_login(self.user)
        # Clear seed data and rate limit counters so tests start clean
        MemoryEntry.objects.all().delete()
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


class EntryListCreateTest(BrainAPITestBase):

    def test_create_entry(self) -> None:
        resp = self.client.post(
            "/api/brain/entries/",
            data=json.dumps({
                "key": "new_key",
                "value": "new value",
                "category": "domain",
                "tags": ["factoring"],
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["key"], "new_key")
        self.assertEqual(body["data"]["category"], "domain")
        self.assertEqual(body["data"]["tags"], ["factoring"])
        self.assertEqual(MemoryEntry.objects.count(), 1)

    def test_create_entry_missing_key(self) -> None:
        resp = self.client.post(
            "/api/brain/entries/",
            data=json.dumps({"value": "v", "category": "domain"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("key and value are required", resp.json()["message"])

    def test_create_entry_invalid_category(self) -> None:
        resp = self.client.post(
            "/api/brain/entries/",
            data=json.dumps({"key": "k", "value": "v", "category": "bogus"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid category", resp.json()["message"])

    def test_create_entry_invalid_confidence(self) -> None:
        resp = self.client.post(
            "/api/brain/entries/",
            data=json.dumps({
                "key": "k", "value": "v", "category": "domain", "confidence": "wrong",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid confidence", resp.json()["message"])

    def test_create_entry_invalid_tags(self) -> None:
        resp = self.client.post(
            "/api/brain/entries/",
            data=json.dumps({
                "key": "k", "value": "v", "category": "domain",
                "tags": "not-a-list",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("tags must be a list", resp.json()["message"])

    def test_create_entry_too_many_tags(self) -> None:
        resp = self.client.post(
            "/api/brain/entries/",
            data=json.dumps({
                "key": "k", "value": "v", "category": "domain",
                "tags": [f"tag{i}" for i in range(25)],
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_list_entries(self) -> None:
        self._create_entry(key="a")
        self._create_entry(key="b", category="identity")
        resp = self.client.get("/api/brain/entries/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["total"], 2)

    def test_list_filter_category(self) -> None:
        self._create_entry(key="a", category="domain")
        self._create_entry(key="b", category="identity")
        resp = self.client.get("/api/brain/entries/?category=domain")
        body = resp.json()
        self.assertEqual(body["data"]["total"], 1)
        self.assertEqual(body["data"]["entries"][0]["category"], "domain")

    def test_list_filter_tag(self) -> None:
        self._create_entry(key="a", tags=["factoring"])
        self._create_entry(key="b", tags=["other"])
        resp = self.client.get("/api/brain/entries/?tag=factoring")
        body = resp.json()
        self.assertEqual(body["data"]["total"], 1)

    def test_list_search(self) -> None:
        self._create_entry(key="reserves_model", value="hopper")
        self._create_entry(key="fee_basis", value="face value")
        resp = self.client.get("/api/brain/entries/?search=hopper")
        body = resp.json()
        self.assertEqual(body["data"]["total"], 1)
        self.assertEqual(body["data"]["entries"][0]["key"], "reserves_model")

    def test_list_stale_filter(self) -> None:
        entry = self._create_entry(key="old")
        # Force update timestamp to 60 days ago
        MemoryEntry.objects.filter(pk=entry.pk).update(
            updated_at=timezone.now() - timedelta(days=60)
        )
        self._create_entry(key="fresh")

        resp = self.client.get("/api/brain/entries/?stale=true")
        body = resp.json()
        self.assertEqual(body["data"]["total"], 1)
        self.assertEqual(body["data"]["entries"][0]["key"], "old")

    def test_body_size_guard(self) -> None:
        large_body = "x" * (257 * 1024)
        resp = self.client.post(
            "/api/brain/entries/",
            data=large_body,
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 413)


class EntryDetailTest(BrainAPITestBase):

    def test_get_entry(self) -> None:
        entry = self._create_entry()
        resp = self.client.get(f"/api/brain/entries/{entry.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["key"], "test_key")

    def test_get_entry_not_found(self) -> None:
        resp = self.client.get("/api/brain/entries/99999/")
        self.assertEqual(resp.status_code, 404)

    def test_update_entry(self) -> None:
        entry = self._create_entry()
        resp = self.client.put(
            f"/api/brain/entries/{entry.pk}/",
            data=json.dumps({"value": "updated value", "tags": ["new"]}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["value"], "updated value")
        self.assertEqual(body["data"]["tags"], ["new"])

    def test_update_entry_invalid_category(self) -> None:
        entry = self._create_entry()
        resp = self.client.put(
            f"/api/brain/entries/{entry.pk}/",
            data=json.dumps({"category": "invalid"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_delete_entry(self) -> None:
        entry = self._create_entry()
        resp = self.client.delete(f"/api/brain/entries/{entry.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(MemoryEntry.objects.count(), 0)

    def test_field_truncation(self) -> None:
        resp = self.client.post(
            "/api/brain/entries/",
            data=json.dumps({
                "key": "k" * 300,
                "value": "v",
                "category": "domain",
                "source": "s" * 200,
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        entry = MemoryEntry.objects.first()
        self.assertLessEqual(len(entry.key), 200)
        self.assertLessEqual(len(entry.source), 100)


class CategoriesTest(BrainAPITestBase):

    def test_categories_list(self) -> None:
        self._create_entry(key="a", category="domain")
        self._create_entry(key="b", category="identity")
        resp = self.client.get("/api/brain/categories/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["domain"]["count"], 1)
        self.assertEqual(body["data"]["identity"]["count"], 1)


class BriefTest(BrainAPITestBase):

    def test_brief_general(self) -> None:
        self._create_entry(key="a", category="domain", value="domain val")
        self._create_entry(key="b", category="identity", value="identity val")
        resp = self.client.post(
            "/api/brain/brief/",
            data=json.dumps({"scope": "general"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("Context Brief", body["data"]["brief"])
        self.assertEqual(body["data"]["entry_count"], 2)

    def test_brief_domain_scope(self) -> None:
        self._create_entry(key="a", category="domain")
        self._create_entry(key="b", category="identity")
        resp = self.client.post(
            "/api/brain/brief/",
            data=json.dumps({"scope": "domain"}),
            content_type="application/json",
        )
        body = resp.json()
        self.assertEqual(body["data"]["entry_count"], 1)

    def test_brief_personal_scope(self) -> None:
        self._create_entry(key="a", category="identity")
        self._create_entry(key="b", category="relationship")
        self._create_entry(key="c", category="domain")
        resp = self.client.post(
            "/api/brain/brief/",
            data=json.dumps({"scope": "personal"}),
            content_type="application/json",
        )
        body = resp.json()
        self.assertEqual(body["data"]["entry_count"], 2)

    def test_brief_project_scope_with_tag(self) -> None:
        self._create_entry(key="nexus", category="project", tags=["nexus"])
        self._create_entry(key="nockcc", category="project", tags=["nockcc"])
        resp = self.client.post(
            "/api/brain/brief/",
            data=json.dumps({"scope": "project", "project": "nexus"}),
            content_type="application/json",
        )
        body = resp.json()
        self.assertEqual(body["data"]["entry_count"], 1)


class StatsTest(BrainAPITestBase):

    def test_stats(self) -> None:
        self._create_entry(key="a", category="domain")
        entry = self._create_entry(key="b", category="identity")
        MemoryEntry.objects.filter(pk=entry.pk).update(
            updated_at=timezone.now() - timedelta(days=60)
        )
        resp = self.client.get("/api/brain/stats/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["data"]["entry_count"], 2)
        self.assertEqual(body["data"]["stale_count"], 1)
        self.assertIn("domain", body["data"]["category_counts"])


class AuthTest(TestCase):
    """Test that endpoints require authentication."""

    def test_list_requires_auth(self) -> None:
        resp = self.client.get("/api/brain/entries/")
        self.assertEqual(resp.status_code, 401)

    def test_stats_requires_auth(self) -> None:
        resp = self.client.get("/api/brain/stats/")
        self.assertEqual(resp.status_code, 401)

    def test_brief_requires_auth(self) -> None:
        resp = self.client.post(
            "/api/brain/brief/",
            data=json.dumps({"scope": "general"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)


class SeedDataTest(TestCase):
    """Verify seed migration created 21 entries."""

    def test_seed_entry_count(self) -> None:
        count = MemoryEntry.objects.filter(source="seed").count()
        self.assertEqual(count, 21)

    def test_seed_categories(self) -> None:
        self.assertEqual(MemoryEntry.objects.filter(source="seed", category="identity").count(), 5)
        self.assertEqual(MemoryEntry.objects.filter(source="seed", category="relationship").count(), 4)
        self.assertEqual(MemoryEntry.objects.filter(source="seed", category="domain").count(), 3)
        self.assertEqual(MemoryEntry.objects.filter(source="seed", category="decision").count(), 3)
        self.assertEqual(MemoryEntry.objects.filter(source="seed", category="project").count(), 3)
        self.assertEqual(MemoryEntry.objects.filter(source="seed", category="lesson").count(), 2)
        self.assertEqual(MemoryEntry.objects.filter(source="seed", category="tool").count(), 1)


class MemoryEntryModelTest(TestCase):

    def setUp(self) -> None:
        MemoryEntry.objects.all().delete()

    def test_str(self) -> None:
        entry = MemoryEntry.objects.create(
            key="test", value="val", category="domain",
        )
        self.assertEqual(str(entry), "domain/test")

    def test_preview_short(self) -> None:
        entry = MemoryEntry.objects.create(
            key="test", value="short", category="domain",
        )
        self.assertEqual(entry.preview, "short")

    def test_preview_truncated(self) -> None:
        long_val = "x" * 300
        entry = MemoryEntry.objects.create(
            key="test", value=long_val, category="domain",
        )
        self.assertEqual(len(entry.preview), 200)

    def test_is_stale(self) -> None:
        entry = MemoryEntry.objects.create(
            key="test", value="val", category="domain",
        )
        self.assertFalse(entry.is_stale)
        MemoryEntry.objects.filter(pk=entry.pk).update(
            updated_at=timezone.now() - timedelta(days=60)
        )
        entry.refresh_from_db()
        self.assertTrue(entry.is_stale)
