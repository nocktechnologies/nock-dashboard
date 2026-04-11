from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from sessions.models import AgentSession, SessionLog


class Command(BaseCommand):
    help = "Seed sample sessions and logs for visual testing"

    def handle(self, *args: object, **options: object) -> None:
        now = timezone.now()

        sessions_data = [
            {
                "agent": "claude_code",
                "machine": "mac",
                "status": "active",
                "branch": "feature/session-models",
                "task_description": "Building session tracking models and REST API",
                "started_at": now - timedelta(hours=2),
                "tokens_input": 45000,
                "tokens_output": 12000,
                "estimated_cost": Decimal("0.3150"),
                "commits_generated": 3,
            },
            {
                "agent": "codex",
                "machine": "windows",
                "status": "active",
                "branch": "feature/spend-dashboard",
                "task_description": "Implementing Anthropic API spend tracking",
                "started_at": now - timedelta(hours=1),
                "tokens_input": 20000,
                "tokens_output": 8000,
                "estimated_cost": Decimal("0.1800"),
                "commits_generated": 1,
            },
            {
                "agent": "claude_code",
                "machine": "mac",
                "status": "completed",
                "branch": "feature/pipeline-dashboard",
                "task_description": "Pipeline dashboard with PR tracking",
                "started_at": now - timedelta(days=1, hours=3),
                "ended_at": now - timedelta(days=1),
                "tokens_input": 120000,
                "tokens_output": 35000,
                "estimated_cost": Decimal("1.2500"),
                "commits_generated": 8,
            },
            {
                "agent": "copilot",
                "machine": "windows",
                "status": "completed",
                "branch": "fix/webhook-validation",
                "task_description": "Fixing HMAC signature validation edge cases",
                "started_at": now - timedelta(days=2, hours=5),
                "ended_at": now - timedelta(days=2, hours=3),
                "tokens_input": 15000,
                "tokens_output": 5000,
                "estimated_cost": Decimal("0.0950"),
                "commits_generated": 2,
            },
            {
                "agent": "claude_code",
                "machine": "mac",
                "status": "failed",
                "branch": "feature/notifications",
                "task_description": "Slack notification integration",
                "started_at": now - timedelta(days=3),
                "ended_at": now - timedelta(days=3) + timedelta(hours=1),
                "tokens_input": 30000,
                "tokens_output": 10000,
                "estimated_cost": Decimal("0.2200"),
                "commits_generated": 0,
                "notes": "Failed due to invalid Slack webhook URL configuration",
            },
        ]

        logs_data = [
            ("info", "Session started — cloning repository"),
            ("info", "Running migrations"),
            ("success", "Models created successfully"),
            ("info", "Writing test suite"),
            ("warning", "Flaky test detected, retrying"),
            ("error", "Connection timeout to database"),
            ("success", "All 15 tests passing"),
        ]

        for data in sessions_data:
            session = AgentSession.objects.create(**data)
            for level, message in logs_data[:3]:
                SessionLog.objects.create(session=session, level=level, message=message)
            self.stdout.write(f"  Created session: {session}")

        # Add extra logs to first session for detail view testing
        first = AgentSession.objects.order_by("-started_at").first()
        if first:
            for level, message in logs_data[3:]:
                SessionLog.objects.create(session=first, level=level, message=message)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(sessions_data)} sessions with log entries"
        ))
