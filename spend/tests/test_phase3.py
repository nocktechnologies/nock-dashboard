"""Tests for Phase 3 spend features — add expense, revenue, P&L, tax prep."""
import os
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from spend.models import Expense, Revenue

_TEST_FERNET_KEYS = [os.environ.get("TEST_FERNET_KEY", "")]


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class RevenueModelTests(TestCase):
    def test_create_revenue(self):
        r = Revenue.objects.create(
            source="consulting",
            description="AI Strategy Consulting",
            amount=Decimal("5000.00"),
            date=date(2026, 3, 1),
        )
        assert r.pk is not None
        assert "Nock Consulting" in str(r)

    def test_money_is_decimal(self):
        r = Revenue.objects.create(
            source="academy",
            description="Course sale",
            amount=Decimal("49.99"),
            date=date(2026, 3, 10),
        )
        r.refresh_from_db()
        assert isinstance(r.amount, Decimal)

    def test_ordering(self):
        Revenue.objects.create(
            source="consulting", description="First", amount=Decimal("100"),
            date=date(2026, 1, 1),
        )
        Revenue.objects.create(
            source="consulting", description="Second", amount=Decimal("200"),
            date=date(2026, 3, 1),
        )
        revenues = list(Revenue.objects.all())
        assert revenues[0].date > revenues[1].date  # most recent first


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class AddExpenseViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="testpass123")
        self.client = Client()
        self.client.force_login(self.user)

    def test_add_expense_page(self):
        resp = self.client.get("/spend/add/")
        assert resp.status_code == 200

    def test_add_expense_post(self):
        resp = self.client.post("/spend/add/", {
            "vendor": "TestVendor",
            "description": "Test purchase",
            "category": "software",
            "subtotal": "99.00",
            "tax": "8.25",
            "total": "107.25",
            "payment_method": "visa_5540",
            "date": "2026-03-15",
        })
        assert resp.status_code == 302  # redirect on success
        assert Expense.objects.count() == 1
        expense = Expense.objects.first()
        assert expense.vendor == "TestVendor"
        assert expense.total == Decimal("107.25")

    def test_add_expense_auto_total(self):
        """Total is auto-calculated from subtotal + tax if not provided."""
        resp = self.client.post("/spend/add/", {
            "vendor": "AutoTotal",
            "description": "Test",
            "category": "software",
            "subtotal": "100.00",
            "tax": "10.00",
            "total": "",
            "payment_method": "visa_5540",
            "date": "2026-03-15",
        })
        assert resp.status_code == 302
        expense = Expense.objects.first()
        assert expense.total == Decimal("110.00")

    def test_requires_auth(self):
        self.client.logout()
        resp = self.client.get("/spend/add/")
        assert resp.status_code == 302


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class AddRevenueViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="testpass123")
        self.client = Client()
        self.client.force_login(self.user)

    def test_add_revenue_page(self):
        resp = self.client.get("/spend/revenue/add/")
        assert resp.status_code == 200

    def test_add_revenue_post(self):
        resp = self.client.post("/spend/revenue/add/", {
            "source": "consulting",
            "description": "Strategy engagement",
            "amount": "5000.00",
            "date": "2026-03-15",
        })
        assert resp.status_code == 302
        assert Revenue.objects.count() == 1


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class PnLViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="testpass123")
        self.client = Client()
        self.client.force_login(self.user)

    def test_pnl_page(self):
        resp = self.client.get("/spend/pnl/")
        assert resp.status_code == 200

    def test_pnl_with_data(self):
        Revenue.objects.create(
            source="consulting", description="Consulting",
            amount=Decimal("5000"), date=date(2026, 3, 1),
        )
        Expense.objects.create(
            vendor="Anthropic", description="API",
            category="software", subtotal=Decimal("200"),
            tax=Decimal("0"), total=Decimal("200"),
            payment_method="visa_5540", date=date(2026, 3, 1),
        )
        resp = self.client.get("/spend/pnl/")
        assert resp.context["net_position"] == Decimal("4800")


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class TaxViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="testpass123")
        self.client = Client()
        self.client.force_login(self.user)

    def test_tax_page(self):
        resp = self.client.get("/spend/tax/")
        assert resp.status_code == 200

    def test_tax_with_expenses(self):
        Expense.objects.create(
            vendor="Apple", description="MacBook",
            category="hardware", subtotal=Decimal("1400"),
            tax=Decimal("114"), total=Decimal("1514"),
            payment_method="visa_5540", date=date(2026, 2, 15),
        )
        Expense.objects.create(
            vendor="TX SecState", description="LLC filing",
            category="formation", subtotal=Decimal("300"),
            tax=Decimal("0"), total=Decimal("300"),
            payment_method="visa_5540", date=date(2026, 2, 10),
        )
        resp = self.client.get("/spend/tax/")
        assert resp.context["grand_total"] == Decimal("1814")

    def test_tax_custom_rate(self):
        resp = self.client.get("/spend/tax/?rate=32")
        assert resp.context["marginal_rate"] == 32

    def test_tax_export_csv(self):
        Expense.objects.create(
            vendor="Apple", description="MacBook",
            category="hardware", subtotal=Decimal("1400"),
            tax=Decimal("114"), total=Decimal("1514"),
            payment_method="visa_5540", date=date(2026, 2, 15),
        )
        resp = self.client.get("/spend/tax/export/")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "text/csv"
        assert b"Apple" in resp.content


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class ExpenseReceiptTests(TestCase):
    def test_receipt_fields_exist(self):
        e = Expense.objects.create(
            vendor="Test", description="Test",
            category="software", subtotal=Decimal("50"),
            tax=Decimal("0"), total=Decimal("50"),
            payment_method="visa_5540", date=date(2026, 3, 1),
        )
        assert hasattr(e, "receipt")
        assert hasattr(e, "receipt_filename")
        assert e.receipt_filename == ""
