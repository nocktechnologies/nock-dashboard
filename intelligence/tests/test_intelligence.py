"""Tests for the Intelligence layer."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from intelligence.models import (
    AdvisorConversation,
    AdvisorMessage,
    BusinessSnapshot,
    PredictiveAlert,
    WeeklyMemo,
)

# ──────────────── Model Tests ────────────────


class BusinessSnapshotModelTest(TestCase):
    def test_create_snapshot(self):
        snap = BusinessSnapshot.objects.create(
            date=timezone.now().date(),
            content="# Test snapshot",
            token_count=100,
        )
        assert str(snap) == f"Snapshot {snap.date}"
        assert snap.token_count == 100

    def test_ordering(self):
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        BusinessSnapshot.objects.create(date=yesterday, content="old")
        BusinessSnapshot.objects.create(date=today, content="new")
        snapshots = list(BusinessSnapshot.objects.all())
        assert snapshots[0].date == today
        assert snapshots[1].date == yesterday


class AdvisorConversationModelTest(TestCase):
    def test_create_conversation(self):
        convo = AdvisorConversation.objects.create(title="Test Chat")
        assert str(convo) == "Test Chat"

    def test_empty_title(self):
        convo = AdvisorConversation.objects.create()
        assert str(convo) == f"Conversation {convo.pk}"


class AdvisorMessageModelTest(TestCase):
    def test_create_message(self):
        convo = AdvisorConversation.objects.create(title="Test")
        msg = AdvisorMessage.objects.create(
            conversation=convo,
            role="user",
            content="What's my burn rate?",
        )
        assert msg.role == "user"
        assert msg.tokens_used == 0
        assert msg.cost == 0

    def test_ordering(self):
        convo = AdvisorConversation.objects.create(title="Test")
        m1 = AdvisorMessage.objects.create(
            conversation=convo, role="user", content="Q1"
        )
        m2 = AdvisorMessage.objects.create(
            conversation=convo, role="assistant", content="A1"
        )
        messages = list(convo.messages.all())
        assert messages[0].pk == m1.pk
        assert messages[1].pk == m2.pk


class PredictiveAlertModelTest(TestCase):
    def test_create_alert(self):
        alert = PredictiveAlert.objects.create(
            category="spend",
            severity="critical",
            title="Budget exceeded",
            message="API spend is over budget",
        )
        assert str(alert) == "[critical] Budget exceeded"
        assert alert.is_resolved is False

    def test_resolve_alert(self):
        alert = PredictiveAlert.objects.create(
            category="spend",
            severity="warning",
            title="Test",
            message="Test message",
        )
        alert.is_resolved = True
        alert.resolved_at = timezone.now()
        alert.save()
        alert.refresh_from_db()
        assert alert.is_resolved is True
        assert alert.resolved_at is not None


class WeeklyMemoModelTest(TestCase):
    def test_create_memo(self):
        today = timezone.now().date()
        memo = WeeklyMemo.objects.create(
            week_start=today - timedelta(days=7),
            week_end=today,
            content="# Weekly Memo",
            tokens_used=500,
            cost=Decimal("0.0150"),
        )
        assert "Memo" in str(memo)
        assert memo.tokens_used == 500


# ──────────────── View Tests ────────────────


class ExecutiveDashboardViewTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.client.force_login(self.user)

    def test_executive_dashboard_page(self):
        response = self.client.get("/intelligence/executive/")
        assert response.status_code == 200
        assert b"Executive Dashboard" in response.content

    def test_executive_api(self):
        response = self.client.get("/intelligence/api/executive/")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "financial" in data["data"]
        assert "development" in data["data"]
        assert "operations" in data["data"]
        assert "growth" in data["data"]

    def test_unauthenticated_redirect(self):
        self.client.logout()
        response = self.client.get("/intelligence/executive/")
        assert response.status_code == 302


class AdvisorViewTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.client.force_login(self.user)

    def test_advisor_page(self):
        response = self.client.get("/intelligence/advisor/")
        assert response.status_code == 200
        assert b"AI Advisor" in response.content

    def test_conversations_list_api(self):
        AdvisorConversation.objects.create(title="Test Chat", owner=self.user)
        response = self.client.get("/intelligence/api/advisor/conversations/")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 1

    def test_conversations_list_scoped_to_user(self):
        from django.contrib.auth.models import User
        other_user = User.objects.create_user(username="other", password="pass")
        AdvisorConversation.objects.create(title="Mine", owner=self.user)
        AdvisorConversation.objects.create(title="Theirs", owner=other_user)
        response = self.client.get("/intelligence/api/advisor/conversations/")
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["title"] == "Mine"

    def test_conversation_detail_api(self):
        convo = AdvisorConversation.objects.create(title="Test", owner=self.user)
        AdvisorMessage.objects.create(
            conversation=convo, role="user", content="Hello"
        )
        response = self.client.get(
            f"/intelligence/api/advisor/conversations/{convo.pk}/"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]["messages"]) == 1

    def test_conversation_detail_other_user_404(self):
        from django.contrib.auth.models import User
        other_user = User.objects.create_user(username="other", password="pass")
        convo = AdvisorConversation.objects.create(title="Theirs", owner=other_user)
        response = self.client.get(
            f"/intelligence/api/advisor/conversations/{convo.pk}/"
        )
        assert response.status_code == 404

    def test_conversation_detail_404(self):
        response = self.client.get(
            "/intelligence/api/advisor/conversations/99999/"
        )
        assert response.status_code == 404

    def test_chat_api_missing_message(self):
        response = self.client.post(
            "/intelligence/api/advisor/chat/",
            data='{"message": ""}',
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_chat_api_invalid_json(self):
        response = self.client.post(
            "/intelligence/api/advisor/chat/",
            data="not json",
            content_type="application/json",
        )
        assert response.status_code == 400

    @patch("intelligence.ai_client.chat")
    def test_chat_api_success(self, mock_chat):
        mock_chat.return_value = {
            "content": "Your burn rate is $470/mo",
            "tool_uses": [],
            "input_tokens": 100,
            "output_tokens": 50,
            "cost": Decimal("0.001050"),
            "stop_reason": "end_turn",
        }
        response = self.client.post(
            "/intelligence/api/advisor/chat/",
            data='{"message": "What is my burn rate?"}',
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "burn rate" in data["data"]["response"]
        assert data["data"]["conversation_id"] is not None

    @patch("intelligence.ai_client.chat")
    def test_chat_api_fallback_when_unavailable(self, mock_chat):
        mock_chat.return_value = None
        response = self.client.post(
            "/intelligence/api/advisor/chat/",
            data='{"message": "Hello"}',
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert "unable to connect" in data["data"]["response"].lower()

    @patch("intelligence.ai_client.chat")
    def test_chat_api_existing_conversation(self, mock_chat):
        mock_chat.return_value = {
            "content": "Answer",
            "tool_uses": [],
            "input_tokens": 50,
            "output_tokens": 25,
            "cost": Decimal("0.000525"),
            "stop_reason": "end_turn",
        }
        convo = AdvisorConversation.objects.create(title="Existing", owner=self.user)
        response = self.client.post(
            "/intelligence/api/advisor/chat/",
            data=f'{{"message": "Follow up", "conversation_id": {convo.pk}}}',
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["conversation_id"] == convo.pk

    def test_chat_api_nonexistent_conversation(self):
        response = self.client.post(
            "/intelligence/api/advisor/chat/",
            data='{"message": "Hello", "conversation_id": 99999}',
            content_type="application/json",
        )
        assert response.status_code == 404


class AlertsViewTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.client.force_login(self.user)

    def test_alerts_page(self):
        response = self.client.get("/intelligence/alerts/")
        assert response.status_code == 200
        assert b"Predictive Alerts" in response.content

    def test_alerts_page_with_data(self):
        PredictiveAlert.objects.create(
            category="spend",
            severity="critical",
            title="Budget alert",
            message="Over budget",
        )
        response = self.client.get("/intelligence/alerts/")
        assert response.status_code == 200
        assert b"Budget alert" in response.content

    def test_alerts_filter_by_category(self):
        PredictiveAlert.objects.create(
            category="spend", severity="warning",
            title="Spend alert", message="Test",
        )
        PredictiveAlert.objects.create(
            category="pipeline", severity="info",
            title="Pipeline alert", message="Test",
        )
        response = self.client.get("/intelligence/alerts/?category=spend")
        assert response.status_code == 200
        assert b"Spend alert" in response.content


class SnapshotAPITest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.client.force_login(self.user)

    def test_snapshot_latest_empty(self):
        response = self.client.get("/intelligence/api/snapshot/latest/")
        assert response.status_code == 200
        data = response.json()
        assert data["data"] is None

    def test_snapshot_latest_with_data(self):
        BusinessSnapshot.objects.create(
            date=timezone.now().date(),
            content="# Test",
            token_count=50,
        )
        response = self.client.get("/intelligence/api/snapshot/latest/")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["content"] == "# Test"


# ──────────────── AI Client Tests ────────────────


class AIClientTest(TestCase):
    def test_calculate_cost(self):
        from intelligence.ai_client import calculate_cost

        cost = calculate_cost(1000, 500)
        # Input: 1000 * 3/1M = 0.003
        # Output: 500 * 15/1M = 0.0075
        assert cost == Decimal("0.0105")

    def test_calculate_cost_zero(self):
        from intelligence.ai_client import calculate_cost

        cost = calculate_cost(0, 0)
        assert cost == Decimal("0")

    @override_settings(ANTHROPIC_API_KEY="")
    def test_chat_no_api_key(self):
        from intelligence.ai_client import chat

        result = chat([{"role": "user", "content": "test"}])
        assert result is None


# ──────────────── Task Tests ────────────────


class SnapshotTaskTest(TestCase):
    def test_generate_snapshot(self):
        from intelligence.tasks import generate_business_snapshot

        result = generate_business_snapshot()
        assert result["created"] is True
        assert result["token_count"] > 0

        # Verify snapshot exists
        snap = BusinessSnapshot.objects.get(date=result["date"])
        assert "Business Snapshot" in snap.content

    def test_snapshot_updates_existing(self):
        from intelligence.tasks import generate_business_snapshot

        generate_business_snapshot()  # first run
        result2 = generate_business_snapshot()
        assert result2["created"] is False
        assert BusinessSnapshot.objects.count() == 1


class PredictiveAlertTaskTest(TestCase):
    def test_check_predictive_alerts(self):
        from intelligence.tasks import check_predictive_alerts

        result = check_predictive_alerts()
        assert "alerts_created" in result

    def test_create_alert_if_new(self):
        from intelligence.tasks import _create_alert_if_new

        count = _create_alert_if_new("spend", "critical", "Test Alert", "Test message")
        assert count == 1
        assert PredictiveAlert.objects.count() == 1

    def test_create_alert_dedup(self):
        from intelligence.tasks import _create_alert_if_new

        _create_alert_if_new("spend", "critical", "Test Alert", "Test message")
        count = _create_alert_if_new("spend", "critical", "Test Alert", "Duplicate")
        assert count == 0
        assert PredictiveAlert.objects.count() == 1


class WeeklyMemoTaskTest(TestCase):
    @patch("intelligence.ai_client.chat")
    def test_generate_weekly_memo(self, mock_chat):
        mock_chat.return_value = {
            "content": "# Weekly Memo\n\nTest content",
            "tool_uses": [],
            "input_tokens": 200,
            "output_tokens": 100,
            "cost": Decimal("0.002100"),
            "stop_reason": "end_turn",
        }
        from intelligence.tasks import generate_weekly_memo

        result = generate_weekly_memo()
        assert result["memo_id"] is not None
        assert WeeklyMemo.objects.count() == 1

    @patch("intelligence.ai_client.chat")
    def test_generate_weekly_memo_api_unavailable(self, mock_chat):
        mock_chat.return_value = None
        from intelligence.tasks import generate_weekly_memo

        result = generate_weekly_memo()
        assert result["error"] == "API unavailable"
        assert WeeklyMemo.objects.count() == 0


# ──────────────── Tool Execution Tests ────────────────


class ToolExecutionTest(TestCase):
    def test_get_expenses_tool(self):
        import json

        from intelligence.views import _execute_tool

        result = json.loads(_execute_tool("get_expenses", {"days": 30}))
        assert "count" in result
        assert "expenses" in result

    def test_get_deals_tool(self):
        import json

        from intelligence.views import _execute_tool

        result = json.loads(_execute_tool("get_deals", {}))
        assert "count" in result
        assert "deals" in result

    def test_get_pr_history_tool(self):
        import json

        from intelligence.views import _execute_tool

        result = json.loads(_execute_tool("get_pr_history", {"days": 7}))
        assert "count" in result
        assert "prs" in result

    def test_get_tasks_tool(self):
        import json

        from intelligence.views import _execute_tool

        result = json.loads(_execute_tool("get_tasks", {"status": "overdue"}))
        assert "count" in result
        assert "tasks" in result

    def test_unknown_tool(self):
        import json

        from intelligence.views import _execute_tool

        result = json.loads(_execute_tool("unknown_tool", {}))
        assert "error" in result


# ──────────────── Executive Data Tests ────────────────


class ExecutiveDataTest(TestCase):
    def test_get_executive_data(self):
        from intelligence.executive import get_executive_data

        data = get_executive_data()
        assert "financial" in data
        assert "development" in data
        assert "operations" in data
        assert "growth" in data
        assert "generated_at" in data

    def test_financial_has_required_fields(self):
        from intelligence.executive import get_executive_data

        data = get_executive_data()
        fin = data["financial"]
        assert "total_spend" in fin
        assert "monthly_burn" in fin
        assert "revenue_mtd" in fin
        assert "net_position" in fin
        assert "trend" in fin

    def test_development_has_required_fields(self):
        from intelligence.executive import get_executive_data

        data = get_executive_data()
        dev = data["development"]
        assert "prs_merged_this_week" in dev
        assert "pr_trend" in dev
        assert "active_sessions" in dev
        assert "context_docs_total" in dev
        assert "context_docs_healthy" in dev


# ──────────────── Snapshot Content Tests ────────────────


class SnapshotContentTest(TestCase):
    def test_generate_snapshot_content(self):
        from intelligence.snapshot import generate_snapshot_content

        content = generate_snapshot_content()
        assert "Business Snapshot" in content
        assert "Financial Summary" in content
        assert "CRM & Pipeline" in content
        assert "Development" in content
        assert "Operations" in content
