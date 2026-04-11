"""Tests for agent config loading and validation."""

import json
import tempfile
from pathlib import Path
from unittest import TestCase

from nockcc_agent.config import AgentConfig, load_config


class AgentConfigValidationTest(TestCase):
    def test_valid_config(self) -> None:
        config = AgentConfig(
            server_url="wss://example.com/ws/agent/",
            agent_token="test-token",
            hmac_key="test-key",
            machine_name="TestMac",
            repos={"nexus": "/Users/kevin/Dev/Nexus"},
        )
        errors = config.validate()
        self.assertEqual(errors, [])

    def test_missing_server_url(self) -> None:
        config = AgentConfig(
            server_url="",
            agent_token="test-token",
            hmac_key="test-key",
        )
        errors = config.validate()
        self.assertIn("server_url is required", errors)

    def test_ws_url_rejected(self) -> None:
        config = AgentConfig(
            server_url="ws://example.com/ws/agent/",
            agent_token="test-token",
            hmac_key="test-key",
        )
        errors = config.validate()
        self.assertTrue(any("wss://" in e for e in errors))

    def test_missing_token(self) -> None:
        config = AgentConfig(
            server_url="wss://example.com/ws/agent/",
            agent_token="",
            hmac_key="test-key",
        )
        errors = config.validate()
        self.assertIn("agent_token is required", errors)

    def test_missing_hmac_key(self) -> None:
        config = AgentConfig(
            server_url="wss://example.com/ws/agent/",
            agent_token="test-token",
            hmac_key="",
        )
        errors = config.validate()
        self.assertIn("hmac_key is required", errors)

    def test_relative_repo_path_rejected(self) -> None:
        config = AgentConfig(
            server_url="wss://example.com/ws/agent/",
            agent_token="test-token",
            hmac_key="test-key",
            repos={"nexus": "relative/path"},
        )
        errors = config.validate()
        self.assertTrue(any("absolute" in e for e in errors))

    def test_repo_names_property(self) -> None:
        config = AgentConfig(
            server_url="wss://example.com/ws/agent/",
            agent_token="test-token",
            hmac_key="test-key",
            repos={"nexus": "/a", "abl": "/b"},
        )
        self.assertEqual(sorted(config.repo_names), ["abl", "nexus"])

    def test_defaults(self) -> None:
        config = AgentConfig(
            server_url="wss://example.com/ws/agent/",
            agent_token="test-token",
            hmac_key="test-key",
        )
        self.assertEqual(config.machine_name, "Unknown")
        self.assertEqual(config.default_flags, "--dangerously-skip-permissions")
        self.assertFalse(config.allow_raw_shell)
        self.assertTrue(config.kill_on_disconnect)


class LoadConfigTest(TestCase):
    def test_load_valid_config(self) -> None:
        data = {
            "server_url": "wss://example.com/ws/agent/",
            "agent_token": "test-token",
            "hmac_key": "test-key",
            "machine_name": "TestMac",
            "repos": {"nexus": "/Users/kevin/Dev/Nexus"},
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            f.flush()
            config = load_config(Path(f.name))

        self.assertEqual(config.server_url, "wss://example.com/ws/agent/")
        self.assertEqual(config.agent_token, "test-token")
        self.assertEqual(config.machine_name, "TestMac")

    def test_load_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_config(Path("/nonexistent/path.json"))

    def test_load_missing_required_fields(self) -> None:
        data = {"server_url": "wss://example.com/ws/agent/"}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            f.flush()
            with self.assertRaises(ValueError) as ctx:
                load_config(Path(f.name))
            self.assertIn("agent_token", str(ctx.exception))

    def test_load_invalid_url(self) -> None:
        data = {
            "server_url": "ws://insecure.com/ws/agent/",
            "agent_token": "test-token",
            "hmac_key": "test-key",
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            f.flush()
            with self.assertRaises(ValueError) as ctx:
                load_config(Path(f.name))
            self.assertIn("wss://", str(ctx.exception))
