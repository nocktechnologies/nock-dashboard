"""
Tests for Agent Teams — multi-agent orchestration layer.

Covers: model CRUD, dependency resolution, API endpoints,
webhook cross-reference, status transitions, events, security.
"""

import json

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from teams.models import AgentTeam, TeamEvent, TeamMember, TeamTask

_TEST_FERNET_KEYS = ["rBj4e7L0PbE7E3H5JhLdOwvSXa3Z3g1mJbkBrkIg5cI="]
_TEST_API_KEY = "test-api-key-for-teams"


def _api_headers() -> dict:
    return {"HTTP_X_API_KEY": _TEST_API_KEY}


def _post_json(client, url, data, **extra):
    return client.post(
        url,
        data=json.dumps(data),
        content_type="application/json",
        **extra,
    )


def _put_json(client, url, data, **extra):
    return client.put(
        url,
        data=json.dumps(data),
        content_type="application/json",
        **extra,
    )


# ── Model tests ──


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class AgentTeamModelTests(TestCase):
    def test_create_team(self):
        team = AgentTeam.objects.create(name="Sprint Alpha", mission="Ship billing")
        self.assertEqual(team.status, "planning")
        self.assertEqual(str(team), "Sprint Alpha (planning)")

    def test_member_count(self):
        team = AgentTeam.objects.create(name="T", mission="M")
        self.assertEqual(team.member_count, 0)
        TeamMember.objects.create(team=team, agent_name="Kit #1")
        self.assertEqual(team.member_count, 1)

    def test_task_summary(self):
        team = AgentTeam.objects.create(name="T", mission="M")
        TeamTask.objects.create(team=team, title="A", status="pending")
        TeamTask.objects.create(team=team, title="B", status="in_progress")
        TeamTask.objects.create(team=team, title="C", status="completed")
        summary = team.task_summary
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["pending"], 1)
        self.assertEqual(summary["in_progress"], 1)
        self.assertEqual(summary["completed"], 1)

    def test_ordering_by_updated_at(self):
        AgentTeam.objects.create(name="Old", mission="M")
        AgentTeam.objects.create(name="New", mission="M")
        teams = list(AgentTeam.objects.all())
        self.assertEqual(teams[0].name, "New")


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class TeamMemberModelTests(TestCase):
    def test_create_member(self):
        team = AgentTeam.objects.create(name="T", mission="M")
        member = TeamMember.objects.create(team=team, agent_name="Kit #1", role="lead")
        self.assertEqual(str(member), "Kit #1 (lead) on T")

    def test_unique_together_constraint(self):
        team = AgentTeam.objects.create(name="T", mission="M")
        TeamMember.objects.create(team=team, agent_name="Kit #1")
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            TeamMember.objects.create(team=team, agent_name="Kit #1")


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class TeamTaskModelTests(TestCase):
    def test_create_task(self):
        team = AgentTeam.objects.create(name="T", mission="M")
        task = TeamTask.objects.create(team=team, title="Build widget", priority=TeamTask.PRIORITY_HIGH)
        self.assertEqual(task.status, "pending")
        self.assertEqual(str(task), "Build widget (pending)")

    def test_is_blocked_no_deps(self):
        team = AgentTeam.objects.create(name="T", mission="M")
        task = TeamTask.objects.create(team=team, title="A")
        self.assertFalse(task.is_blocked)

    def test_is_blocked_with_incomplete_dep(self):
        team = AgentTeam.objects.create(name="T", mission="M")
        dep = TeamTask.objects.create(team=team, title="Dep", status="in_progress")
        task = TeamTask.objects.create(team=team, title="Main")
        task.depends_on.add(dep)
        self.assertTrue(task.is_blocked)

    def test_is_not_blocked_when_dep_completed(self):
        team = AgentTeam.objects.create(name="T", mission="M")
        dep = TeamTask.objects.create(team=team, title="Dep", status="completed")
        task = TeamTask.objects.create(team=team, title="Main")
        task.depends_on.add(dep)
        self.assertFalse(task.is_blocked)

    def test_blocking_tasks_returns_incomplete(self):
        team = AgentTeam.objects.create(name="T", mission="M")
        dep1 = TeamTask.objects.create(team=team, title="Done", status="completed")
        dep2 = TeamTask.objects.create(team=team, title="Pending", status="pending")
        task = TeamTask.objects.create(team=team, title="Main")
        task.depends_on.add(dep1, dep2)
        blocking = list(task.blocking_tasks)
        self.assertEqual(len(blocking), 1)
        self.assertEqual(blocking[0].title, "Pending")


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class TeamEventModelTests(TestCase):
    def test_create_event(self):
        team = AgentTeam.objects.create(name="T", mission="M")
        event = TeamEvent.objects.create(
            team=team, event_type="mission_started", description="Go!"
        )
        self.assertIn("Mission Started", str(event))


# ── API tests ──


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    NOCKCC_API_KEY=_TEST_API_KEY,
    TELEGRAM_ENABLED=False,
)
class TeamCRUDAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass", is_staff=True)

    def test_create_team(self):
        resp = _post_json(self.client, "/api/teams/", {"name": "Alpha", "mission": "Ship it"}, **_api_headers())
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["name"], "Alpha")
        self.assertEqual(data["data"]["status"], "planning")

    def test_create_team_missing_fields(self):
        resp = _post_json(self.client, "/api/teams/", {"name": ""}, **_api_headers())
        self.assertEqual(resp.status_code, 400)

    def test_list_teams(self):
        AgentTeam.objects.create(name="A", mission="M")
        AgentTeam.objects.create(name="B", mission="M", status="active")
        resp = self.client.get("/api/teams/", **_api_headers())
        data = resp.json()
        self.assertEqual(len(data["data"]["teams"]), 2)

    def test_list_teams_filter_status(self):
        AgentTeam.objects.create(name="A", mission="M", status="planning")
        AgentTeam.objects.create(name="B", mission="M", status="active")
        resp = self.client.get("/api/teams/?status=active", **_api_headers())
        data = resp.json()
        self.assertEqual(len(data["data"]["teams"]), 1)
        self.assertEqual(data["data"]["teams"][0]["name"], "B")

    def test_team_detail(self):
        team = AgentTeam.objects.create(name="Alpha", mission="Ship it")
        resp = self.client.get(f"/api/teams/{team.id}/", **_api_headers())
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("members", data["data"])
        self.assertIn("recent_events", data["data"])

    def test_update_team(self):
        team = AgentTeam.objects.create(name="Alpha", mission="Ship it")
        resp = _put_json(self.client, f"/api/teams/{team.id}/", {"name": "Beta", "status": "active"}, **_api_headers())
        data = resp.json()
        self.assertEqual(data["data"]["name"], "Beta")
        self.assertEqual(data["data"]["status"], "active")

    def test_delete_team_soft(self):
        team = AgentTeam.objects.create(name="A", mission="M")
        resp = self.client.delete(f"/api/teams/{team.id}/", **_api_headers())
        self.assertEqual(resp.status_code, 200)
        team.refresh_from_db()
        self.assertEqual(team.status, "completed")

    def test_active_teams_endpoint(self):
        AgentTeam.objects.create(name="A", mission="M", status="active")
        AgentTeam.objects.create(name="B", mission="M", status="planning")
        resp = self.client.get("/api/teams/active/", **_api_headers())
        data = resp.json()
        self.assertEqual(len(data["data"]["teams"]), 1)

    def test_auth_required(self):
        resp = self.client.get("/api/teams/")
        self.assertEqual(resp.status_code, 401)


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    NOCKCC_API_KEY=_TEST_API_KEY,
    TELEGRAM_ENABLED=False,
)
class MemberAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass", is_staff=True)
        self.team = AgentTeam.objects.create(name="Alpha", mission="Ship it")

    def test_add_member(self):
        resp = _post_json(
            self.client, f"/api/teams/{self.team.id}/members/",
            {"agent_name": "Kit #1", "role": "lead"},
            **_api_headers(),
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["data"]["agent_name"], "Kit #1")
        self.assertEqual(data["data"]["role"], "lead")
        # Should create an event
        self.assertEqual(TeamEvent.objects.filter(event_type="agent_joined").count(), 1)

    def test_add_duplicate_member(self):
        TeamMember.objects.create(team=self.team, agent_name="Kit #1")
        resp = _post_json(
            self.client, f"/api/teams/{self.team.id}/members/",
            {"agent_name": "Kit #1"},
            **_api_headers(),
        )
        self.assertEqual(resp.status_code, 409)

    def test_list_members(self):
        TeamMember.objects.create(team=self.team, agent_name="Kit #1")
        TeamMember.objects.create(team=self.team, agent_name="Kit #2")
        resp = self.client.get(f"/api/teams/{self.team.id}/members/", **_api_headers())
        data = resp.json()
        self.assertEqual(len(data["data"]["members"]), 2)

    def test_update_member(self):
        member = TeamMember.objects.create(team=self.team, agent_name="Kit #1", role="worker")
        resp = _put_json(
            self.client, f"/api/teams/{self.team.id}/members/{member.id}/",
            {"role": "lead"},
            **_api_headers(),
        )
        data = resp.json()
        self.assertEqual(data["data"]["role"], "lead")

    def test_remove_member(self):
        member = TeamMember.objects.create(team=self.team, agent_name="Kit #1")
        resp = self.client.delete(f"/api/teams/{self.team.id}/members/{member.id}/", **_api_headers())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(TeamMember.objects.count(), 0)
        self.assertEqual(TeamEvent.objects.filter(event_type="agent_left").count(), 1)


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    NOCKCC_API_KEY=_TEST_API_KEY,
    TELEGRAM_ENABLED=False,
)
class TaskAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass", is_staff=True)
        self.team = AgentTeam.objects.create(name="Alpha", mission="Ship it", status="active")
        self.member = TeamMember.objects.create(team=self.team, agent_name="Kit #1")

    def test_create_task(self):
        resp = _post_json(
            self.client, f"/api/teams/{self.team.id}/tasks/",
            {"title": "Build widget", "priority": "high", "repo": "kkwills13/nexus"},
            **_api_headers(),
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["data"]["title"], "Build widget")
        self.assertEqual(data["data"]["priority"], "high")
        self.assertEqual(data["data"]["status"], "pending")

    def test_create_task_assigned(self):
        resp = _post_json(
            self.client, f"/api/teams/{self.team.id}/tasks/",
            {"title": "Build widget", "assigned_to": self.member.id},
            **_api_headers(),
        )
        data = resp.json()
        self.assertEqual(data["data"]["status"], "assigned")
        self.assertEqual(data["data"]["assigned_to"], "Kit #1")

    def test_create_task_missing_title(self):
        resp = _post_json(
            self.client, f"/api/teams/{self.team.id}/tasks/",
            {"title": ""},
            **_api_headers(),
        )
        self.assertEqual(resp.status_code, 400)

    def test_list_tasks(self):
        TeamTask.objects.create(team=self.team, title="A")
        TeamTask.objects.create(team=self.team, title="B")
        resp = self.client.get(f"/api/teams/{self.team.id}/tasks/", **_api_headers())
        data = resp.json()
        self.assertEqual(len(data["data"]["tasks"]), 2)

    def test_list_tasks_filter_status(self):
        TeamTask.objects.create(team=self.team, title="A", status="pending")
        TeamTask.objects.create(team=self.team, title="B", status="completed")
        resp = self.client.get(f"/api/teams/{self.team.id}/tasks/?status=pending", **_api_headers())
        data = resp.json()
        self.assertEqual(len(data["data"]["tasks"]), 1)

    def test_task_detail(self):
        task = TeamTask.objects.create(team=self.team, title="Widget")
        resp = self.client.get(f"/api/teams/{self.team.id}/tasks/{task.id}/", **_api_headers())
        data = resp.json()
        self.assertEqual(data["data"]["title"], "Widget")
        self.assertIn("events", data["data"])

    def test_update_task(self):
        task = TeamTask.objects.create(team=self.team, title="A", status="pending")
        resp = _put_json(
            self.client, f"/api/teams/{self.team.id}/tasks/{task.id}/",
            {"status": "assigned", "branch": "feature/widget"},
            **_api_headers(),
        )
        data = resp.json()
        self.assertEqual(data["data"]["status"], "assigned")
        self.assertEqual(data["data"]["branch"], "feature/widget")


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    NOCKCC_API_KEY=_TEST_API_KEY,
    TELEGRAM_ENABLED=False,
)
class TaskStartCompleteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass", is_staff=True)
        self.team = AgentTeam.objects.create(name="Alpha", mission="Ship it", status="active")
        self.member = TeamMember.objects.create(team=self.team, agent_name="Kit #1")

    def test_start_task(self):
        task = TeamTask.objects.create(team=self.team, title="A", assigned_to=self.member)
        resp = self.client.post(f"/api/teams/{self.team.id}/tasks/{task.id}/start/", **_api_headers())
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["data"]["status"], "in_progress")
        self.assertIsNotNone(data["data"]["started_at"])
        # Member's current_task should be set
        self.member.refresh_from_db()
        self.assertEqual(self.member.current_task_id, task.id)
        # Event should be created
        self.assertTrue(TeamEvent.objects.filter(event_type="task_started").exists())

    def test_start_blocked_task_fails(self):
        dep = TeamTask.objects.create(team=self.team, title="Dep", status="pending")
        task = TeamTask.objects.create(team=self.team, title="Main")
        task.depends_on.add(dep)
        resp = self.client.post(f"/api/teams/{self.team.id}/tasks/{task.id}/start/", **_api_headers())
        self.assertEqual(resp.status_code, 409)
        data = resp.json()
        self.assertIn("blocked by", data["message"])

    def test_complete_task(self):
        task = TeamTask.objects.create(
            team=self.team, title="A", status="in_progress", assigned_to=self.member
        )
        self.member.current_task = task
        self.member.save(update_fields=["current_task"])

        resp = self.client.post(f"/api/teams/{self.team.id}/tasks/{task.id}/complete/", **_api_headers())
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["data"]["status"], "completed")
        self.assertIsNotNone(data["data"]["completed_at"])
        # Member's current_task should be cleared
        self.member.refresh_from_db()
        self.assertIsNone(self.member.current_task)

    def test_complete_task_unblocks_dependents(self):
        dep = TeamTask.objects.create(team=self.team, title="Dep", status="in_progress")
        blocked = TeamTask.objects.create(
            team=self.team, title="Blocked", status="blocked", assigned_to=self.member
        )
        blocked.depends_on.add(dep)

        self.client.post(f"/api/teams/{self.team.id}/tasks/{dep.id}/complete/", **_api_headers())
        blocked.refresh_from_db()
        self.assertEqual(blocked.status, "assigned")  # Unblocked and has assignee → assigned

    def test_complete_task_unblocks_to_pending_if_no_assignee(self):
        dep = TeamTask.objects.create(team=self.team, title="Dep", status="in_progress")
        blocked = TeamTask.objects.create(team=self.team, title="Blocked", status="blocked")
        blocked.depends_on.add(dep)

        self.client.post(f"/api/teams/{self.team.id}/tasks/{dep.id}/complete/", **_api_headers())
        blocked.refresh_from_db()
        self.assertEqual(blocked.status, "pending")  # No assignee → pending

    def test_all_tasks_complete_triggers_mission_complete(self):
        task = TeamTask.objects.create(team=self.team, title="Only task", status="in_progress")
        self.client.post(f"/api/teams/{self.team.id}/tasks/{task.id}/complete/", **_api_headers())
        self.team.refresh_from_db()
        self.assertEqual(self.team.status, "completed")
        self.assertTrue(TeamEvent.objects.filter(event_type="mission_completed").exists())


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    NOCKCC_API_KEY=_TEST_API_KEY,
    TELEGRAM_ENABLED=False,
)
class EventsAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass", is_staff=True)
        self.team = AgentTeam.objects.create(name="Alpha", mission="Ship it")

    def test_list_events(self):
        TeamEvent.objects.create(team=self.team, event_type="mission_started", description="Go!")
        TeamEvent.objects.create(team=self.team, event_type="task_completed", description="Done")
        resp = self.client.get(f"/api/teams/{self.team.id}/events/", **_api_headers())
        data = resp.json()
        self.assertEqual(len(data["data"]["events"]), 2)

    def test_events_limited_to_50(self):
        for i in range(60):
            TeamEvent.objects.create(team=self.team, event_type="task_started", description=f"Task {i}")
        resp = self.client.get(f"/api/teams/{self.team.id}/events/", **_api_headers())
        data = resp.json()
        self.assertEqual(len(data["data"]["events"]), 50)


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    NOCKCC_API_KEY=_TEST_API_KEY,
    TELEGRAM_ENABLED=False,
)
class StatusTransitionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass", is_staff=True)
        self.team = AgentTeam.objects.create(name="Alpha", mission="Ship it")

    def test_team_activate_creates_event(self):
        _put_json(self.client, f"/api/teams/{self.team.id}/", {"status": "active"}, **_api_headers())
        self.assertTrue(TeamEvent.objects.filter(event_type="mission_started").exists())

    def test_team_complete_creates_event(self):
        self.team.status = "active"
        self.team.save()
        _put_json(self.client, f"/api/teams/{self.team.id}/", {"status": "completed"}, **_api_headers())
        self.assertTrue(TeamEvent.objects.filter(event_type="mission_completed").exists())

    def test_task_status_flow(self):
        """Test: pending → assigned → in_progress → in_review → completed"""
        member = TeamMember.objects.create(team=self.team, agent_name="Kit #1")
        task = TeamTask.objects.create(team=self.team, title="Flow test", status="pending")

        # Assign
        _put_json(
            self.client, f"/api/teams/{self.team.id}/tasks/{task.id}/",
            {"status": "assigned", "assigned_to": member.id},
            **_api_headers(),
        )
        task.refresh_from_db()
        self.assertEqual(task.status, "assigned")

        # Start
        self.client.post(f"/api/teams/{self.team.id}/tasks/{task.id}/start/", **_api_headers())
        task.refresh_from_db()
        self.assertEqual(task.status, "in_progress")

        # In review
        _put_json(
            self.client, f"/api/teams/{self.team.id}/tasks/{task.id}/",
            {"status": "in_review"},
            **_api_headers(),
        )
        task.refresh_from_db()
        self.assertEqual(task.status, "in_review")

        # Complete
        self.client.post(f"/api/teams/{self.team.id}/tasks/{task.id}/complete/", **_api_headers())
        task.refresh_from_db()
        self.assertEqual(task.status, "completed")


# ── Webhook integration tests ──


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    NOCKCC_API_KEY=_TEST_API_KEY,
    TELEGRAM_ENABLED=False,
)
class WebhookCrossReferenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass", is_staff=True)
        self.team = AgentTeam.objects.create(name="Alpha", mission="Ship it", status="active")
        self.member = TeamMember.objects.create(team=self.team, agent_name="Kit #1")

    def test_pr_opened_updates_task(self):
        task = TeamTask.objects.create(
            team=self.team, title="Build widget", status="in_progress",
            repo="kkwills13/nexus", branch="feature/widget",
            assigned_to=self.member,
        )
        from teams.signals import on_pr_opened
        on_pr_opened("kkwills13/nexus", "feature/widget", 42, "https://github.com/kkwills13/nexus/pull/42")

        task.refresh_from_db()
        self.assertEqual(task.pr_number, 42)
        self.assertEqual(task.pr_url, "https://github.com/kkwills13/nexus/pull/42")
        self.assertEqual(task.status, "in_review")
        self.assertTrue(TeamEvent.objects.filter(event_type="pr_opened").exists())

    def test_pr_merged_auto_completes_task(self):
        task = TeamTask.objects.create(
            team=self.team, title="Build widget", status="in_review",
            repo="kkwills13/nexus", pr_number=42,
            assigned_to=self.member,
        )
        self.member.current_task = task
        self.member.save(update_fields=["current_task"])

        from teams.signals import on_pr_merged
        on_pr_merged("kkwills13/nexus", 42)

        task.refresh_from_db()
        self.assertEqual(task.status, "completed")
        self.assertIsNotNone(task.completed_at)
        self.assertTrue(TeamEvent.objects.filter(event_type="pr_merged").exists())

        self.member.refresh_from_db()
        self.assertIsNone(self.member.current_task)

    def test_pr_merged_unblocks_dependents(self):
        dep = TeamTask.objects.create(
            team=self.team, title="Dep", status="in_review",
            repo="kkwills13/nexus", pr_number=42,
        )
        blocked = TeamTask.objects.create(
            team=self.team, title="Blocked", status="blocked",
            assigned_to=self.member,
        )
        blocked.depends_on.add(dep)

        from teams.signals import on_pr_merged
        on_pr_merged("kkwills13/nexus", 42)

        blocked.refresh_from_db()
        self.assertEqual(blocked.status, "assigned")

    def test_review_alert_creates_team_event(self):
        TeamTask.objects.create(
            team=self.team, title="Widget", status="in_review",
            repo="kkwills13/nexus", pr_number=42,
        )
        from teams.signals import on_review_alert
        on_review_alert("kkwills13/nexus", 42, "CodeRabbit", "approved")

        self.assertTrue(TeamEvent.objects.filter(event_type="review_completed").exists())


# ── Security tests ──


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY=_TEST_API_KEY)
class SecurityTests(TestCase):
    def test_api_requires_auth(self):
        resp = self.client.get("/api/teams/")
        self.assertEqual(resp.status_code, 401)

    def test_oversized_body_rejected(self):
        User.objects.create_user(username="testuser", password="pass", is_staff=True)
        big_body = json.dumps({"name": "x" * 40_000, "mission": "y"})
        resp = self.client.post(
            "/api/teams/",
            data=big_body,
            content_type="application/json",
            **_api_headers(),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("too large", resp.json()["message"])

    def test_field_length_limits(self):
        User.objects.create_user(username="testuser", password="pass", is_staff=True)
        resp = _post_json(
            self.client, "/api/teams/",
            {"name": "x" * 300, "mission": "Ship it"},
            **_api_headers(),
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        # Name should be truncated to 200
        self.assertLessEqual(len(data["data"]["name"]), 200)

    def test_invalid_team_id_404(self):
        User.objects.create_user(username="testuser", password="pass", is_staff=True)
        resp = self.client.get("/api/teams/99999/", **_api_headers())
        self.assertEqual(resp.status_code, 404)


# ── Task dependency chain test ──


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    NOCKCC_API_KEY=_TEST_API_KEY,
    TELEGRAM_ENABLED=False,
)
class DependencyChainTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass", is_staff=True)
        self.team = AgentTeam.objects.create(name="Alpha", mission="Ship it", status="active")

    def test_create_task_with_deps_sets_blocked(self):
        dep = TeamTask.objects.create(team=self.team, title="Dep", status="pending")
        resp = _post_json(
            self.client, f"/api/teams/{self.team.id}/tasks/",
            {"title": "Dependent", "depends_on": [dep.id]},
            **_api_headers(),
        )
        data = resp.json()
        self.assertEqual(data["data"]["status"], "blocked")
        self.assertEqual(data["data"]["depends_on"], [dep.id])
