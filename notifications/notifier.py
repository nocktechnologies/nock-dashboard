"""Notification dispatch — sends alerts to Slack, Discord, and generic webhooks."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .models import NotificationChannel, NotificationLog, NotificationRule

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds


def _mask_url(url: str) -> str:
    """Mask webhook URL for logging — show scheme + host only."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.hostname}/****"


def format_slack_message(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    """Format notification as Slack Block Kit payload."""
    title = data.get("title", event_type.replace("_", " ").title())
    message = data.get("message", "")
    fields = []
    for key, value in data.items():
        if key not in ("title", "message"):
            fields.append({"type": "mrkdwn", "text": f"*{key}:* {value}"})

    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": f"NockCC: {title}"}},
    ]
    if message:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": message}})
    if fields:
        blocks.append({"type": "section", "fields": fields[:10]})

    return {"blocks": blocks}


def format_discord_message(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    """Format notification as Discord embed payload."""
    title = data.get("title", event_type.replace("_", " ").title())
    message = data.get("message", "")
    fields = [
        {"name": key, "value": str(value), "inline": True}
        for key, value in data.items()
        if key not in ("title", "message")
    ]

    color_map = {
        "ci_failed": 0xFF0000,
        "budget_threshold": 0xFF8C00,
        "pr_merged": 0x800080,
        "pr_opened": 0x00FF00,
        "context_stale": 0xFFFF00,
    }

    return {
        "embeds": [{
            "title": f"NockCC: {title}",
            "description": message,
            "color": color_map.get(event_type, 0x0EA5E9),
            "fields": fields[:25],
        }],
    }


def send_notification(
    channel: NotificationChannel,
    event_type: str,
    data: dict[str, Any],
    rule: NotificationRule | None = None,
) -> bool:
    """Send a notification to a channel with retry logic.

    Returns True if delivery succeeded.
    """
    if channel.channel_type == "slack":
        payload = format_slack_message(event_type, data)
    elif channel.channel_type == "discord":
        payload = format_discord_message(event_type, data)
    else:
        payload = {"event": event_type, "data": data}

    masked_url = _mask_url(channel.webhook_url)
    last_error = ""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(channel.webhook_url, json=payload, timeout=10)
            resp.raise_for_status()

            NotificationLog.objects.create(
                rule=rule,
                channel=channel,
                event_type=event_type,
                payload=data,
                success=True,
            )
            logger.info("Notification sent: %s → %s", event_type, masked_url)
            return True

        except requests.RequestException as exc:
            last_error = str(exc)
            logger.warning(
                "Notification attempt %d/%d failed for %s → %s: %s",
                attempt, MAX_RETRIES, event_type, masked_url, last_error,
            )
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE ** attempt)

    # All retries exhausted
    NotificationLog.objects.create(
        rule=rule,
        channel=channel,
        event_type=event_type,
        payload=data,
        success=False,
        error_message=last_error,
    )
    logger.warning("Notification failed after %d attempts: %s → %s", MAX_RETRIES, event_type, masked_url)
    return False


def trigger_event(event_type: str, data: dict[str, Any]) -> int:
    """Find all active rules for an event type and send notifications.

    Returns number of notifications sent successfully.
    """
    rules = (
        NotificationRule.objects.filter(trigger_event=event_type, is_active=True)
        .select_related("channel")
        .order_by("pk")
    )
    sent = 0
    for rule in rules:
        if not rule.channel.is_active:
            continue
        if send_notification(rule.channel, event_type, data, rule=rule):
            sent += 1
    return sent
