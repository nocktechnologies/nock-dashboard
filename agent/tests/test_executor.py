"""Tests for the subprocess executor."""

import asyncio
from unittest import TestCase

from nockcc_agent.config import AgentConfig
from nockcc_agent.executor import Executor


def _make_config(**kwargs) -> AgentConfig:
    defaults = {
        "server_url": "wss://example.com/ws/agent/",
        "agent_token": "test-token",
        "hmac_key": "test-key",
        "repos": {"test_repo": "/tmp"},
        "default_flags": "",
    }
    defaults.update(kwargs)
    return AgentConfig(**defaults)


class ExecutorTest(TestCase):
    def test_list_processes_empty(self) -> None:
        config = _make_config()
        executor = Executor(config)
        self.assertEqual(executor.list_processes(), [])

    def test_active_sessions_empty(self) -> None:
        config = _make_config()
        executor = Executor(config)
        self.assertEqual(executor.active_sessions, [])

    def test_start_session_rejects_unknown_repo(self) -> None:
        config = _make_config()
        executor = Executor(config)

        async def run():
            with self.assertRaises(ValueError) as ctx:
                await executor.start_session("unknown_repo", "test")
            self.assertIn("allowlist", str(ctx.exception))

        asyncio.run(run())

    def test_stop_nonexistent_session(self) -> None:
        config = _make_config()
        executor = Executor(config)

        async def run():
            result = await executor.stop_session("nonexistent")
            self.assertFalse(result)

        asyncio.run(run())

    def test_send_prompt_nonexistent_session(self) -> None:
        config = _make_config()
        executor = Executor(config)

        async def run():
            result = await executor.send_prompt("nonexistent", "test")
            self.assertFalse(result)

        asyncio.run(run())

    def test_kill_all_empty(self) -> None:
        config = _make_config()
        executor = Executor(config)

        async def run():
            count = await executor.kill_all()
            self.assertEqual(count, 0)

        asyncio.run(run())
