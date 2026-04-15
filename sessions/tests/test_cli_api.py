"""Tests for the new API endpoints used by the CLI tool."""

import os
import secrets
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from pipeline.models import PullRequest, Repository
from sessions.models import AgentSession
from workspaces.models import Workspace, WorkspaceMembership

_TEST_FERNET_KEYS = [os.environ.get("TEST_FERNET_KEY", "")]
_TEST_WEBHOOK_SECRET = secrets.token_hex(16)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class PipelinePRsAPITests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(self.user)
        self.repo = Repository.objects.create(
            name="project-nexus",
            owner="kkwills13",
            github_id=100001,
            webhook_secret=_TEST_WEBHOOK_SECRET,
        )
        PullRequest.objects.create(
            repository=self.repo,
            github_pr_id=1001,
            number=1,
            title="Add dashboard",
            branch="feature/dashboard",
            author="kkwills13",
            state=PullRequest.State.OPEN,
            ci_status=PullRequest.CIStatus.PASSED,
            opened_at=timezone.now(),
        )
        PullRequest.objects.create(
            repository=self.repo,
            github_pr_id=1002,
            number=2,
            title="Fix login bug",
            branch="fix/login",
            author="kkwills13",
            state=PullRequest.State.MERGED,
            ci_status=PullRequest.CIStatus.PASSED,
            opened_at=timezone.now() - timedelta(days=2),
            merged_at=timezone.now() - timedelta(days=1),
        )

    def test_pipeline_prs_returns_json(self) -> None:
        resp = self.client.get("/api/pipeline/prs/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["total"], 2)
        self.assertEqual(len(body["data"]["prs"]), 2)

    def test_pipeline_prs_filter_by_repo(self) -> None:
        resp = self.client.get("/api/pipeline/prs/?repo=project-nexus")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["data"]["total"], 2)

    def test_pipeline_prs_filter_by_state(self) -> None:
        resp = self.client.get("/api/pipeline/prs/?state=open")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["data"]["total"], 1)
        self.assertEqual(body["data"]["prs"][0]["state"], "open")

    def test_pipeline_prs_limit(self) -> None:
        resp = self.client.get("/api/pipeline/prs/?limit=1")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body["data"]["prs"]), 1)

    def test_pipeline_prs_has_expected_keys(self) -> None:
        resp = self.client.get("/api/pipeline/prs/")
        body = resp.json()
        pr = body["data"]["prs"][0]
        expected_keys = {
            "number", "title", "repository", "branch", "author",
            "state", "ci_status", "coderabbit_status", "opened_at", "merged_at",
        }
        self.assertEqual(set(pr.keys()), expected_keys)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class DashboardSummaryAPITests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(self.user)
        self.repo = Repository.objects.create(
            name="test-repo",
            owner="kkwills13",
            github_id=200001,
            webhook_secret=_TEST_WEBHOOK_SECRET,
        )
        PullRequest.objects.create(
            repository=self.repo,
            github_pr_id=2001,
            number=1,
            title="Open PR",
            branch="feature/open",
            author="kkwills13",
            state=PullRequest.State.OPEN,
            ci_status=PullRequest.CIStatus.FAILED,
            opened_at=timezone.now(),
        )
        PullRequest.objects.create(
            repository=self.repo,
            github_pr_id=2002,
            number=2,
            title="Merged PR",
            branch="feature/merged",
            author="kkwills13",
            state=PullRequest.State.MERGED,
            ci_status=PullRequest.CIStatus.PASSED,
            opened_at=timezone.now() - timedelta(days=2),
            merged_at=timezone.now() - timedelta(hours=1),
        )
        AgentSession.objects.create(agent="claude_code", status="active")
        AgentSession.objects.create(agent="copilot", status="completed")

    def test_summary_returns_expected_keys(self) -> None:
        resp = self.client.get("/api/dashboard/summary/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        data = body["data"]
        expected_keys = {"open_prs", "failed_ci", "merged_this_week", "active_sessions", "todays_spend"}
        self.assertEqual(set(data.keys()), expected_keys)

    def test_summary_counts_correct(self) -> None:
        resp = self.client.get("/api/dashboard/summary/")
        body = resp.json()
        data = body["data"]
        self.assertEqual(data["open_prs"], 1)
        self.assertEqual(data["failed_ci"], 1)
        self.assertEqual(data["merged_this_week"], 1)
        self.assertEqual(data["active_sessions"], 1)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class SessionListPageTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(self.user)
        self.workspace = Workspace.objects.create(name="Test Workspace", owner=self.user)
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=self.user, role=WorkspaceMembership.ROLE_OWNER,
            accepted_at=timezone.now(),
        )

    def test_sessions_page_returns_200(self) -> None:
        resp = self.client.get("/sessions/")
        self.assertEqual(resp.status_code, 200)

    def test_sessions_page_shows_sessions(self) -> None:
        AgentSession.objects.create(
            agent="claude_code", machine="mac", branch="feature/test", status="active",
            workspace=self.workspace,
        )
        resp = self.client.get("/sessions/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Claude Code")
        self.assertContains(resp, "feature/test")

    def test_sessions_page_filter_by_agent(self) -> None:
        AgentSession.objects.create(agent="claude_code", status="active", branch="branch-cc", workspace=self.workspace)
        AgentSession.objects.create(agent="copilot", status="active", branch="branch-cop", workspace=self.workspace)
        resp = self.client.get("/sessions/?agent=claude_code")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "branch-cc")
        self.assertNotContains(resp, "branch-cop")
