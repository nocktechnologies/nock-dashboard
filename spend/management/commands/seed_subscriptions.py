"""Seed Kevin's current real subscriptions."""

from datetime import date
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand

from spend.models import SubscriptionTracker

SUBSCRIPTIONS = [
    {
        "name": "Claude Max 20x",
        "provider": "anthropic",
        "monthly_cost": Decimal("200.00"),
        "renewal_date": date(2026, 4, 21),
        "notes": "Monthly",
    },
    {
        "name": "Kimi",
        "provider": "moonshot",
        "monthly_cost": Decimal("99.00"),
        "renewal_date": date(2026, 4, 25),
        "notes": "Monthly",
    },
    {
        "name": "ChatGPT Plus",
        "provider": "openai",
        "monthly_cost": Decimal("21.28"),
        "renewal_date": date(2026, 4, 22),
        "notes": "Monthly (per seat)",
    },
    {
        "name": "CodeRabbit Pro",
        "provider": "coderabbit",
        "monthly_cost": Decimal("30.00"),
        "renewal_date": date(2026, 4, 6),
        "notes": "Monthly",
    },
    {
        "name": "Asana Starter (5 seats)",
        "provider": "asana",
        "monthly_cost": Decimal("71.36"),
        "renewal_date": date(2026, 4, 8),
        "notes": "Monthly",
    },
    {
        "name": "v0",
        "provider": "vercel",
        "monthly_cost": Decimal("21.32"),
        "renewal_date": date(2026, 4, 5),
        "notes": "Monthly",
    },
    {
        "name": "Workplace Mail Lite (2 users)",
        "provider": "zoho",
        "monthly_cost": Decimal("2.00"),
        "renewal_date": date(2027, 3, 14),
        "notes": "Yearly ($24/yr, Mar 14 2026-Mar 13 2027)",
    },
    {
        "name": "NockCC Hosting (est.)",
        "provider": "railway",
        "monthly_cost": Decimal("25.00"),
        "renewal_date": date(2026, 4, 1),
        "notes": "Monthly (trial ending soon)",
    },
]


class Command(BaseCommand):
    help = "Seed Kevin's current real subscriptions."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing subscriptions before seeding.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["clear"]:
            deleted, _ = SubscriptionTracker.objects.all().delete()
            self.stdout.write(f"  Cleared {deleted} existing subscriptions.")

        for sub in SUBSCRIPTIONS:
            _, created = SubscriptionTracker.objects.get_or_create(
                name=sub["name"],
                defaults={
                    "provider": sub["provider"],
                    "monthly_cost": sub["monthly_cost"],
                    "renewal_date": sub["renewal_date"],
                    "notes": sub.get("notes", ""),
                },
            )
            status = "created" if created else "exists"
            self.stdout.write(f"  {sub['name']} — ${sub['monthly_cost']}/mo — {status}")

        total = sum(s["monthly_cost"] for s in SUBSCRIPTIONS)
        self.stdout.write(f"\n  Total monthly: ${total}")
        self.stdout.write(f"  Annual projection: ${total * 12}")
        self.stdout.write(self.style.SUCCESS("Done."))
