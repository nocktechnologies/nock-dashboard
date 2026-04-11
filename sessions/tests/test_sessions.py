import json
import os
from decimal import Decimal

from django.test import TestCase, override_settings

from sessions.models import AgentSession, SessionLog

_TEST_FERNET_KEYS = [os.environ.get("TEST_FERNET_KEY", "")]
_TEST_API_KEY = "test-nockcc-api-key-12345"

API_BASE = "/api/sessions/"


def _auth_headers() -> dict[str, str]:
    return {"HTTP_X_API_KEY": _TEST_API_KEY}


def _make_session(**kwargs: object) -> AgentSession:
    defaults: dict[str, object] = {
        "agent": "claude_code",
        "machine": "mac",
        "branch": "feature/test",
        "task_description": "Testing session",
    }
    defaults.update(kwargs)
    return AgentSession.objects.create(**defaults)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY=_TEST_API_KEY)
class SessionAPICreateTests(TestCase):
    def test_create_session_returns_201(self) -> None:
        resp = self.client.post(
            API_BASE,
            data=json.dumps({"agent": "claude_code", "machine": "mac", "branch": "feature/x"}),
            content_type="application/json",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["agent"], "claude_code")
        self.assertEqual(body["data"]["status"], "active")
        self.assertEqual(AgentSession.objects.count(), 1)

    def test_create_session_invalid_agent_returns_400(self) -> None:
        resp = self.client.post(
            API_BASE,
            data=json.dumps({"agent": "invalid_agent"}),
            content_type="application/json",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertFalse(body["success"])
        self.assertIn("invalid_agent", body["message"])


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY=_TEST_API_KEY)
class SessionAPIUpdateTests(TestCase):
    def test_patch_update_session_returns_200(self) -> None:
        session = _make_session()
        resp = self.client.patch(
            f"{API_BASE}{session.pk}/",
            data=json.dumps({
                "status": "idle",
                "tokens_input": 5000,
                "estimated_cost": "0.1500",
            }),
            content_type="application/json",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["status"], "idle")
        self.assertEqual(body["data"]["tokens_input"], 5000)
        self.assertEqual(body["data"]["estimated_cost"], "0.1500")

    def test_patch_not_found_returns_404(self) -> None:
        resp = self.client.patch(
            f"{API_BASE}99999/",
            data=json.dumps({"status": "idle"}),
            content_type="application/json",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 404)

    def test_patch_invalid_status_returns_400(self) -> None:
        session = _make_session()
        resp = self.client.patch(
            f"{API_BASE}{session.pk}/",
            data=json.dumps({"status": "nonexistent"}),
            content_type="application/json",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid status", resp.json()["message"])

    def test_patch_invalid_tokens_returns_400(self) -> None:
        session = _make_session()
        resp = self.client.patch(
            f"{API_BASE}{session.pk}/",
            data=json.dumps({"tokens_input": "not_a_number"}),
            content_type="application/json",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("must be an integer", resp.json()["message"])

    def test_patch_invalid_cost_returns_400(self) -> None:
        session = _make_session()
        resp = self.client.patch(
            f"{API_BASE}{session.pk}/",
            data=json.dumps({"estimated_cost": "not_decimal"}),
            content_type="application/json",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("estimated_cost", resp.json()["message"])


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY=_TEST_API_KEY)
class SessionAPIEndTests(TestCase):
    def test_end_session_sets_ended_at_and_status(self) -> None:
        session = _make_session()
        resp = self.client.post(
            f"{API_BASE}{session.pk}/end/",
            data=json.dumps({"status": "completed", "notes": "All done"}),
            content_type="application/json",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["status"], "completed")
        self.assertIsNotNone(body["data"]["ended_at"])
        self.assertEqual(body["data"]["notes"], "All done")

        session.refresh_from_db()
        self.assertIsNotNone(session.ended_at)
        self.assertEqual(session.status, "completed")


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY=_TEST_API_KEY)
class SessionAPILogTests(TestCase):
    def test_add_log_returns_201(self) -> None:
        session = _make_session()
        resp = self.client.post(
            f"{API_BASE}{session.pk}/log/",
            data=json.dumps({"level": "info", "message": "Started PR review"}),
            content_type="application/json",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["level"], "info")
        self.assertEqual(SessionLog.objects.count(), 1)

    def test_add_log_invalid_level_returns_400(self) -> None:
        session = _make_session()
        resp = self.client.post(
            f"{API_BASE}{session.pk}/log/",
            data=json.dumps({"level": "critical", "message": "Bad level"}),
            content_type="application/json",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 400)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY=_TEST_API_KEY)
class SessionAPIListTests(TestCase):
    def test_list_sessions_paginated(self) -> None:
        for i in range(5):
            _make_session(branch=f"feature/test-{i}")
        resp = self.client.get(
            f"{API_BASE}?limit=2&offset=0",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["total"], 5)
        self.assertEqual(len(body["data"]["sessions"]), 2)

    def test_list_with_status_filter(self) -> None:
        _make_session(status="active")
        _make_session(status="completed")
        _make_session(status="failed")
        resp = self.client.get(
            f"{API_BASE}?status=active",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        sessions = body["data"]["sessions"]
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["status"], "active")

    def test_active_sessions_endpoint(self) -> None:
        _make_session(status="active", branch="feature/a")
        _make_session(status="active", branch="feature/b")
        _make_session(status="completed", branch="feature/c")
        resp = self.client.get(
            f"{API_BASE}active/",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(len(body["data"]), 2)
        for s in body["data"]:
            self.assertEqual(s["status"], "active")


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY=_TEST_API_KEY)
class SessionAPIDetailTests(TestCase):
    def test_detail_includes_logs(self) -> None:
        session = _make_session()
        SessionLog.objects.create(session=session, level="info", message="Log one")
        SessionLog.objects.create(session=session, level="error", message="Log two")

        resp = self.client.get(
            f"{API_BASE}{session.pk}/",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertIn("logs", body["data"])
        self.assertEqual(len(body["data"]["logs"]), 2)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY=_TEST_API_KEY)
class SessionAPIAuthTests(TestCase):
    def test_missing_api_key_returns_401(self) -> None:
        resp = self.client.get(API_BASE)
        self.assertEqual(resp.status_code, 401)
        body = resp.json()
        self.assertFalse(body["success"])
        self.assertIn("Authentication required", body["message"])

    def test_wrong_api_key_returns_401(self) -> None:
        resp = self.client.get(
            API_BASE,
            HTTP_X_API_KEY="wrong-key",
        )
        self.assertEqual(resp.status_code, 401)
        body = resp.json()
        self.assertFalse(body["success"])
        self.assertIn("Invalid API key", body["message"])


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY="")
class SessionAPIEmptyKeyTests(TestCase):
    def test_unconfigured_api_key_returns_500(self) -> None:
        resp = self.client.get(API_BASE, **_auth_headers())
        self.assertEqual(resp.status_code, 500)
        body = resp.json()
        self.assertFalse(body["success"])
        self.assertIn("not configured", body["message"])


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class SessionModelTests(TestCase):
    def test_session_creation_with_defaults(self) -> None:
        session = AgentSession.objects.create(agent="claude_code")
        self.assertEqual(session.status, "active")
        self.assertEqual(session.machine, "mac")
        self.assertEqual(session.tokens_input, 0)
        self.assertEqual(session.estimated_cost, Decimal("0"))
        self.assertIsNotNone(session.started_at)

    def test_session_str_format(self) -> None:
        session = AgentSession.objects.create(
            agent="claude_code",
            machine="mac",
            branch="feature/test",
            status="active",
        )
        expected = "Claude Code on Mac Secondary — feature/test (active)"
        self.assertEqual(str(session), expected)

    def test_session_log_cascade_delete(self) -> None:
        session = _make_session()
        SessionLog.objects.create(session=session, level="info", message="Test log")
        SessionLog.objects.create(session=session, level="error", message="Error log")
        self.assertEqual(SessionLog.objects.count(), 2)

        session.delete()
        self.assertEqual(SessionLog.objects.count(), 0)

    def test_session_ordering(self) -> None:
        s1 = _make_session(branch="first")
        s2 = _make_session(branch="second")
        sessions = list(AgentSession.objects.all())
        # Most recent first (s2 was created after s1)
        self.assertEqual(sessions[0].pk, s2.pk)
        self.assertEqual(sessions[1].pk, s1.pk)

    def test_session_log_str_format(self) -> None:
        session = _make_session()
        log = SessionLog.objects.create(
            session=session,
            level="info",
            message="A" * 100,
        )
        result = str(log)
        self.assertEqual(result, f"info: {'A' * 50}")


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class SeedSessionsCommandTests(TestCase):
    def test_seed_sessions_creates_data(self) -> None:
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("seed_sessions", stdout=out)
        self.assertEqual(AgentSession.objects.count(), 5)
        self.assertGreater(SessionLog.objects.count(), 0)
        self.assertIn("Seeded", out.getvalue())
