# brain/tests/test_identity.py
import json
from io import StringIO

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase

from brain.models import IdentityDocument, IdentityDocumentVersion

# ──────────────────────────────────────────────
# MODEL TESTS
# ──────────────────────────────────────────────


class IdentityDocumentModelTest(TestCase):

    def _make(self, **kwargs) -> IdentityDocument:
        defaults = {
            "slug": "test-doc",
            "title": "Test Document",
            "content": "Test content here",
            "document_type": "core_identity",
            "load_order": 0,
            "updated_by": "test",
        }
        defaults.update(kwargs)
        return IdentityDocument.objects.create(**defaults)

    def test_create_document(self) -> None:
        doc = self._make()
        self.assertEqual(doc.title, "Test Document")
        self.assertEqual(doc.version, 1)
        self.assertTrue(doc.is_active)
        self.assertEqual(doc.load_order, 0)

    def test_slug_unique(self) -> None:
        from django.db import IntegrityError

        self._make(slug="unique-slug")
        with self.assertRaises(IntegrityError):
            self._make(slug="unique-slug")

    def test_ordering_by_load_order(self) -> None:
        d2 = self._make(slug="second", load_order=2)
        d0 = self._make(slug="first", load_order=0)
        d1 = self._make(slug="middle", load_order=1)
        docs = list(IdentityDocument.objects.all())
        self.assertEqual(docs[0].pk, d0.pk)
        self.assertEqual(docs[1].pk, d1.pk)
        self.assertEqual(docs[2].pk, d2.pk)

    def test_soft_delete(self) -> None:
        doc = self._make()
        self.assertTrue(doc.is_active)
        doc.is_active = False
        doc.save()
        doc.refresh_from_db()
        self.assertFalse(doc.is_active)
        # Still exists in DB
        self.assertTrue(IdentityDocument.objects.filter(slug="test-doc").exists())

    def test_str_format(self) -> None:
        doc = self._make(title="MARA_CORE", version=1)
        self.assertEqual(str(doc), "MARA_CORE (v1)")

    def test_version_default_is_1(self) -> None:
        doc = self._make()
        self.assertEqual(doc.version, 1)


class IdentityDocumentVersionModelTest(TestCase):

    def _make_doc(self, **kwargs) -> IdentityDocument:
        defaults = {
            "slug": "test-doc",
            "title": "Test Document",
            "content": "Original content",
            "document_type": "core_identity",
            "updated_by": "test",
        }
        defaults.update(kwargs)
        return IdentityDocument.objects.create(**defaults)

    def test_create_version(self) -> None:
        doc = self._make_doc()
        ver = IdentityDocumentVersion.objects.create(
            document=doc,
            version=1,
            title=doc.title,
            content=doc.content,
            document_type=doc.document_type,
            updated_by=doc.updated_by,
        )
        self.assertEqual(ver.version, 1)
        self.assertEqual(ver.content, "Original content")

    def test_version_unique_together(self) -> None:
        from django.db import IntegrityError

        doc = self._make_doc()
        IdentityDocumentVersion.objects.create(
            document=doc, version=1, title="v1", content="c1",
            document_type="core_identity", updated_by="test",
        )
        with self.assertRaises(IntegrityError):
            IdentityDocumentVersion.objects.create(
                document=doc, version=1, title="v1 dup", content="c1 dup",
                document_type="core_identity", updated_by="test",
            )

    def test_versions_ordered_newest_first(self) -> None:
        doc = self._make_doc()
        v1 = IdentityDocumentVersion.objects.create(
            document=doc, version=1, title="v1", content="c1",
            document_type="core_identity", updated_by="test",
        )
        v2 = IdentityDocumentVersion.objects.create(
            document=doc, version=2, title="v2", content="c2",
            document_type="core_identity", updated_by="test",
        )
        versions = list(doc.versions.all())
        self.assertEqual(versions[0].pk, v2.pk)
        self.assertEqual(versions[1].pk, v1.pk)

    def test_cascade_delete(self) -> None:
        doc = self._make_doc()
        IdentityDocumentVersion.objects.create(
            document=doc, version=1, title="v1", content="c1",
            document_type="core_identity", updated_by="test",
        )
        doc.delete()
        self.assertEqual(IdentityDocumentVersion.objects.count(), 0)

    def test_str_format(self) -> None:
        doc = self._make_doc()
        ver = IdentityDocumentVersion.objects.create(
            document=doc, version=3, title="MARA_CORE", content="c",
            document_type="core_identity", updated_by="test",
        )
        self.assertEqual(str(ver), "MARA_CORE v3")


# ──────────────────────────────────────────────
# API BASE
# ──────────────────────────────────────────────


class IdentityAPIBase(TestCase):

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="testidentity", password="testpass", is_staff=True,
        )
        self.client.force_login(self.user)
        cache.clear()

    def _make(self, **kwargs) -> IdentityDocument:
        defaults = {
            "slug": "test-doc",
            "title": "Test Document",
            "content": "Test content",
            "document_type": "core_identity",
            "load_order": 0,
            "updated_by": "test",
        }
        defaults.update(kwargs)
        return IdentityDocument.objects.create(**defaults)


# ──────────────────────────────────────────────
# LIST TESTS
# ──────────────────────────────────────────────


class IdentityListTest(IdentityAPIBase):

    def test_list_empty(self) -> None:
        resp = self.client.get("/api/brain/identity/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["total"], 0)

    def test_list_excludes_inactive(self) -> None:
        self._make(slug="active", is_active=True)
        self._make(slug="inactive", is_active=False)
        resp = self.client.get("/api/brain/identity/")
        data = resp.json()["data"]
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["documents"][0]["slug"], "active")

    def test_list_excludes_content(self) -> None:
        self._make(content="This should not appear in list")
        resp = self.client.get("/api/brain/identity/")
        doc = resp.json()["data"]["documents"][0]
        self.assertNotIn("content", doc)
        self.assertIn("slug", doc)
        self.assertIn("title", doc)
        self.assertIn("version", doc)

    def test_list_ordered_by_load_order(self) -> None:
        self._make(slug="second", load_order=2)
        self._make(slug="first", load_order=0)
        self._make(slug="third", load_order=5)
        resp = self.client.get("/api/brain/identity/")
        slugs = [d["slug"] for d in resp.json()["data"]["documents"]]
        self.assertEqual(slugs, ["first", "second", "third"])


# ──────────────────────────────────────────────
# DETAIL TESTS
# ──────────────────────────────────────────────


class IdentityDetailTest(IdentityAPIBase):

    def test_get_detail_includes_content(self) -> None:
        self._make(slug="mara-core", content="Full identity content here")
        resp = self.client.get("/api/brain/identity/mara-core/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["content"], "Full identity content here")
        self.assertEqual(data["slug"], "mara-core")

    def test_get_nonexistent_returns_404(self) -> None:
        resp = self.client.get("/api/brain/identity/nonexistent/")
        self.assertEqual(resp.status_code, 404)

    def test_get_inactive_doc_still_accessible(self) -> None:
        self._make(slug="old-doc", is_active=False)
        resp = self.client.get("/api/brain/identity/old-doc/")
        self.assertEqual(resp.status_code, 200)


# ──────────────────────────────────────────────
# CREATE TESTS
# ──────────────────────────────────────────────


class IdentityCreateTest(IdentityAPIBase):

    def test_create_document(self) -> None:
        payload = {
            "slug": "new-doc",
            "title": "New Identity Doc",
            "content": "Content here",
            "document_type": "operational",
            "load_order": 5,
            "updated_by": "kevin",
        }
        resp = self.client.post(
            "/api/brain/identity/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()["data"]
        self.assertEqual(data["slug"], "new-doc")
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["document_type"], "operational")

    def test_create_missing_fields_returns_400(self) -> None:
        resp = self.client.post(
            "/api/brain/identity/",
            data=json.dumps({"slug": "x"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_create_invalid_type_returns_400(self) -> None:
        resp = self.client.post(
            "/api/brain/identity/",
            data=json.dumps({
                "slug": "x", "title": "T", "content": "C", "document_type": "invalid",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("document_type", resp.json()["message"].lower())

    def test_create_duplicate_slug_returns_409(self) -> None:
        self._make(slug="existing")
        resp = self.client.post(
            "/api/brain/identity/",
            data=json.dumps({
                "slug": "existing", "title": "T", "content": "C",
                "document_type": "core_identity",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 409)

    def test_create_no_auth_returns_401(self) -> None:
        self.client.logout()
        resp = self.client.post(
            "/api/brain/identity/",
            data=json.dumps({
                "slug": "x", "title": "T", "content": "C",
                "document_type": "core_identity",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)


# ──────────────────────────────────────────────
# UPDATE TESTS
# ──────────────────────────────────────────────


class IdentityUpdateTest(IdentityAPIBase):

    def test_update_increments_version(self) -> None:
        self._make(slug="mara-core", content="v1 content")
        resp = self.client.put(
            "/api/brain/identity/mara-core/",
            data=json.dumps({"content": "v2 content", "updated_by": "mara-session"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["version"], 2)
        self.assertEqual(data["content"], "v2 content")
        self.assertEqual(data["updated_by"], "mara-session")

    def test_update_creates_version_history(self) -> None:
        self._make(slug="mara-core", content="original", title="Original Title")
        self.client.put(
            "/api/brain/identity/mara-core/",
            data=json.dumps({"content": "updated content", "title": "New Title"}),
            content_type="application/json",
        )
        versions = IdentityDocumentVersion.objects.filter(document__slug="mara-core")
        self.assertEqual(versions.count(), 1)
        v1 = versions.first()
        self.assertEqual(v1.version, 1)
        self.assertEqual(v1.content, "original")
        self.assertEqual(v1.title, "Original Title")

    def test_update_preserves_version_chain(self) -> None:
        self._make(slug="mara-core", content="v1")
        self.client.put(
            "/api/brain/identity/mara-core/",
            data=json.dumps({"content": "v2"}),
            content_type="application/json",
        )
        self.client.put(
            "/api/brain/identity/mara-core/",
            data=json.dumps({"content": "v3"}),
            content_type="application/json",
        )
        doc = IdentityDocument.objects.get(slug="mara-core")
        self.assertEqual(doc.version, 3)
        self.assertEqual(doc.content, "v3")
        versions = list(doc.versions.all().order_by("version"))
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0].content, "v1")
        self.assertEqual(versions[1].content, "v2")

    def test_update_nonexistent_returns_404(self) -> None:
        resp = self.client.put(
            "/api/brain/identity/nonexistent/",
            data=json.dumps({"content": "x"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_update_invalid_type_returns_400(self) -> None:
        self._make(slug="test-doc")
        resp = self.client.put(
            "/api/brain/identity/test-doc/",
            data=json.dumps({"document_type": "invalid"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_update_partial_fields(self) -> None:
        self._make(slug="test-doc", title="Old", content="Old content", load_order=0)
        resp = self.client.put(
            "/api/brain/identity/test-doc/",
            data=json.dumps({"title": "New Title"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["title"], "New Title")
        self.assertEqual(data["content"], "Old content")  # unchanged


# ──────────────────────────────────────────────
# SOFT DELETE TESTS
# ──────────────────────────────────────────────


class IdentitySoftDeleteTest(IdentityAPIBase):

    def test_delete_soft_deletes(self) -> None:
        self._make(slug="to-delete")
        resp = self.client.delete("/api/brain/identity/to-delete/")
        self.assertEqual(resp.status_code, 200)
        doc = IdentityDocument.objects.get(slug="to-delete")
        self.assertFalse(doc.is_active)

    def test_delete_excluded_from_list(self) -> None:
        self._make(slug="to-delete")
        self.client.delete("/api/brain/identity/to-delete/")
        resp = self.client.get("/api/brain/identity/")
        self.assertEqual(resp.json()["data"]["total"], 0)

    def test_delete_excluded_from_boot(self) -> None:
        self._make(slug="to-delete")
        self.client.delete("/api/brain/identity/to-delete/")
        resp = self.client.get("/api/brain/identity/boot/")
        self.assertEqual(resp.json()["data"]["total"], 0)

    def test_delete_already_inactive_returns_400(self) -> None:
        self._make(slug="inactive", is_active=False)
        resp = self.client.delete("/api/brain/identity/inactive/")
        self.assertEqual(resp.status_code, 400)

    def test_delete_nonexistent_returns_404(self) -> None:
        resp = self.client.delete("/api/brain/identity/nonexistent/")
        self.assertEqual(resp.status_code, 404)


# ──────────────────────────────────────────────
# HISTORY TESTS
# ──────────────────────────────────────────────


class IdentityHistoryTest(IdentityAPIBase):

    def test_history_empty_for_new_doc(self) -> None:
        self._make(slug="new-doc")
        resp = self.client.get("/api/brain/identity/new-doc/history/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["current_version"], 1)

    def test_history_after_updates(self) -> None:
        self._make(slug="evolving", content="v1 content")
        self.client.put(
            "/api/brain/identity/evolving/",
            data=json.dumps({"content": "v2 content"}),
            content_type="application/json",
        )
        self.client.put(
            "/api/brain/identity/evolving/",
            data=json.dumps({"content": "v3 content"}),
            content_type="application/json",
        )
        resp = self.client.get("/api/brain/identity/evolving/history/")
        data = resp.json()["data"]
        self.assertEqual(data["current_version"], 3)
        self.assertEqual(data["total"], 2)
        # Newest version first
        self.assertEqual(data["versions"][0]["version"], 2)
        self.assertEqual(data["versions"][0]["content"], "v2 content")
        self.assertEqual(data["versions"][1]["version"], 1)
        self.assertEqual(data["versions"][1]["content"], "v1 content")

    def test_history_nonexistent_returns_404(self) -> None:
        resp = self.client.get("/api/brain/identity/nonexistent/history/")
        self.assertEqual(resp.status_code, 404)


# ──────────────────────────────────────────────
# BOOT TESTS
# ──────────────────────────────────────────────


class IdentityBootTest(IdentityAPIBase):

    def test_boot_returns_all_active_with_content(self) -> None:
        self._make(slug="mara-core", content="Mara identity", load_order=0)
        self._make(slug="kevin-core", content="Kevin identity", load_order=1)
        self._make(slug="inactive", content="Should not appear", is_active=False, load_order=99)
        resp = self.client.get("/api/brain/identity/boot/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["documents"][0]["slug"], "mara-core")
        self.assertEqual(data["documents"][0]["content"], "Mara identity")
        self.assertEqual(data["documents"][1]["slug"], "kevin-core")

    def test_boot_empty(self) -> None:
        resp = self.client.get("/api/brain/identity/boot/")
        data = resp.json()["data"]
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["documents"], [])

    def test_boot_ordering(self) -> None:
        self._make(slug="last", load_order=10)
        self._make(slug="first", load_order=0)
        self._make(slug="middle", load_order=5)
        resp = self.client.get("/api/brain/identity/boot/")
        slugs = [d["slug"] for d in resp.json()["data"]["documents"]]
        self.assertEqual(slugs, ["first", "middle", "last"])


# ──────────────────────────────────────────────
# AUTH TESTS
# ──────────────────────────────────────────────


class IdentityAuthTest(TestCase):

    def setUp(self) -> None:
        cache.clear()

    def test_unauthenticated_returns_401(self) -> None:
        resp = self.client.get("/api/brain/identity/")
        self.assertEqual(resp.status_code, 401)

    def test_api_key_auth_works(self) -> None:
        User.objects.create_user(username="staffuser", password="p", is_staff=True)
        with self.settings(NOCKCC_API_KEY="test-key-123"):
            resp = self.client.get(
                "/api/brain/identity/",
                HTTP_X_API_KEY="test-key-123",
            )
        self.assertEqual(resp.status_code, 200)

    def test_drf_token_auth_works(self) -> None:
        from rest_framework.authtoken.models import Token

        user = User.objects.create_user(username="tokenuser", password="p", is_active=True)
        token = Token.objects.create(user=user)
        resp = self.client.get(
            "/api/brain/identity/",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )
        self.assertEqual(resp.status_code, 200)

    def test_invalid_token_returns_401(self) -> None:
        resp = self.client.get(
            "/api/brain/identity/",
            HTTP_AUTHORIZATION="Token invalid-token-value",
        )
        self.assertEqual(resp.status_code, 401)

    def test_boot_requires_auth(self) -> None:
        resp = self.client.get("/api/brain/identity/boot/")
        self.assertEqual(resp.status_code, 401)

    def test_all_endpoints_require_auth(self) -> None:
        endpoints = [
            ("/api/brain/identity/", "GET"),
            ("/api/brain/identity/boot/", "GET"),
            ("/api/brain/identity/mara-core/", "GET"),
            ("/api/brain/identity/mara-core/history/", "GET"),
        ]
        for url, method in endpoints:
            resp = getattr(self.client, method.lower())(url)
            self.assertEqual(
                resp.status_code, 401,
                f"{method} {url} should return 401 without auth, got {resp.status_code}",
            )


# ──────────────────────────────────────────────
# SEED COMMAND TESTS
# ──────────────────────────────────────────────


class SeedIdentityCommandTest(TestCase):

    def test_seed_creates_documents(self) -> None:
        out = StringIO()
        call_command("seed_identity", stdout=out)
        self.assertEqual(IdentityDocument.objects.count(), 4)
        self.assertTrue(IdentityDocument.objects.filter(slug="mara-core").exists())
        self.assertTrue(IdentityDocument.objects.filter(slug="kevin-core").exists())
        self.assertTrue(IdentityDocument.objects.filter(slug="fuzzy").exists())
        self.assertTrue(IdentityDocument.objects.filter(slug="operating-agreements").exists())
        self.assertIn("CREATE", out.getvalue())

    def test_seed_idempotent(self) -> None:
        call_command("seed_identity", stdout=StringIO())
        out = StringIO()
        call_command("seed_identity", stdout=out)
        self.assertEqual(IdentityDocument.objects.count(), 4)
        self.assertIn("SKIP", out.getvalue())
        self.assertNotIn("CREATE", out.getvalue())

    def test_seed_load_order(self) -> None:
        call_command("seed_identity", stdout=StringIO())
        docs = list(IdentityDocument.objects.all())
        self.assertEqual(docs[0].slug, "mara-core")
        self.assertEqual(docs[0].load_order, 0)
        self.assertEqual(docs[1].slug, "kevin-core")
        self.assertEqual(docs[1].load_order, 1)

    def test_seed_document_types(self) -> None:
        call_command("seed_identity", stdout=StringIO())
        self.assertEqual(
            IdentityDocument.objects.get(slug="mara-core").document_type,
            "core_identity",
        )
        self.assertEqual(
            IdentityDocument.objects.get(slug="kevin-core").document_type,
            "partner_identity",
        )
        self.assertEqual(
            IdentityDocument.objects.get(slug="fuzzy").document_type,
            "framework",
        )
        self.assertEqual(
            IdentityDocument.objects.get(slug="operating-agreements").document_type,
            "operational",
        )
