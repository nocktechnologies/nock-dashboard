"""Tests for agent security module."""

import hashlib
import hmac
import json
from unittest import TestCase
from unittest.mock import patch

from nockcc_agent.config import AgentConfig
from nockcc_agent.security import (
    check_startup_safety,
    validate_command,
    verify_hmac,
)


def _make_config(**kwargs) -> AgentConfig:
    defaults = {
        "server_url": "wss://example.com/ws/agent/",
        "agent_token": "test-token",
        "hmac_key": "test-hmac-key",
        "repos": {"nexus": "/Users/kevin/Dev/Nexus"},
        "allow_raw_shell": False,
    }
    defaults.update(kwargs)
    return AgentConfig(**defaults)


def _sign(payload: dict, key: str = "test-hmac-key") -> str:
    payload_bytes = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(key.encode(), payload_bytes, hashlib.sha256).hexdigest()


class VerifyHmacTest(TestCase):
    def test_valid_signature(self) -> None:
        payload = {"repo": "nexus", "prompt": "fix tests"}
        signature = _sign(payload)
        self.assertTrue(verify_hmac(payload, signature, "test-hmac-key"))

    def test_invalid_signature(self) -> None:
        payload = {"repo": "nexus"}
        self.assertFalse(verify_hmac(payload, "invalid", "test-hmac-key"))

    def test_wrong_key(self) -> None:
        payload = {"repo": "nexus"}
        signature = _sign(payload, key="correct-key")
        self.assertFalse(verify_hmac(payload, signature, "wrong-key"))

    def test_empty_signature(self) -> None:
        self.assertFalse(verify_hmac({}, "", "test-hmac-key"))

    def test_empty_key(self) -> None:
        self.assertFalse(verify_hmac({}, "some-sig", ""))


class ValidateCommandTest(TestCase):
    def test_valid_start_session(self) -> None:
        config = _make_config()
        payload = {"repo": "nexus", "prompt": "fix"}
        signature = _sign(payload)
        result = validate_command("start_session", payload, signature, config)
        self.assertIsNone(result)

    def test_invalid_hmac(self) -> None:
        config = _make_config()
        result = validate_command("start_session", {}, "bad-sig", config)
        self.assertIn("HMAC", result)

    def test_unknown_command_type(self) -> None:
        config = _make_config()
        payload = {}
        signature = _sign(payload)
        result = validate_command("unknown_type", payload, signature, config)
        self.assertIn("Unknown command type", result)

    def test_repo_not_in_allowlist(self) -> None:
        config = _make_config()
        payload = {"repo": "forbidden_repo"}
        signature = _sign(payload)
        result = validate_command("start_session", payload, signature, config)
        self.assertIn("allowlist", result)

    def test_repo_in_allowlist(self) -> None:
        config = _make_config()
        payload = {"repo": "nexus", "prompt": "test"}
        signature = _sign(payload)
        result = validate_command("start_session", payload, signature, config)
        self.assertIsNone(result)

    def test_raw_shell_blocked(self) -> None:
        """run_command is not in allowed types, so it's rejected as unknown."""
        config = _make_config(allow_raw_shell=False)
        payload = {"command": "ls -la"}
        signature = _sign(payload)
        result = validate_command("run_command", payload, signature, config)
        self.assertIsNotNone(result)  # Rejected regardless of allow_raw_shell

    def test_kill_all_valid(self) -> None:
        config = _make_config()
        payload = {}
        signature = _sign(payload)
        result = validate_command("kill_all", payload, signature, config)
        self.assertIsNone(result)


class StartupSafetyTest(TestCase):
    @patch("os.getuid", return_value=0)
    def test_rejects_root(self, mock_uid) -> None:
        errors = check_startup_safety()
        self.assertTrue(any("root" in e for e in errors))

    @patch("os.getuid", return_value=501)
    def test_accepts_normal_user(self, mock_uid) -> None:
        errors = check_startup_safety()
        self.assertEqual(errors, [])
