"""Seed default Smart Watch rules."""
from typing import Any

from django.core.management.base import BaseCommand

from intelligence.models import SmartWatchRule

DEFAULT_RULES = [
    {
        "name": "PR Waiting for Review",
        "condition_type": "pr_waiting",
        "threshold_minutes": 240,
        "severity": "warning",
        "message_template": "\u23f3 PR #{pr_number} on {repo} has been waiting {value} hours for review",
        "cooldown_minutes": 120,
    },
    {
        "name": "Long Running Session",
        "condition_type": "session_long",
        "threshold_minutes": 180,
        "severity": "info",
        "message_template": "\u23f0 Kit session on {project} ({branch}) has been running for {value}",
        "cooldown_minutes": 60,
    },
    {
        "name": "Task Due Tomorrow",
        "condition_type": "task_due_tomorrow",
        "threshold_minutes": 0,
        "severity": "warning",
        "message_template": "\U0001f4cb Due tomorrow: {task_name} ({project})",
        "cooldown_minutes": 720,
    },
    {
        "name": "High Context Usage",
        "condition_type": "context_high",
        "threshold_value": 75,
        "severity": "warning",
        "message_template": "\U0001f9e0 {project} session at {value}% context \u2014 consider wrapping up",
        "cooldown_minutes": 30,
    },
    {
        "name": "Stale Brain Entries",
        "condition_type": "brain_stale",
        "threshold_minutes": 43200,
        "severity": "info",
        "message_template": "\U0001f4da {value} Brain entries haven't been updated in {threshold} days",
        "cooldown_minutes": 10080,
    },
]


class Command(BaseCommand):
    help = "Seed default Smart Watch rules (idempotent — skips existing)"

    def handle(self, *args: Any, **options: Any) -> None:
        created = 0
        skipped = 0

        for rule_data in DEFAULT_RULES:
            _, was_created = SmartWatchRule.objects.get_or_create(
                name=rule_data["name"],
                defaults=rule_data,
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"  Created: {rule_data['name']}"))
            else:
                skipped += 1
                self.stdout.write(f"  Skipped (exists): {rule_data['name']}")

        self.stdout.write(
            self.style.SUCCESS(f"\nDone: {created} created, {skipped} skipped"),
        )
