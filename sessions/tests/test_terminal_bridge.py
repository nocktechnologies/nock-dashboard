"""Tests for Terminal Bridge — heartbeat and status endpoints."""
import json
import os
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from sessions.models import TerminalHeartbeat

_TEST_FERNET_KEYS = [os.environ.get("TEST_FERNET_KEY", "")]
_TEST_API_KEY = "test-nockcc-api-key-12345"

HEARTBEAT_URL = "/api/terminal/heartbeat/"
STATUS_URL = "/api/terminal/status/"


def _auth_headers() -> dict[str, str]:
    return {"HTTP_X_API_KEY": _TEST_API_KEY}


def _valid_heartbeat(**overrides: object) -> dict:
    data: dict = {
        "machine": "mac",
        "sessions": [
            {
                "project": "nock-command-center",
                "status": "working",
                "branch": "feature/test",
                "context_pct": 34,
            }
        ],
        "active_ports": [3000, 8000],
        "terminal_version": "1.0.0",
    }
    data.update(overrides)
    return data


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY=_TEST_API_KEY)
class HeartbeatCreateTests(TestCase):
    def test_heartbeat_creates_record(self) -> None:
        resp = self.client.post(
            HEARTBEAT_URL,
            data=json.dumps(_valid_heartbeat()),
            content_type="application/json",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["session_count"], 1)
        self.assertEqual(TerminalHeartbeat.objects.count(), 1)

    def test_heartbeat_upserts(self) -> None:
        """POST twice with same machine — only one record should exist."""
        for sessions in [
            [{"project": "a", "status": "working"}],
            [{"project": "b", "status": "idle"}, {"project": "c", "status": "working"}],
        ]:
            self.client.post(
                HEARTBEAT_URL,
                data=json.dumps(_valid_heartbeat(sessions=sessions)),
                content_type="application/json",
                **_auth_headers(),
            )
        self.assertEqual(TerminalHeartbeat.objects.count(), 1)
        hb = TerminalHeartbeat.objects.first()
        self.assertEqual(hb.session_count, 2)

    def test_heartbeat_requires_api_key(self) -> None:
        resp = self.client.post(
            HEARTBEAT_URL,
            data=json.dumps(_valid_heartbeat()),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_heartbeat_validates_sessions_array(self) -> None:
        resp = self.client.post(
            HEARTBEAT_URL,
            data=json.dumps(_valid_heartbeat(sessions="not a list")),
            content_type="application/json",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("array", resp.json()["message"])

    def test_heartbeat_validates_session_fields(self) -> None:
        resp = self.client.post(
            HEARTBEAT_URL,
            data=json.dumps(_valid_heartbeat(sessions=[{"branch": "x"}])),
            content_type="application/json",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("missing fields", resp.json()["message"])


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY=_TEST_API_KEY)
class TerminalStatusTests(TestCase):
    def test_terminal_status_returns_heartbeat(self) -> None:
        self.client.post(
            HEARTBEAT_URL,
            data=json.dumps(_valid_heartbeat()),
            content_type="application/json",
            **_auth_headers(),
        )
        resp = self.client.get(STATUS_URL, **_auth_headers())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["machine"], "mac")
        self.assertEqual(body["data"][0]["session_count"], 1)

    def test_terminal_status_empty(self) -> None:
        resp = self.client.get(STATUS_URL, **_auth_headers())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"], [])

    def test_terminal_status_stale_detection(self) -> None:
        hb = TerminalHeartbeat.objects.create(
            machine="mac",
            sessions=[],
            active_ports=[],
        )
        # Force received_at to 5 minutes ago
        TerminalHeartbeat.objects.filter(pk=hb.pk).update(
            received_at=timezone.now() - timedelta(minutes=5)
        )

        resp = self.client.get(STATUS_URL, **_auth_headers())
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["data"][0]["is_stale"])
