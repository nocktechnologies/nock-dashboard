import os
from datetime import UTC, datetime
from itertools import count as _counter

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from pipeline.models import PREvent, PullRequest, Repository
from workspaces.models import Workspace, WorkspaceMembership

_TEST_FERNET_KEYS = [os.environ["TEST_FERNET_KEY"]]
_TEST_WEBHOOK_SECRET = os.environ["TEST_WEBHOOK_SECRET"]

_REPO_GH_ID_SEQ = _counter(99000)


def make_repo(workspace=None) -> Repository:
    return Repository.objects.create(
        name="test-repo", owner="testuser",
        github_id=next(_REPO_GH_ID_SEQ),
        webhook_secret=_TEST_WEBHOOK_SECRET,
        workspace=workspace,
    )


def make_pr(repo: Repository, number: int = 1, state: str = "open", workspace=None, **kwargs) -> PullRequest:
    return PullRequest.objects.create(
        repository=repo,
        github_pr_id=number,
        number=number,
        title=f"PR #{number}",
        branch="feature/test",
        author="dev",
        state=state,
        opened_at=datetime(2026, 3, 14, 10, 0, tzinfo=UTC),
        workspace=workspace,
        **kwargs,
    )


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class DashboardViewTests(TestCase):

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(self.user)

    def test_dashboard_loads_empty(self) -> None:
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "dashboard/index.html")

    def test_dashboard_shows_open_pr_count(self) -> None:
        repo = make_repo()
        make_pr(repo, 1, state="open")
        make_pr(repo, 2, state="open")
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["open_pr_count"], 2)

    def test_dashboard_empty_state_graceful(self) -> None:
        resp = self.client.get("/")
        self.assertContains(resp, "No merged PRs yet")

    def test_dashboard_shows_failed_ci(self) -> None:
        repo = make_repo()
        make_pr(repo, 1, state="open", ci_status="failed")
        resp = self.client.get("/")
        self.assertEqual(len(resp.context["failed_ci_prs"]), 1)

    def test_pipeline_status_api_returns_json(self) -> None:
        resp = self.client.get("/api/pipeline/status/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("message", data)
        self.assertIsInstance(data["message"], str)
        self.assertTrue(data["message"].strip())
        self.assertIn("open_pr_count", data["data"])
        self.assertIn("failed_ci_count", data["data"])
        self.assertIn("latest_event_at", data["data"])

    def test_pipeline_status_api_counts(self) -> None:
        repo = make_repo()
        make_pr(repo, 1, state="open", ci_status="failed")
        make_pr(repo, 2, state="open", ci_status="passed")
        resp = self.client.get("/api/pipeline/status/")
        data = resp.json()["data"]
        self.assertEqual(data["open_pr_count"], 2)
        self.assertEqual(data["failed_ci_count"], 1)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class PipelineListViewTests(TestCase):

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(self.user)
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=self.user, role=WorkspaceMembership.ROLE_OWNER,
            accepted_at=timezone.now(),
        )

    def test_pipeline_list_loads(self) -> None:
        resp = self.client.get("/pipeline/")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "pipeline/list.html")

    def test_pipeline_list_shows_prs(self) -> None:
        repo = make_repo(workspace=self.workspace)
        make_pr(repo, 1, workspace=self.workspace)
        make_pr(repo, 2, workspace=self.workspace)
        resp = self.client.get("/pipeline/")
        self.assertEqual(resp.context["prs"].count(), 2)

    def test_pipeline_list_filter_by_state(self) -> None:
        repo = make_repo(workspace=self.workspace)
        make_pr(repo, 1, state="open", workspace=self.workspace)
        make_pr(repo, 2, state="merged", merged_at=datetime(2026, 3, 14, 12, 0, tzinfo=UTC), workspace=self.workspace)
        resp = self.client.get("/pipeline/?state=open")
        self.assertEqual(resp.context["prs"].count(), 1)

    def test_pipeline_list_filter_by_repo(self) -> None:
        repo1 = make_repo(workspace=self.workspace)
        repo2 = Repository.objects.create(
            name="other-repo", owner="testuser", github_id=88888, webhook_secret=_TEST_WEBHOOK_SECRET,
            workspace=self.workspace,
        )
        make_pr(repo1, 1, workspace=self.workspace)
        make_pr(repo2, 2, workspace=self.workspace)
        resp = self.client.get(f"/pipeline/?repository={repo1.pk}")
        self.assertEqual(resp.context["prs"].count(), 1)

    def test_pipeline_list_empty_state(self) -> None:
        resp = self.client.get("/pipeline/")
        self.assertContains(resp, "No pull requests found")


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class PRDetailViewTests(TestCase):

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(self.user)
        self.workspace = Workspace.objects.create(name="Test Workspace 2", owner=self.user)
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=self.user, role=WorkspaceMembership.ROLE_OWNER,
            accepted_at=timezone.now(),
        )

    def test_pr_detail_loads(self) -> None:
        repo = make_repo(workspace=self.workspace)
        make_pr(repo, 42, workspace=self.workspace)
        resp = self.client.get("/pipeline/testuser/test-repo/42/")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "pipeline/detail.html")

    def test_pr_detail_shows_events(self) -> None:
        repo = make_repo(workspace=self.workspace)
        pr = make_pr(repo, 42, workspace=self.workspace)
        PREvent.objects.create(
            pull_request=pr, event_type="opened", actor="dev",
            delivery_id="test-del-1", payload={"delivery_id": "test-del-1"},
        )
        resp = self.client.get("/pipeline/testuser/test-repo/42/")
        self.assertEqual(resp.context["events"].count(), 1)

    def test_pr_detail_404_for_unknown_pr(self) -> None:
        make_repo(workspace=self.workspace)
        resp = self.client.get("/pipeline/testuser/test-repo/999/")
        self.assertEqual(resp.status_code, 404)

    def test_pr_detail_404_for_unknown_repo(self) -> None:
        resp = self.client.get("/pipeline/nobody/no-repo/1/")
        self.assertEqual(resp.status_code, 404)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class SeedCommandTests(TestCase):

    def test_seed_command_creates_data(self) -> None:
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("seed_pipeline_data", confirm=True, stdout=out)
        self.assertGreaterEqual(Repository.objects.count(), 2)
        self.assertGreaterEqual(PullRequest.objects.count(), 10)
        self.assertGreaterEqual(PREvent.objects.count(), 10)
        self.assertIn("Done", out.getvalue())
