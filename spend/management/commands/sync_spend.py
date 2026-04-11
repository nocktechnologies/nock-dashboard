"""Manual sync — fetch last N days of Anthropic usage data."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand

from spend.anthropic_client import fetch_cost_report, fetch_usage_report
from spend.models import UsagePeriod


class Command(BaseCommand):
    help = "Sync Anthropic usage data for the last N days."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--days", type=int, default=7, help="Number of days to sync (default: 7)")

    def handle(self, *args: Any, **options: Any) -> None:
        days = options["days"]
        if days <= 0:
            self.stderr.write(self.style.ERROR("--days must be a positive integer"))
            return
        end = date.today()
        start = end - timedelta(days=days - 1)

        self.stdout.write(f"Syncing usage from {start} to {end}...")

        usage_records = fetch_usage_report(start, end)
        cost_records = fetch_cost_report(start, end)

        # Build cost lookup by date
        cost_by_date: dict[str, Decimal] = {}
        for c in cost_records:
            key = c["date"]
            cost_by_date[key] = cost_by_date.get(key, Decimal("0")) + c["cost_usd"]

        created = 0
        updated = 0
        for rec in usage_records:
            _, was_created = UsagePeriod.objects.update_or_create(
                date=rec["date"],
                model=rec["model"],
                workspace=rec.get("workspace", ""),
                defaults={
                    "input_tokens": rec["input_tokens"],
                    "output_tokens": rec["output_tokens"],
                    "cache_read_tokens": rec.get("cache_read_tokens", 0),
                    "cache_write_tokens": rec.get("cache_write_tokens", 0),
                    "request_count": rec.get("request_count", 0),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        # Apply daily cost across models
        for day_str, total_cost in cost_by_date.items():
            day_records = UsagePeriod.objects.filter(date=day_str).order_by("model")
            count = day_records.count()
            if count and total_cost:
                per_model = total_cost / count
                for rec in day_records:
                    rec.cost_usd = per_model
                    rec.save(update_fields=["cost_usd"])

        self.stdout.write(self.style.SUCCESS(
            f"Done. {created} created, {updated} updated across {days} days."
        ))
