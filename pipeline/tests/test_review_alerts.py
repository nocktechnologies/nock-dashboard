"""
Tests for ReviewAlert model, reviewer classification, webhook integration,
deduplication, API endpoints, and TelegramNotifier.
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from core.telegram import TelegramNotifier
from pipeline.models import (
    PullRequest,
    Repository,
    ReviewAlert,
    classify_reviewer,
)
from pipeline.tasks import process_check_run, process_pull_request_review

_TEST_FERNET_KEYS = ["rBj4e7L0PbE7E3H5JhLdOwvSXa3Z3g1mJbkBrkIg5cI="]
_TEST_SECRET = "test-webhook-secret-for-tests-only"
_TEST_API_KEY = "test-api-key-for-tests"


def _make_repo(secret: str = _TEST_SECRET) -> Repository:
    return Repository.objects.create(
        name="nock-command-center",
        owner="kkwills13",
        github_id=12345,
        webhook_secret=secret,
    )


def _make_pr(repo: Repository, number: int = 42) -> PullRequest:
    return PullRequest.objects.create(
        repository=repo,
        github_pr_id=999,
        number=number,
        title="feat: add widget",
        branch="feature/widget",
        author="kev",
        state=PullRequest.State.OPEN,
        opened_at=datetime(2026, 3, 14, 10, 0, tzinfo=UTC),
    )


def _review_payload(
    login: str = "coderabbitai[bot]",
    state: str = "approved",
    body: str = "looks good",
    pr_number: int = 42,
) -> dict[str, Any]:
    return {
        "action": "submitted",
        "review": {
            "user": {"login": login, "type": "Bot"},
            "state": state,
            "body": body,
            "submitted_at": "2026-03-14T11:00:00Z",
        },
        "pull_request": {
            "id": 999,
            "number": pr_number,
            "title": "feat: add widget",
            "html_url": f"https://github.com/kkwills13/nock-command-center/pull/{pr_number}",
            "head": {"ref": "feature/widget"},
            "user": {"login": "kev"},
            "state": "open",
            "merged": False,
            "changed_files": 3,
            "additions": 50,
            "deletions": 10,
            "created_at": "2026-03-14T10:00:00Z",
            "merged_at": None,
            "closed_at": None,
        },
        "repository": {"full_name": "kkwills13/nock-command-center"},
    }


def _check_payload(
    conclusion: str = "success",
    status: str = "completed",
    pr_number: int = 42,
    check_name: str = "pytest",
) -> dict[str, Any]:
    return {
        "action": "completed",
        "check_run": {
            "id": 1,
            "name": check_name,
            "status": status,
            "conclusion": conclusion,
            "html_url": "https://github.com/kkwills13/nock-command-center/runs/1",
            "pull_requests": [{"number": pr_number}],
            "output": {"text": None},
            "app": {"slug": "github-actions"},
        },
        "repository": {"full_name": "kkwills13/nock-command-center"},
    }


# --- Model creation ---


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class ReviewAlertModelTests(TestCase):
    def test_create_review_alert(self):
        alert = ReviewAlert.objects.create(
            repo="kkwills13/nock-command-center",
            pr_number=32,
            pr_title="Brain App + Nerve Center",
            pr_url="https://github.com/kkwills13/nock-command-center/pull/32",
            branch="feature/brain-nerve-center",
            reviewer="coderabbit",
            reviewer_login="coderabbitai[bot]",
            status="approved",
            body_preview="Looks great!",
        )
        self.assertEqual(alert.pr_number, 32)
        self.assertEqual(alert.reviewer, "coderabbit")
        self.assertFalse(alert.is_read)

    def test_str_representation(self):
        alert = ReviewAlert.objects.create(
            repo="kkwills13/nock-command-center",
            pr_number=32,
            pr_title="Brain App",
            pr_url="https://github.com/kkwills13/nock-command-center/pull/32",
            reviewer="coderabbit",
            reviewer_login="coderabbitai[bot]",
            status="approved",
        )
        self.assertIn("coderabbit", str(alert))
        self.assertIn("#32", str(alert))

    def test_ordering_newest_first(self):
        ReviewAlert.objects.create(
            repo="r", pr_number=1, pr_title="A", pr_url="http://x",
            reviewer="human", reviewer_login="a", status="approved",
        )
        ReviewAlert.objects.create(
            repo="r", pr_number=2, pr_title="B", pr_url="http://x",
            reviewer="human", reviewer_login="b", status="approved",
        )
        alerts = list(ReviewAlert.objects.all())
        self.assertEqual(alerts[0].pr_number, 2)  # newest first


# --- Reviewer classification ---


class ClassifyReviewerTests(TestCase):
    def test_coderabbit_bot(self):
        self.assertEqual(classify_reviewer("coderabbitai[bot]"), "coderabbit")

    def test_coderabbit_plain(self):
        self.assertEqual(classify_reviewer("coderabbitai"), "coderabbit")

    def test_copilot_bot(self):
        self.assertEqual(classify_reviewer("copilot[bot]"), "copilot")

    def test_github_copilot_bot(self):
        self.assertEqual(classify_reviewer("github-copilot[bot]"), "copilot")

    def test_gemini_code_review_bot(self):
        self.assertEqual(classify_reviewer("gemini-code-review[bot]"), "gemini")

    def test_gemini_bot(self):
        self.assertEqual(classify_reviewer("gemini[bot]"), "gemini")

    def test_unknown_bot_is_ci(self):
        self.assertEqual(classify_reviewer("some-other[bot]"), "ci")

    def test_human_reviewer(self):
        self.assertEqual(classify_reviewer("kevdev"), "human")

    def test_case_insensitive(self):
        self.assertEqual(classify_reviewer("CodeRabbitAI[bot]"), "coderabbit")


# --- Webhook tasks → ReviewAlert creation ---


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, TELEGRAM_ENABLED=False)
class ReviewWebhookAlertTests(TestCase):
    def setUp(self):
        self.repo = _make_repo()
        self.pr = _make_pr(self.repo)

    def test_review_approved_creates_alert(self):
        payload = _review_payload("coderabbitai[bot]", "approved")
        process_pull_request_review.apply(args=[payload, "del-ra-1"])
        self.assertEqual(ReviewAlert.objects.count(), 1)
        alert = ReviewAlert.objects.get()
        self.assertEqual(alert.reviewer, "coderabbit")
        self.assertEqual(alert.status, "approved")
        self.assertEqual(alert.pr_number, 42)

    def test_review_changes_requested_creates_alert(self):
        payload = _review_payload("copilot[bot]", "changes_requested")
        process_pull_request_review.apply(args=[payload, "del-ra-2"])
        alert = ReviewAlert.objects.get()
        self.assertEqual(alert.reviewer, "copilot")
        self.assertEqual(alert.status, "changes_requested")

    def test_review_commented_creates_alert(self):
        payload = _review_payload("humandev", "commented", "nice work")
        process_pull_request_review.apply(args=[payload, "del-ra-3"])
        alert = ReviewAlert.objects.get()
        self.assertEqual(alert.reviewer, "human")
        self.assertEqual(alert.status, "commented")
        self.assertEqual(alert.body_preview, "nice work")

    def test_check_run_success_creates_alert(self):
        payload = _check_payload("success")
        process_check_run.apply(args=[payload, "del-ra-4"])
        self.assertEqual(ReviewAlert.objects.count(), 1)
        alert = ReviewAlert.objects.get()
        self.assertEqual(alert.reviewer, "ci")
        self.assertEqual(alert.status, "success")

    def test_check_run_failure_creates_alert(self):
        payload = _check_payload("failure")
        process_check_run.apply(args=[payload, "del-ra-5"])
        alert = ReviewAlert.objects.get()
        self.assertEqual(alert.status, "failure")

    def test_check_run_in_progress_no_alert(self):
        payload = _check_payload(None, status="in_progress")
        process_check_run.apply(args=[payload, "del-ra-6"])
        self.assertEqual(ReviewAlert.objects.count(), 0)

    def test_body_preview_truncated_to_500(self):
        long_body = "x" * 1000
        payload = _review_payload("coderabbitai[bot]", "commented", long_body)
        process_pull_request_review.apply(args=[payload, "del-ra-7"])
        alert = ReviewAlert.objects.get()
        self.assertEqual(len(alert.body_preview), 500)


# --- Deduplication ---


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, TELEGRAM_ENABLED=False)
class DeduplicationTests(TestCase):
    def setUp(self):
        self.repo = _make_repo()
        self.pr = _make_pr(self.repo)

    def test_duplicate_review_within_60s_not_created(self):
        payload = _review_payload("coderabbitai[bot]", "approved")
        process_pull_request_review.apply(args=[payload, "del-dedup-1"])
        self.assertEqual(ReviewAlert.objects.count(), 1)

        # Same reviewer + PR + status within 60s (different delivery_id)
        process_pull_request_review.apply(args=[payload, "del-dedup-2"])
        self.assertEqual(ReviewAlert.objects.count(), 1)

    def test_different_status_not_deduped(self):
        payload1 = _review_payload("coderabbitai[bot]", "commented")
        process_pull_request_review.apply(args=[payload1, "del-dedup-3"])

        payload2 = _review_payload("coderabbitai[bot]", "approved")
        process_pull_request_review.apply(args=[payload2, "del-dedup-4"])
        self.assertEqual(ReviewAlert.objects.count(), 2)


# --- API endpoints ---


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY=_TEST_API_KEY)
class ReviewAlertAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(self.user)
        # Create some alerts
        for i in range(3):
            ReviewAlert.objects.create(
                repo="kkwills13/nock-command-center",
                pr_number=30 + i,
                pr_title=f"PR #{30 + i}",
                pr_url=f"https://github.com/kkwills13/nock-command-center/pull/{30 + i}",
                reviewer="coderabbit",
                reviewer_login="coderabbitai[bot]",
                status="approved",
            )

    def test_list_returns_alerts(self):
        resp = self.client.get("/api/alerts/reviews/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["data"]["alerts"]), 3)

    def test_list_filter_by_repo(self):
        ReviewAlert.objects.create(
            repo="kkwills13/other-repo", pr_number=1, pr_title="Other",
            pr_url="http://x", reviewer="human", reviewer_login="dev", status="approved",
        )
        resp = self.client.get("/api/alerts/reviews/?repo=kkwills13/other-repo")
        data = resp.json()
        self.assertEqual(len(data["data"]["alerts"]), 1)

    def test_mark_read_specific_ids(self):
        ids = list(ReviewAlert.objects.values_list("id", flat=True)[:2])
        resp = self.client.post(
            "/api/alerts/reviews/read/",
            data=json.dumps({"ids": ids}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["data"]["marked"], 2)
        self.assertEqual(ReviewAlert.objects.filter(is_read=True).count(), 2)

    def test_mark_read_all(self):
        resp = self.client.post(
            "/api/alerts/reviews/read/",
            data=json.dumps({"all": True}),
            content_type="application/json",
        )
        data = resp.json()
        self.assertEqual(data["data"]["marked"], 3)
        self.assertEqual(ReviewAlert.objects.filter(is_read=False).count(), 0)

    def test_summary_returns_unread_count(self):
        resp = self.client.get("/api/alerts/reviews/summary/")
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["unread_count"], 3)
        self.assertIn("alerts", data["data"])
        self.assertIn("by_pr", data["data"])


# --- TelegramNotifier ---


@override_settings(
    TELEGRAM_ENABLED=True,
    TELEGRAM_BOT_TOKEN="test-token",
    TELEGRAM_CHAT_ID="12345",
    TELEGRAM_QUIET_START=0,
    TELEGRAM_QUIET_END=0,
)
class TelegramNotifierTests(TestCase):
    @patch("core.telegram.httpx.post")
    def test_send_with_valid_config(self, mock_post):
        mock_post.return_value.json.return_value = {"ok": True, "result": {}}
        result = TelegramNotifier.send("Hello test")
        self.assertTrue(result["ok"])
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        self.assertIn("test-token", call_kwargs[0][0])
        self.assertEqual(call_kwargs[1]["json"]["chat_id"], "12345")

    @override_settings(TELEGRAM_ENABLED=False)
    def test_send_disabled_returns_none(self):
        result = TelegramNotifier.send("Hello")
        self.assertIsNone(result)

    @override_settings(TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID="")
    def test_send_missing_config_returns_none(self):
        result = TelegramNotifier.send("Hello")
        self.assertIsNone(result)

    @override_settings(TELEGRAM_QUIET_START=23, TELEGRAM_QUIET_END=7)
    @patch("core.telegram.dj_timezone")
    def test_quiet_hours_midnight_crossing(self, mock_tz):
        # 23:00 should be quiet (between 23 and 7)
        mock_tz.localtime.return_value.hour = 23
        self.assertTrue(TelegramNotifier._is_quiet_hours())

    @override_settings(TELEGRAM_QUIET_START=23, TELEGRAM_QUIET_END=7)
    @patch("core.telegram.dj_timezone")
    def test_not_quiet_hours(self, mock_tz):
        # 12:00 should not be quiet
        mock_tz.localtime.return_value.hour = 12
        self.assertFalse(TelegramNotifier._is_quiet_hours())

    @patch("core.telegram.httpx.post")
    def test_message_truncated_to_4096(self, mock_post):
        mock_post.return_value.json.return_value = {"ok": True}
        long_msg = "x" * 5000
        TelegramNotifier.send(long_msg)
        sent_text = mock_post.call_args[1]["json"]["text"]
        self.assertEqual(len(sent_text), 4096)


# --- Webhook endpoint integration ---


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, CELERY_TASK_ALWAYS_EAGER=True, TELEGRAM_ENABLED=False)
class WebhookReviewAlertIntegrationTests(TestCase):
    """Test that the full webhook → ReviewAlert pipeline works end-to-end."""

    def setUp(self):
        self.repo = _make_repo()
        self.pr = _make_pr(self.repo)

    def _sign(self, body: bytes) -> str:
        return "sha256=" + hmac.new(_TEST_SECRET.encode(), body, hashlib.sha256).hexdigest()

    def test_pull_request_review_webhook_creates_alert(self):
        payload = _review_payload("gemini-code-review[bot]", "approved")
        body = json.dumps(payload).encode()
        resp = self.client.post(
            "/webhooks/github/",
            data=body,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="pull_request_review",
            HTTP_X_HUB_SIGNATURE_256=self._sign(body),
            HTTP_X_GITHUB_DELIVERY="del-int-1",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ReviewAlert.objects.count(), 1)
        alert = ReviewAlert.objects.get()
        self.assertEqual(alert.reviewer, "gemini")

    def test_check_run_webhook_creates_alert(self):
        payload = _check_payload("failure", check_name="CodeRabbit")
        body = json.dumps(payload).encode()
        resp = self.client.post(
            "/webhooks/github/",
            data=body,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="check_run",
            HTTP_X_HUB_SIGNATURE_256=self._sign(body),
            HTTP_X_GITHUB_DELIVERY="del-int-2",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ReviewAlert.objects.count(), 1)
        alert = ReviewAlert.objects.get()
        self.assertEqual(alert.status, "failure")
        self.assertEqual(alert.reviewer_login, "CodeRabbit")
