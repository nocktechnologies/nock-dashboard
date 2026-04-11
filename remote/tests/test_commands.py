import hashlib
import os
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from remote.models import AgentStatus, AgentToken

_TEST_FERNET_KEYS = [os.environ.get("TEST_FERNET_KEY", "")]


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class CreateAgentTokenCommandTest(TestCase):
    def test_creates_token_and_status(self) -> None:
        out = StringIO()
        call_command("create_agent_token", "--name", "Test Mac", stdout=out)

        self.assertEqual(AgentToken.objects.count(), 1)
        self.assertEqual(AgentStatus.objects.count(), 1)

        token = AgentToken.objects.first()
        self.assertEqual(token.name, "Test Mac")
        self.assertTrue(token.is_active)

    def test_prints_raw_token(self) -> None:
        out = StringIO()
        call_command("create_agent_token", "--name", "Test Mac", stdout=out)

        output = out.getvalue()
        self.assertIn("Token created for: Test Mac", output)
        self.assertIn("Raw token", output)
        self.assertIn("shown only once", output)

    def test_stored_hash_matches_printed_token(self) -> None:
        out = StringIO()
        call_command("create_agent_token", "--name", "Test Mac", stdout=out)

        output = out.getvalue()
        token = AgentToken.objects.first()

        # The raw token is on the line after "shown only once"
        lines = output.strip().split("\n")
        raw_token = None
        for i, line in enumerate(lines):
            if "shown only once" in line:
                raw_token = lines[i + 1].strip()
                break

        self.assertIsNotNone(raw_token, "Raw token not found in output")
        expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        self.assertEqual(token.token_hash, expected_hash)

    def test_requires_name(self) -> None:
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command("create_agent_token", stdout=out, stderr=StringIO())
