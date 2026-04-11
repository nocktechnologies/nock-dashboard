"""Tests for the vault app — Document model, views, seed command."""
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from vault.models import Document

FERNET_KEY = "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ9PQ=="


@override_settings(FERNET_KEYS=[FERNET_KEY])
class DocumentModelTests(TestCase):
    def test_create_document(self):
        doc = Document.objects.create(
            title="Test Doc",
            category="formation",
            filename="test.pdf",
            file_size=1024,
            file_type="application/pdf",
        )
        assert doc.pk is not None
        assert str(doc) == "Test Doc"

    def test_file_size_display_bytes(self):
        doc = Document(file_size=500)
        assert doc.file_size_display == "500 B"

    def test_file_size_display_kb(self):
        doc = Document(file_size=5120)
        assert doc.file_size_display == "5.0 KB"

    def test_file_size_display_mb(self):
        doc = Document(file_size=2_097_152)
        assert doc.file_size_display == "2.0 MB"

    def test_is_image(self):
        doc = Document(file_type="image/png")
        assert doc.is_image is True

    def test_is_not_image(self):
        doc = Document(file_type="application/pdf")
        assert doc.is_image is False

    def test_is_pdf(self):
        doc = Document(file_type="application/pdf")
        assert doc.is_pdf is True

    def test_tag_list(self):
        doc = Document(tags="foo, bar, baz")
        assert doc.tag_list == ["foo", "bar", "baz"]

    def test_tag_list_empty(self):
        doc = Document(tags="")
        assert doc.tag_list == []

    def test_ordering(self):
        doc1 = Document.objects.create(
            title="A", category="other", filename="a.pdf", file_size=0
        )
        doc2 = Document.objects.create(
            title="B", category="other", filename="b.pdf", file_size=0
        )
        # Most recent first
        docs = list(Document.objects.all())
        assert docs[0] == doc2
        assert docs[1] == doc1

    def test_category_choices(self):
        keys = [c[0] for c in Document.CATEGORIES]
        assert "formation" in keys
        assert "legal" in keys
        assert "trademark" in keys


@override_settings(FERNET_KEYS=[FERNET_KEY])
class DocumentViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="testpass123")
        self.client = Client()
        self.client.force_login(self.user)

    def test_list_returns_200(self):
        resp = self.client.get("/vault/")
        assert resp.status_code == 200

    def test_upload_page_returns_200(self):
        resp = self.client.get("/vault/upload/")
        assert resp.status_code == 200

    def test_detail_returns_200(self):
        doc = Document.objects.create(
            title="Test", category="other", filename="t.pdf", file_size=0
        )
        resp = self.client.get(f"/vault/{doc.pk}/")
        assert resp.status_code == 200

    def test_detail_404(self):
        resp = self.client.get("/vault/9999/")
        assert resp.status_code == 404

    def test_list_filter_category(self):
        Document.objects.create(
            title="Formation Doc", category="formation", filename="f.pdf", file_size=0
        )
        Document.objects.create(
            title="Legal Doc", category="legal", filename="l.pdf", file_size=0
        )
        resp = self.client.get("/vault/?category=formation")
        assert resp.status_code == 200
        assert b"Formation Doc" in resp.content
        assert b"Legal Doc" not in resp.content

    def test_requires_auth(self):
        self.client.logout()
        resp = self.client.get("/vault/")
        assert resp.status_code == 302


@override_settings(FERNET_KEYS=[FERNET_KEY])
class SeedVaultTests(TestCase):
    def test_seed_creates_documents(self):
        from django.core.management import call_command
        call_command("seed_vault")
        assert Document.objects.count() == 4

    def test_seed_idempotent(self):
        from django.core.management import call_command
        call_command("seed_vault")
        call_command("seed_vault")
        assert Document.objects.count() == 4

    def test_seed_clear(self):
        from django.core.management import call_command
        call_command("seed_vault")
        call_command("seed_vault", clear=True)
        assert Document.objects.count() == 4
