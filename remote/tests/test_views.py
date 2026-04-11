import hashlib
import json
import os
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from remote.models import (
    AgentStatus,
    AgentToken,
    CommandRequest,
    ConversationThread,
    SessionOutputBuffer,
)

_TEST_FERNET_KEYS = [os.environ.get("TEST_FERNET_KEY", "")]
_CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}
_TEST_HMAC_KEY = "test-hmac-key-for-unit-tests"


def _make_token(name: str = "Test Mac", active: bool = True) -> AgentToken:
    token_hash = hashlib.sha256(f"test-token-{name}".encode()).hexdigest()
    return AgentToken.objects.create(
        name=name, token_hash=token_hash, is_active=active
    )


def _make_online_agent(name: str = "Test Mac") -> AgentStatus:
    token = _make_token(name)
    from django.utils import timezone

    return AgentStatus.objects.create(
        agent_token=token,
        is_online=True,
        connected_at=timezone.now(),
        last_heartbeat=timezone.now(),
        channel_name="test.channel.1",
        machine_name="TestMac",
    )


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    CHANNEL_LAYERS=_CHANNEL_LAYERS,
    AGENT_HMAC_KEY=_TEST_HMAC_KEY,
)
class CommandListCreateTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="kevin", password="testpass")
        self.client.force_login(self.user)

    def test_create_command(self) -> None:
        resp = self.client.post(
            "/remote/api/remote/commands/",
            data=json.dumps({
                "command_type": "start_session",
                "payload": {"repo": "nexus", "prompt": "fix tests"},
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["command_type"], "start_session")
        self.assertEqual(body["data"]["status"], "queued")
        self.assertEqual(CommandRequest.objects.count(), 1)

    def test_create_command_invalid_type(self) -> None:
        resp = self.client.post(
            "/remote/api/remote/commands/",
            data=json.dumps({"command_type": "invalid_type", "payload": {}}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])
        self.assertIn("Invalid command_type", resp.json()["message"])

    def test_create_command_invalid_json(self) -> None:
        resp = self.client.post(
            "/remote/api/remote/commands/",
            data="not json",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid JSON", resp.json()["message"])

    def test_create_command_payload_not_dict(self) -> None:
        resp = self.client.post(
            "/remote/api/remote/commands/",
            data=json.dumps({"command_type": "kill_all", "payload": "string"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("payload must be", resp.json()["message"])

    def test_create_command_sends_to_online_agent(self) -> None:
        _make_online_agent()
        with patch("remote.views._push_to_agent", return_value=True):
            resp = self.client.post(
                "/remote/api/remote/commands/",
                data=json.dumps({
                    "command_type": "list_processes",
                    "payload": {},
                }),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["data"]["status"], "sent")
        cmd = CommandRequest.objects.first()
        self.assertIsNotNone(cmd.sent_at)

    def test_create_command_stays_queued_when_no_agent(self) -> None:
        resp = self.client.post(
            "/remote/api/remote/commands/",
            data=json.dumps({
                "command_type": "list_processes",
                "payload": {},
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["data"]["status"], "queued")

    def test_create_command_has_hmac_signature(self) -> None:
        resp = self.client.post(
            "/remote/api/remote/commands/",
            data=json.dumps({
                "command_type": "start_session",
                "payload": {"repo": "nexus"},
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        cmd = CommandRequest.objects.first()
        self.assertEqual(len(cmd.hmac_signature), 64)
        self.assertNotEqual(cmd.hmac_signature, "")

    def test_list_commands(self) -> None:
        CommandRequest.objects.create(
            command_type="start_session",
            payload={},
            hmac_signature="a" * 64,
            created_by=self.user,
        )
        CommandRequest.objects.create(
            command_type="kill_all",
            payload={},
            hmac_signature="b" * 64,
            created_by=self.user,
        )
        resp = self.client.get("/remote/api/remote/commands/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["total"], 2)
        self.assertEqual(len(body["data"]["commands"]), 2)

    def test_list_commands_filter_status(self) -> None:
        CommandRequest.objects.create(
            command_type="start_session",
            payload={},
            hmac_signature="a" * 64,
            status="completed",
        )
        CommandRequest.objects.create(
            command_type="kill_all",
            payload={},
            hmac_signature="b" * 64,
            status="queued",
        )
        resp = self.client.get("/remote/api/remote/commands/?status=completed")
        self.assertEqual(resp.json()["data"]["total"], 1)

    def test_list_commands_filter_type(self) -> None:
        CommandRequest.objects.create(
            command_type="start_session",
            payload={},
            hmac_signature="a" * 64,
        )
        CommandRequest.objects.create(
            command_type="kill_all",
            payload={},
            hmac_signature="b" * 64,
        )
        resp = self.client.get("/remote/api/remote/commands/?command_type=kill_all")
        self.assertEqual(resp.json()["data"]["total"], 1)

    def test_unauthenticated_rejected(self) -> None:
        self.client.logout()
        resp = self.client.get("/remote/api/remote/commands/")
        # require_api_key returns 401 for unauthenticated requests
        self.assertEqual(resp.status_code, 401)

    def test_create_sets_created_by(self) -> None:
        resp = self.client.post(
            "/remote/api/remote/commands/",
            data=json.dumps({"command_type": "kill_all", "payload": {}}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        cmd = CommandRequest.objects.first()
        self.assertEqual(cmd.created_by, self.user)


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    CHANNEL_LAYERS=_CHANNEL_LAYERS,
    AGENT_HMAC_KEY=_TEST_HMAC_KEY,
)
class CommandDetailTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="kevin", password="testpass")
        self.client.force_login(self.user)

    def test_get_command(self) -> None:
        cmd = CommandRequest.objects.create(
            command_type="start_session",
            payload={"repo": "nexus"},
            hmac_signature="a" * 64,
        )
        resp = self.client.get(f"/remote/api/remote/commands/{cmd.pk}/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["id"], cmd.pk)
        self.assertEqual(body["data"]["payload"], {"repo": "nexus"})

    def test_get_nonexistent_command(self) -> None:
        resp = self.client.get("/remote/api/remote/commands/99999/")
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(resp.json()["success"])


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    CHANNEL_LAYERS=_CHANNEL_LAYERS,
    AGENT_HMAC_KEY=_TEST_HMAC_KEY,
)
class CommandCancelTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="kevin", password="testpass")
        self.client.force_login(self.user)

    def test_cancel_queued_command(self) -> None:
        cmd = CommandRequest.objects.create(
            command_type="start_session",
            payload={},
            hmac_signature="a" * 64,
            status="queued",
        )
        resp = self.client.delete(f"/remote/api/remote/commands/{cmd.pk}/cancel/")
        self.assertEqual(resp.status_code, 200)
        cmd.refresh_from_db()
        self.assertEqual(cmd.status, "cancelled")
        self.assertIsNotNone(cmd.completed_at)

    def test_cancel_non_queued_fails(self) -> None:
        cmd = CommandRequest.objects.create(
            command_type="start_session",
            payload={},
            hmac_signature="a" * 64,
            status="running",
        )
        resp = self.client.delete(f"/remote/api/remote/commands/{cmd.pk}/cancel/")
        self.assertEqual(resp.status_code, 409)
        self.assertFalse(resp.json()["success"])

    def test_cancel_nonexistent(self) -> None:
        resp = self.client.delete("/remote/api/remote/commands/99999/cancel/")
        self.assertEqual(resp.status_code, 404)


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    CHANNEL_LAYERS=_CHANNEL_LAYERS,
    AGENT_HMAC_KEY=_TEST_HMAC_KEY,
)
class AgentStatusViewTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="kevin", password="testpass")
        self.client.force_login(self.user)

    def test_no_agents(self) -> None:
        resp = self.client.get("/remote/api/remote/agent/status/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["agents"], [])
        self.assertFalse(body["data"]["any_online"])

    def test_online_agent(self) -> None:
        _make_online_agent()
        resp = self.client.get("/remote/api/remote/agent/status/")
        body = resp.json()
        self.assertTrue(body["data"]["any_online"])
        self.assertEqual(len(body["data"]["agents"]), 1)
        self.assertTrue(body["data"]["agents"][0]["is_online"])
        self.assertEqual(body["data"]["agents"][0]["machine_name"], "TestMac")

    def test_offline_agent(self) -> None:
        token = _make_token()
        AgentStatus.objects.create(agent_token=token, is_online=False)
        resp = self.client.get("/remote/api/remote/agent/status/")
        body = resp.json()
        self.assertFalse(body["data"]["any_online"])

    def test_unauthenticated(self) -> None:
        self.client.logout()
        resp = self.client.get("/remote/api/remote/agent/status/")
        self.assertEqual(resp.status_code, 401)


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    CHANNEL_LAYERS=_CHANNEL_LAYERS,
    AGENT_HMAC_KEY=_TEST_HMAC_KEY,
)
class StreamOutputTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="kevin", password="testpass")
        self.client.force_login(self.user)

    def test_stream_returns_sse_content_type(self) -> None:
        resp = self.client.get("/remote/api/remote/stream/sess-1/")
        self.assertEqual(resp["Content-Type"], "text/event-stream")
        self.assertEqual(resp["Cache-Control"], "no-cache")

    def test_stream_sends_existing_lines(self) -> None:
        SessionOutputBuffer.objects.create(
            session_id="sess-test",
            line_number=1,
            content="Hello",
            stream="stdout",
        )
        SessionOutputBuffer.objects.create(
            session_id="sess-test",
            line_number=2,
            content="World",
            stream="stdout",
        )

        resp = self.client.get("/remote/api/remote/stream/sess-test/")
        # Read first few chunks from the streaming response
        content = b""
        for i, chunk in enumerate(resp.streaming_content):
            content += chunk
            if i >= 2:
                break

        content_str = content.decode()
        self.assertIn("Hello", content_str)
        self.assertIn("World", content_str)
        self.assertIn("event: output", content_str)

    def test_stream_respects_last_event_id(self) -> None:
        SessionOutputBuffer.objects.create(
            session_id="sess-test",
            line_number=1,
            content="First",
            stream="stdout",
        )
        SessionOutputBuffer.objects.create(
            session_id="sess-test",
            line_number=2,
            content="Second",
            stream="stdout",
        )

        resp = self.client.get(
            "/remote/api/remote/stream/sess-test/",
            HTTP_LAST_EVENT_ID="1",
        )
        content = b""
        for i, chunk in enumerate(resp.streaming_content):
            content += chunk
            if i >= 1:
                break

        content_str = content.decode()
        self.assertNotIn("First", content_str)
        self.assertIn("Second", content_str)


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    CHANNEL_LAYERS=_CHANNEL_LAYERS,
    AGENT_HMAC_KEY=_TEST_HMAC_KEY,
)
class KillAllTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="kevin", password="testpass")
        self.client.force_login(self.user)

    def test_kill_all_cancels_pending(self) -> None:
        CommandRequest.objects.create(
            command_type="start_session",
            payload={},
            hmac_signature="a" * 64,
            status="queued",
        )
        CommandRequest.objects.create(
            command_type="start_session",
            payload={},
            hmac_signature="b" * 64,
            status="running",
        )
        CommandRequest.objects.create(
            command_type="start_session",
            payload={},
            hmac_signature="c" * 64,
            status="completed",
        )

        resp = self.client.post("/remote/api/remote/kill-all/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["cancelled_count"], 2)

        # The completed one should be untouched
        self.assertEqual(
            CommandRequest.objects.filter(status="completed").count(), 1
        )
        self.assertEqual(
            CommandRequest.objects.filter(status="cancelled").count(), 2
        )

    def test_kill_all_sends_to_agent(self) -> None:
        _make_online_agent()
        with patch("remote.views._push_to_agent", return_value=True):
            resp = self.client.post("/remote/api/remote/kill-all/")
        body = resp.json()
        self.assertTrue(body["data"]["kill_sent"])
        # Should have created a kill_all command
        self.assertTrue(
            CommandRequest.objects.filter(command_type="kill_all").exists()
        )

    def test_kill_all_no_agent(self) -> None:
        resp = self.client.post("/remote/api/remote/kill-all/")
        body = resp.json()
        self.assertFalse(body["data"]["kill_sent"])

    def test_kill_all_unauthenticated(self) -> None:
        self.client.logout()
        resp = self.client.post("/remote/api/remote/kill-all/")
        self.assertEqual(resp.status_code, 401)


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    AGENT_HMAC_KEY=_TEST_HMAC_KEY,
)
class HmacSignatureTest(TestCase):
    def test_signature_is_deterministic(self) -> None:
        from remote.views import _sign_payload

        sig1 = _sign_payload({"repo": "nexus", "prompt": "fix"})
        sig2 = _sign_payload({"repo": "nexus", "prompt": "fix"})
        self.assertEqual(sig1, sig2)

    def test_signature_changes_with_payload(self) -> None:
        from remote.views import _sign_payload

        sig1 = _sign_payload({"repo": "nexus"})
        sig2 = _sign_payload({"repo": "abl"})
        self.assertNotEqual(sig1, sig2)

    def test_signature_is_64_hex_chars(self) -> None:
        from remote.views import _sign_payload

        sig = _sign_payload({"test": True})
        self.assertEqual(len(sig), 64)
        # Verify it's valid hex
        int(sig, 16)


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    CHANNEL_LAYERS=_CHANNEL_LAYERS,
    AGENT_HMAC_KEY=_TEST_HMAC_KEY,
)
class ConversationListCreateTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="kevin", password="testpass")
        self.client.force_login(self.user)

    def test_create_conversation(self) -> None:
        resp = self.client.post(
            "/remote/api/remote/conversations/",
            data=json.dumps({"repo": "nexus", "prompt": "Fix the auth bug"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["conversation"]["repo"], "nexus")
        self.assertIn("Fix the auth bug", body["data"]["conversation"]["title"])
        self.assertEqual(ConversationThread.objects.count(), 1)
        self.assertEqual(CommandRequest.objects.count(), 1)
        cmd = CommandRequest.objects.first()
        self.assertEqual(cmd.command_type, "start_session")
        self.assertEqual(cmd.conversation_id, body["data"]["conversation"]["id"])

    def test_create_conversation_missing_fields(self) -> None:
        resp = self.client.post(
            "/remote/api/remote/conversations/",
            data=json.dumps({"repo": "nexus"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("required", resp.json()["message"])

    def test_create_conversation_sends_to_agent(self) -> None:
        _make_online_agent()
        with patch("remote.views._push_to_agent", return_value=True):
            resp = self.client.post(
                "/remote/api/remote/conversations/",
                data=json.dumps({"repo": "nexus", "prompt": "test"}),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["data"]["command"]["status"], "sent")

    def test_list_conversations(self) -> None:
        ConversationThread.objects.create(
            repo="nexus", title="Fix auth", created_by=self.user
        )
        ConversationThread.objects.create(
            repo="abl", title="Add feature", created_by=self.user
        )
        resp = self.client.get("/remote/api/remote/conversations/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(len(body["data"]["conversations"]), 2)

    def test_list_conversations_only_own(self) -> None:
        other = User.objects.create_user(username="other", password="testpass")
        ConversationThread.objects.create(
            repo="nexus", title="My conv", created_by=self.user
        )
        ConversationThread.objects.create(
            repo="nexus", title="Other conv", created_by=other
        )
        resp = self.client.get("/remote/api/remote/conversations/")
        self.assertEqual(len(resp.json()["data"]["conversations"]), 1)

    def test_unauthenticated_rejected(self) -> None:
        self.client.logout()
        resp = self.client.get("/remote/api/remote/conversations/")
        self.assertEqual(resp.status_code, 401)


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    CHANNEL_LAYERS=_CHANNEL_LAYERS,
    AGENT_HMAC_KEY=_TEST_HMAC_KEY,
)
class ConversationDetailTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="kevin", password="testpass")
        self.client.force_login(self.user)

    def test_get_conversation(self) -> None:
        conv = ConversationThread.objects.create(
            repo="nexus", title="Fix auth", created_by=self.user, session_id="sess-1"
        )
        CommandRequest.objects.create(
            command_type="start_session",
            payload={"repo": "nexus", "prompt": "Fix auth"},
            hmac_signature="a" * 64,
            conversation=conv,
            created_by=self.user,
        )
        resp = self.client.get(f"/remote/api/remote/conversations/{conv.pk}/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["conversation"]["id"], conv.pk)
        self.assertEqual(len(body["data"]["commands"]), 1)

    def test_get_conversation_with_output(self) -> None:
        conv = ConversationThread.objects.create(
            repo="nexus", title="Test", created_by=self.user, session_id="sess-2"
        )
        SessionOutputBuffer.objects.create(
            session_id="sess-2", line_number=1, content="Hello", stream="stdout"
        )
        resp = self.client.get(f"/remote/api/remote/conversations/{conv.pk}/")
        body = resp.json()
        self.assertEqual(len(body["data"]["output_lines"]), 1)
        self.assertEqual(body["data"]["output_lines"][0]["content"], "Hello")

    def test_get_nonexistent_conversation(self) -> None:
        resp = self.client.get("/remote/api/remote/conversations/99999/")
        self.assertEqual(resp.status_code, 404)

    def test_get_other_users_conversation(self) -> None:
        other = User.objects.create_user(username="other", password="testpass")
        conv = ConversationThread.objects.create(
            repo="nexus", title="Other", created_by=other
        )
        resp = self.client.get(f"/remote/api/remote/conversations/{conv.pk}/")
        self.assertEqual(resp.status_code, 404)


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    CHANNEL_LAYERS=_CHANNEL_LAYERS,
    AGENT_HMAC_KEY=_TEST_HMAC_KEY,
)
class ConversationSendTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="kevin", password="testpass")
        self.client.force_login(self.user)

    def test_send_follow_up(self) -> None:
        conv = ConversationThread.objects.create(
            repo="nexus", title="Test", created_by=self.user, session_id="sess-1"
        )
        resp = self.client.post(
            f"/remote/api/remote/conversations/{conv.pk}/send/",
            data=json.dumps({"prompt": "Add tests too"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body["success"])
        cmd = CommandRequest.objects.first()
        self.assertEqual(cmd.command_type, "send_prompt")
        self.assertEqual(cmd.conversation, conv)
        self.assertEqual(cmd.payload["session_id"], "sess-1")

    def test_send_no_session_id(self) -> None:
        conv = ConversationThread.objects.create(
            repo="nexus", title="Test", created_by=self.user, session_id=""
        )
        resp = self.client.post(
            f"/remote/api/remote/conversations/{conv.pk}/send/",
            data=json.dumps({"prompt": "test"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 409)

    def test_send_missing_prompt(self) -> None:
        conv = ConversationThread.objects.create(
            repo="nexus", title="Test", created_by=self.user, session_id="sess-1"
        )
        resp = self.client.post(
            f"/remote/api/remote/conversations/{conv.pk}/send/",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_send_to_other_users_conversation(self) -> None:
        other = User.objects.create_user(username="other", password="testpass")
        conv = ConversationThread.objects.create(
            repo="nexus", title="Other", created_by=other, session_id="sess-1"
        )
        resp = self.client.post(
            f"/remote/api/remote/conversations/{conv.pk}/send/",
            data=json.dumps({"prompt": "test"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)


_TEST_API_KEY = "test-nockcc-api-key-for-unit-tests"


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    CHANNEL_LAYERS=_CHANNEL_LAYERS,
    AGENT_HMAC_KEY=_TEST_HMAC_KEY,
    NOCKCC_API_KEY=_TEST_API_KEY,
)
class OutputPushTest(TestCase):
    def setUp(self) -> None:
        from sessions.models import AgentSession

        self.user = User.objects.create_user(
            username="kevin", password="testpass", is_staff=True
        )
        # Create a session to push output to
        self.session = AgentSession.objects.create(
            agent="claude_code", machine="mac", status="tracking"
        )
        self.push_url = f"/remote/api/remote/output/{self.session.pk}/push/"

    def _post(self, url: str, data: str):  # type: ignore[no-untyped-def]
        """POST with API key header (not browser session)."""
        return self.client.post(
            url,
            data=data,
            content_type="application/json",
            HTTP_X_API_KEY=_TEST_API_KEY,
        )

    def test_push_single_line(self) -> None:
        resp = self._post(
            self.push_url,
            json.dumps({
                "line_number": 1,
                "content": "Hello from track mode",
                "stream": "stdout",
            }),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["lines_stored"], 1)
        self.assertEqual(SessionOutputBuffer.objects.count(), 1)
        line = SessionOutputBuffer.objects.first()
        self.assertEqual(line.session_id, str(self.session.pk))
        self.assertEqual(line.content, "Hello from track mode")
        self.assertEqual(line.stream, "stdout")

    def test_push_batch_lines(self) -> None:
        resp = self._post(
            self.push_url,
            json.dumps({
                "lines": [
                    {"line_number": 1, "content": "Line 1", "stream": "stdout"},
                    {"line_number": 2, "content": "Line 2", "stream": "stderr"},
                    {"line_number": 3, "content": "Line 3", "stream": "stdout"},
                ],
            }),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["data"]["lines_stored"], 3)
        self.assertEqual(
            SessionOutputBuffer.objects.filter(session_id=str(self.session.pk)).count(), 3
        )

    def test_push_duplicate_line_ignored(self) -> None:
        sid = str(self.session.pk)
        SessionOutputBuffer.objects.create(
            session_id=sid, line_number=1, content="Existing", stream="stdout"
        )
        resp = self._post(
            self.push_url,
            json.dumps({
                "line_number": 1,
                "content": "Duplicate attempt",
                "stream": "stdout",
            }),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["lines_stored"], 0)
        # Content should remain the original
        line = SessionOutputBuffer.objects.get(session_id=sid, line_number=1)
        self.assertEqual(line.content, "Existing")

    def test_push_missing_fields(self) -> None:
        resp = self._post(
            self.push_url,
            json.dumps({"content": "no line number"}),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("required", resp.json()["message"])

    def test_push_invalid_json(self) -> None:
        resp = self._post(self.push_url, "not json")
        self.assertEqual(resp.status_code, 400)

    def test_push_unauthenticated(self) -> None:
        """No API key and no session = 401."""
        resp = self.client.post(
            self.push_url,
            data=json.dumps({"line_number": 1, "content": "test", "stream": "stdout"}),
            content_type="application/json",
        )
        # Browser-session-only auth is rejected with 403 (API key required)
        self.assertIn(resp.status_code, [401, 403])

    def test_push_browser_session_only_rejected(self) -> None:
        """Browser session auth without API key header is rejected."""
        self.client.force_login(self.user)
        resp = self.client.post(
            self.push_url,
            data=json.dumps({"line_number": 1, "content": "test", "stream": "stdout"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("API key required", resp.json()["message"])

    def test_push_default_stream(self) -> None:
        """stream defaults to stdout when not provided."""
        resp = self._post(
            self.push_url,
            json.dumps({"line_number": 1, "content": "test"}),
        )
        self.assertEqual(resp.status_code, 200)
        line = SessionOutputBuffer.objects.first()
        self.assertEqual(line.stream, "stdout")

    def test_push_lines_not_list(self) -> None:
        resp = self._post(
            self.push_url,
            json.dumps({"lines": "not a list"}),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("list", resp.json()["message"])

    def test_push_nonexistent_session(self) -> None:
        """Pushing to a session that doesn't exist returns 404."""
        resp = self._post(
            "/remote/api/remote/output/99999/push/",
            json.dumps({"line_number": 1, "content": "test", "stream": "stdout"}),
        )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["message"])

    def test_push_invalid_session_id(self) -> None:
        """Non-numeric session ID returns 400."""
        resp = self._post(
            "/remote/api/remote/output/not-a-number/push/",
            json.dumps({"line_number": 1, "content": "test", "stream": "stdout"}),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid session ID", resp.json()["message"])

    def test_push_invalid_stream_defaults_to_stdout(self) -> None:
        """Invalid stream values are normalized to stdout."""
        resp = self._post(
            self.push_url,
            json.dumps({"line_number": 1, "content": "test", "stream": "invalid"}),
        )
        self.assertEqual(resp.status_code, 200)
        line = SessionOutputBuffer.objects.first()
        self.assertEqual(line.stream, "stdout")

    def test_push_works_with_sse_stream(self) -> None:
        """Pushed lines should be readable via the output endpoint."""
        sid = str(self.session.pk)
        self._post(
            self.push_url,
            json.dumps({"line_number": 1, "content": "Track line", "stream": "stdout"}),
        )
        # Read via output endpoint (uses browser session auth, which is fine for GET)
        self.client.force_login(self.user)
        resp = self.client.get(f"/remote/api/remote/output/{sid}/")
        body = resp.json()
        self.assertEqual(len(body["data"]["lines"]), 1)
        self.assertEqual(body["data"]["lines"][0]["content"], "Track line")
