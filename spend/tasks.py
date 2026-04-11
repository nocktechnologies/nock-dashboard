"""Celery tasks for Anthropic spend syncing and budget alerts."""

import logging
from datetime import date, timedelta
from decimal import Decimal

import requests
from celery import shared_task
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .anthropic_client import fetch_cost_report, fetch_usage_report
from .models import SpendBudget, UsagePeriod

logger = logging.getLogger(__name__)


def _upsert_usage_and_cost(
    target_date: date,
    usage_records: list[dict],
    cost_records: list[dict],
) -> dict[str, int]:
    """Shared upsert logic for sync and backfill tasks."""
    cost_lookup: dict[str, Decimal] = {}
    for c in cost_records:
        key = c["date"]
        cost_lookup[key] = cost_lookup.get(key, Decimal("0")) + c["cost_usd"]

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

    # Apply cost data with row locking
    total_cost = sum(cost_lookup.values(), Decimal("0"))
    if total_cost:
        with transaction.atomic():
            day_records = list(
                UsagePeriod.objects.select_for_update()
                .filter(date=target_date)
                .order_by("model")
            )
            count = len(day_records)
            if count:
                per_model = total_cost / count
                for rec in day_records:
                    rec.cost_usd = per_model
                    rec.save(update_fields=["cost_usd"])

    return {"created": created, "updated": updated}


@shared_task
def sync_anthropic_usage() -> dict[str, int]:
    """Fetch current day's usage and cost data, upsert into UsagePeriod."""
    today = date.today()
    usage_records = fetch_usage_report(today, today)
    cost_records = fetch_cost_report(today, today)
    result = _upsert_usage_and_cost(today, usage_records, cost_records)
    logger.info("Spend sync: %d created, %d updated for %s", result["created"], result["updated"], today)
    return result


@shared_task
def daily_usage_backfill() -> dict[str, int]:
    """Backfill yesterday's complete data."""
    yesterday = date.today() - timedelta(days=1)
    usage_records = fetch_usage_report(yesterday, yesterday)
    cost_records = fetch_cost_report(yesterday, yesterday)
    result = _upsert_usage_and_cost(yesterday, usage_records, cost_records)
    logger.info("Backfill: %d created, %d updated for %s", result["created"], result["updated"], yesterday)
    return result


@shared_task
def check_budget_alerts() -> bool:
    """Check if current month spend exceeds budget threshold."""
    now = timezone.now()
    first_of_month = now.date().replace(day=1)

    with transaction.atomic():
        budget = (
            SpendBudget.objects.select_for_update()
            .filter(month=first_of_month)
            .first()
        )
        if not budget:
            return False

        if budget.alert_sent:
            return False

        if budget.budget_usd <= 0:
            return False

        mtd_spend = (
            UsagePeriod.objects.filter(date__gte=first_of_month)
            .aggregate(total=Sum("cost_usd"))["total"]
        ) or Decimal("0")

        pct = (mtd_spend / budget.budget_usd) * 100
        if pct >= budget.alert_threshold_pct:
            budget.alert_sent = True
            budget.save(update_fields=["alert_sent"])
            logger.warning(
                "Budget alert: MTD spend $%s is %d%% of $%s budget",
                mtd_spend, int(pct), budget.budget_usd,
            )

            # Fire notification
            try:
                from notifications.notifier import trigger_event
                trigger_event("budget_threshold", {
                    "title": "Budget Alert",
                    "message": f"MTD spend ${mtd_spend} is {int(pct)}% of ${budget.budget_usd} budget",
                })
            except (ImportError, requests.RequestException, OSError) as exc:
                logger.warning("Budget notification dispatch failed: %s", exc)

            return True

    return False
