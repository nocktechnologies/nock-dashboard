import hashlib
import os

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase, override_settings

from remote.models import (
    AgentStatus,
    AgentToken,
    CommandRequest,
    SessionOutputBuffer,
)

_TEST_FERNET_KEYS = [os.environ.get("TEST_FERNET_KEY", "")]


def _make_token(name: str = "Test MacBook", active: bool = True) -> AgentToken:
    token_hash = hashlib.sha256(f"test-token-{name}".encode()).hexdigest()
    return AgentToken.objects.create(
        name=name, token_hash=token_hash, is_active=active
    )


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class AgentTokenModelTest(TestCase):
    def test_create_token(self) -> None:
        token = _make_token()
        self.assertEqual(token.name, "Test MacBook")
        self.assertTrue(token.is_active)
        self.assertIsNotNone(token.created_at)
        self.assertIsNone(token.last_used_at)

    def test_str_active(self) -> None:
        token = _make_token()
        self.assertEqual(str(token), "Test MacBook (active)")

    def test_str_inactive(self) -> None:
        token = _make_token(name="Old Mac", active=False)
        self.assertEqual(str(token), "Old Mac (inactive)")

    def test_token_hash_unique(self) -> None:
        _make_token(name="First")
        with self.assertRaises(IntegrityError):
            # Same name produces same hash in our factory
            _make_token(name="First")

    def test_ordering_newest_first(self) -> None:
        t1 = _make_token(name="First")
        t2 = _make_token(name="Second")
        tokens = list(AgentToken.objects.all())
        self.assertEqual(tokens[0], t2)
        self.assertEqual(tokens[1], t1)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class AgentStatusModelTest(TestCase):
    def test_defaults(self) -> None:
        token = _make_token()
        status = AgentStatus.objects.create(agent_token=token)
        self.assertFalse(status.is_online)
        self.assertIsNone(status.last_heartbeat)
        self.assertEqual(status.machine_name, "")
        self.assertEqual(status.active_sessions, 0)

    def test_str(self) -> None:
        token = _make_token()
        status = AgentStatus.objects.create(agent_token=token, is_online=True)
        self.assertEqual(str(status), "Test MacBook (online)")

    def test_cascade_delete(self) -> None:
        token = _make_token()
        AgentStatus.objects.create(agent_token=token)
        self.assertEqual(AgentStatus.objects.count(), 1)
        token.delete()
        self.assertEqual(AgentStatus.objects.count(), 0)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class CommandRequestModelTest(TestCase):
    def test_create_with_defaults(self) -> None:
        cmd = CommandRequest.objects.create(
            command_type=CommandRequest.CommandType.START_SESSION,
            payload={"repo": "nexus", "prompt": "fix tests"},
            hmac_signature="a" * 64,
        )
        self.assertEqual(cmd.status, CommandRequest.Status.QUEUED)
        self.assertEqual(cmd.result, "")
        self.assertIsNotNone(cmd.created_at)
        self.assertIsNone(cmd.sent_at)

    def test_str(self) -> None:
        cmd = CommandRequest.objects.create(
            command_type=CommandRequest.CommandType.KILL_ALL,
            hmac_signature="a" * 64,
        )
        self.assertEqual(str(cmd), "Kill All Sessions (Queued)")

    def test_all_command_types_valid(self) -> None:
        for ct in CommandRequest.CommandType:
            cmd = CommandRequest.objects.create(
                command_type=ct,
                hmac_signature=hashlib.sha256(ct.value.encode()).hexdigest(),
            )
            self.assertEqual(cmd.command_type, ct)

    def test_ordering_newest_first(self) -> None:
        c1 = CommandRequest.objects.create(
            command_type=CommandRequest.CommandType.LIST_PROCESSES,
            hmac_signature="a" * 64,
        )
        c2 = CommandRequest.objects.create(
            command_type=CommandRequest.CommandType.LIST_PROCESSES,
            hmac_signature="b" * 64,
        )
        cmds = list(CommandRequest.objects.all())
        self.assertEqual(cmds[0], c2)
        self.assertEqual(cmds[1], c1)

    def test_created_by_nullable(self) -> None:
        user = User.objects.create_user(username="kevin", password="testpass")
        cmd = CommandRequest.objects.create(
            command_type=CommandRequest.CommandType.SEND_PROMPT,
            hmac_signature="a" * 64,
            created_by=user,
        )
        self.assertEqual(cmd.created_by, user)

        # SET_NULL on delete
        user.delete()
        cmd.refresh_from_db()
        self.assertIsNone(cmd.created_by)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class SessionOutputBufferModelTest(TestCase):
    def test_create(self) -> None:
        buf = SessionOutputBuffer.objects.create(
            session_id="sess-123",
            line_number=1,
            content="Hello world",
            stream=SessionOutputBuffer.Stream.STDOUT,
        )
        self.assertEqual(buf.session_id, "sess-123")
        self.assertIsNotNone(buf.timestamp)

    def test_str(self) -> None:
        buf = SessionOutputBuffer.objects.create(
            session_id="sess-abc",
            line_number=42,
            content="output",
            stream=SessionOutputBuffer.Stream.STDERR,
        )
        self.assertEqual(str(buf), "sess-abc:42 (stderr)")

    def test_unique_constraint(self) -> None:
        SessionOutputBuffer.objects.create(
            session_id="sess-1",
            line_number=1,
            content="first",
            stream=SessionOutputBuffer.Stream.STDOUT,
        )
        with self.assertRaises(IntegrityError):
            SessionOutputBuffer.objects.create(
                session_id="sess-1",
                line_number=1,
                content="duplicate",
                stream=SessionOutputBuffer.Stream.STDOUT,
            )

    def test_ordering_by_line_number(self) -> None:
        SessionOutputBuffer.objects.create(
            session_id="sess-1",
            line_number=3,
            content="third",
            stream=SessionOutputBuffer.Stream.STDOUT,
        )
        SessionOutputBuffer.objects.create(
            session_id="sess-1",
            line_number=1,
            content="first",
            stream=SessionOutputBuffer.Stream.STDOUT,
        )
        SessionOutputBuffer.objects.create(
            session_id="sess-1",
            line_number=2,
            content="second",
            stream=SessionOutputBuffer.Stream.STDOUT,
        )
        lines = list(
            SessionOutputBuffer.objects.filter(session_id="sess-1").values_list(
                "line_number", flat=True
            )
        )
        self.assertEqual(lines, [1, 2, 3])
