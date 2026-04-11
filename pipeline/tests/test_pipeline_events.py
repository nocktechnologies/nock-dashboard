"""Tests for PipelineEvent model and API endpoints."""

import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from pipeline.models import PipelineEvent

_TEST_FERNET_KEYS = ["rBj4e7L0PbE7E3H5JhLdOwvSXa3Z3g1mJbkBrkIg5cI="]
_TEST_API_KEY = "test-api-key-for-tests"


def _api_headers() -> dict:
    return {"HTTP_X_API_KEY": _TEST_API_KEY}


def _make_event(**kwargs) -> PipelineEvent:
    defaults = {
        "workflow_id": "wf-test-001",
        "repo": "nock-command-center",
        "category": "build",
        "severity": "info",
        "title": "Build completed",
    }
    defaults.update(kwargs)
    return PipelineEvent.objects.create(**defaults)


# --- Model ---


class PipelineEventModelTests(TestCase):
    def test_create_event(self):
        event = _make_event()
        self.assertIsNotNone(event.id)
        self.assertIsNotNone(event.created_at)
        self.assertEqual(event.workflow_id, "wf-test-001")
        self.assertEqual(event.repo, "nock-command-center")
        self.assertEqual(event.category, "build")
        self.assertEqual(event.severity, "info")
        self.assertEqual(event.lane, "manual")
        self.assertEqual(event.agent, "kit")

    def test_str_representation(self):
        event = _make_event(severity="success", category="test", title="All 48 tests passing")
        self.assertEqual(str(event), "[success] test: All 48 tests passing")

    def test_ordering_newest_first(self):
        e1 = _make_event(title="First")
        e2 = _make_event(title="Second")
        events = list(PipelineEvent.objects.all())
        self.assertEqual(events[0].pk, e2.pk)
        self.assertEqual(events[1].pk, e1.pk)


# --- POST /api/pipeline/events/ ---


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY=_TEST_API_KEY)
class LogEventAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(self.user)

    def _post(self, data: dict):
        return self.client.post(
            "/api/pipeline/events/",
            data=json.dumps(data),
            content_type="application/json",
        )

    def test_log_event_valid(self):
        resp = self._post({
            "workflow_id": "phase-17",
            "repo": "claude-terminal",
            "category": "build",
            "severity": "success",
            "title": "Created 6 files for AI Chat Panel",
        })
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["message"], "Event logged")
        self.assertEqual(data["data"]["repo"], "claude-terminal")
        self.assertEqual(data["data"]["category"], "build")
        self.assertEqual(PipelineEvent.objects.count(), 1)

    def test_log_event_all_fields(self):
        resp = self._post({
            "workflow_id": "phase-17",
            "repo": "claude-terminal",
            "category": "test",
            "severity": "success",
            "title": "All 48 tests passing",
            "details": "pytest -q passed in 3.2s",
            "lane": "prompt",
            "agent": "kit",
            "pr_number": 48,
            "branch": "feature/ai-chat",
            "asana_task_id": "12345",
            "duration_seconds": 3,
            "token_count": 1500,
            "files_changed": 6,
            "test_count": 48,
        })
        self.assertEqual(resp.status_code, 201)
        event = PipelineEvent.objects.get()
        self.assertEqual(event.pr_number, 48)
        self.assertEqual(event.branch, "feature/ai-chat")
        self.assertEqual(event.lane, "prompt")
        self.assertEqual(event.duration_seconds, 3)
        self.assertEqual(event.files_changed, 6)
        self.assertEqual(event.test_count, 48)

    def test_log_event_missing_required_field(self):
        resp = self._post({
            "workflow_id": "phase-17",
            "repo": "claude-terminal",
            "category": "build",
            # missing title
        })
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["success"])
        self.assertIn("required", data["message"])

    def test_log_event_invalid_category(self):
        resp = self._post({
            "workflow_id": "phase-17",
            "repo": "claude-terminal",
            "category": "bogus",
            "title": "Test",
        })
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["success"])
        self.assertIn("Invalid category", data["message"])

    def test_log_event_invalid_severity(self):
        resp = self._post({
            "workflow_id": "phase-17",
            "repo": "claude-terminal",
            "category": "build",
            "severity": "mega",
            "title": "Test",
        })
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["success"])
        self.assertIn("Invalid severity", data["message"])

    def test_log_event_body_too_large(self):
        resp = self._post({
            "workflow_id": "phase-17",
            "repo": "claude-terminal",
            "category": "build",
            "title": "Test",
            "details": "x" * 70_000,
        })
        self.assertEqual(resp.status_code, 413)


# --- GET /api/pipeline/events/list/ ---


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY=_TEST_API_KEY)
class ListEventsAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(self.user)
        _make_event(workflow_id="wf-1", repo="repo-a", category="build", severity="info")
        _make_event(workflow_id="wf-1", repo="repo-a", category="test", severity="success")
        _make_event(workflow_id="wf-2", repo="repo-b", category="pr", severity="error")

    def test_list_returns_events(self):
        resp = self.client.get("/api/pipeline/events/list/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["count"], 3)

    def test_filter_by_workflow_id(self):
        resp = self.client.get("/api/pipeline/events/list/?workflow_id=wf-1")
        data = resp.json()
        self.assertEqual(data["data"]["count"], 2)

    def test_filter_by_repo(self):
        resp = self.client.get("/api/pipeline/events/list/?repo=repo-b")
        data = resp.json()
        self.assertEqual(data["data"]["count"], 1)
        self.assertEqual(data["data"]["events"][0]["repo"], "repo-b")

    def test_filter_by_category(self):
        resp = self.client.get("/api/pipeline/events/list/?category=build")
        data = resp.json()
        self.assertEqual(data["data"]["count"], 1)

    def test_filter_by_severity(self):
        resp = self.client.get("/api/pipeline/events/list/?severity=error")
        data = resp.json()
        self.assertEqual(data["data"]["count"], 1)
        self.assertEqual(data["data"]["events"][0]["severity"], "error")

    def test_filter_by_since(self):
        # Use a future timestamp — no events should match
        future = (timezone.now() + timedelta(hours=1)).isoformat()
        resp = self.client.get("/api/pipeline/events/list/", data={"since": future})
        data = resp.json()
        self.assertEqual(data["data"]["count"], 0)

        # Use a past timestamp — all events should match
        past = (timezone.now() - timedelta(hours=1)).isoformat()
        resp = self.client.get("/api/pipeline/events/list/", data={"since": past})
        data = resp.json()
        self.assertEqual(data["data"]["count"], 3)

    def test_limit_param(self):
        resp = self.client.get("/api/pipeline/events/list/?limit=2")
        data = resp.json()
        self.assertEqual(data["data"]["count"], 2)


# --- GET /api/pipeline/events/summary/ ---


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY=_TEST_API_KEY)
class EventSummaryAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(self.user)
        _make_event(category="build", severity="success")
        _make_event(category="test", severity="success")
        _make_event(category="pr", severity="info", title="PR #48 opened", pr_number=48)
        _make_event(category="error", severity="error", title="Tests failing")
        _make_event(category="escalation", severity="warning", title="Circuit breaker: 3 rounds")

    def test_summary_returns_totals(self):
        resp = self.client.get("/api/pipeline/events/summary/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["total"], 5)
        self.assertIn("by_category", data)
        self.assertIn("by_severity", data)
        self.assertEqual(data["by_category"]["build"], 1)
        self.assertEqual(data["by_severity"]["success"], 2)

    def test_summary_errors_collected(self):
        resp = self.client.get("/api/pipeline/events/summary/")
        data = resp.json()["data"]
        self.assertEqual(len(data["errors"]), 1)
        self.assertEqual(data["errors"][0]["title"], "Tests failing")

    def test_summary_escalations_collected(self):
        resp = self.client.get("/api/pipeline/events/summary/")
        data = resp.json()["data"]
        self.assertEqual(len(data["escalations"]), 1)
        self.assertIn("Circuit breaker", data["escalations"][0]["title"])

    def test_summary_prs_opened_collected(self):
        resp = self.client.get("/api/pipeline/events/summary/")
        data = resp.json()["data"]
        self.assertEqual(len(data["prs_opened"]), 1)
        self.assertEqual(data["prs_opened"][0]["pr_number"], 48)

    def test_summary_hours_filter(self):
        # Backdate all events to 48 hours ago
        PipelineEvent.objects.all().update(
            created_at=timezone.now() - timedelta(hours=48),
        )
        resp = self.client.get("/api/pipeline/events/summary/?hours=1")
        data = resp.json()["data"]
        self.assertEqual(data["total"], 0)


# --- Auth ---


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY=_TEST_API_KEY)
class PipelineEventAuthTests(TestCase):
    def test_log_event_requires_auth(self):
        resp = self.client.post(
            "/api/pipeline/events/",
            data=json.dumps({
                "workflow_id": "wf-1",
                "repo": "repo",
                "category": "build",
                "title": "Test",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_list_events_with_api_key(self):
        _make_event()
        resp = self.client.get("/api/pipeline/events/list/", **_api_headers())
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["count"], 1)

    def test_log_event_with_api_key(self):
        resp = self.client.post(
            "/api/pipeline/events/",
            data=json.dumps({
                "workflow_id": "wf-1",
                "repo": "repo",
                "category": "build",
                "title": "Test",
            }),
            content_type="application/json",
            **_api_headers(),
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()["success"])

    def test_summary_with_api_key(self):
        resp = self.client.get("/api/pipeline/events/summary/", **_api_headers())
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
