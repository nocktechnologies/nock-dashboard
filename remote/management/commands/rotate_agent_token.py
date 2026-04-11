import hashlib
import secrets
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from remote.models import AgentStatus, AgentToken


class Command(BaseCommand):
    help = "Rotate an agent token — deactivates old token, creates new one"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--name",
            required=True,
            help="Name of the agent token to rotate",
        )

    def handle(self, *args: object, **options: Any) -> None:
        name = options["name"]

        try:
            old_token = AgentToken.objects.get(name=name, is_active=True)
        except AgentToken.DoesNotExist as err:
            raise CommandError(f"No active token found with name: {name}") from err

        # Deactivate old token
        old_token.is_active = False
        old_token.save(update_fields=["is_active"])
        self.stdout.write(f"Deactivated old token for: {name}")

        # Create new token
        raw_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        new_token = AgentToken.objects.create(name=name, token_hash=token_hash)

        # Migrate AgentStatus to new token
        AgentStatus.objects.filter(agent_token=old_token).update(
            agent_token=new_token, is_online=False, channel_name=""
        )
        # Ensure status exists
        if not AgentStatus.objects.filter(agent_token=new_token).exists():
            AgentStatus.objects.create(agent_token=new_token)

        self.stdout.write(self.style.SUCCESS(f"New token created for: {name}"))
        self.stdout.write("\nNew raw token (SAVE THIS — shown only once):")
        self.stdout.write(self.style.WARNING(raw_token))
        self.stdout.write(f"\nToken hash: {token_hash}")
        self.stdout.write(
            '\nUpdate ~/.nockcc/agent.json with the new "agent_token" value.'
        )
