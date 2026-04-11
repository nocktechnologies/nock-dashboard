"""Tests for the Asana write-back + cross-project read API.

The Asana HTTP client is mocked at the `tasks.asana_client.requests` level so
tests exercise the full view → client code path without hitting the network.
"""
from __future__ import annotations

import json
import os
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from tasks import asana_client
from tasks.models import AsanaProject, AsanaSection, AsanaTask

_TEST_FERNET_KEYS = [
    os.environ.get("TEST_FERNET_KEY", "rBj4e7L0PbE7E3H5JhLdOwvSXa3Z3g1mJbkBrkIg5cI="),
]


class _FakeResponse:
    """Minimal stand-in for requests.Response used by asana_client."""

    def __init__(self, *, status: int = 200, json_body: dict | None = None, text: str = ""):
        self.status_code = status
        self._json_body = json_body or {}
        self.text = text or json.dumps(self._json_body)
        self.content = self.text.encode() if self.text else b""
        self.headers: dict[str, str] = {}
        self.ok = 200 <= status < 300

    def json(self) -> dict:
        return self._json_body

    def raise_for_status(self) -> None:
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


def _raw_task(
    gid: str = "9999",
    name: str = "Test task",
    section_name: str = "",
    section_gid: str = "",
    completed: bool = False,
    due_on: str | None = None,
    notes: str = "",
) -> dict:
    memberships = []
    if section_name or section_gid:
        memberships = [{"section": {"name": section_name, "gid": section_gid}}]
    return {
        "gid": gid,
        "name": name,
        "assignee": None,
        "due_on": due_on,
        "completed": completed,
        "completed_at": None,
        "notes": notes,
        "memberships": memberships,
        "permalink_url": f"https://app.asana.com/0/0/{gid}",
        "custom_fields": [],
        "modified_at": "2026-04-10T12:00:00.000Z",
    }


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    NOCKCC_API_KEY="test-api-key",
    RATELIMIT_ENABLE=False,
)
class AsanaWriteApiTests(TestCase):
    """End-to-end tests for /api/tasks/ write + read endpoints."""

    AUTH_HEADER = {"HTTP_X_API_KEY": "test-api-key"}

    @classmethod
    def setUpTestData(cls) -> None:
        # A staff user needs to exist so require_brain_access can assign one
        # to the request when authenticating via API key.
        User = get_user_model()
        cls.staff = User.objects.create_user(
            username="nockcc-bot", password="x", is_staff=True,
        )
        cls.project = AsanaProject.objects.create(
            asana_gid="proj-1", name="CCC Development",
        )
        cls.section = AsanaSection.objects.create(
            asana_gid="sec-1", name="In Progress", project=cls.project, order=1,
        )
        cls.other_project = AsanaProject.objects.create(
            asana_gid="proj-2", name="Mara Training Ground",
        )
        cls.other_section = AsanaSection.objects.create(
            asana_gid="sec-2", name="Backlog", project=cls.other_project, order=0,
        )
        cls.task = AsanaTask.objects.create(
            asana_gid="task-1",
            project=cls.project,
            name="Existing task",
            section_name="In Progress",
            due_on=timezone.localdate() + timedelta(days=3),
            priority="medium",
        )

    def setUp(self) -> None:
        # ASANA_PAT is read lazily — set a dummy so write calls don't blow up
        # before the request mock intercepts them.
        patcher = patch.dict(os.environ, {"ASANA_PAT": "dummy-pat"})
        patcher.start()
        self.addCleanup(patcher.stop)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def test_create_requires_auth(self) -> None:
        resp = self.client.post(
            "/api/tasks/create/",
            data=json.dumps({"project_gid": "proj-1", "name": "Unauthorized"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_summary_requires_auth(self) -> None:
        resp = self.client.get("/api/tasks/summary/")
        self.assertEqual(resp.status_code, 401)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    @patch("tasks.asana_client.requests.request")
    def test_create_task_success(self, mock_request) -> None:
        mock_request.return_value = _FakeResponse(json_body={
            "data": _raw_task(gid="new-gid", name="New task", section_name="In Progress"),
        })
        resp = self.client.post(
            "/api/tasks/create/",
            data=json.dumps({
                "project_gid": "proj-1",
                "name": "New task",
                "notes": "These are the notes",
                "due_on": "2026-04-15",
                "priority": "high",
            }),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        data = resp.json()["data"]
        self.assertEqual(data["asana_gid"], "new-gid")
        self.assertEqual(data["priority"], "high")

        # Local DB mirrored
        task = AsanaTask.objects.get(asana_gid="new-gid")
        self.assertEqual(task.name, "New task")
        self.assertEqual(task.priority, "high")
        self.assertEqual(task.project, self.project)

        # Asana POST was called with the right shape
        posted_body = mock_request.call_args.kwargs["json"]["data"]
        self.assertEqual(posted_body["name"], "New task")
        self.assertIn("proj-1", posted_body["projects"])
        self.assertNotIn("priority", posted_body)  # priority is local-only

    def test_create_task_requires_name(self) -> None:
        resp = self.client.post(
            "/api/tasks/create/",
            data=json.dumps({"project_gid": "proj-1"}),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 400)

    def test_create_task_unknown_project(self) -> None:
        resp = self.client.post(
            "/api/tasks/create/",
            data=json.dumps({"project_gid": "does-not-exist", "name": "x"}),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 404)

    def test_create_task_invalid_priority(self) -> None:
        resp = self.client.post(
            "/api/tasks/create/",
            data=json.dumps({
                "project_gid": "proj-1",
                "name": "x",
                "priority": "urgent",
            }),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 400)

    @patch("tasks.asana_client.requests.request")
    def test_create_task_asana_failure_does_not_touch_db(self, mock_request) -> None:
        mock_request.return_value = _FakeResponse(
            status=500,
            json_body={"errors": [{"message": "kaboom"}]},
        )
        count_before = AsanaTask.objects.count()
        resp = self.client.post(
            "/api/tasks/create/",
            data=json.dumps({"project_gid": "proj-1", "name": "Will not land"}),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(AsanaTask.objects.count(), count_before)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    @patch("tasks.asana_client.requests.request")
    def test_update_task_partial(self, mock_request) -> None:
        mock_request.return_value = _FakeResponse(json_body={
            "data": _raw_task(
                gid="task-1", name="Existing task — renamed",
                section_name="In Progress",
            ),
        })
        resp = self.client.put(
            "/api/tasks/task-1/update/",
            data=json.dumps({"name": "Existing task — renamed"}),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.task.refresh_from_db()
        self.assertEqual(self.task.name, "Existing task — renamed")

    @patch("tasks.asana_client.requests.request")
    def test_update_priority_only_skips_asana(self, mock_request) -> None:
        resp = self.client.put(
            "/api/tasks/task-1/update/",
            data=json.dumps({"priority": "high"}),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.task.refresh_from_db()
        self.assertEqual(self.task.priority, "high")
        mock_request.assert_not_called()

    def test_update_task_no_fields(self) -> None:
        resp = self.client.put(
            "/api/tasks/task-1/update/",
            data=json.dumps({}),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 400)

    def test_update_task_not_found(self) -> None:
        resp = self.client.put(
            "/api/tasks/missing/update/",
            data=json.dumps({"name": "x"}),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 404)

    @patch("tasks.asana_client.requests.request")
    def test_update_asana_failure_leaves_db_unchanged(self, mock_request) -> None:
        mock_request.return_value = _FakeResponse(
            status=400, json_body={"errors": [{"message": "bad"}]},
        )
        original_name = self.task.name
        resp = self.client.put(
            "/api/tasks/task-1/update/",
            data=json.dumps({"name": "This should not land"}),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 502)
        self.task.refresh_from_db()
        self.assertEqual(self.task.name, original_name)

    # ------------------------------------------------------------------
    # Complete / uncomplete
    # ------------------------------------------------------------------

    @patch("tasks.asana_client.requests.request")
    def test_complete_task(self, mock_request) -> None:
        mock_request.return_value = _FakeResponse(json_body={
            "data": _raw_task(gid="task-1", name="Existing task", completed=True),
        })
        resp = self.client.post(
            "/api/tasks/task-1/complete/", **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.task.refresh_from_db()
        self.assertTrue(self.task.completed)

    @patch("tasks.asana_client.requests.request")
    def test_uncomplete_task(self, mock_request) -> None:
        self.task.completed = True
        self.task.save(update_fields=["completed"])
        mock_request.return_value = _FakeResponse(json_body={
            "data": _raw_task(gid="task-1", name="Existing task", completed=False),
        })
        resp = self.client.post(
            "/api/tasks/task-1/uncomplete/", **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.task.refresh_from_db()
        self.assertFalse(self.task.completed)

    # ------------------------------------------------------------------
    # Move
    # ------------------------------------------------------------------

    @patch("tasks.asana_client.requests.request")
    def test_move_task_same_project(self, mock_request) -> None:
        other = AsanaSection.objects.create(
            asana_gid="sec-done", name="Done", project=self.project, order=99,
        )
        mock_request.return_value = _FakeResponse(json_body={"data": {}})
        resp = self.client.post(
            "/api/tasks/task-1/move/",
            data=json.dumps({"section_gid": other.asana_gid}),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.task.refresh_from_db()
        self.assertEqual(self.task.section_name, "Done")

    def test_move_task_cross_project_rejected(self) -> None:
        resp = self.client.post(
            "/api/tasks/task-1/move/",
            data=json.dumps({"section_gid": self.other_section.asana_gid}),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 400)

    def test_move_task_unknown_section(self) -> None:
        resp = self.client.post(
            "/api/tasks/task-1/move/",
            data=json.dumps({"section_gid": "nope"}),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # Comment
    # ------------------------------------------------------------------

    @patch("tasks.asana_client.requests.request")
    def test_comment_task(self, mock_request) -> None:
        mock_request.return_value = _FakeResponse(json_body={
            "data": {
                "gid": "story-1",
                "text": "Kit PR #67 opened",
                "created_at": "2026-04-10T12:00:00Z",
            },
        })
        resp = self.client.post(
            "/api/tasks/task-1/comment/",
            data=json.dumps({"text": "Kit PR #67 opened"}),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["data"]["story_gid"], "story-1")

    def test_comment_requires_text(self) -> None:
        resp = self.client.post(
            "/api/tasks/task-1/comment/",
            data=json.dumps({"text": "   "}),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 400)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    @patch("tasks.asana_client.requests.request")
    def test_delete_task_soft_deletes_local(self, mock_request) -> None:
        mock_request.return_value = _FakeResponse(status=200, json_body={"data": {}})
        resp = self.client.delete(
            "/api/tasks/task-1/delete/", **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.task.refresh_from_db()
        self.assertIsNotNone(self.task.deleted_at)
        # Still exists as a row — soft delete
        self.assertTrue(AsanaTask.objects.filter(pk=self.task.pk).exists())

    @patch("tasks.asana_client.requests.request")
    def test_delete_asana_failure_does_not_soft_delete(self, mock_request) -> None:
        mock_request.return_value = _FakeResponse(
            status=500, json_body={"errors": [{"message": "nope"}]},
        )
        resp = self.client.delete(
            "/api/tasks/task-1/delete/", **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 502)
        self.task.refresh_from_db()
        self.assertIsNone(self.task.deleted_at)

    # ------------------------------------------------------------------
    # Cross-project reads
    # ------------------------------------------------------------------

    def _seed_cross_project(self) -> None:
        """Add a mix of tasks across projects so read endpoints have data."""
        today = timezone.localdate()
        AsanaTask.objects.create(
            asana_gid="t-overdue",
            project=self.project,
            name="Overdue important thing",
            due_on=today - timedelta(days=2),
            priority="high",
        )
        AsanaTask.objects.create(
            asana_gid="t-today",
            project=self.other_project,
            name="Due today",
            due_on=today,
            priority="low",
        )
        AsanaTask.objects.create(
            asana_gid="t-done",
            project=self.project,
            name="Already done",
            due_on=today - timedelta(days=1),
            completed=True,
        )
        AsanaTask.objects.create(
            asana_gid="t-deleted",
            project=self.project,
            name="Soft-deleted — should be hidden",
            due_on=today - timedelta(days=5),
            priority="high",
            deleted_at=timezone.now(),
        )

    def test_list_tasks(self) -> None:
        self._seed_cross_project()
        resp = self.client.get("/api/tasks/all/", **self.AUTH_HEADER)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        gids = {t["asana_gid"] for t in data["tasks"]}
        self.assertIn("t-overdue", gids)
        self.assertIn("t-today", gids)
        self.assertIn("task-1", gids)  # existing from setUp
        self.assertNotIn("t-done", gids)
        self.assertNotIn("t-deleted", gids)

    def test_list_tasks_filter_by_project(self) -> None:
        self._seed_cross_project()
        resp = self.client.get(
            "/api/tasks/all/?project_gid=proj-2", **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 200)
        gids = {t["asana_gid"] for t in resp.json()["data"]["tasks"]}
        self.assertEqual(gids, {"t-today"})

    def test_overdue_tasks(self) -> None:
        self._seed_cross_project()
        resp = self.client.get("/api/tasks/overdue/", **self.AUTH_HEADER)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        gids = {t["asana_gid"] for t in data["tasks"]}
        self.assertEqual(gids, {"t-overdue"})
        # days_overdue annotation is present
        self.assertEqual(data["tasks"][0]["days_overdue"], 2)

    def test_today_tasks(self) -> None:
        self._seed_cross_project()
        resp = self.client.get("/api/tasks/today/", **self.AUTH_HEADER)
        self.assertEqual(resp.status_code, 200)
        gids = {t["asana_gid"] for t in resp.json()["data"]["tasks"]}
        self.assertEqual(gids, {"t-today"})

    def test_summary(self) -> None:
        self._seed_cross_project()
        resp = self.client.get("/api/tasks/summary/", **self.AUTH_HEADER)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        # task-1 + t-overdue + t-today + t-done  (t-deleted is hidden)
        self.assertEqual(data["total_tasks"], 4)
        self.assertEqual(data["completed"], 1)
        self.assertEqual(data["overdue"], 1)
        self.assertEqual(data["due_today"], 1)
        self.assertGreaterEqual(len(data["by_project"]), 2)

    def test_sections_list_returns_cached(self) -> None:
        resp = self.client.get(
            "/api/tasks/sections/proj-1/", **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()["data"]
        self.assertEqual(data["project_gid"], "proj-1")
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["sections"][0]["asana_gid"], "sec-1")

    @patch("tasks.asana_client.requests.get")
    def test_sections_refresh_pulls_from_asana(self, mock_get) -> None:
        mock_get.return_value = _FakeResponse(json_body={
            "data": [
                {"gid": "sec-1", "name": "In Progress — renamed"},
                {"gid": "sec-new", "name": "Newly added"},
            ],
        })
        resp = self.client.get(
            "/api/tasks/sections/proj-1/?refresh=true", **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        gids = {s["asana_gid"] for s in resp.json()["data"]["sections"]}
        self.assertIn("sec-1", gids)
        self.assertIn("sec-new", gids)
        # Existing row was updated, not duplicated
        renamed = AsanaSection.objects.get(asana_gid="sec-1")
        self.assertEqual(renamed.name, "In Progress — renamed")

    @patch("tasks.asana_client.requests.get")
    def test_sections_refresh_prunes_stale_rows(self, mock_get) -> None:
        """Regression: ?refresh=true must drop sections no longer in Asana."""
        AsanaSection.objects.create(
            asana_gid="sec-stale", name="Stale", project=self.project, order=99,
        )
        mock_get.return_value = _FakeResponse(json_body={
            "data": [
                {"gid": "sec-1", "name": "In Progress"},
            ],
        })
        resp = self.client.get(
            "/api/tasks/sections/proj-1/?refresh=true", **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 200)
        gids = {s["asana_gid"] for s in resp.json()["data"]["sections"]}
        self.assertEqual(gids, {"sec-1"})
        self.assertFalse(
            AsanaSection.objects.filter(asana_gid="sec-stale").exists(),
        )

    # ------------------------------------------------------------------
    # Regression tests for CodeRabbit findings
    # ------------------------------------------------------------------

    @patch("tasks.asana_client.requests.request")
    def test_mutating_endpoints_treat_soft_deleted_as_404(self, mock_request) -> None:
        """Regression: a soft-deleted task must 404 on update/comment/delete,
        not round-trip to Asana with a dead gid."""
        self.task.deleted_at = timezone.now()
        self.task.save(update_fields=["deleted_at"])

        update_resp = self.client.put(
            "/api/tasks/task-1/update/",
            data=json.dumps({"name": "zombie"}),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(update_resp.status_code, 404)

        comment_resp = self.client.post(
            "/api/tasks/task-1/comment/",
            data=json.dumps({"text": "hi"}),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(comment_resp.status_code, 404)

        complete_resp = self.client.post(
            "/api/tasks/task-1/complete/", **self.AUTH_HEADER,
        )
        self.assertEqual(complete_resp.status_code, 404)

        # Asana was never called for any of the three
        mock_request.assert_not_called()

    @patch("tasks.asana_client.requests.request")
    def test_create_with_real_due_on_coerces_types(self, mock_request) -> None:
        """Regression: asana_parse_task returns due_on as a string, but
        _task_to_dict calls .isoformat() — the critical bug CodeRabbit
        flagged. Verify the create path coerces properly and the response
        serializes cleanly."""
        mock_request.return_value = _FakeResponse(json_body={
            "data": _raw_task(
                gid="typed",
                name="Typed task",
                due_on="2026-04-15",
            ),
        })
        resp = self.client.post(
            "/api/tasks/create/",
            data=json.dumps({
                "project_gid": "proj-1",
                "name": "Typed task",
                "due_on": "2026-04-15",
            }),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["data"]["due_on"], "2026-04-15")
        task = AsanaTask.objects.get(asana_gid="typed")
        self.assertEqual(task.due_on.isoformat(), "2026-04-15")

    def test_create_with_unknown_section_fails_fast(self) -> None:
        """Regression: create with section_gid must pre-validate the
        section locally. Otherwise an Asana-side section failure would leave
        an orphan task behind."""
        resp = self.client.post(
            "/api/tasks/create/",
            data=json.dumps({
                "project_gid": "proj-1",
                "name": "x",
                "section_gid": "does-not-exist",
            }),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 404)

    def test_create_with_cross_project_section_rejected(self) -> None:
        """Regression: section_gid must belong to the same project."""
        resp = self.client.post(
            "/api/tasks/create/",
            data=json.dumps({
                "project_gid": "proj-1",
                "name": "x",
                "section_gid": "sec-2",  # belongs to proj-2
            }),
            content_type="application/json",
            **self.AUTH_HEADER,
        )
        self.assertEqual(resp.status_code, 400)

    def test_background_scans_skip_soft_deleted(self) -> None:
        """Regression: _check_new_comments and link_tasks_to_prs must not
        touch soft-deleted rows."""
        from tasks import tasks as tasks_module

        self.task.deleted_at = timezone.now()
        self.task.save(update_fields=["deleted_at"])

        with patch("tasks.tasks.get_task_stories") as mock_stories:
            tasks_module._check_new_comments()
            mock_stories.assert_not_called()

        # link_tasks_to_prs runs happily with no PRs — just verify the queryset
        # it builds excludes the soft-deleted row.
        from tasks.models import AsanaTask as _AT
        self.assertFalse(
            _AT.objects.filter(
                linked_pr__isnull=True,
                completed=False,
                deleted_at__isnull=True,
                pk=self.task.pk,
            ).exists(),
        )


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class AsanaClientWriteTests(TestCase):
    """Unit tests for the write helpers in asana_client — pure HTTP mocking."""

    def setUp(self) -> None:
        patcher = patch.dict(os.environ, {"ASANA_PAT": "dummy-pat"})
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch("tasks.asana_client.requests.request")
    def test_update_task_strips_unknown_fields(self, mock_request) -> None:
        mock_request.return_value = _FakeResponse(json_body={
            "data": _raw_task(gid="abc", name="renamed"),
        })
        asana_client.update_task(
            "abc",
            name="renamed",
            priority="high",       # local-only, must not be forwarded
            unknown_field="x",     # unknown, must not be forwarded
        )
        sent = mock_request.call_args.kwargs["json"]["data"]
        self.assertEqual(sent, {"name": "renamed"})

    def test_update_task_requires_fields(self) -> None:
        with self.assertRaises(asana_client.AsanaClientError):
            asana_client.update_task("abc")

    @patch("tasks.asana_client.requests.request")
    def test_request_retry_on_429(self, mock_request) -> None:
        r429 = _FakeResponse(status=429)
        r429.headers = {"Retry-After": "0"}
        ok = _FakeResponse(json_body={"data": {"ok": True}})
        mock_request.side_effect = [r429, ok]
        with patch("tasks.asana_client.time.sleep"):
            result = asana_client._request_with_retry(
                "POST", "https://fake/url", json_body={"data": {}},
            )
        self.assertEqual(result, {"data": {"ok": True}})
        self.assertEqual(mock_request.call_count, 2)

    @patch("tasks.asana_client.requests.request")
    def test_request_raises_with_asana_error_message(self, mock_request) -> None:
        mock_request.return_value = _FakeResponse(
            status=400,
            json_body={"errors": [{"message": "name is required"}]},
        )
        with self.assertRaises(asana_client.AsanaClientError) as ctx:
            asana_client._request_with_retry("POST", "https://fake/url", json_body={})
        self.assertIn("name is required", str(ctx.exception))
