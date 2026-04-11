"""Tests for Asana integration — models, fuzzy linking, views, sync."""
import os
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from pipeline.models import PullRequest, Repository
from tasks.asana_client import _parse_priority, parse_task
from tasks.models import AsanaProject, AsanaTask
from tasks.tasks import _words, link_tasks_to_prs

_TEST_FERNET_KEYS = [os.environ.get("TEST_FERNET_KEY", "rBj4e7L0PbE7E3H5JhLdOwvSXa3Z3g1mJbkBrkIg5cI=")]


def make_project(name: str = "Test Project", color: str = "blue") -> AsanaProject:
    import secrets as _secrets
    return AsanaProject.objects.create(
        asana_gid=_secrets.token_hex(8),
        name=name,
        color=color,
    )


def make_task(project: AsanaProject, name: str = "Test Task", due_days: int | None = None) -> AsanaTask:
    import secrets as _secrets
    due = (timezone.localdate() + timedelta(days=due_days)) if due_days is not None else None
    return AsanaTask.objects.create(
        asana_gid=_secrets.token_hex(8),
        project=project,
        name=name,
        due_on=due,
    )


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class AsanaModelTests(TestCase):

    def test_project_creation(self) -> None:
        proj = make_project("Project Nexus", "blue")
        self.assertEqual(str(proj), "Project Nexus")
        self.assertTrue(proj.is_active)

    def test_task_creation(self) -> None:
        proj = make_project()
        task = make_task(proj, "Build pipeline models")
        self.assertEqual(str(task), "Build pipeline models")
        self.assertFalse(task.completed)

    def test_is_overdue_past_due(self) -> None:
        proj = make_project()
        task = make_task(proj, "Overdue task", due_days=-2)
        self.assertTrue(task.is_overdue)

    def test_is_overdue_future(self) -> None:
        proj = make_project()
        task = make_task(proj, "Future task", due_days=5)
        self.assertFalse(task.is_overdue)

    def test_is_overdue_no_due_date(self) -> None:
        proj = make_project()
        task = make_task(proj, "No due date")
        self.assertFalse(task.is_overdue)

    def test_is_overdue_completed(self) -> None:
        proj = make_project()
        task = make_task(proj, "Done task", due_days=-2)
        task.completed = True
        task.save()
        self.assertFalse(task.is_overdue)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class FuzzyLinkingTests(TestCase):

    def setUp(self) -> None:
        import secrets as _secrets
        self.repo = Repository.objects.create(
            name="nock-command-center",
            owner="kkwills13",
            github_id=_secrets.randbelow(900000) + 100000,
            webhook_secret=os.environ.get("TEST_WEBHOOK_SECRET", "test-secret"),
        )

    def _make_pr(self, title: str, branch: str) -> PullRequest:
        return PullRequest.objects.create(
            repository=self.repo,
            github_pr_id=PullRequest.objects.count() + 1,
            number=PullRequest.objects.count() + 1,
            title=title,
            branch=branch,
            author="kev",
            state="open",
            opened_at=timezone.now(),
        )

    def test_fuzzy_match_links_task_to_pr(self) -> None:
        proj = make_project()
        task = make_task(proj, "Pipeline Models — Repository PullRequest Branch")
        pr = self._make_pr("feat: pipeline models", "feature/pipeline-models")
        link_tasks_to_prs()
        task.refresh_from_db()
        self.assertEqual(task.linked_pr, pr)

    def test_fuzzy_no_match_unrelated(self) -> None:
        proj = make_project()
        task = make_task(proj, "Design marketing landing page")
        self._make_pr("feat: pipeline models", "feature/pipeline-models")
        link_tasks_to_prs()
        task.refresh_from_db()
        self.assertIsNone(task.linked_pr)

    def test_words_normalisation(self) -> None:
        words = _words("feat: Add Pipeline Models — Repository")
        self.assertIn("pipeline", words)
        self.assertIn("models", words)
        self.assertIn("repository", words)
        self.assertNotIn("feat", words)  # stop word


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class ParseTaskTests(TestCase):

    def test_parse_task_basic(self) -> None:
        raw = {
            "gid": "123456",
            "name": "Test task",
            "assignee": {"name": "Kevin"},
            "due_on": "2026-03-20",
            "completed": False,
            "completed_at": None,
            "notes": "Some notes here",
            "memberships": [{"section": {"name": "In Progress"}}],
            "permalink_url": "https://app.asana.com/task/123",
            "custom_fields": [],
        }
        parsed = parse_task(raw)
        self.assertEqual(parsed["name"], "Test task")
        self.assertEqual(parsed["assignee_name"], "Kevin")
        self.assertEqual(parsed["section_name"], "In Progress")
        self.assertEqual(parsed["due_on"], "2026-03-20")

    def test_parse_priority_from_custom_fields(self) -> None:
        custom_fields = [
            {"name": "Priority", "enum_value": {"name": "High"}},
        ]
        priority = _parse_priority(custom_fields)
        self.assertEqual(priority, "high")

    def test_parse_priority_missing(self) -> None:
        self.assertIsNone(_parse_priority([]))


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class TaskViewTests(TestCase):

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(self.user)

    def test_task_feed_loads(self) -> None:
        resp = self.client.get("/tasks/")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "tasks/feed.html")

    def test_task_feed_empty_state(self) -> None:
        resp = self.client.get("/tasks/")
        self.assertContains(resp, "No tasks found")

    def test_handoffs_loads(self) -> None:
        resp = self.client.get("/handoffs/")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "tasks/handoffs.html")

    def test_dashboard_shows_upcoming_tasks(self) -> None:
        proj = make_project()
        make_task(proj, "Important upcoming task", due_days=2)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("upcoming_tasks", resp.context)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class SeedCommandTests(TestCase):

    def test_seed_asana_projects(self) -> None:
        from io import StringIO

        from django.core.management import call_command
        out = StringIO()
        call_command("seed_asana_projects", "--confirm", stdout=out)
        self.assertEqual(AsanaProject.objects.count(), 4)
        self.assertIn("Done", out.getvalue())
        gids = list(AsanaProject.objects.values_list("asana_gid", flat=True))
        self.assertIn("1213659188123153", gids)
        self.assertIn("1213660356472624", gids)
