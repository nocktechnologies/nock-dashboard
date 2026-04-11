"""
Tests for GitHub webhook receiver and Celery event-processing tasks.

Tasks are called synchronously via .apply() — no Celery worker needed.
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

from django.test import Client, TestCase, override_settings

from pipeline.models import Branch, BranchEvent, PREvent, PullRequest, Repository
from pipeline.tasks import (
    process_check_run,
    process_pull_request_event,
    process_pull_request_review,
    process_push,
)

WEBHOOK_URL = "/webhooks/github/"
# These are test-only dummy values — not real credentials
_TEST_SECRET = "test-webhook-secret-for-tests-only"
_TEST_FERNET_KEYS = ["rBj4e7L0PbE7E3H5JhLdOwvSXa3Z3g1mJbkBrkIg5cI="]


def _sign(body: bytes, secret: str = _TEST_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _post(
    client: Client,
    payload: dict[str, Any],
    event: str = "pull_request",
    secret: str = _TEST_SECRET,
    delivery: str = "abc-123",
) -> Any:
    body = json.dumps(payload).encode()
    sig = _sign(body, secret)
    return client.post(
        WEBHOOK_URL,
        data=body,
        content_type="application/json",
        HTTP_X_GITHUB_EVENT=event,
        HTTP_X_HUB_SIGNATURE_256=sig,
        HTTP_X_GITHUB_DELIVERY=delivery,
    )


def make_repo(secret: str = _TEST_SECRET) -> Repository:
    return Repository.objects.create(
        name="nock-command-center",
        owner="kkwills13",
        github_id=12345,
        webhook_secret=secret,
    )


def make_pr_payload(action: str = "opened", merged: bool = False, number: int = 42) -> dict[str, Any]:
    return {
        "action": action,
        "pull_request": {
            "id": 999,
            "number": number,
            "title": "feat: add widget",
            "head": {"ref": "feature/widget"},
            "user": {"login": "kev"},
            "state": "open",
            "merged": merged,
            "changed_files": 3,
            "additions": 50,
            "deletions": 10,
            "created_at": "2026-03-14T10:00:00Z",
            "merged_at": "2026-03-14T11:00:00Z" if merged else None,
            "closed_at": "2026-03-14T11:00:00Z",
        },
        "sender": {"login": "kev"},
        "repository": {"full_name": "kkwills13/nock-command-center"},
    }


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, CELERY_TASK_ALWAYS_EAGER=True)
class WebhookEndpointTests(TestCase):
    def setUp(self):
        self.repo = make_repo()

    # --- Signature / auth ---

    def test_valid_signature_returns_200(self):
        payload = make_pr_payload()
        resp = _post(self.client, payload)
        self.assertEqual(resp.status_code, 200)

    def test_invalid_signature_returns_403(self):
        payload = make_pr_payload()
        body = json.dumps(payload).encode()
        resp = self.client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="pull_request",
            HTTP_X_HUB_SIGNATURE_256="sha256=badhash",
            HTTP_X_GITHUB_DELIVERY="del-1",
        )
        self.assertEqual(resp.status_code, 403)

    def test_missing_signature_returns_403(self):
        body = json.dumps(make_pr_payload()).encode()
        resp = self.client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="pull_request",
            HTTP_X_GITHUB_DELIVERY="del-2",
        )
        self.assertEqual(resp.status_code, 403)

    def test_unknown_repo_returns_404(self):
        payload = make_pr_payload()
        payload["repository"]["full_name"] = "unknown/repo"
        body = json.dumps(payload).encode()
        sig = _sign(body)
        resp = self.client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="pull_request",
            HTTP_X_HUB_SIGNATURE_256=sig,
            HTTP_X_GITHUB_DELIVERY="del-3",
        )
        self.assertEqual(resp.status_code, 404)

    def test_ping_event_returns_pong(self):
        resp = self.client.post(
            WEBHOOK_URL,
            data=b'{"zen":"Keep it logically awesome"}',
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="ping",
            HTTP_X_GITHUB_DELIVERY="del-ping",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["message"], "pong")

    def test_missing_event_header_returns_400(self):
        body = json.dumps(make_pr_payload()).encode()
        resp = self.client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_missing_delivery_id_returns_400(self):
        body = json.dumps(make_pr_payload()).encode()
        sig = _sign(body)
        resp = self.client.post(
            WEBHOOK_URL,
            data=body,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="pull_request",
            HTTP_X_HUB_SIGNATURE_256=sig,
            # No HTTP_X_GITHUB_DELIVERY header
        )
        self.assertEqual(resp.status_code, 400)

    # --- Response envelope ---

    def test_accepted_response_envelope(self):
        resp = _post(self.client, make_pr_payload())
        data = resp.json()
        self.assertIn("success", data)
        self.assertIn("message", data)
        self.assertIn("data", data)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class PREventTaskTests(TestCase):
    def setUp(self):
        self.repo = make_repo()

    def test_pr_opened_creates_pull_request(self):
        payload = make_pr_payload("opened")
        process_pull_request_event.apply(args=[payload, "opened", "del-open-1"])
        self.assertEqual(PullRequest.objects.count(), 1)
        pr = PullRequest.objects.get()
        self.assertEqual(pr.title, "feat: add widget")
        self.assertEqual(pr.branch, "feature/widget")
        self.assertEqual(pr.author, "kev")
        self.assertEqual(pr.state, PullRequest.State.OPEN)

    def test_pr_opened_creates_pr_event(self):
        payload = make_pr_payload("opened")
        process_pull_request_event.apply(args=[payload, "opened", "del-open-2"])
        self.assertEqual(PREvent.objects.filter(event_type="opened").count(), 1)

    def test_pr_merged_updates_state(self):
        pr = PullRequest.objects.create(
            repository=self.repo, github_pr_id=999, number=42,
            title="feat: add widget", branch="feature/widget", author="kev",
            state=PullRequest.State.OPEN,
            opened_at=datetime(2026, 3, 14, 10, 0, tzinfo=UTC),
        )
        payload = make_pr_payload("closed", merged=True)
        process_pull_request_event.apply(args=[payload, "closed", "del-close-1"])
        pr.refresh_from_db()
        self.assertEqual(pr.state, PullRequest.State.MERGED)
        self.assertIsNotNone(pr.merged_at)

    def test_pr_closed_without_merge(self):
        PullRequest.objects.create(
            repository=self.repo, github_pr_id=999, number=42,
            title="feat: add widget", branch="feature/widget", author="kev",
            state=PullRequest.State.OPEN,
            opened_at=datetime(2026, 3, 14, 10, 0, tzinfo=UTC),
        )
        payload = make_pr_payload("closed", merged=False)
        process_pull_request_event.apply(args=[payload, "closed", "del-close-2"])
        pr = PullRequest.objects.get()
        self.assertEqual(pr.state, PullRequest.State.CLOSED)
        self.assertIsNone(pr.merged_at)

    def test_pr_reopened_sets_state_open(self):
        pr = PullRequest.objects.create(
            repository=self.repo, github_pr_id=999, number=42,
            title="feat: add widget", branch="feature/widget", author="kev",
            state=PullRequest.State.CLOSED,
            opened_at=datetime(2026, 3, 14, 10, 0, tzinfo=UTC),
        )
        payload = make_pr_payload("reopened")
        process_pull_request_event.apply(args=[payload, "reopened", "del-reopen-1"])
        pr.refresh_from_db()
        self.assertEqual(pr.state, PullRequest.State.OPEN)

    def test_pr_edited_updates_title(self):
        pr = PullRequest.objects.create(
            repository=self.repo, github_pr_id=999, number=42,
            title="old title", branch="feature/widget", author="kev",
            state=PullRequest.State.OPEN,
            opened_at=datetime(2026, 3, 14, 10, 0, tzinfo=UTC),
        )
        payload = make_pr_payload("edited")
        payload["pull_request"]["title"] = "feat: add widget"
        process_pull_request_event.apply(args=[payload, "edited", "del-edit-1"])
        pr.refresh_from_db()
        self.assertEqual(pr.title, "feat: add widget")

    def test_duplicate_delivery_id_skipped(self):
        payload = make_pr_payload("opened")
        process_pull_request_event.apply(args=[payload, "opened", "del-dup-1"])
        process_pull_request_event.apply(args=[payload, "opened", "del-dup-1"])
        self.assertEqual(PullRequest.objects.count(), 1)
        self.assertEqual(PREvent.objects.count(), 1)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class ReviewTaskTests(TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.pr = PullRequest.objects.create(
            repository=self.repo, github_pr_id=999, number=42,
            title="feat: add widget", branch="feature/widget", author="kev",
            state=PullRequest.State.OPEN,
            opened_at=datetime(2026, 3, 14, 10, 0, tzinfo=UTC),
        )

    def _review_payload(self, login: str, state: str, user_type: str = "User") -> dict[str, Any]:
        return {
            "review": {"user": {"login": login, "type": user_type}, "state": state, "body": "looks good"},
            "pull_request": {
                "id": 999, "number": 42, "title": "feat: add widget",
                "head": {"ref": "feature/widget"}, "user": {"login": "kev"},
                "state": "open", "merged": False, "changed_files": 3,
                "additions": 50, "deletions": 10,
                "created_at": "2026-03-14T10:00:00Z",
                "merged_at": None, "closed_at": None,
            },
            "repository": {"full_name": "kkwills13/nock-command-center"},
        }

    def test_coderabbit_approved(self):
        payload = self._review_payload("coderabbitai[bot]", "approved", "Bot")
        process_pull_request_review.apply(args=[payload, "del-rev-1"])
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.coderabbit_status, PullRequest.CodeRabbitStatus.APPROVED)

    def test_coderabbit_changes_requested(self):
        payload = self._review_payload("coderabbitai[bot]", "changes_requested", "Bot")
        process_pull_request_review.apply(args=[payload, "del-rev-2"])
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.coderabbit_status, PullRequest.CodeRabbitStatus.CHANGES_REQUESTED)

    def test_human_review_does_not_change_coderabbit_status(self):
        payload = self._review_payload("humandev", "approved", "User")
        process_pull_request_review.apply(args=[payload, "del-rev-3"])
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.coderabbit_status, PullRequest.CodeRabbitStatus.PENDING)

    def test_review_creates_pr_event(self):
        payload = self._review_payload("coderabbitai[bot]", "commented", "Bot")
        process_pull_request_review.apply(args=[payload, "del-rev-4"])
        self.assertEqual(PREvent.objects.filter(event_type="review_submitted").count(), 1)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class CheckRunTaskTests(TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.pr = PullRequest.objects.create(
            repository=self.repo, github_pr_id=999, number=42,
            title="feat: add widget", branch="feature/widget", author="kev",
            state=PullRequest.State.OPEN,
            opened_at=datetime(2026, 3, 14, 10, 0, tzinfo=UTC),
        )

    def _check_payload(self, conclusion: str | None, status: str = "completed", output_text: str | None = None) -> dict[str, Any]:
        return {
            "check_run": {
                "id": 1,
                "name": "pytest",
                "status": status,
                "conclusion": conclusion,
                "pull_requests": [{"number": 42}],
                "output": {"text": output_text},
                "app": {"slug": "github-actions"},
            },
            "repository": {"full_name": "kkwills13/nock-command-center"},
        }

    def test_ci_success_sets_passed(self):
        payload = self._check_payload("success")
        process_check_run.apply(args=[payload, "del-ci-1"])
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.ci_status, PullRequest.CIStatus.PASSED)

    def test_ci_failure_sets_failed(self):
        payload = self._check_payload("failure")
        process_check_run.apply(args=[payload, "del-ci-2"])
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.ci_status, PullRequest.CIStatus.FAILED)

    def test_ci_in_progress_sets_running(self):
        payload = self._check_payload(None, status="in_progress")
        process_check_run.apply(args=[payload, "del-ci-3"])
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.ci_status, PullRequest.CIStatus.RUNNING)

    def test_test_counts_parsed_from_output(self):
        payload = self._check_payload("success", output_text="42 passed, 3 failed in 12.3s")
        process_check_run.apply(args=[payload, "del-ci-4"])
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.tests_passed, 42)
        self.assertEqual(self.pr.tests_failed, 3)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class PushTaskTests(TestCase):
    def setUp(self):
        self.repo = make_repo()

    def _push_payload(self, branch: str = "feature/widget", deleted: bool = False) -> dict[str, Any]:
        return {
            "ref": f"refs/heads/{branch}",
            "deleted": deleted,
            "head_commit": {
                "id": "abc123def456abc123def456abc123def456abc1",
                "message": "feat: add widget",
                "timestamp": "2026-03-14T10:00:00Z",
            },
            "repository": {"full_name": "kkwills13/nock-command-center"},
        }

    def test_push_creates_branch(self):
        process_push.apply(args=[self._push_payload(), "del-push-1"])
        self.assertEqual(Branch.objects.count(), 1)
        branch = Branch.objects.get()
        self.assertEqual(branch.name, "feature/widget")
        self.assertEqual(branch.last_commit_sha, "abc123def456abc123def456abc123def456abc1")
        self.assertTrue(branch.is_active)

    def test_push_updates_existing_branch(self):
        Branch.objects.create(
            repository=self.repo, name="feature/widget",
            last_commit_sha="old000", last_commit_message="old",
        )
        process_push.apply(args=[self._push_payload(), "del-push-2"])
        branch = Branch.objects.get()
        self.assertEqual(branch.last_commit_sha, "abc123def456abc123def456abc123def456abc1")

    def test_branch_deleted_sets_inactive(self):
        Branch.objects.create(
            repository=self.repo, name="feature/widget",
            last_commit_sha="abc123", is_active=True,
        )
        process_push.apply(args=[self._push_payload(deleted=True), "del-push-3"])
        branch = Branch.objects.get()
        self.assertFalse(branch.is_active)

    def test_duplicate_push_delivery_skipped(self):
        process_push.apply(args=[self._push_payload(), "del-push-dup"])
        process_push.apply(args=[self._push_payload(), "del-push-dup"])
        self.assertEqual(Branch.objects.count(), 1)
        self.assertEqual(BranchEvent.objects.count(), 1)
