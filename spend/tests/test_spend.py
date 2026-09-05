"""Tests for the spend app — models, views, tasks, API, commands."""

import os
import secrets
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase, override_settings
from django.utils import timezone

from pipeline.models import PullRequest, Repository
from spend.models import Expense, SpendBudget, SubscriptionTracker, UsagePeriod
from spend.tasks import check_budget_alerts

_TEST_FERNET_KEYS = [os.environ.get("TEST_FERNET_KEY", "")]
_TEST_WEBHOOK_SECRET = secrets.token_hex(16)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class UsagePeriodModelTests(TestCase):
    def test_create_usage_period(self) -> None:
        up = UsagePeriod.objects.create(
            date=date.today(),
            model="claude-opus-4-6",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=Decimal("0.0150"),
        )
        self.assertEqual(str(up), f"{date.today()} — claude-opus-4-6: $0.0150")

    def test_unique_constraint(self) -> None:
        UsagePeriod.objects.create(
            date=date.today(),
            model="claude-opus-4-6",
            workspace="",
            cost_usd=Decimal("0.01"),
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            UsagePeriod.objects.create(
                date=date.today(),
                model="claude-opus-4-6",
                workspace="",
                cost_usd=Decimal("0.02"),
            )

    def test_aggregation_by_month(self) -> None:
        today = date.today()
        first = today.replace(day=1)
        UsagePeriod.objects.create(date=first, model="opus", cost_usd=Decimal("10.0000"))
        UsagePeriod.objects.create(date=first + timedelta(days=1), model="opus", cost_usd=Decimal("5.0000"))
        UsagePeriod.objects.create(date=first, model="sonnet", cost_usd=Decimal("3.0000"))

        total = UsagePeriod.objects.filter(date__gte=first).aggregate(t=Sum("cost_usd"))["t"]
        self.assertEqual(total, Decimal("18.0000"))

    def test_aggregation_by_model(self) -> None:
        today = date.today()
        UsagePeriod.objects.create(date=today, model="opus", cost_usd=Decimal("10.0000"))
        UsagePeriod.objects.create(date=today, model="sonnet", cost_usd=Decimal("3.0000"))

        by_model = (
            UsagePeriod.objects.filter(date=today)
            .values("model")
            .annotate(total=Sum("cost_usd"))
            .order_by("-total")
        )
        self.assertEqual(by_model[0]["model"], "opus")
        self.assertEqual(by_model[0]["total"], Decimal("10.0000"))

    def test_cost_is_decimal_not_float(self) -> None:
        up = UsagePeriod.objects.create(
            date=date.today(),
            model="test",
            cost_usd=Decimal("0.1234"),
        )
        up.refresh_from_db()
        self.assertIsInstance(up.cost_usd, Decimal)
        self.assertEqual(up.cost_usd, Decimal("0.1234"))


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class SpendBudgetTests(TestCase):
    def test_budget_under_threshold(self) -> None:
        first = date.today().replace(day=1)
        SpendBudget.objects.create(month=first, budget_usd=Decimal("500.00"), alert_threshold_pct=80)
        UsagePeriod.objects.create(date=first, model="opus", cost_usd=Decimal("100.0000"))

        result = check_budget_alerts()
        self.assertFalse(result)

    def test_budget_over_threshold(self) -> None:
        first = date.today().replace(day=1)
        SpendBudget.objects.create(month=first, budget_usd=Decimal("500.00"), alert_threshold_pct=80)
        UsagePeriod.objects.create(date=first, model="opus", cost_usd=Decimal("450.0000"))

        result = check_budget_alerts()
        self.assertTrue(result)

        budget = SpendBudget.objects.get(month=first)
        self.assertTrue(budget.alert_sent)

    def test_budget_alert_not_sent_twice(self) -> None:
        first = date.today().replace(day=1)
        SpendBudget.objects.create(month=first, budget_usd=Decimal("500.00"), alert_sent=True)
        UsagePeriod.objects.create(date=first, model="opus", cost_usd=Decimal("450.0000"))

        result = check_budget_alerts()
        self.assertFalse(result)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, ANTHROPIC_ADMIN_API_KEY="test-key")
class AnthropicClientTests(TestCase):
    @patch("spend.anthropic_client.requests.get")
    def test_fetch_usage_success(self, mock_get: MagicMock) -> None:
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {
            "data": [
                {
                    "bucket_start_time": "2026-03-14T00:00:00Z",
                    "model": "claude-opus-4-6",
                    "input_tokens": 5000,
                    "output_tokens": 2000,
                    "input_cached_tokens": 100,
                    "input_cache_write_tokens": 50,
                    "request_count": 10,
                }
            ]
        }

        from spend.anthropic_client import fetch_usage_report
        records = fetch_usage_report(date(2026, 3, 14), date(2026, 3, 14))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["model"], "claude-opus-4-6")
        self.assertEqual(records[0]["input_tokens"], 5000)

    @patch("spend.anthropic_client.requests.get")
    def test_fetch_usage_error(self, mock_get: MagicMock) -> None:
        import requests
        mock_get.side_effect = requests.RequestException("Connection error")

        from spend.anthropic_client import fetch_usage_report
        records = fetch_usage_report(date(2026, 3, 14), date(2026, 3, 14))
        self.assertEqual(records, [])

    @override_settings(ANTHROPIC_ADMIN_API_KEY="")
    def test_fetch_usage_no_key(self) -> None:
        from spend.anthropic_client import fetch_usage_report
        records = fetch_usage_report(date(2026, 3, 14), date(2026, 3, 14))
        self.assertEqual(records, [])


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, ANTHROPIC_ADMIN_API_KEY="test")
class SyncTaskTests(TestCase):
    @patch("spend.tasks.fetch_cost_report", return_value=[])
    @patch("spend.tasks.fetch_usage_report")
    def test_sync_creates_records(self, mock_usage: MagicMock, mock_cost: MagicMock) -> None:
        mock_usage.return_value = [
            {
                "date": str(date.today()),
                "model": "claude-opus-4-6",
                "workspace": "",
                "input_tokens": 1000,
                "output_tokens": 500,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "request_count": 5,
            }
        ]

        from spend.tasks import sync_anthropic_usage
        result = sync_anthropic_usage()
        self.assertEqual(result["created"], 1)
        self.assertEqual(UsagePeriod.objects.count(), 1)

    @patch("spend.tasks.fetch_cost_report", return_value=[])
    @patch("spend.tasks.fetch_usage_report")
    def test_sync_updates_existing(self, mock_usage: MagicMock, mock_cost: MagicMock) -> None:
        UsagePeriod.objects.create(
            date=date.today(), model="claude-opus-4-6", workspace="", input_tokens=100
        )
        mock_usage.return_value = [
            {
                "date": str(date.today()),
                "model": "claude-opus-4-6",
                "workspace": "",
                "input_tokens": 2000,
                "output_tokens": 1000,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "request_count": 10,
            }
        ]

        from spend.tasks import sync_anthropic_usage
        result = sync_anthropic_usage()
        self.assertEqual(result["updated"], 1)
        up = UsagePeriod.objects.get(date=date.today(), model="claude-opus-4-6")
        self.assertEqual(up.input_tokens, 2000)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class SpendViewTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(self.user)

    def test_spend_dashboard_returns_200(self) -> None:
        resp = self.client.get("/spend/")
        self.assertEqual(resp.status_code, 200)

    def test_spend_dashboard_empty_state(self) -> None:
        resp = self.client.get("/spend/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Spend Dashboard")

    def test_spend_dashboard_with_data(self) -> None:
        UsagePeriod.objects.create(
            date=date.today(),
            model="claude-opus-4-6",
            cost_usd=Decimal("5.0000"),
            input_tokens=10000,
            output_tokens=5000,
        )
        resp = self.client.get("/spend/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "5.00")

    def test_spend_dashboard_with_expenses(self) -> None:
        Expense.objects.create(
            vendor="Test Vendor",
            description="Test expense",
            category="software",
            subtotal=Decimal("100.00"),
            tax=Decimal("8.25"),
            total=Decimal("108.25"),
            payment_method="card_a",
            date=date.today(),
        )
        resp = self.client.get("/spend/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Test Vendor")
        self.assertContains(resp, "108.25")

    def test_spend_dashboard_expense_category_filter(self) -> None:
        Expense.objects.create(
            vendor="Soft Co", description="Soft", category="software",
            subtotal=Decimal("50.00"), tax=Decimal("0"), total=Decimal("50.00"),
            payment_method="card_a", date=date.today(),
        )
        Expense.objects.create(
            vendor="Hard Co", description="Hard", category="hardware",
            subtotal=Decimal("100.00"), tax=Decimal("0"), total=Decimal("100.00"),
            payment_method="card_b", date=date.today(),
        )
        resp = self.client.get("/spend/?expense_category=software")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Soft Co")
        self.assertNotContains(resp, "Hard Co")

    def test_spend_dashboard_expense_payment_filter(self) -> None:
        Expense.objects.create(
            vendor="Amex Co", description="Amex", category="software",
            subtotal=Decimal("50.00"), tax=Decimal("0"), total=Decimal("50.00"),
            payment_method="card_a", date=date.today(),
        )
        Expense.objects.create(
            vendor="Visa Co", description="Visa", category="software",
            subtotal=Decimal("100.00"), tax=Decimal("0"), total=Decimal("100.00"),
            payment_method="card_b", date=date.today(),
        )
        resp = self.client.get("/spend/?expense_payment=card_a")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Amex Co")
        self.assertNotContains(resp, "Visa Co")

    def test_spend_dashboard_refund_display(self) -> None:
        Expense.objects.create(
            vendor="Refund Co", description="Refund test", category="software",
            subtotal=Decimal("36.21"), tax=Decimal("0"), total=Decimal("36.21"),
            is_refund=True, payment_method="card_c", date=date.today(),
        )
        resp = self.client.get("/spend/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Refund Co")
        self.assertContains(resp, "-$36.21")


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class SpendAPITests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(self.user)

    def test_summary_api_returns_expected_keys(self) -> None:
        resp = self.client.get("/spend/api/summary/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        expected_keys = {
            "today_spend", "mtd_spend", "budget_total", "budget_pct",
            "projected_month_end", "subscriptions_total",
            "expense_total", "expense_tax",
            "total_spend", "burn_rate", "revenue_mtd",
        }
        self.assertEqual(set(body["data"].keys()), expected_keys)

    def test_summary_api_includes_expense_totals(self) -> None:
        Expense.objects.create(
            vendor="Test", description="t", category="software",
            subtotal=Decimal("100.00"), tax=Decimal("8.00"), total=Decimal("108.00"),
            payment_method="card_a", date=date.today(),
        )
        resp = self.client.get("/spend/api/summary/")
        body = resp.json()
        self.assertEqual(body["data"]["expense_total"], "108.00")
        self.assertEqual(body["data"]["expense_tax"], "8.00")

    def test_daily_api_returns_json(self) -> None:
        UsagePeriod.objects.create(
            date=date.today(),
            model="opus",
            cost_usd=Decimal("1.0000"),
        )
        resp = self.client.get("/spend/api/daily/?days=7")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["model"], "opus")

    def test_daily_api_clamps_days(self) -> None:
        resp = self.client.get("/spend/api/daily/?days=999")
        self.assertEqual(resp.status_code, 200)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class ExpensesAPITests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(self.user)

    def test_expenses_api_returns_all(self) -> None:
        Expense.objects.create(
            vendor="V1", description="d", category="software",
            subtotal=Decimal("10.00"), tax=Decimal("0"), total=Decimal("10.00"),
            payment_method="card_a", date=date.today(),
        )
        Expense.objects.create(
            vendor="V2", description="d", category="hardware",
            subtotal=Decimal("20.00"), tax=Decimal("0"), total=Decimal("20.00"),
            payment_method="card_b", date=date.today(),
        )
        resp = self.client.get("/spend/api/expenses/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(len(body["data"]), 2)

    def test_expenses_api_filter_category(self) -> None:
        Expense.objects.create(
            vendor="V1", description="d", category="software",
            subtotal=Decimal("10.00"), tax=Decimal("0"), total=Decimal("10.00"),
            payment_method="card_a", date=date.today(),
        )
        Expense.objects.create(
            vendor="V2", description="d", category="hardware",
            subtotal=Decimal("20.00"), tax=Decimal("0"), total=Decimal("20.00"),
            payment_method="card_b", date=date.today(),
        )
        resp = self.client.get("/spend/api/expenses/?category=software")
        body = resp.json()
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["vendor"], "V1")

    def test_expenses_api_filter_payment_method(self) -> None:
        Expense.objects.create(
            vendor="V1", description="d", category="software",
            subtotal=Decimal("10.00"), tax=Decimal("0"), total=Decimal("10.00"),
            payment_method="card_a", date=date.today(),
        )
        Expense.objects.create(
            vendor="V2", description="d", category="software",
            subtotal=Decimal("20.00"), tax=Decimal("0"), total=Decimal("20.00"),
            payment_method="card_b", date=date.today(),
        )
        resp = self.client.get("/spend/api/expenses/?payment_method=card_b")
        body = resp.json()
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["vendor"], "V2")

    def test_expenses_api_includes_refund_flag(self) -> None:
        Expense.objects.create(
            vendor="Refund Co", description="refund", category="software",
            subtotal=Decimal("36.21"), tax=Decimal("0"), total=Decimal("36.21"),
            is_refund=True, payment_method="card_c", date=date.today(),
        )
        resp = self.client.get("/spend/api/expenses/")
        body = resp.json()
        self.assertTrue(body["data"][0]["is_refund"])

    def test_expenses_api_requires_auth(self) -> None:
        self.client.logout()
        resp = self.client.get("/spend/api/expenses/")
        self.assertEqual(resp.status_code, 401)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class SubscriptionsAPITests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(self.user)

    def test_subscriptions_api_returns_active(self) -> None:
        SubscriptionTracker.objects.create(
            name="Active Sub", provider="anthropic",
            monthly_cost=Decimal("200.00"), renewal_date=date.today(),
            is_active=True,
        )
        SubscriptionTracker.objects.create(
            name="Inactive Sub", provider="openai",
            monthly_cost=Decimal("20.00"), renewal_date=date.today(),
            is_active=False,
        )
        resp = self.client.get("/spend/api/subscriptions/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(len(body["data"]["subscriptions"]), 1)
        self.assertEqual(body["data"]["monthly_total"], "200.00")
        self.assertEqual(body["data"]["annual_projection"], "2400.00")

    def test_subscriptions_api_requires_auth(self) -> None:
        self.client.logout()
        resp = self.client.get("/spend/api/subscriptions/")
        self.assertEqual(resp.status_code, 401)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class ExpenseModelTests(TestCase):
    def test_create_expense(self) -> None:
        exp = Expense.objects.create(
            vendor="Anthropic",
            description="Claude Max 20x",
            category="software",
            subtotal=Decimal("200.00"),
            tax=Decimal("11.60"),
            total=Decimal("211.60"),
            payment_method="card_a",
            date=date.today(),
            reference="INV-001",
        )
        self.assertEqual(str(exp), f"{date.today()} — Anthropic: $211.60")

    def test_refund_str(self) -> None:
        exp = Expense.objects.create(
            vendor="Moonshot AI",
            description="Refund",
            category="software",
            subtotal=Decimal("36.21"),
            tax=Decimal("0"),
            total=Decimal("36.21"),
            is_refund=True,
            payment_method="card_c",
            date=date.today(),
        )
        self.assertIn("REFUND", str(exp))

    def test_expense_money_is_decimal(self) -> None:
        exp = Expense.objects.create(
            vendor="Test",
            description="Test",
            category="other",
            subtotal=Decimal("99.99"),
            tax=Decimal("5.50"),
            total=Decimal("105.49"),
            payment_method="other",
            date=date.today(),
        )
        exp.refresh_from_db()
        self.assertIsInstance(exp.subtotal, Decimal)
        self.assertIsInstance(exp.tax, Decimal)
        self.assertIsInstance(exp.total, Decimal)

    def test_expense_ordering(self) -> None:
        Expense.objects.create(
            vendor="A Vendor", description="d", category="software",
            subtotal=Decimal("10.00"), tax=Decimal("0"), total=Decimal("10.00"),
            payment_method="card_a", date=date(2026, 3, 1),
        )
        Expense.objects.create(
            vendor="B Vendor", description="d", category="software",
            subtotal=Decimal("20.00"), tax=Decimal("0"), total=Decimal("20.00"),
            payment_method="card_a", date=date(2026, 3, 5),
        )
        expenses = list(Expense.objects.all())
        # Most recent first
        self.assertEqual(expenses[0].vendor, "B Vendor")

    def test_expense_category_choices(self) -> None:
        categories = [c[0] for c in Expense.CATEGORIES]
        self.assertIn("software", categories)
        self.assertIn("hardware", categories)
        self.assertIn("formation", categories)
        self.assertIn("legal", categories)
        self.assertIn("domains", categories)

    def test_expense_payment_method_choices(self) -> None:
        methods = [m[0] for m in Expense.PAYMENT_METHODS]
        self.assertIn("card_a", methods)
        self.assertIn("card_b", methods)
        self.assertIn("stripe_link", methods)
        self.assertIn("paypal", methods)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class SeedExpensesTests(TestCase):
    def test_seed_creates_expenses(self) -> None:
        out = StringIO()
        call_command("seed_expenses", stdout=out)
        self.assertEqual(Expense.objects.count(), 18)
        self.assertIn("Done", out.getvalue())

    def test_seed_idempotent(self) -> None:
        call_command("seed_expenses", stdout=StringIO())
        call_command("seed_expenses", stdout=StringIO())
        self.assertEqual(Expense.objects.count(), 18)

    def test_seed_clear_option(self) -> None:
        call_command("seed_expenses", stdout=StringIO())
        self.assertEqual(Expense.objects.count(), 18)
        call_command("seed_expenses", "--clear", stdout=StringIO())
        self.assertEqual(Expense.objects.count(), 18)

    def test_seed_has_correct_net_total(self) -> None:
        call_command("seed_expenses", stdout=StringIO())
        from spend.views import _expense_totals
        totals = _expense_totals()
        self.assertEqual(totals["net"], Decimal("3201.97"))

    def test_seed_refund_count(self) -> None:
        call_command("seed_expenses", stdout=StringIO())
        refunds = Expense.objects.filter(is_refund=True).count()
        self.assertEqual(refunds, 1)

    def test_seed_tax_total(self) -> None:
        call_command("seed_expenses", stdout=StringIO())
        from spend.views import _expense_totals
        totals = _expense_totals()
        self.assertEqual(totals["tax"], Decimal("139.64"))


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class SeedSubscriptionsTests(TestCase):
    def test_seed_creates_subscriptions(self) -> None:
        out = StringIO()
        call_command("seed_subscriptions", stdout=out)
        self.assertEqual(SubscriptionTracker.objects.count(), 8)
        self.assertIn("Done", out.getvalue())

    def test_seed_idempotent(self) -> None:
        call_command("seed_subscriptions", stdout=StringIO())
        call_command("seed_subscriptions", stdout=StringIO())
        self.assertEqual(SubscriptionTracker.objects.count(), 8)

    def test_seed_clear_option(self) -> None:
        call_command("seed_subscriptions", stdout=StringIO())
        self.assertEqual(SubscriptionTracker.objects.count(), 8)
        call_command("seed_subscriptions", "--clear", stdout=StringIO())
        self.assertEqual(SubscriptionTracker.objects.count(), 8)

    def test_seed_monthly_total(self) -> None:
        call_command("seed_subscriptions", stdout=StringIO())
        total = SubscriptionTracker.objects.filter(is_active=True).aggregate(
            t=Sum("monthly_cost")
        )["t"]
        self.assertEqual(total, Decimal("469.96"))


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class SetBudgetTests(TestCase):
    def test_set_budget_creates(self) -> None:
        out = StringIO()
        call_command("set_budget", "--month", "2026-03", "--amount", "500", stdout=out)
        self.assertEqual(SpendBudget.objects.count(), 1)
        budget = SpendBudget.objects.first()
        self.assertEqual(budget.budget_usd, Decimal("500.00"))
        self.assertIn("Created", out.getvalue())

    def test_set_budget_updates(self) -> None:
        call_command("set_budget", "--month", "2026-03", "--amount", "500", stdout=StringIO())
        call_command("set_budget", "--month", "2026-03", "--amount", "750", stdout=StringIO())
        self.assertEqual(SpendBudget.objects.count(), 1)
        budget = SpendBudget.objects.first()
        self.assertEqual(budget.budget_usd, Decimal("750.00"))


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class CostPerPRTests(TestCase):
    def setUp(self) -> None:
        self.repo = Repository.objects.create(
            name="test-repo",
            owner="kkwills13",
            github_id=400001,
            webhook_secret=_TEST_WEBHOOK_SECRET,
        )

    def test_cost_per_pr_with_data(self) -> None:
        first = date.today().replace(day=1)
        UsagePeriod.objects.create(date=first, model="opus", cost_usd=Decimal("100.0000"))
        PullRequest.objects.create(
            repository=self.repo,
            github_pr_id=1,
            number=1,
            title="Test PR",
            branch="test",
            author="kev",
            state=PullRequest.State.MERGED,
            opened_at=timezone.now() - timedelta(days=2),
            merged_at=timezone.now(),
        )

        from spend.views import _cost_per_pr
        result = _cost_per_pr()
        self.assertIsNotNone(result)
        self.assertEqual(result, Decimal("100.0000"))

    def test_cost_per_pr_no_prs(self) -> None:
        from spend.views import _cost_per_pr
        result = _cost_per_pr()
        self.assertIsNone(result)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class ProjectedMonthEndTests(TestCase):
    def test_projected_with_data(self) -> None:
        today = date.today()
        first = today.replace(day=1)
        UsagePeriod.objects.create(date=first, model="opus", cost_usd=Decimal("10.0000"))

        from spend.views import _projected_month_end
        result = _projected_month_end()
        self.assertIsInstance(result, Decimal)
        self.assertGreater(result, Decimal("0"))

    def test_projected_no_data(self) -> None:
        from spend.views import _projected_month_end
        result = _projected_month_end()
        self.assertEqual(result, Decimal("0"))


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class MoneyDecimalTests(TestCase):
    def test_all_money_fields_are_decimal(self) -> None:
        up = UsagePeriod.objects.create(
            date=date.today(), model="test", cost_usd=Decimal("1.2345")
        )
        up.refresh_from_db()
        self.assertIsInstance(up.cost_usd, Decimal)

        budget = SpendBudget.objects.create(
            month=date.today().replace(day=1), budget_usd=Decimal("500.00")
        )
        budget.refresh_from_db()
        self.assertIsInstance(budget.budget_usd, Decimal)

        sub = SubscriptionTracker.objects.create(
            name="Test", provider="anthropic", monthly_cost=Decimal("20.00"),
            renewal_date=date.today(),
        )
        sub.refresh_from_db()
        self.assertIsInstance(sub.monthly_cost, Decimal)

        exp = Expense.objects.create(
            vendor="Test", description="d", category="other",
            subtotal=Decimal("99.99"), tax=Decimal("5.50"), total=Decimal("105.49"),
            payment_method="other", date=date.today(),
        )
        exp.refresh_from_db()
        self.assertIsInstance(exp.subtotal, Decimal)
        self.assertIsInstance(exp.tax, Decimal)
        self.assertIsInstance(exp.total, Decimal)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class ExpenseTotalsTests(TestCase):
    def test_expense_totals_with_refund(self) -> None:
        Expense.objects.create(
            vendor="V1", description="d", category="software",
            subtotal=Decimal("100.00"), tax=Decimal("8.00"), total=Decimal("108.00"),
            payment_method="card_a", date=date.today(),
        )
        Expense.objects.create(
            vendor="V2", description="refund", category="software",
            subtotal=Decimal("36.21"), tax=Decimal("0"), total=Decimal("36.21"),
            is_refund=True, payment_method="card_c", date=date.today(),
        )
        from spend.views import _expense_totals
        totals = _expense_totals()
        self.assertEqual(totals["gross"], Decimal("108.00"))
        self.assertEqual(totals["refunds"], Decimal("36.21"))
        self.assertEqual(totals["net"], Decimal("71.79"))
        self.assertEqual(totals["tax"], Decimal("8.00"))

    def test_expense_totals_empty(self) -> None:
        from spend.views import _expense_totals
        totals = _expense_totals()
        self.assertEqual(totals["net"], Decimal("0"))

    def test_category_breakdown(self) -> None:
        Expense.objects.create(
            vendor="V1", description="d", category="software",
            subtotal=Decimal("100.00"), tax=Decimal("0"), total=Decimal("100.00"),
            payment_method="card_a", date=date.today(),
        )
        Expense.objects.create(
            vendor="V2", description="d", category="hardware",
            subtotal=Decimal("200.00"), tax=Decimal("0"), total=Decimal("200.00"),
            payment_method="card_b", date=date.today(),
        )
        from spend.views import _category_breakdown
        breakdown = _category_breakdown()
        self.assertEqual(len(breakdown), 2)
        # Sorted by gross descending
        self.assertEqual(breakdown[0]["category"], "hardware")
        self.assertEqual(breakdown[0]["total"], Decimal("200.00"))

    def test_payment_method_breakdown(self) -> None:
        Expense.objects.create(
            vendor="V1", description="d", category="software",
            subtotal=Decimal("100.00"), tax=Decimal("0"), total=Decimal("100.00"),
            payment_method="card_a", date=date.today(),
        )
        Expense.objects.create(
            vendor="V2", description="d", category="software",
            subtotal=Decimal("200.00"), tax=Decimal("0"), total=Decimal("200.00"),
            payment_method="card_b", date=date.today(),
        )
        from spend.views import _payment_method_breakdown
        breakdown = _payment_method_breakdown()
        self.assertEqual(len(breakdown), 2)
