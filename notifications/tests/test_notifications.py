"""Tests for the notifications app — models, notifier, views, commands."""

import os
from io import StringIO
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from notifications.models import NotificationChannel, NotificationLog, NotificationRule
from workspaces.models import Workspace, WorkspaceMembership
from notifications.notifier import (
    format_discord_message,
    format_slack_message,
    send_notification,
    trigger_event,
)

_TEST_FERNET_KEYS = [os.environ.get("TEST_FERNET_KEY", "")]


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class NotificationChannelModelTests(TestCase):
    def test_create_channel(self) -> None:
        ch = NotificationChannel.objects.create(
            name="Test Slack",
            channel_type="slack",
            webhook_url="https://hooks.slack.com/test",
        )
        self.assertEqual(str(ch), "Test Slack (slack)")
        self.assertTrue(ch.is_active)

    def test_create_rule(self) -> None:
        ch = NotificationChannel.objects.create(
            name="Slack", channel_type="slack", webhook_url="https://hooks.slack.com/test",
        )
        rule = NotificationRule.objects.create(
            name="PR Merged", trigger_event="pr_merged", channel=ch,
        )
        self.assertEqual(str(rule), "PR Merged → PR Merged")

    def test_create_log(self) -> None:
        ch = NotificationChannel.objects.create(
            name="Slack", channel_type="slack", webhook_url="https://hooks.slack.com/test",
        )
        log = NotificationLog.objects.create(
            channel=ch, event_type="pr_merged", success=True, payload={"title": "Test"},
        )
        self.assertIn("OK", str(log))

    def test_failed_log(self) -> None:
        ch = NotificationChannel.objects.create(
            name="Slack", channel_type="slack", webhook_url="https://hooks.slack.com/test",
        )
        log = NotificationLog.objects.create(
            channel=ch, event_type="ci_failed", success=False, error_message="Timeout",
        )
        self.assertIn("FAIL", str(log))


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class NotifierTests(TestCase):
    def setUp(self) -> None:
        self.channel = NotificationChannel.objects.create(
            name="Test Slack",
            channel_type="slack",
            webhook_url="https://hooks.slack.com/test/123",
        )

    def test_format_slack_message(self) -> None:
        msg = format_slack_message("pr_merged", {"title": "PR #7 Merged", "message": "Context map", "repo": "nockcc"})
        self.assertIn("blocks", msg)
        self.assertEqual(msg["blocks"][0]["type"], "header")

    def test_format_discord_message(self) -> None:
        msg = format_discord_message("ci_failed", {"title": "CI Failed", "message": "Tests broke", "repo": "nockcc"})
        self.assertIn("embeds", msg)
        self.assertEqual(msg["embeds"][0]["color"], 0xFF0000)

    @patch("notifications.notifier.requests.post")
    def test_send_notification_success(self, mock_post: MagicMock) -> None:
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = MagicMock()

        result = send_notification(self.channel, "pr_merged", {"title": "Test"})
        self.assertTrue(result)
        self.assertEqual(NotificationLog.objects.count(), 1)
        self.assertTrue(NotificationLog.objects.first().success)

    @patch("notifications.notifier.requests.post")
    def test_send_notification_failure(self, mock_post: MagicMock) -> None:
        import requests
        mock_post.side_effect = requests.RequestException("Connection refused")

        result = send_notification(self.channel, "ci_failed", {"title": "Test"})
        self.assertFalse(result)
        self.assertEqual(NotificationLog.objects.count(), 1)
        log = NotificationLog.objects.first()
        self.assertFalse(log.success)
        self.assertIn("Connection refused", log.error_message)

    @patch("notifications.notifier.requests.post")
    def test_trigger_event_sends_to_matching_rules(self, mock_post: MagicMock) -> None:
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = MagicMock()

        NotificationRule.objects.create(
            name="PR Alert", trigger_event="pr_merged", channel=self.channel,
        )
        NotificationRule.objects.create(
            name="CI Alert", trigger_event="ci_failed", channel=self.channel,
        )

        sent = trigger_event("pr_merged", {"title": "Test"})
        self.assertEqual(sent, 1)
        self.assertEqual(NotificationLog.objects.filter(event_type="pr_merged").count(), 1)

    @patch("notifications.notifier.requests.post")
    def test_notification_log_records_delivery(self, mock_post: MagicMock) -> None:
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = MagicMock()

        rule = NotificationRule.objects.create(
            name="Budget Alert", trigger_event="budget_threshold", channel=self.channel,
        )
        send_notification(self.channel, "budget_threshold", {"title": "Over budget"}, rule=rule)

        log = NotificationLog.objects.first()
        self.assertEqual(log.rule, rule)
        self.assertEqual(log.event_type, "budget_threshold")
        self.assertTrue(log.success)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class NotificationViewTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(self.user)
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=self.user, role=WorkspaceMembership.ROLE_OWNER,
            accepted_at=timezone.now(),
        )

    def test_notification_list_returns_200(self) -> None:
        resp = self.client.get("/notifications/")
        self.assertEqual(resp.status_code, 200)

    def test_notification_list_shows_logs(self) -> None:
        ch = NotificationChannel.objects.create(
            name="Slack", channel_type="slack", webhook_url="https://test.com",
            workspace=self.workspace,
        )
        NotificationLog.objects.create(
            channel=ch, event_type="pr_merged", success=True,
            workspace=self.workspace,
        )
        resp = self.client.get("/notifications/")
        self.assertContains(resp, "pr_merged")


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, SLACK_WEBHOOK_URL="", DISCORD_WEBHOOK_URL="")
class SeedNotificationsTests(TestCase):
    def test_seed_creates_channels_and_rules(self) -> None:
        out = StringIO()
        call_command("seed_notifications", stdout=out)
        self.assertEqual(NotificationChannel.objects.count(), 2)
        self.assertEqual(NotificationRule.objects.count(), 4)
        self.assertIn("Done", out.getvalue())

    def test_seed_idempotent(self) -> None:
        call_command("seed_notifications", stdout=StringIO())
        call_command("seed_notifications", stdout=StringIO())
        self.assertEqual(NotificationChannel.objects.count(), 2)
        self.assertEqual(NotificationRule.objects.count(), 4)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class ErrorPageTests(TestCase):
    def test_404_page_renders(self) -> None:
        resp = self.client.get("/nonexistent-page-that-does-not-exist/")
        self.assertEqual(resp.status_code, 404)

    def test_readme_exists(self) -> None:
        from pathlib import Path
        readme = Path(__file__).resolve().parent.parent.parent / "README.md"
        self.assertTrue(readme.exists())
        content = readme.read_text()
        self.assertIn("Setup", content)
        self.assertIn("NockCC", content)
