"""Seed default notification channels and rules."""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from notifications.models import NotificationChannel, NotificationRule

DEFAULT_RULES = [
    ("PR Merged Alert", "pr_merged"),
    ("CI Failed Alert", "ci_failed"),
    ("Budget Threshold Alert", "budget_threshold"),
    ("Context Stale Alert", "context_stale"),
]


class Command(BaseCommand):
    help = "Seed default notification channels and rules."

    def handle(self, *args: Any, **options: Any) -> None:
        # Create Slack channel
        slack_url = getattr(settings, "SLACK_WEBHOOK_URL", "") or "https://hooks.slack.com/services/placeholder"
        slack_channel, created = NotificationChannel.objects.get_or_create(
            name="Slack — NockCC",
            defaults={
                "channel_type": "slack",
                "webhook_url": slack_url,
            },
        )
        self.stdout.write(f"  Slack channel — {'created' if created else 'exists'}")

        # Create Discord channel
        discord_url = getattr(settings, "DISCORD_WEBHOOK_URL", "") or "https://discord.com/api/webhooks/placeholder"
        _discord_channel, created = NotificationChannel.objects.get_or_create(
            name="Discord — NockCC",
            defaults={
                "channel_type": "discord",
                "webhook_url": discord_url,
            },
        )
        self.stdout.write(f"  Discord channel — {'created' if created else 'exists'}")

        # Create rules (route to Slack by default)
        for name, event in DEFAULT_RULES:
            _, created = NotificationRule.objects.get_or_create(
                name=name,
                defaults={
                    "trigger_event": event,
                    "channel": slack_channel,
                },
            )
            self.stdout.write(f"  Rule: {name} — {'created' if created else 'exists'}")

        self.stdout.write(self.style.SUCCESS("Done."))
