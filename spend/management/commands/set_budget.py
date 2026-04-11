"""Create or update a monthly spend budget."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand

from spend.models import SpendBudget


class Command(BaseCommand):
    help = "Create or update a monthly spend budget."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--month", required=True, help="Month in YYYY-MM format")
        parser.add_argument("--amount", required=True, type=str, help="Budget amount in USD")

    def handle(self, *args: Any, **options: Any) -> None:
        month_str = options["month"]
        amount = Decimal(str(options["amount"]))

        if amount < 0:
            self.stderr.write(self.style.ERROR("Budget amount cannot be negative"))
            return

        month_date = datetime.strptime(month_str, "%Y-%m").date().replace(day=1)

        _, created = SpendBudget.objects.update_or_create(
            month=month_date,
            defaults={"budget_usd": amount},
        )
        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} budget: {month_date} — ${amount}"))
