"""
Tests for Prompt Queue — autonomous agent pipeline.

Covers: model CRUD, is_executable, queue ordering, execute/complete flow,
review cycles, webhook integration, dependency resolution, API endpoints,
template resolution, Agent Teams integration.
"""

import json

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from teams.models import AgentTeam, PromptExecution, PromptFile, TeamTask

_TEST_FERNET_KEYS = ["rBj4e7L0PbE7E3H5JhLdOwvSXa3Z3g1mJbkBrkIg5cI="]
_TEST_API_KEY = "test-api-key-for-prompts"


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


def _make_prompt(**kwargs) -> PromptFile:
    defaults = {
        "title": "Test Prompt",
        "slug": "test-prompt",
        "content": "Build the thing",
        "target_repo": "kkwills13/test-repo",
        "status": "draft",
    }
    defaults.update(kwargs)
    return PromptFile.objects.create(**defaults)


# ── Model tests ──


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class PromptFileModelTests(TestCase):
    def test_create_prompt(self):
        p = _make_prompt()
        self.assertEqual(p.status, "draft")
        self.assertEqual(str(p), "Test Prompt (draft)")

    def test_auto_slug_from_title(self):
        p = PromptFile.objects.create(
            title="My Amazing Feature",
            content="Build it",
            target_repo="kkwills13/repo",
        )
        self.assertEqual(p.slug, "my-amazing-feature")

    def test_expected_branch(self):
        p = _make_prompt(target_branch_prefix="feature/")
        self.assertEqual(p.expected_branch, "feature/test-prompt")

    def test_is_executable_when_ready_no_deps(self):
        p = _make_prompt(status="ready")
        self.assertTrue(p.is_executable)

    def test_is_not_executable_when_draft(self):
        p = _make_prompt(status="draft")
        self.assertFalse(p.is_executable)

    def test_is_not_executable_with_incomplete_dep(self):
        dep = _make_prompt(slug="dep-prompt", status="in_progress")
        p = _make_prompt(slug="main-prompt", status="ready")
        p.depends_on_prompts.add(dep)
        self.assertFalse(p.is_executable)

    def test_is_executable_with_completed_dep(self):
        dep = _make_prompt(slug="dep-prompt", status="completed")
        p = _make_prompt(slug="main-prompt", status="ready")
        p.depends_on_prompts.add(dep)
        self.assertTrue(p.is_executable)

    def test_ordering_by_priority_then_created(self):
        _make_prompt(slug="low-pri", priority=10)
        _make_prompt(slug="high-pri", priority=90)
        prompts = list(PromptFile.objects.all())
        self.assertEqual(prompts[0].slug, "high-pri")
        self.assertEqual(prompts[1].slug, "low-pri")


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class PromptExecutionModelTests(TestCase):
    def test_create_execution(self):
        p = _make_prompt()
        ex = PromptExecution.objects.create(prompt=p, agent_name="Kit #1")
        self.assertIsNone(ex.result)
        self.assertEqual(ex.review_cycles, 0)
        self.assertIn("Kit #1", str(ex))


# ── API tests ──


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    NOCKCC_API_KEY=_TEST_API_KEY,
    TELEGRAM_ENABLED=False,
)
class PromptCRUDAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass", is_staff=True)

    def test_create_prompt(self):
        resp = _post_json(
            self.client, "/api/prompts/",
            {"title": "New Feature", "content": "Build it", "target_repo": "kkwills13/repo"},
            **_api_headers(),
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["title"], "New Feature")
        self.assertEqual(data["data"]["status"], "draft")
        self.assertEqual(data["data"]["slug"], "new-feature")

    def test_create_prompt_missing_fields(self):
        resp = _post_json(
            self.client, "/api/prompts/",
            {"title": "Incomplete"},
            **_api_headers(),
        )
        self.assertEqual(resp.status_code, 400)

    def test_list_prompts(self):
        _make_prompt(slug="p1")
        _make_prompt(slug="p2", status="ready")
        resp = self.client.get("/api/prompts/", **_api_headers())
        data = resp.json()
        self.assertEqual(len(data["data"]["prompts"]), 2)

    def test_list_prompts_filter_status(self):
        _make_prompt(slug="draft-one")
        _make_prompt(slug="ready-one", status="ready")
        resp = self.client.get("/api/prompts/?status=ready", **_api_headers())
        data = resp.json()
        self.assertEqual(len(data["data"]["prompts"]), 1)
        self.assertEqual(data["data"]["prompts"][0]["status"], "ready")

    def test_prompt_detail(self):
        _make_prompt()
        resp = self.client.get("/api/prompts/test-prompt/", **_api_headers())
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["slug"], "test-prompt")
        self.assertIn("content", data["data"])

    def test_update_prompt(self):
        _make_prompt()
        resp = _put_json(
            self.client, "/api/prompts/test-prompt/",
            {"priority": 99, "status": "ready"},
            **_api_headers(),
        )
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["priority"], 99)
        self.assertEqual(data["data"]["status"], "ready")

    def test_archive_prompt(self):
        _make_prompt()
        resp = self.client.delete("/api/prompts/test-prompt/", **_api_headers())
        data = resp.json()
        self.assertTrue(data["success"])
        p = PromptFile.objects.get(slug="test-prompt")
        self.assertEqual(p.status, "archived")

    def test_prompt_not_found(self):
        resp = self.client.get("/api/prompts/nonexistent/", **_api_headers())
        self.assertEqual(resp.status_code, 404)


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    NOCKCC_API_KEY=_TEST_API_KEY,
    TELEGRAM_ENABLED=False,
)
class QueueManagementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass", is_staff=True)

    def test_queue_returns_only_executable(self):
        _make_prompt(slug="draft-one", status="draft")
        _make_prompt(slug="ready-one", status="ready", priority=80)
        _make_prompt(slug="ready-two", status="ready", priority=60)
        resp = self.client.get("/api/prompts/queue/", **_api_headers())
        data = resp.json()
        self.assertEqual(len(data["data"]["prompts"]), 2)
        self.assertEqual(data["data"]["prompts"][0]["slug"], "ready-one")

    def test_queue_excludes_blocked_by_deps(self):
        dep = _make_prompt(slug="blocker", status="in_progress")
        p = _make_prompt(slug="blocked", status="ready")
        p.depends_on_prompts.add(dep)
        resp = self.client.get("/api/prompts/queue/", **_api_headers())
        data = resp.json()
        self.assertEqual(len(data["data"]["prompts"]), 0)

    def test_execute_prompt(self):
        _make_prompt(status="ready")
        resp = _post_json(
            self.client, "/api/prompts/test-prompt/execute/",
            {"agent_name": "Kit #1"},
            **_api_headers(),
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("resolved_content", data["data"])
        self.assertEqual(data["data"]["status"], "in_progress")
        self.assertEqual(PromptExecution.objects.count(), 1)

    def test_execute_non_ready_prompt_rejected(self):
        _make_prompt(status="draft")
        resp = _post_json(
            self.client, "/api/prompts/test-prompt/execute/",
            {"agent_name": "Kit #1"},
            **_api_headers(),
        )
        self.assertEqual(resp.status_code, 409)

    def test_execute_missing_agent_name(self):
        _make_prompt(status="ready")
        resp = _post_json(
            self.client, "/api/prompts/test-prompt/execute/",
            {},
            **_api_headers(),
        )
        self.assertEqual(resp.status_code, 400)

    def test_complete_prompt(self):
        p = _make_prompt(status="in_progress")
        PromptExecution.objects.create(prompt=p, agent_name="Kit #1")
        resp = _post_json(
            self.client, "/api/prompts/test-prompt/complete/",
            {"pr_number": 42, "pr_url": "https://github.com/kkwills13/repo/pull/42"},
            **_api_headers(),
        )
        data = resp.json()
        self.assertTrue(data["success"])
        p.refresh_from_db()
        self.assertEqual(p.status, "completed")
        self.assertEqual(p.pr_number, 42)
        ex = PromptExecution.objects.first()
        self.assertEqual(ex.result, "success")

    def test_complete_draft_rejected(self):
        _make_prompt(status="draft")
        resp = _post_json(
            self.client, "/api/prompts/test-prompt/complete/",
            {},
            **_api_headers(),
        )
        self.assertEqual(resp.status_code, 409)

    def test_review_cycle_tracking(self):
        p = _make_prompt(status="in_progress")
        PromptExecution.objects.create(prompt=p, agent_name="Kit #1", max_review_cycles=3)
        resp = _post_json(
            self.client, "/api/prompts/test-prompt/review/",
            {"notes": "Fix linting issues"},
            **_api_headers(),
        )
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["review_cycles"], 1)

    def test_review_cycle_max_exceeded(self):
        p = _make_prompt(status="in_progress")
        PromptExecution.objects.create(
            prompt=p, agent_name="Kit #1", review_cycles=2, max_review_cycles=3
        )
        resp = _post_json(
            self.client, "/api/prompts/test-prompt/review/",
            {"notes": "Too many issues"},
            **_api_headers(),
        )
        data = resp.json()
        self.assertEqual(data["data"]["review_cycles"], 3)
        ex = PromptExecution.objects.first()
        self.assertEqual(ex.result, "review_requested")

    def test_ready_for_kevin(self):
        _make_prompt(slug="done", status="completed", pr_number=10)
        _make_prompt(slug="not-done", status="in_progress")
        resp = self.client.get("/api/prompts/queued/", **_api_headers())
        data = resp.json()
        self.assertEqual(data["data"]["count"], 1)
        self.assertEqual(data["data"]["prompts"][0]["slug"], "done")

    def test_stats_endpoint(self):
        _make_prompt(slug="d", status="draft")
        _make_prompt(slug="r", status="ready")
        _make_prompt(slug="ip", status="in_progress")
        resp = self.client.get("/api/prompts/stats/", **_api_headers())
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["draft"], 1)
        self.assertEqual(data["data"]["ready"], 1)
        self.assertEqual(data["data"]["in_progress"], 1)


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    NOCKCC_API_KEY=_TEST_API_KEY,
    TELEGRAM_ENABLED=False,
)
class TemplateResolutionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass", is_staff=True)

    def test_execute_returns_resolved_template(self):
        _make_prompt(
            title="Smart Watch",
            slug="smart-watch",
            content="Build the smart watch feature",
            target_repo="kkwills13/nock-command-center",
            target_branch_prefix="feature/",
            status="ready",
        )
        resp = _post_json(
            self.client, "/api/prompts/smart-watch/execute/",
            {"agent_name": "Kit #1"},
            **_api_headers(),
        )
        data = resp.json()
        resolved = data["data"]["resolved_content"]
        self.assertIn("# PROMPT: Smart Watch", resolved)
        self.assertIn("**Repo:** kkwills13/nock-command-center", resolved)
        self.assertIn("**Branch:** feature/smart-watch (from main)", resolved)
        self.assertIn("Build the smart watch feature", resolved)
        self.assertIn("Run code-simplifier", resolved)


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    NOCKCC_API_KEY=_TEST_API_KEY,
    TELEGRAM_ENABLED=False,
)
class DependencyResolutionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass", is_staff=True)

    def test_completing_prompt_unblocks_dependent(self):
        a = _make_prompt(slug="prompt-a", status="in_progress")
        PromptExecution.objects.create(prompt=a, agent_name="Kit #1")
        b = _make_prompt(slug="prompt-b", status="ready")
        b.depends_on_prompts.add(a)
        self.assertFalse(b.is_executable)

        _post_json(
            self.client, "/api/prompts/prompt-a/complete/",
            {},
            **_api_headers(),
        )
        b.refresh_from_db()
        self.assertTrue(b.is_executable)

    def test_create_prompt_with_dependencies(self):
        _make_prompt(slug="dep-one")
        resp = _post_json(
            self.client, "/api/prompts/",
            {
                "title": "Blocked Prompt",
                "content": "After dep completes",
                "target_repo": "kkwills13/repo",
                "depends_on_prompts": ["dep-one"],
            },
            **_api_headers(),
        )
        self.assertEqual(resp.status_code, 201)
        p = PromptFile.objects.get(slug="blocked-prompt")
        self.assertEqual(set(p.depends_on_prompts.values_list("slug", flat=True)), {"dep-one"})


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    NOCKCC_API_KEY=_TEST_API_KEY,
    TELEGRAM_ENABLED=False,
)
class AgentTeamsIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass", is_staff=True)

    def test_execute_syncs_team_task_status(self):
        team = AgentTeam.objects.create(name="Sprint", mission="Ship it", status="active")
        task = TeamTask.objects.create(team=team, title="Build thing", status="pending")
        p = _make_prompt(status="ready")
        p.team_task = task
        p.save(update_fields=["team_task_id"])

        _post_json(
            self.client, "/api/prompts/test-prompt/execute/",
            {"agent_name": "Kit #1"},
            **_api_headers(),
        )
        task.refresh_from_db()
        self.assertEqual(task.status, "in_progress")

    def test_complete_syncs_team_task_status(self):
        team = AgentTeam.objects.create(name="Sprint", mission="Ship it", status="active")
        task = TeamTask.objects.create(team=team, title="Build thing", status="in_progress")
        p = _make_prompt(status="in_progress")
        p.team_task = task
        p.save(update_fields=["team_task_id"])
        PromptExecution.objects.create(prompt=p, agent_name="Kit #1")

        _post_json(
            self.client, "/api/prompts/test-prompt/complete/",
            {"pr_number": 55, "pr_url": "https://github.com/kkwills13/repo/pull/55"},
            **_api_headers(),
        )
        task.refresh_from_db()
        self.assertEqual(task.status, "completed")
        self.assertEqual(task.pr_number, 55)


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    NOCKCC_API_KEY=_TEST_API_KEY,
    TELEGRAM_ENABLED=False,
)
class WebhookIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass", is_staff=True)

    def test_pr_opened_links_to_prompt(self):
        p = _make_prompt(
            status="in_progress",
            target_repo="kkwills13/repo",
            target_branch_prefix="feature/",
        )
        from teams.signals import _link_pr_to_prompt
        _link_pr_to_prompt("kkwills13/repo", "feature/test-prompt", 42, "https://github.com/kkwills13/repo/pull/42")

        p.refresh_from_db()
        self.assertEqual(p.pr_number, 42)
        self.assertEqual(p.pr_url, "https://github.com/kkwills13/repo/pull/42")

    def test_pr_opened_no_match(self):
        p = _make_prompt(status="in_progress", target_repo="kkwills13/repo")
        from teams.signals import _link_pr_to_prompt
        _link_pr_to_prompt("kkwills13/repo", "fix/something-else", 99, "https://github.com/kkwills13/repo/pull/99")

        p.refresh_from_db()
        self.assertIsNone(p.pr_number)

    def test_review_changes_requested_increments_cycles(self):
        p = _make_prompt(status="in_progress", target_repo="kkwills13/repo", pr_number=42)
        ex = PromptExecution.objects.create(prompt=p, agent_name="Kit #1")

        from teams.signals import on_prompt_pr_review
        on_prompt_pr_review("kkwills13/repo", 42, "changes_requested")

        ex.refresh_from_db()
        self.assertEqual(ex.review_cycles, 1)

    def test_pr_merged_completes_prompt(self):
        p = _make_prompt(status="in_progress", target_repo="kkwills13/repo", pr_number=42)
        ex = PromptExecution.objects.create(prompt=p, agent_name="Kit #1")

        from teams.signals import on_prompt_pr_merged
        on_prompt_pr_merged("kkwills13/repo", 42)

        p.refresh_from_db()
        self.assertEqual(p.status, "completed")
        ex.refresh_from_db()
        self.assertEqual(ex.result, "success")

    def test_pr_merged_unblocks_dependent_prompts(self):
        a = _make_prompt(slug="prompt-a", status="in_progress", target_repo="kkwills13/repo", pr_number=42)
        PromptExecution.objects.create(prompt=a, agent_name="Kit #1")
        b = _make_prompt(slug="prompt-b", status="ready")
        b.depends_on_prompts.add(a)
        self.assertFalse(b.is_executable)

        from teams.signals import on_prompt_pr_merged
        on_prompt_pr_merged("kkwills13/repo", 42)

        b.refresh_from_db()
        a.refresh_from_db()
        self.assertEqual(a.status, "completed")
        self.assertTrue(b.is_executable)


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    NOCKCC_API_KEY=_TEST_API_KEY,
    TELEGRAM_ENABLED=False,
)
class SecurityTests(TestCase):
    def test_api_requires_auth(self):
        resp = self.client.get("/api/prompts/")
        self.assertEqual(resp.status_code, 401)

    def test_oversized_body_rejected(self):
        User.objects.create_user(username="testuser", password="pass", is_staff=True)
        big_body = json.dumps({"content": "x" * 40_000})
        resp = self.client.post(
            "/api/prompts/",
            data=big_body,
            content_type="application/json",
            **_api_headers(),
        )
        self.assertEqual(resp.status_code, 400)

    def test_search_filter(self):
        User.objects.create_user(username="testuser", password="pass", is_staff=True)
        _make_prompt(slug="brain-feature", title="Brain Feature")
        _make_prompt(slug="other-thing", title="Other Thing")
        resp = self.client.get("/api/prompts/?search=Brain", **_api_headers())
        data = resp.json()
        self.assertEqual(len(data["data"]["prompts"]), 1)
        self.assertEqual(data["data"]["prompts"][0]["slug"], "brain-feature")


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    NOCKCC_API_KEY=_TEST_API_KEY,
    TELEGRAM_ENABLED=False,
)
class PromptPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass")
        self.client.force_login(self.user)

    def test_prompts_page_loads(self):
        resp = self.client.get("/prompts/")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "teams/prompts.html")
