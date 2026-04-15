"""Cross-tenant isolation tests — Phase 5 of P75.

Each test creates objects in workspace_a and workspace_b, then verifies that
tenant_objects.for_request(request) scoped to workspace_a returns ONLY
workspace_a's rows. 24 models × 2 assertions + cross-cutting edge cases.
"""
from __future__ import annotations

import pytest
from django.test import RequestFactory
from django.utils import timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_TEST_FERNET_KEYS = ["rBj4e7L0PbE7E3H5JhLdOwvSXa3Z3g1mJbkBrkIg5cI="]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _fernet(settings):
    """Set a test Fernet key so Repository.webhook_secret encrypts cleanly."""
    settings.FERNET_KEYS = _TEST_FERNET_KEYS


@pytest.fixture
def rf():
    return RequestFactory()


def _req(rf, user, workspace):
    """Build a fake request with user + workspace attached."""
    r = rf.get("/")
    r.user = user
    r.workspace = workspace
    return r


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def repo_a(db, workspace_a):
    from pipeline.models import Repository
    return Repository.objects.create(
        name="repo-a", owner="kkwills13", github_id=1001,
        webhook_secret="s3cr3t", workspace=workspace_a,
    )


@pytest.fixture
def repo_b(db, workspace_b):
    from pipeline.models import Repository
    return Repository.objects.create(
        name="repo-b", owner="kkwills13", github_id=1002,
        webhook_secret="s3cr3t", workspace=workspace_b,
    )


@pytest.fixture
def pr_a(db, repo_a, workspace_a):
    from pipeline.models import PullRequest
    return PullRequest.objects.create(
        repository=repo_a, github_pr_id=101, number=1,
        title="PR A", branch="feat/a", author="alice",
        state="open", opened_at=timezone.now(), workspace=workspace_a,
    )


@pytest.fixture
def pr_b(db, repo_b, workspace_b):
    from pipeline.models import PullRequest
    return PullRequest.objects.create(
        repository=repo_b, github_pr_id=102, number=1,
        title="PR B", branch="feat/b", author="bob",
        state="open", opened_at=timezone.now(), workspace=workspace_b,
    )


# ---------------------------------------------------------------------------
# Pipeline: Repository
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestRepositoryIsolation:
    def test_for_request_returns_own_workspace_repo(self, rf, user_a, workspace_a, repo_a, repo_b):
        from pipeline.models import Repository
        req = _req(rf, user_a, workspace_a)
        qs = Repository.tenant_objects.for_request(req)
        assert repo_a in qs
        assert repo_b not in qs

    def test_for_request_returns_no_other_workspace(self, rf, user_b, workspace_b, repo_a, repo_b):
        from pipeline.models import Repository
        req = _req(rf, user_b, workspace_b)
        qs = Repository.tenant_objects.for_request(req)
        assert repo_b in qs
        assert repo_a not in qs


# ---------------------------------------------------------------------------
# Pipeline: PullRequest
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestPullRequestIsolation:
    def test_for_request_scopes_to_workspace(self, rf, user_a, workspace_a, pr_a, pr_b):
        from pipeline.models import PullRequest
        req = _req(rf, user_a, workspace_a)
        qs = PullRequest.tenant_objects.for_request(req)
        assert pr_a in qs
        assert pr_b not in qs

    def test_other_workspace_user_cannot_see_pr(self, rf, user_b, workspace_b, pr_a, pr_b):
        from pipeline.models import PullRequest
        req = _req(rf, user_b, workspace_b)
        qs = PullRequest.tenant_objects.for_request(req)
        assert pr_b in qs
        assert pr_a not in qs


# ---------------------------------------------------------------------------
# Pipeline: PREvent
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestPREventIsolation:
    def test_pr_event_scoped_to_workspace(self, rf, user_a, workspace_a, workspace_b, pr_a, pr_b):
        from pipeline.models import PREvent
        ev_a = PREvent.objects.create(
            pull_request=pr_a, event_type="opened", actor="alice",
            workspace=workspace_a,
        )
        ev_b = PREvent.objects.create(
            pull_request=pr_b, event_type="opened", actor="bob",
            workspace=workspace_b,
        )
        req = _req(rf, user_a, workspace_a)
        qs = PREvent.tenant_objects.for_request(req)
        assert ev_a in qs
        assert ev_b not in qs

    def test_pr_event_no_cross_tenant_leakage(self, rf, user_b, workspace_a, workspace_b, pr_a, pr_b):
        from pipeline.models import PREvent
        ev_a = PREvent.objects.create(
            pull_request=pr_a, event_type="closed", actor="alice",
            workspace=workspace_a,
        )
        ev_b = PREvent.objects.create(
            pull_request=pr_b, event_type="closed", actor="bob",
            workspace=workspace_b,
        )
        req = _req(rf, user_b, workspace_b)
        qs = PREvent.tenant_objects.for_request(req)
        assert ev_b in qs
        assert ev_a not in qs


# ---------------------------------------------------------------------------
# Pipeline: Branch
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestBranchIsolation:
    def test_branch_scoped_to_workspace(self, rf, user_a, workspace_a, workspace_b, repo_a, repo_b):
        from pipeline.models import Branch
        br_a = Branch.objects.create(
            repository=repo_a, name="main", last_commit_sha="abc" * 13 + "a",
            workspace=workspace_a,
        )
        br_b = Branch.objects.create(
            repository=repo_b, name="main", last_commit_sha="abc" * 13 + "b",
            workspace=workspace_b,
        )
        req = _req(rf, user_a, workspace_a)
        qs = Branch.tenant_objects.for_request(req)
        assert br_a in qs
        assert br_b not in qs

    def test_branch_other_workspace_excluded(self, rf, user_b, workspace_a, workspace_b, repo_a, repo_b):
        from pipeline.models import Branch
        br_a = Branch.objects.create(
            repository=repo_a, name="feat-x", last_commit_sha="def" * 13 + "a",
            workspace=workspace_a,
        )
        br_b = Branch.objects.create(
            repository=repo_b, name="feat-x", last_commit_sha="def" * 13 + "b",
            workspace=workspace_b,
        )
        req = _req(rf, user_b, workspace_b)
        qs = Branch.tenant_objects.for_request(req)
        assert br_b in qs
        assert br_a not in qs


# ---------------------------------------------------------------------------
# Pipeline: BranchEvent
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestBranchEventIsolation:
    def test_branch_event_scoped_to_workspace(self, rf, user_a, workspace_a, workspace_b, repo_a, repo_b):
        from pipeline.models import BranchEvent
        be_a = BranchEvent.objects.create(
            repository=repo_a, delivery_id="del-a", ref="refs/heads/main",
            workspace=workspace_a,
        )
        be_b = BranchEvent.objects.create(
            repository=repo_b, delivery_id="del-b", ref="refs/heads/main",
            workspace=workspace_b,
        )
        req = _req(rf, user_a, workspace_a)
        qs = BranchEvent.tenant_objects.for_request(req)
        assert be_a in qs
        assert be_b not in qs


# ---------------------------------------------------------------------------
# Pipeline: ReviewAlert
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestReviewAlertIsolation:
    def _make_alert(self, workspace, suffix="a"):
        from pipeline.models import ReviewAlert
        return ReviewAlert.objects.create(
            repo=f"kkwills13/repo-{suffix}",
            pr_number=1,
            pr_title=f"PR {suffix}",
            pr_url=f"https://github.com/kkwills13/repo-{suffix}/pull/1",
            reviewer=ReviewAlert.Reviewer.CODERABBIT,
            reviewer_login="coderabbitai[bot]",
            status=ReviewAlert.Status.APPROVED,
            workspace=workspace,
        )

    def test_review_alert_scoped(self, rf, user_a, workspace_a, workspace_b):
        from pipeline.models import ReviewAlert
        al_a = self._make_alert(workspace_a, "a")
        al_b = self._make_alert(workspace_b, "b")
        req = _req(rf, user_a, workspace_a)
        qs = ReviewAlert.tenant_objects.for_request(req)
        assert al_a in qs
        assert al_b not in qs

    def test_review_alert_no_leakage_to_other_tenant(self, rf, user_b, workspace_a, workspace_b):
        from pipeline.models import ReviewAlert
        al_a = self._make_alert(workspace_a, "c")
        al_b = self._make_alert(workspace_b, "d")
        req = _req(rf, user_b, workspace_b)
        qs = ReviewAlert.tenant_objects.for_request(req)
        assert al_b in qs
        assert al_a not in qs


# ---------------------------------------------------------------------------
# Pipeline: PipelineEvent
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestPipelineEventIsolation:
    def _make_event(self, workspace, suffix="a"):
        from pipeline.models import PipelineEvent
        return PipelineEvent.objects.create(
            workflow_id=f"wf-{suffix}",
            repo="nock-command-center",
            category=PipelineEvent.Category.BUILD,
            title=f"Build {suffix}",
            workspace=workspace,
        )

    def test_pipeline_event_scoped(self, rf, user_a, workspace_a, workspace_b):
        from pipeline.models import PipelineEvent
        ev_a = self._make_event(workspace_a, "x")
        ev_b = self._make_event(workspace_b, "y")
        req = _req(rf, user_a, workspace_a)
        qs = PipelineEvent.tenant_objects.for_request(req)
        assert ev_a in qs
        assert ev_b not in qs

    def test_pipeline_event_other_workspace_sees_own(self, rf, user_b, workspace_a, workspace_b):
        from pipeline.models import PipelineEvent
        ev_a = self._make_event(workspace_a, "p")
        ev_b = self._make_event(workspace_b, "q")
        req = _req(rf, user_b, workspace_b)
        qs = PipelineEvent.tenant_objects.for_request(req)
        assert ev_b in qs
        assert ev_a not in qs


# ---------------------------------------------------------------------------
# Sessions: AgentSession
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestAgentSessionIsolation:
    def _make_session(self, workspace):
        from sessions.models import AgentSession
        return AgentSession.objects.create(
            agent="claude_code", workspace=workspace,
        )

    def test_agent_session_scoped(self, rf, user_a, workspace_a, workspace_b):
        from sessions.models import AgentSession
        s_a = self._make_session(workspace_a)
        s_b = self._make_session(workspace_b)
        req = _req(rf, user_a, workspace_a)
        qs = AgentSession.tenant_objects.for_request(req)
        assert s_a in qs
        assert s_b not in qs

    def test_agent_session_no_cross_tenant(self, rf, user_b, workspace_a, workspace_b):
        from sessions.models import AgentSession
        s_a = self._make_session(workspace_a)
        s_b = self._make_session(workspace_b)
        req = _req(rf, user_b, workspace_b)
        qs = AgentSession.tenant_objects.for_request(req)
        assert s_b in qs
        assert s_a not in qs


# ---------------------------------------------------------------------------
# Sessions: SessionLog
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestSessionLogIsolation:
    def test_session_log_scoped(self, rf, user_a, workspace_a, workspace_b):
        from sessions.models import AgentSession, SessionLog
        s_a = AgentSession.objects.create(agent="claude_code", workspace=workspace_a)
        s_b = AgentSession.objects.create(agent="codex", workspace=workspace_b)
        log_a = SessionLog.objects.create(session=s_a, level="info", message="a", workspace=workspace_a)
        log_b = SessionLog.objects.create(session=s_b, level="info", message="b", workspace=workspace_b)
        req = _req(rf, user_a, workspace_a)
        qs = SessionLog.tenant_objects.for_request(req)
        assert log_a in qs
        assert log_b not in qs


# ---------------------------------------------------------------------------
# Sessions: TerminalHeartbeat
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestTerminalHeartbeatIsolation:
    def test_heartbeat_scoped(self, rf, user_a, workspace_a, workspace_b):
        from sessions.models import TerminalHeartbeat
        hb_a = TerminalHeartbeat.objects.create(machine="mac-a", workspace=workspace_a)
        hb_b = TerminalHeartbeat.objects.create(machine="mac-b", workspace=workspace_b)
        req = _req(rf, user_a, workspace_a)
        qs = TerminalHeartbeat.tenant_objects.for_request(req)
        assert hb_a in qs
        assert hb_b not in qs


# ---------------------------------------------------------------------------
# Notifications: NotificationChannel
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestNotificationChannelIsolation:
    def _make_channel(self, workspace, name):
        from notifications.models import NotificationChannel
        return NotificationChannel.objects.create(
            name=name, channel_type="slack",
            webhook_url="https://hooks.slack.com/test",
            workspace=workspace,
        )

    def test_channel_scoped(self, rf, user_a, workspace_a, workspace_b):
        from notifications.models import NotificationChannel
        ch_a = self._make_channel(workspace_a, "ch-a")
        ch_b = self._make_channel(workspace_b, "ch-b")
        req = _req(rf, user_a, workspace_a)
        qs = NotificationChannel.tenant_objects.for_request(req)
        assert ch_a in qs
        assert ch_b not in qs

    def test_channel_cross_tenant(self, rf, user_b, workspace_a, workspace_b):
        from notifications.models import NotificationChannel
        ch_a = self._make_channel(workspace_a, "ch-x")
        ch_b = self._make_channel(workspace_b, "ch-y")
        req = _req(rf, user_b, workspace_b)
        qs = NotificationChannel.tenant_objects.for_request(req)
        assert ch_b in qs
        assert ch_a not in qs


# ---------------------------------------------------------------------------
# Notifications: NotificationRule
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestNotificationRuleIsolation:
    def test_rule_scoped(self, rf, user_a, workspace_a, workspace_b):
        from notifications.models import NotificationChannel, NotificationRule
        ch_a = NotificationChannel.objects.create(
            name="r-ch-a", channel_type="slack",
            webhook_url="https://hooks.slack.com/a", workspace=workspace_a,
        )
        ch_b = NotificationChannel.objects.create(
            name="r-ch-b", channel_type="slack",
            webhook_url="https://hooks.slack.com/b", workspace=workspace_b,
        )
        rule_a = NotificationRule.objects.create(
            name="rule-a", trigger_event="pr_merged", channel=ch_a, workspace=workspace_a,
        )
        rule_b = NotificationRule.objects.create(
            name="rule-b", trigger_event="pr_merged", channel=ch_b, workspace=workspace_b,
        )
        req = _req(rf, user_a, workspace_a)
        qs = NotificationRule.tenant_objects.for_request(req)
        assert rule_a in qs
        assert rule_b not in qs


# ---------------------------------------------------------------------------
# Notifications: NotificationLog
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestNotificationLogIsolation:
    def test_log_scoped(self, rf, user_a, workspace_a, workspace_b):
        from notifications.models import NotificationChannel, NotificationLog
        ch_a = NotificationChannel.objects.create(
            name="l-ch-a", channel_type="discord",
            webhook_url="https://discord.com/a", workspace=workspace_a,
        )
        ch_b = NotificationChannel.objects.create(
            name="l-ch-b", channel_type="discord",
            webhook_url="https://discord.com/b", workspace=workspace_b,
        )
        log_a = NotificationLog.objects.create(
            channel=ch_a, event_type="pr_merged", workspace=workspace_a,
        )
        log_b = NotificationLog.objects.create(
            channel=ch_b, event_type="pr_merged", workspace=workspace_b,
        )
        req = _req(rf, user_a, workspace_a)
        qs = NotificationLog.tenant_objects.for_request(req)
        assert log_a in qs
        assert log_b not in qs


# ---------------------------------------------------------------------------
# Tasks: AsanaProject
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestAsanaProjectIsolation:
    def test_project_scoped(self, rf, user_a, workspace_a, workspace_b):
        from tasks.models import AsanaProject
        proj_a = AsanaProject.objects.create(asana_gid="gid-a", name="Proj A", workspace=workspace_a)
        proj_b = AsanaProject.objects.create(asana_gid="gid-b", name="Proj B", workspace=workspace_b)
        req = _req(rf, user_a, workspace_a)
        qs = AsanaProject.tenant_objects.for_request(req)
        assert proj_a in qs
        assert proj_b not in qs

    def test_project_other_tenant(self, rf, user_b, workspace_a, workspace_b):
        from tasks.models import AsanaProject
        proj_a = AsanaProject.objects.create(asana_gid="gid-c", name="Proj C", workspace=workspace_a)
        proj_b = AsanaProject.objects.create(asana_gid="gid-d", name="Proj D", workspace=workspace_b)
        req = _req(rf, user_b, workspace_b)
        qs = AsanaProject.tenant_objects.for_request(req)
        assert proj_b in qs
        assert proj_a not in qs


# ---------------------------------------------------------------------------
# Tasks: AsanaSection
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestAsanaSectionIsolation:
    def test_section_scoped(self, rf, user_a, workspace_a, workspace_b):
        from tasks.models import AsanaProject, AsanaSection
        proj_a = AsanaProject.objects.create(asana_gid="sp-a", name="P A", workspace=workspace_a)
        proj_b = AsanaProject.objects.create(asana_gid="sp-b", name="P B", workspace=workspace_b)
        sec_a = AsanaSection.objects.create(asana_gid="sec-a", name="Sec A", project=proj_a, workspace=workspace_a)
        sec_b = AsanaSection.objects.create(asana_gid="sec-b", name="Sec B", project=proj_b, workspace=workspace_b)
        req = _req(rf, user_a, workspace_a)
        qs = AsanaSection.tenant_objects.for_request(req)
        assert sec_a in qs
        assert sec_b not in qs


# ---------------------------------------------------------------------------
# Tasks: AsanaTask
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestAsanaTaskIsolation:
    def test_task_scoped(self, rf, user_a, workspace_a, workspace_b):
        from tasks.models import AsanaProject, AsanaTask
        proj_a = AsanaProject.objects.create(asana_gid="tp-a", name="TP A", workspace=workspace_a)
        proj_b = AsanaProject.objects.create(asana_gid="tp-b", name="TP B", workspace=workspace_b)
        task_a = AsanaTask.objects.create(asana_gid="task-a", project=proj_a, name="Task A", workspace=workspace_a)
        task_b = AsanaTask.objects.create(asana_gid="task-b", project=proj_b, name="Task B", workspace=workspace_b)
        req = _req(rf, user_a, workspace_a)
        qs = AsanaTask.tenant_objects.for_request(req)
        assert task_a in qs
        assert task_b not in qs

    def test_task_other_tenant_excluded(self, rf, user_b, workspace_a, workspace_b):
        from tasks.models import AsanaProject, AsanaTask
        proj_a = AsanaProject.objects.create(asana_gid="tp-c", name="TP C", workspace=workspace_a)
        proj_b = AsanaProject.objects.create(asana_gid="tp-d", name="TP D", workspace=workspace_b)
        task_a = AsanaTask.objects.create(asana_gid="task-c", project=proj_a, name="Task C", workspace=workspace_a)
        task_b = AsanaTask.objects.create(asana_gid="task-d", project=proj_b, name="Task D", workspace=workspace_b)
        req = _req(rf, user_b, workspace_b)
        qs = AsanaTask.tenant_objects.for_request(req)
        assert task_b in qs
        assert task_a not in qs


# ---------------------------------------------------------------------------
# Teams: AgentTeam
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestAgentTeamIsolation:
    def test_team_scoped(self, rf, user_a, workspace_a, workspace_b):
        from teams.models import AgentTeam
        team_a = AgentTeam.objects.create(name="Team A", mission="Build X", workspace=workspace_a)
        team_b = AgentTeam.objects.create(name="Team B", mission="Build Y", workspace=workspace_b)
        req = _req(rf, user_a, workspace_a)
        qs = AgentTeam.tenant_objects.for_request(req)
        assert team_a in qs
        assert team_b not in qs

    def test_team_other_tenant(self, rf, user_b, workspace_a, workspace_b):
        from teams.models import AgentTeam
        team_a = AgentTeam.objects.create(name="Team C", mission="Build C", workspace=workspace_a)
        team_b = AgentTeam.objects.create(name="Team D", mission="Build D", workspace=workspace_b)
        req = _req(rf, user_b, workspace_b)
        qs = AgentTeam.tenant_objects.for_request(req)
        assert team_b in qs
        assert team_a not in qs


# ---------------------------------------------------------------------------
# Teams: PromptFile
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestPromptFileIsolation:
    def test_prompt_file_scoped(self, rf, user_a, workspace_a, workspace_b):
        from teams.models import PromptFile
        pf_a = PromptFile.objects.create(
            title="Prompt A", content="do a", target_repo="kkwills13/repo",
            workspace=workspace_a,
        )
        pf_b = PromptFile.objects.create(
            title="Prompt B", content="do b", target_repo="kkwills13/repo",
            workspace=workspace_b,
        )
        req = _req(rf, user_a, workspace_a)
        qs = PromptFile.tenant_objects.for_request(req)
        assert pf_a in qs
        assert pf_b not in qs

    def test_prompt_file_other_tenant(self, rf, user_b, workspace_a, workspace_b):
        from teams.models import PromptFile
        pf_a = PromptFile.objects.create(
            title="Prompt C", content="do c", target_repo="kkwills13/repo",
            workspace=workspace_a,
        )
        pf_b = PromptFile.objects.create(
            title="Prompt D", content="do d", target_repo="kkwills13/repo",
            workspace=workspace_b,
        )
        req = _req(rf, user_b, workspace_b)
        qs = PromptFile.tenant_objects.for_request(req)
        assert pf_b in qs
        assert pf_a not in qs


# ---------------------------------------------------------------------------
# Context: ContextDocument
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestContextDocumentIsolation:
    def test_context_doc_scoped(self, rf, user_a, workspace_a, workspace_b, repo_a, repo_b):
        from context.models import ContextDocument
        doc_a = ContextDocument.objects.create(
            repository=repo_a, doc_type="claude_md",
            file_path="CLAUDE.md", title="Claude A",
            workspace=workspace_a,
        )
        doc_b = ContextDocument.objects.create(
            repository=repo_b, doc_type="claude_md",
            file_path="CLAUDE.md", title="Claude B",
            workspace=workspace_b,
        )
        req = _req(rf, user_a, workspace_a)
        qs = ContextDocument.tenant_objects.for_request(req)
        assert doc_a in qs
        assert doc_b not in qs

    def test_context_doc_other_tenant(self, rf, user_b, workspace_a, workspace_b, repo_a, repo_b):
        from context.models import ContextDocument
        doc_a = ContextDocument.objects.create(
            repository=repo_a, doc_type="architecture",
            file_path="ARCHITECTURE.md", title="Arch A",
            workspace=workspace_a,
        )
        doc_b = ContextDocument.objects.create(
            repository=repo_b, doc_type="architecture",
            file_path="ARCHITECTURE.md", title="Arch B",
            workspace=workspace_b,
        )
        req = _req(rf, user_b, workspace_b)
        qs = ContextDocument.tenant_objects.for_request(req)
        assert doc_b in qs
        assert doc_a not in qs


# ---------------------------------------------------------------------------
# Context: ContextSnapshot
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestContextSnapshotIsolation:
    def test_snapshot_scoped(self, rf, user_a, workspace_a, workspace_b, repo_a, repo_b):
        from context.models import ContextDocument, ContextSnapshot
        doc_a = ContextDocument.objects.create(
            repository=repo_a, doc_type="claude_md",
            file_path="CLAUDE.md", title="Doc A",
            workspace=workspace_a,
        )
        doc_b = ContextDocument.objects.create(
            repository=repo_b, doc_type="claude_md",
            file_path="CLAUDE.md", title="Doc B",
            workspace=workspace_b,
        )
        snap_a = ContextSnapshot.objects.create(
            document=doc_a, content_hash="aaa" * 21 + "a",
            workspace=workspace_a,
        )
        snap_b = ContextSnapshot.objects.create(
            document=doc_b, content_hash="bbb" * 21 + "b",
            workspace=workspace_b,
        )
        req = _req(rf, user_a, workspace_a)
        qs = ContextSnapshot.tenant_objects.for_request(req)
        assert snap_a in qs
        assert snap_b not in qs


# ---------------------------------------------------------------------------
# Cross-cutting: superuser bypass
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestSuperuserBypass:
    def test_superuser_sees_all_workspaces(self, rf, superuser, workspace_a, workspace_b):
        from teams.models import AgentTeam
        team_a = AgentTeam.objects.create(name="Super A", mission="x", workspace=workspace_a)
        team_b = AgentTeam.objects.create(name="Super B", mission="y", workspace=workspace_b)
        req = _req(rf, superuser, workspace_a)  # scoped to A, but superuser bypasses
        qs = AgentTeam.tenant_objects.for_request(req)
        assert team_a in qs
        assert team_b in qs  # superuser sees both


# ---------------------------------------------------------------------------
# Cross-cutting: no workspace → empty queryset
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestNoWorkspaceReturnsEmpty:
    def test_none_workspace_returns_empty(self, rf, user_a, workspace_a):
        from teams.models import AgentTeam
        AgentTeam.objects.create(name="Team Z", mission="z", workspace=workspace_a)
        req = _req(rf, user_a, workspace=None)
        qs = AgentTeam.tenant_objects.for_request(req)
        assert qs.count() == 0

    def test_missing_workspace_attr_returns_empty(self, rf, user_a, workspace_a):
        from teams.models import AgentTeam
        AgentTeam.objects.create(name="Team ZZ", mission="zz", workspace=workspace_a)
        req = rf.get("/")
        req.user = user_a
        # request has NO workspace attribute at all
        qs = AgentTeam.tenant_objects.for_request(req)
        assert qs.count() == 0


# ---------------------------------------------------------------------------
# Cross-cutting: for_workspace vs for_request consistency
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestForWorkspaceMatchesForRequest:
    def test_for_workspace_consistent_with_for_request(self, rf, user_a, workspace_a, workspace_b):
        from pipeline.models import PipelineEvent
        ev_a = PipelineEvent.objects.create(
            workflow_id="wf-con-a", repo="repo",
            category=PipelineEvent.Category.GIT,
            title="Consistent A", workspace=workspace_a,
        )
        PipelineEvent.objects.create(
            workflow_id="wf-con-b", repo="repo",
            category=PipelineEvent.Category.GIT,
            title="Consistent B", workspace=workspace_b,
        )
        req = _req(rf, user_a, workspace_a)
        by_request = set(PipelineEvent.tenant_objects.for_request(req).values_list("pk", flat=True))
        by_workspace = set(PipelineEvent.tenant_objects.for_workspace(workspace_a).values_list("pk", flat=True))
        assert by_request == by_workspace
        assert ev_a.pk in by_request
