"""Celery tasks for notifications — daily digest and scheduled alerts."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from celery import shared_task
from django.conf import settings
from django.db import DatabaseError
from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def send_daily_digest() -> dict:
    """Send daily digest to Slack — morning summary of all systems."""
    from context.models import ContextDocument
    from notifications.models import NotificationChannel
    from pipeline.models import PullRequest
    from remote.models import AgentStatus
    from sessions.models import AgentSession
    from spend.models import SubscriptionTracker, UsagePeriod
    from tasks.models import AsanaTask

    now = timezone.now()
    today = now.date()
    yesterday = today - timedelta(days=1)
    first_of_month = today.replace(day=1)
    week_ahead = today + timedelta(days=7)

    sections = []

    # --- Pipeline ---
    merged_yesterday = PullRequest.objects.filter(
        state=PullRequest.State.MERGED,
        merged_at__date=yesterday,
    ).count()
    open_prs = PullRequest.objects.filter(state=PullRequest.State.OPEN).count()
    failed_ci = PullRequest.objects.filter(
        state=PullRequest.State.OPEN, ci_status=PullRequest.CIStatus.FAILED
    ).count()
    pipeline_parts = [f"Merged yesterday: {merged_yesterday}", f"Open PRs: {open_prs}"]
    if failed_ci:
        pipeline_parts.append(f"Failed CI: {failed_ci}")
    sections.append(("Pipeline", "\n".join(pipeline_parts)))

    # --- Sessions ---
    sessions_yesterday = AgentSession.objects.filter(
        started_at__date=yesterday,
    ).count()
    sections.append(("Sessions", f"Sessions logged yesterday: {sessions_yesterday}"))

    # --- Tasks ---
    overdue_tasks = AsanaTask.objects.filter(
        completed=False,
        due_on__lt=today,
        due_on__isnull=False,
    ).order_by("due_on")
    overdue_count = overdue_tasks.count()
    due_today = AsanaTask.objects.filter(
        completed=False, due_on=today,
    ).count()
    task_lines = [f"Overdue: {overdue_count}", f"Due today: {due_today}"]
    if overdue_count > 0:
        top_overdue = overdue_tasks[:3]
        for t in top_overdue:
            task_lines.append(f"  - {t.name} (due {t.due_on})")
    sections.append(("Tasks", "\n".join(task_lines)))

    # --- Context ---
    stale_threshold = now - timedelta(days=7)
    stale_docs = ContextDocument.objects.filter(
        last_synced__lt=stale_threshold,
    ).count()
    sections.append(("Context", f"Stale documents (>7 days): {stale_docs}"))

    # --- Spend ---
    yesterday_spend = (
        UsagePeriod.objects.filter(date=yesterday)
        .aggregate(total=Sum("cost_usd"))["total"]
    ) or Decimal("0")
    mtd_spend = (
        UsagePeriod.objects.filter(date__gte=first_of_month)
        .aggregate(total=Sum("cost_usd"))["total"]
    ) or Decimal("0")
    renewals_soon = SubscriptionTracker.objects.filter(
        is_active=True,
        renewal_date__lte=week_ahead,
        renewal_date__gte=today,
    ).count()
    spend_lines = [
        f"Yesterday API spend: ${yesterday_spend:.2f}",
        f"MTD spend: ${mtd_spend:.2f}",
    ]
    if renewals_soon:
        spend_lines.append(f"Renewals in next 7 days: {renewals_soon}")
    sections.append(("Spend", "\n".join(spend_lines)))

    # --- Agent ---
    agent_online = AgentStatus.objects.filter(is_online=True).exists()
    agent_status = "Online" if agent_online else "Offline"
    sections.append(("Agent", f"Mac agent: {agent_status}"))

    # Build raw data for AI enhancement
    raw_data = ""
    for title, content in sections:
        raw_data += f"## {title}\n{content}\n\n"

    # Try AI-enhanced digest
    message = _generate_ai_digest(raw_data, today)
    if not message:
        # Fallback to static format
        message = f"*NockCC Daily Digest — {today.strftime('%A, %B %d')}*\n\n"
        emoji_map = {
            "Pipeline": ":rocket:",
            "Sessions": ":robot_face:",
            "Tasks": ":clipboard:",
            "Context": ":books:",
            "Spend": ":moneybag:",
            "Agent": ":computer:",
        }
        for title, content in sections:
            emoji = emoji_map.get(title, ":bell:")
            message += f"{emoji} *{title}*\n{content}\n\n"

    # Append active predictive alerts
    try:
        from django.db.models import Case, IntegerField, Value, When

        from intelligence.models import PredictiveAlert
        active_alerts = PredictiveAlert.objects.filter(
            is_resolved=False,
        ).annotate(
            severity_rank=Case(
                When(severity="critical", then=Value(3)),
                When(severity="warning", then=Value(2)),
                When(severity="info", then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            ),
        ).order_by("-severity_rank", "-created_at", "-pk")
        if active_alerts.exists():
            message += "\n:warning: *Active Alerts*\n"
            for alert in active_alerts[:5]:
                message += f"  [{alert.severity.upper()}] {alert.title}\n"
    except (ImportError, DatabaseError):
        pass

    # Send to Slack
    sent = False
    slack_url = getattr(settings, "SLACK_WEBHOOK_URL", "")
    if slack_url:
        import requests as http_requests
        try:
            resp = http_requests.post(slack_url, json={"text": message}, timeout=10)
            resp.raise_for_status()
            logger.info("Daily digest sent to Slack")
            sent = True
        except http_requests.RequestException as exc:
            logger.warning("Daily digest Slack delivery failed: %s", exc)
    else:
        # Try notification channels
        channels = NotificationChannel.objects.filter(
            channel_type="slack", is_active=True,
        ).order_by("pk")
        if channels.exists():
            from notifications.notifier import send_notification
            for channel in channels:
                send_notification(
                    channel, "daily_digest",
                    {"title": "Daily Digest", "message": message},
                )
            sent = True

    return {"sent": sent, "date": str(today)}


def _generate_ai_digest(raw_data: str, today: date) -> str | None:
    """Generate AI-enhanced daily digest. Returns None if AI unavailable."""
    try:
        from intelligence import ai_client
    except ImportError:
        logger.info("Intelligence module not available for AI digest")
        return None

    prompt = (
        "Given today's business data for Nock Technologies, write a 5-10 line "
        "morning briefing for the founder. Be specific with numbers. Highlight "
        "anything that needs attention today. Keep it crisp — this is read on a "
        "phone over coffee.\n\n"
        f"Data:\n{raw_data}"
    )

    result = ai_client.chat(
        messages=[{"role": "user", "content": prompt}],
        system=(
            "You are a concise business briefing writer. Output Slack-formatted "
            "text (use *bold* for emphasis). No headers or sections — just a "
            "natural paragraph-style briefing."
        ),
        max_tokens=1024,
    )

    if result is None:
        return None

    header = f"*NockCC Morning Briefing — {today.strftime('%A, %B %d')}*\n\n"
    return header + result["content"]
