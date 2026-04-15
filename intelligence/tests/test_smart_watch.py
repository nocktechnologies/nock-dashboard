"""Tests for the Smart Watch feature."""
from __future__ import annotations

import os
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from intelligence.models import SmartWatchEvent, SmartWatchRule

_TEST_FERNET_KEYS = [os.environ.get("FERNET_KEYS", "rBj4e7L0PbE7E3H5JhLdOwvSXa3Z3g1mJbkBrkIg5cI=")]


def _make_rule(**kwargs) -> SmartWatchRule:
    defaults = {
        "name": "Test Rule",
        "condition_type": "pr_waiting",
        "threshold_minutes": 240,
        "severity": "warning",
        "message_template": "Alert: {name} — {value}/{threshold}",
        "enabled": True,
        "send_telegram": True,
        "cooldown_minutes": 60,
    }
    defaults.update(kwargs)
    return SmartWatchRule.objects.create(**defaults)


# ──────────────── Model Tests ────────────────


class SmartWatchRuleModelTest(TestCase):
    def test_create_rule(self):
        rule = _make_rule()
        assert rule.pk is not None
        assert str(rule) == "Test Rule (enabled)"

    def test_disabled_str(self):
        rule = _make_rule(enabled=False)
        assert "(disabled)" in str(rule)

    def test_in_cooldown_false_when_never_triggered(self):
        rule = _make_rule()
        assert not rule.in_cooldown

    def test_in_cooldown_true_when_recently_triggered(self):
        rule = _make_rule(cooldown_minutes=60)
        rule.last_triggered = timezone.now() - timedelta(minutes=30)
        rule.save()
        assert rule.in_cooldown

    def test_in_cooldown_false_when_cooldown_elapsed(self):
        rule = _make_rule(cooldown_minutes=60)
        rule.last_triggered = timezone.now() - timedelta(minutes=90)
        rule.save()
        assert not rule.in_cooldown

    def test_ordering(self):
        _make_rule(name="Critical Rule", severity="critical")
        _make_rule(name="Info Rule", severity="info")
        _make_rule(name="Warning Rule", severity="warning")
        rules = list(SmartWatchRule.objects.all())
        names = [r.name for r in rules]
        assert names.index("Critical Rule") < names.index("Info Rule")


class SmartWatchEventModelTest(TestCase):
    def test_create_event(self):
        rule = _make_rule()
        event = SmartWatchEvent.objects.create(
            rule=rule,
            message="Test alert fired",
            severity="warning",
            context={"key": "value"},
            notified=True,
        )
        assert event.pk is not None
        assert "[warning]" in str(event)

    def test_ordering(self):
        rule = _make_rule()
        SmartWatchEvent.objects.create(rule=rule, message="old", severity="info")
        e2 = SmartWatchEvent.objects.create(rule=rule, message="new", severity="info")
        events = list(SmartWatchEvent.objects.all())
        assert events[0].pk == e2.pk


# ──────────────── Evaluator Tests ────────────────


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class PRWaitingEvaluatorTest(TestCase):
    def test_returns_alerts_for_old_unreviewed_prs(self):
        from pipeline.models import PullRequest, Repository

        repo = Repository.objects.create(
            name="test-repo", owner="testowner",
            github_id=99990, webhook_secret="secret",
        )
        PullRequest.objects.create(
            repository=repo, github_pr_id=100, number=100,
            title="Old PR", branch="feature/old", author="dev",
            state="open", opened_at=timezone.now() - timedelta(hours=6),
        )
        rule = _make_rule(
            condition_type="pr_waiting",
            threshold_minutes=240,
            message_template="PR #{pr_number} on {repo} waiting {value}h",
        )

        from intelligence.smart_watch import check_pr_waiting
        alerts = check_pr_waiting(rule)
        assert len(alerts) == 1
        assert "#100" in alerts[0][0]

    def test_no_alert_for_recent_prs(self):
        from pipeline.models import PullRequest, Repository

        repo = Repository.objects.create(
            name="test-repo", owner="testowner",
            github_id=99991, webhook_secret="secret",
        )
        PullRequest.objects.create(
            repository=repo, github_pr_id=101, number=101,
            title="Fresh PR", branch="feature/new", author="dev",
            state="open", opened_at=timezone.now() - timedelta(hours=1),
        )
        rule = _make_rule(condition_type="pr_waiting", threshold_minutes=240)

        from intelligence.smart_watch import check_pr_waiting
        alerts = check_pr_waiting(rule)
        assert len(alerts) == 0


class SessionLongEvaluatorTest(TestCase):
    def test_returns_alerts_for_long_sessions(self):
        from sessions.models import AgentSession

        AgentSession.objects.create(
            agent="claude_code", status="active", branch="feature/test",
            started_at=timezone.now() - timedelta(hours=5),
        )
        rule = _make_rule(
            condition_type="session_long",
            threshold_minutes=180,
            message_template="Session on {project} running {value}",
        )

        from intelligence.smart_watch import check_session_long
        alerts = check_session_long(rule)
        assert len(alerts) == 1
        assert "5.0h" in alerts[0][0]

    def test_no_alert_for_short_sessions(self):
        from sessions.models import AgentSession

        AgentSession.objects.create(
            agent="claude_code", status="active", branch="feature/test",
            started_at=timezone.now() - timedelta(minutes=30),
        )
        rule = _make_rule(condition_type="session_long", threshold_minutes=180)

        from intelligence.smart_watch import check_session_long
        assert len(check_session_long(rule)) == 0


class TaskDueTomorrowEvaluatorTest(TestCase):
    def test_returns_alerts_for_tasks_due_tomorrow(self):
        from tasks.models import AsanaProject, AsanaTask

        project = AsanaProject.objects.create(
            asana_gid="proj1", name="Test Project",
        )
        tomorrow = (timezone.now() + timedelta(days=1)).date()
        AsanaTask.objects.create(
            asana_gid="task1", name="Finish report",
            section_name="To Do", assignee_name="Kevin",
            due_on=tomorrow, project=project,
        )
        rule = _make_rule(
            condition_type="task_due_tomorrow",
            message_template="Due tomorrow: {task_name} ({project})",
        )

        from intelligence.smart_watch import check_task_due_tomorrow
        alerts = check_task_due_tomorrow(rule)
        assert len(alerts) == 1
        assert "Finish report" in alerts[0][0]


class ContextHighEvaluatorTest(TestCase):
    def test_returns_alert_for_high_context(self):
        from sessions.models import TerminalHeartbeat

        TerminalHeartbeat.objects.create(
            machine="mac-test",
            sessions=[{"project": "nockcc", "branch": "main", "context_percent": 85}],
        )
        rule = _make_rule(
            condition_type="context_high",
            threshold_value=75,
            message_template="{project} at {value}% context",
        )

        from intelligence.smart_watch import check_context_high
        alerts = check_context_high(rule)
        assert len(alerts) == 1
        assert "85" in alerts[0][0]


# ──────────────── Celery Task Tests ────────────────


class SmartWatchTickTest(TestCase):
    @patch("core.telegram.TelegramNotifier")
    def test_tick_evaluates_enabled_rules(self, mock_telegram):
        from sessions.models import AgentSession

        AgentSession.objects.create(
            agent="claude_code", status="active", branch="feature/long",
            started_at=timezone.now() - timedelta(hours=5),
        )
        rule = _make_rule(
            name="Long Session Watch",
            condition_type="session_long",
            threshold_minutes=180,
            message_template="Session on {project} running {value}",
        )

        from intelligence.tasks import smart_watch_tick
        result = smart_watch_tick()

        assert result["alerts_fired"] >= 1
        assert SmartWatchEvent.objects.filter(rule=rule).exists()
        mock_telegram.send.assert_called()

    def test_tick_skips_disabled_rules(self):
        _make_rule(name="Disabled Rule", enabled=False)

        from intelligence.tasks import smart_watch_tick
        result = smart_watch_tick()
        assert result["alerts_fired"] == 0

    @patch("core.telegram.TelegramNotifier")
    def test_tick_respects_cooldown(self, mock_telegram):
        from sessions.models import AgentSession

        AgentSession.objects.create(
            agent="claude_code", status="active", branch="feature/test",
            started_at=timezone.now() - timedelta(hours=5),
        )
        rule = _make_rule(
            condition_type="session_long",
            threshold_minutes=180,
            cooldown_minutes=60,
            message_template="Session {project} {value}",
        )
        rule.last_triggered = timezone.now() - timedelta(minutes=30)
        rule.save()

        from intelligence.tasks import smart_watch_tick
        result = smart_watch_tick()
        assert result["alerts_fired"] == 0

    @patch("core.telegram.TelegramNotifier")
    def test_tick_updates_rule_trigger_state(self, mock_telegram):
        from sessions.models import AgentSession

        AgentSession.objects.create(
            agent="claude_code", status="active", branch="feature/long",
            started_at=timezone.now() - timedelta(hours=5),
        )
        rule = _make_rule(
            condition_type="session_long",
            threshold_minutes=180,
            message_template="Session {project} {value}",
        )

        from intelligence.tasks import smart_watch_tick
        smart_watch_tick()

        rule.refresh_from_db()
        assert rule.last_triggered is not None
        assert rule.trigger_count >= 1


# ──────────────── API Tests ────────────────


class SmartWatchAPITest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass", is_staff=True,
        )
        self.client.force_login(self.user)

    def test_rules_list(self):
        _make_rule(name="Rule A")
        _make_rule(name="Rule B", condition_type="session_long")
        resp = self.client.get("/intelligence/api/smart-watch/rules/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"]
        assert len(data["data"]) == 2

    def test_rules_create(self):
        resp = self.client.post(
            "/intelligence/api/smart-watch/rules/create/",
            data='{"name": "New Rule", "condition_type": "pr_waiting"}',
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["name"] == "New Rule"
        assert SmartWatchRule.objects.filter(name="New Rule").exists()

    def test_rules_create_invalid(self):
        resp = self.client.post(
            "/intelligence/api/smart-watch/rules/create/",
            data='{"name": ""}',
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_rules_update(self):
        rule = _make_rule()
        resp = self.client.put(
            f"/intelligence/api/smart-watch/rules/{rule.pk}/",
            data='{"enabled": false, "cooldown_minutes": 120}',
            content_type="application/json",
        )
        assert resp.status_code == 200
        rule.refresh_from_db()
        assert not rule.enabled
        assert rule.cooldown_minutes == 120

    def test_rules_update_404(self):
        resp = self.client.put(
            "/intelligence/api/smart-watch/rules/9999/",
            data='{"enabled": false}',
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_events_list(self):
        rule = _make_rule()
        SmartWatchEvent.objects.create(
            rule=rule, message="Test event", severity="warning",
        )
        resp = self.client.get("/intelligence/api/smart-watch/events/")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    @patch("core.telegram.TelegramNotifier")
    def test_force_tick(self, mock_telegram):
        resp = self.client.post("/intelligence/api/smart-watch/tick/")
        assert resp.status_code == 200
        assert resp.json()["data"]["rules_evaluated"] == 0

    def test_status(self):
        _make_rule()
        resp = self.client.get("/intelligence/api/smart-watch/status/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_rules"] == 1
        assert data["enabled_rules"] == 1
        assert data["events_today"] == 0


# ──────────────── Seed Command Test ────────────────


class SeedSmartWatchTest(TestCase):
    def test_seed_creates_default_rules(self):
        from django.core.management import call_command

        call_command("seed_smart_watch")
        assert SmartWatchRule.objects.count() == 4

    def test_seed_is_idempotent(self):
        from django.core.management import call_command

        call_command("seed_smart_watch")
        call_command("seed_smart_watch")
        assert SmartWatchRule.objects.count() == 4
