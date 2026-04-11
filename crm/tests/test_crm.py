"""Tests for the CRM app — Contact, Deal, DealNote models and views."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from crm.models import Contact, Deal, DealNote

FERNET_KEY = "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ9PQ=="


@override_settings(FERNET_KEYS=[FERNET_KEY])
class ContactModelTests(TestCase):
    def test_create_contact(self):
        c = Contact.objects.create(name="Alice", company="Acme")
        assert c.pk is not None
        assert str(c) == "Alice (Acme)"

    def test_str_no_company(self):
        c = Contact(name="Bob")
        assert str(c) == "Bob"

    def test_ordering(self):
        Contact.objects.create(name="Zara")
        Contact.objects.create(name="Alice")
        names = list(Contact.objects.values_list("name", flat=True))
        assert names == ["Alice", "Zara"]


@override_settings(FERNET_KEYS=[FERNET_KEY])
class DealModelTests(TestCase):
    def test_create_deal(self):
        d = Deal.objects.create(
            title="Consulting Project",
            source="consulting",
            estimated_value=Decimal("5000.00"),
        )
        assert d.pk is not None
        assert str(d) == "Consulting Project"

    def test_display_value_estimated(self):
        d = Deal(estimated_value=Decimal("5000.00"))
        assert d.display_value == Decimal("5000.00")

    def test_display_value_actual_preferred(self):
        d = Deal(
            estimated_value=Decimal("5000.00"),
            actual_value=Decimal("6000.00"),
        )
        assert d.display_value == Decimal("6000.00")

    def test_is_open(self):
        d = Deal(stage="prospect")
        assert d.is_open is True

    def test_is_closed(self):
        d = Deal(stage="closed_won")
        assert d.is_open is False

    def test_default_stage(self):
        d = Deal.objects.create(title="Test", source="other")
        assert d.stage == "prospect"

    def test_money_is_decimal(self):
        d = Deal.objects.create(
            title="Test",
            source="consulting",
            estimated_value=Decimal("100.50"),
        )
        d.refresh_from_db()
        assert isinstance(d.estimated_value, Decimal)


@override_settings(FERNET_KEYS=[FERNET_KEY])
class DealNoteTests(TestCase):
    def test_create_note(self):
        deal = Deal.objects.create(title="Test Deal", source="other")
        note = DealNote.objects.create(deal=deal, content="First call went well.")
        assert note.pk is not None
        assert note.deal == deal

    def test_ordering(self):
        deal = Deal.objects.create(title="Test", source="other")
        DealNote.objects.create(deal=deal, content="First")
        n2 = DealNote.objects.create(deal=deal, content="Second")
        notes = list(deal.deal_notes.all())
        assert notes[0] == n2  # newest first


@override_settings(FERNET_KEYS=[FERNET_KEY])
class CRMViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="testpass123")
        self.client = Client()
        self.client.force_login(self.user)

    def test_pipeline_kanban(self):
        resp = self.client.get("/crm/")
        assert resp.status_code == 200

    def test_pipeline_table(self):
        resp = self.client.get("/crm/?view=table")
        assert resp.status_code == 200

    def test_deal_create_page(self):
        resp = self.client.get("/crm/deals/add/")
        assert resp.status_code == 200

    def test_deal_create_post(self):
        resp = self.client.post("/crm/deals/add/", {
            "title": "New Deal",
            "source": "consulting",
            "stage": "prospect",
        })
        assert resp.status_code == 302
        assert Deal.objects.count() == 1

    def test_deal_detail(self):
        deal = Deal.objects.create(title="Test", source="other")
        resp = self.client.get(f"/crm/deals/{deal.pk}/")
        assert resp.status_code == 200

    def test_deal_add_note(self):
        deal = Deal.objects.create(title="Test", source="other")
        resp = self.client.post(f"/crm/deals/{deal.pk}/", {
            "add_note": "1",
            "content": "Follow-up call.",
        })
        assert resp.status_code == 302
        assert deal.deal_notes.count() == 1

    def test_deal_update_stage(self):
        deal = Deal.objects.create(title="Test", source="other", stage="prospect")
        resp = self.client.post(f"/crm/deals/{deal.pk}/", {
            "update_stage": "1",
            "stage": "contacted",
        })
        assert resp.status_code == 302
        deal.refresh_from_db()
        assert deal.stage == "contacted"

    def test_contacts_page(self):
        resp = self.client.get("/crm/contacts/")
        assert resp.status_code == 200

    def test_contact_create(self):
        resp = self.client.post("/crm/contacts/add/", {"name": "John Doe"})
        assert resp.status_code == 302
        assert Contact.objects.count() == 1

    def test_pipeline_stats(self):
        Deal.objects.create(title="D1", source="consulting", estimated_value=Decimal("1000"))
        Deal.objects.create(title="D2", source="academy", estimated_value=Decimal("2000"))
        resp = self.client.get("/crm/")
        assert resp.status_code == 200
        assert resp.context["pipeline_value"] == Decimal("3000")

    def test_requires_auth(self):
        self.client.logout()
        resp = self.client.get("/crm/")
        assert resp.status_code == 302
