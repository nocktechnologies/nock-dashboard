import hashlib
import secrets
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from remote.models import AgentStatus, AgentToken


class Command(BaseCommand):
    help = "Generate an agent authentication token for the Mac daemon"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--name",
            required=True,
            help='Human-readable name, e.g. "Kevin\'s MacBook"',
        )

    def handle(self, *args: object, **options: Any) -> None:
        name = options["name"]

        raw_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        with transaction.atomic():
            token = AgentToken.objects.create(name=name, token_hash=token_hash)
            AgentStatus.objects.create(agent_token=token)

        self.stdout.write(self.style.SUCCESS(f"Token created for: {name}"))
        self.stdout.write("\nRaw token (SAVE THIS — shown only once):")
        self.stdout.write(self.style.WARNING(raw_token))
        self.stdout.write(f"\nToken hash: {token_hash}")
        self.stdout.write(
            '\nAdd to ~/.nockcc/agent.json as the "agent_token" value.'
        )
