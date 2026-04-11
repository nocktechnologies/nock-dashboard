"""Anthropic Usage & Cost API client for spend tracking."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.anthropic.com/v1/organizations"


def _api_key() -> str:
    return getattr(settings, "ANTHROPIC_ADMIN_API_KEY", "") or ""


def _headers() -> dict[str, str]:
    key = _api_key()
    return {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }


def fetch_usage_report(
    start_date: date, end_date: date, bucket_width: str = "1d"
) -> list[dict[str, Any]]:
    """Fetch usage data from Anthropic Messages Usage API.

    Returns list of dicts with: date, model, workspace, input_tokens,
    output_tokens, cache_read_tokens, cache_write_tokens, request_count.
    """
    if not _api_key():
        logger.warning("ANTHROPIC_ADMIN_API_KEY not set — skipping usage fetch")
        return []

    # Convert dates to ISO 8601 with midnight UTC
    start_ts = datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)
    end_ts = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC)

    params = {
        "starting_at": start_ts.isoformat(),
        "ending_at": end_ts.isoformat(),
        "bucket_width": bucket_width,
        "group_by[]": "model",
    }

    records: list[dict[str, Any]] = []
    try:
        resp = requests.get(
            f"{BASE_URL}/usage_report/messages",
            headers=_headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        for bucket in data.get("data", []):
            record_date = bucket.get("bucket_start_time", "")[:10]
            if not record_date:
                continue
            records.append({
                "date": record_date,
                "model": bucket.get("model", "unknown"),
                "workspace": bucket.get("workspace", ""),
                "input_tokens": bucket.get("input_tokens", 0),
                "output_tokens": bucket.get("output_tokens", 0),
                "cache_read_tokens": bucket.get("input_cached_tokens", 0),
                "cache_write_tokens": bucket.get("input_cache_write_tokens", 0),
                "request_count": bucket.get("request_count", 0),
            })
    except requests.RequestException as exc:
        logger.warning("Anthropic usage API error: %s", exc)
    return records


def fetch_cost_report(start_date: date, end_date: date) -> list[dict[str, Any]]:
    """Fetch cost data from Anthropic Cost API.

    Returns list of dicts with: date, description, cost_usd.
    """
    if not _api_key():
        logger.warning("ANTHROPIC_ADMIN_API_KEY not set — skipping cost fetch")
        return []

    start_ts = datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)
    end_ts = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC)

    params = {
        "starting_at": start_ts.isoformat(),
        "ending_at": end_ts.isoformat(),
        "group_by[]": "description",
        "bucket_width": "1d",
    }

    records: list[dict[str, Any]] = []
    try:
        resp = requests.get(
            f"{BASE_URL}/cost_report",
            headers=_headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        for bucket in data.get("data", []):
            record_date = bucket.get("bucket_start_time", "")[:10]
            if not record_date:
                continue
            records.append({
                "date": record_date,
                "description": bucket.get("description", ""),
                "cost_usd": Decimal(str(bucket.get("cost_usd", 0))),
            })
    except requests.RequestException as exc:
        logger.warning("Anthropic cost API error: %s", exc)
    return records
