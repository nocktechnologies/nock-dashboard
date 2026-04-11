import asyncio
import hashlib
import os

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase, override_settings

from remote.consumers import AgentConsumer
from remote.models import (
    AgentStatus,
    AgentToken,
    CommandRequest,
    SessionOutputBuffer,
)

_TEST_FERNET_KEYS = [os.environ.get("TEST_FERNET_KEY", "")]
_CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

RAW_TOKEN = "test-agent-token-for-websocket"
TOKEN_HASH = hashlib.sha256(RAW_TOKEN.encode()).hexdigest()


async def _wait_for(predicate, timeout: float = 2.0, interval: float = 0.05):
    """Poll predicate until truthy or timeout."""
    elapsed = 0.0
    while elapsed < timeout:
        result = await predicate()
        if result:
            return result
        await asyncio.sleep(interval)
        elapsed += interval
    return await predicate()


@database_sync_to_async
def _create_token(
    name: str = "Test Mac", raw_token: str = RAW_TOKEN, active: bool = True
) -> AgentToken:
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    token = AgentToken.objects.create(
        name=name, token_hash=token_hash, is_active=active
    )
    AgentStatus.objects.create(agent_token=token)
    return token


@database_sync_to_async
def _get_agent_status(token: AgentToken) -> AgentStatus:
    return AgentStatus.objects.get(agent_token=token)


@database_sync_to_async
def _create_command(token_hash: str) -> CommandRequest:
    return CommandRequest.objects.create(
        command_type=CommandRequest.CommandType.START_SESSION,
        payload={"repo": "nexus"},
        hmac_signature="a" * 64,
        status=CommandRequest.Status.SENT,
    )


@database_sync_to_async
def _get_command(pk: int) -> CommandRequest:
    return CommandRequest.objects.get(pk=pk)


@database_sync_to_async
def _get_output_count(session_id: str) -> int:
    return SessionOutputBuffer.objects.filter(session_id=session_id).count()


@database_sync_to_async
def _get_token(pk: int) -> AgentToken:
    return AgentToken.objects.get(pk=pk)


def _make_communicator(token: str = RAW_TOKEN) -> WebsocketCommunicator:
    return WebsocketCommunicator(
        AgentConsumer.as_asgi(),
        f"/ws/agent/?token={token}",
    )


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    CHANNEL_LAYERS=_CHANNEL_LAYERS,
)
class AgentConsumerConnectTest(TransactionTestCase):
    async def test_connect_with_valid_token(self) -> None:
        token = await _create_token()
        communicator = _make_communicator()
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        status = await _get_agent_status(token)
        self.assertTrue(status.is_online)
        self.assertIsNotNone(status.connected_at)

        await communicator.disconnect()

    async def test_connect_with_invalid_token(self) -> None:
        await _create_token()
        communicator = _make_communicator(token="wrong-token")
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4001)

    async def test_connect_with_no_token(self) -> None:
        communicator = WebsocketCommunicator(
            AgentConsumer.as_asgi(),
            "/ws/agent/",
        )
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4001)

    async def test_connect_with_inactive_token(self) -> None:
        await _create_token(active=False)
        communicator = _make_communicator()
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4001)

    async def test_connect_updates_last_used_at(self) -> None:
        token = await _create_token()
        communicator = _make_communicator()
        await communicator.connect()

        refreshed = await _get_token(token.pk)
        self.assertIsNotNone(refreshed.last_used_at)

        await communicator.disconnect()


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    CHANNEL_LAYERS=_CHANNEL_LAYERS,
)
class AgentConsumerDisconnectTest(TransactionTestCase):
    async def test_disconnect_sets_offline(self) -> None:
        token = await _create_token()
        communicator = _make_communicator()
        await communicator.connect()

        status = await _get_agent_status(token)
        self.assertTrue(status.is_online)

        await communicator.disconnect()

        status = await _get_agent_status(token)
        self.assertFalse(status.is_online)
        self.assertIsNotNone(status.disconnected_at)


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    CHANNEL_LAYERS=_CHANNEL_LAYERS,
)
class AgentConsumerMessageTest(TransactionTestCase):
    async def test_heartbeat(self) -> None:
        token = await _create_token()
        communicator = _make_communicator()
        await communicator.connect()

        await communicator.send_json_to({"type": "heartbeat"})
        response = await communicator.receive_json_from()

        self.assertEqual(response["type"], "heartbeat_ack")
        self.assertIn("server_time", response)

        status = await _get_agent_status(token)
        self.assertIsNotNone(status.last_heartbeat)

        await communicator.disconnect()

    async def test_identify(self) -> None:
        token = await _create_token()
        communicator = _make_communicator()
        await communicator.connect()

        await communicator.send_json_to({
            "type": "identify",
            "machine": "Kevins-MacBook",
        })

        async def check():
            s = await _get_agent_status(token)
            return s.machine_name == "Kevins-MacBook"

        await _wait_for(check)

        status = await _get_agent_status(token)
        self.assertEqual(status.machine_name, "Kevins-MacBook")

        await communicator.disconnect()

    async def test_output_creates_buffer(self) -> None:
        await _create_token()
        communicator = _make_communicator()
        await communicator.connect()

        await communicator.send_json_to({
            "type": "output",
            "session_id": "sess-test-1",
            "line": 1,
            "content": "Hello from Claude",
            "stream": "stdout",
        })

        async def check():
            return await _get_output_count("sess-test-1") == 1

        await _wait_for(check)

        count = await _get_output_count("sess-test-1")
        self.assertEqual(count, 1)

        await communicator.disconnect()

    async def test_output_missing_fields_returns_error(self) -> None:
        await _create_token()
        communicator = _make_communicator()
        await communicator.connect()

        await communicator.send_json_to({
            "type": "output",
            "session_id": "sess-test-2",
            # missing "line"
        })
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "error")
        self.assertIn("requires", response["message"])

        await communicator.disconnect()

    async def test_command_result_updates_status(self) -> None:
        await _create_token()
        cmd = await _create_command(TOKEN_HASH)
        communicator = _make_communicator()
        await communicator.connect()

        await communicator.send_json_to({
            "type": "command_result",
            "command_id": cmd.pk,
            "status": "completed",
            "result": "Done successfully",
        })

        async def check():
            c = await _get_command(cmd.pk)
            return c.status == "completed"

        await _wait_for(check)

        updated = await _get_command(cmd.pk)
        self.assertEqual(updated.status, "completed")
        self.assertEqual(updated.result, "Done successfully")
        self.assertIsNotNone(updated.completed_at)

        await communicator.disconnect()

    async def test_process_list_updates_count(self) -> None:
        token = await _create_token()
        communicator = _make_communicator()
        await communicator.connect()

        await communicator.send_json_to({
            "type": "process_list",
            "processes": [
                {"pid": 123, "repo": "nexus"},
                {"pid": 456, "repo": "abl"},
            ],
        })

        async def check():
            s = await _get_agent_status(token)
            return s.active_sessions == 2

        await _wait_for(check)

        status = await _get_agent_status(token)
        self.assertEqual(status.active_sessions, 2)

        await communicator.disconnect()

    async def test_unknown_type_returns_error(self) -> None:
        await _create_token()
        communicator = _make_communicator()
        await communicator.connect()

        await communicator.send_json_to({"type": "bogus_type"})
        response = await communicator.receive_json_from()

        self.assertEqual(response["type"], "error")
        self.assertIn("Unknown message type", response["message"])

        await communicator.disconnect()
