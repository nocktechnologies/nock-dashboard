import hashlib
import os
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from remote.models import AgentStatus, AgentToken, CommandAuditLog

_TEST_FERNET_KEYS = [os.environ.get("TEST_FERNET_KEY", "")]


def _make_token(name: str = "Test Mac", active: bool = True) -> AgentToken:
    token_hash = hashlib.sha256(f"test-token-{name}".encode()).hexdigest()
    return AgentToken.objects.create(
        name=name, token_hash=token_hash, is_active=active
    )


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class RotateAgentTokenTest(TestCase):
    def test_rotate_creates_new_deactivates_old(self) -> None:
        old_token = _make_token("Test Mac")
        AgentStatus.objects.create(agent_token=old_token)

        out = StringIO()
        call_command("rotate_agent_token", "--name", "Test Mac", stdout=out)

        old_token.refresh_from_db()
        self.assertFalse(old_token.is_active)

        new_token = AgentToken.objects.get(name="Test Mac", is_active=True)
        self.assertNotEqual(new_token.pk, old_token.pk)

        output = out.getvalue()
        self.assertIn("New token created", output)
        self.assertIn("shown only once", output)

    def test_rotate_migrates_status(self) -> None:
        old_token = _make_token("Test Mac")
        AgentStatus.objects.create(
            agent_token=old_token, is_online=True, machine_name="TestMac"
        )

        out = StringIO()
        call_command("rotate_agent_token", "--name", "Test Mac", stdout=out)

        new_token = AgentToken.objects.get(name="Test Mac", is_active=True)
        status = AgentStatus.objects.get(agent_token=new_token)
        self.assertFalse(status.is_online)  # Reset on rotate

    def test_rotate_nonexistent_fails(self) -> None:
        with self.assertRaises(CommandError):
            call_command(
                "rotate_agent_token",
                "--name",
                "Nonexistent",
                stdout=StringIO(),
            )

    def test_rotate_inactive_fails(self) -> None:
        _make_token("Old Mac", active=False)
        with self.assertRaises(CommandError):
            call_command(
                "rotate_agent_token",
                "--name",
                "Old Mac",
                stdout=StringIO(),
            )


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class CommandAuditLogTest(TestCase):
    def test_create_audit_log(self) -> None:
        log = CommandAuditLog.objects.create(
            action="ws_auth_failed",
            source_ip="1.2.3.4",
            details={"reason": "Invalid token"},
        )
        self.assertEqual(log.action, "ws_auth_failed")
        self.assertIsNotNone(log.timestamp)

    def test_audit_log_str(self) -> None:
        log = CommandAuditLog.objects.create(action="test_action")
        self.assertIn("test_action", str(log))

    def test_audit_log_ordering(self) -> None:
        CommandAuditLog.objects.create(action="first")
        CommandAuditLog.objects.create(action="second")
        logs = list(CommandAuditLog.objects.values_list("action", flat=True))
        self.assertEqual(logs[0], "second")


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class SessionTimeoutSettingsTest(TestCase):
    def test_prod_session_cookie_age(self) -> None:
        from config.settings import prod

        self.assertEqual(prod.SESSION_COOKIE_AGE, 1800)
        self.assertTrue(prod.SESSION_SAVE_EVERY_REQUEST)
