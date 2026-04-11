"""Web Push notification helpers."""

import json
import logging

from django.conf import settings
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


def send_push_notification(user: User, title: str, body: str, url: str = "/remote/") -> int:
    """Send a Web Push notification to all of a user's subscriptions.

    Returns count of successful sends. Falls back to Slack if no
    push subscriptions exist and pywebpush is not installed.
    """
    from .models import PushSubscription

    subscriptions = PushSubscription.objects.filter(user=user)
    if not subscriptions.exists():
        _fallback_slack(title, body)
        return 0

    vapid_public = getattr(settings, "VAPID_PUBLIC_KEY", "")
    vapid_private = getattr(settings, "VAPID_PRIVATE_KEY", "")
    vapid_email = getattr(settings, "VAPID_CLAIMS_EMAIL", "")

    if not vapid_public or not vapid_private:
        logger.warning("VAPID keys not configured, falling back to Slack")
        _fallback_slack(title, body)
        return 0

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.warning("pywebpush not installed, falling back to Slack")
        _fallback_slack(title, body)
        return 0

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
    })

    sent = 0
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {
                        "p256dh": sub.p256dh,
                        "auth": sub.auth,
                    },
                },
                data=payload,
                vapid_private_key=vapid_private,
                vapid_claims={"sub": vapid_email},
            )
            sent += 1
        except WebPushException as e:
            logger.warning("Push failed for subscription %s: %s", sub.pk, e)
            if "410" in str(e) or "404" in str(e):
                sub.delete()
                logger.info("Removed expired push subscription %s", sub.pk)

    return sent


def notify_command_completed(user: User, command_type: str, result: str) -> None:
    """Notify user that a command completed."""
    send_push_notification(
        user,
        title=f"Command completed: {command_type}",
        body=result[:100] if result else "Done",
    )


def notify_command_failed(user: User, command_type: str, error: str) -> None:
    """Notify user that a command failed."""
    send_push_notification(
        user,
        title=f"Command failed: {command_type}",
        body=error[:100] if error else "Unknown error",
    )


def notify_agent_offline(user: User, agent_name: str) -> None:
    """Notify user that an agent went offline."""
    send_push_notification(
        user,
        title="Agent disconnected",
        body=f"{agent_name} went offline",
    )


def _fallback_slack(title: str, body: str) -> None:
    """Fall back to Slack notification if push is unavailable."""
    slack_url = getattr(settings, "SLACK_WEBHOOK_URL", "")
    if not slack_url:
        return

    try:
        import requests

        requests.post(
            slack_url,
            json={"text": f"*{title}*\n{body}"},
            timeout=5,
        )
    except Exception:
        logger.exception("Slack fallback notification failed")
