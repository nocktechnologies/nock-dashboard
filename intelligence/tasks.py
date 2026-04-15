"""Celery tasks for the Intelligence layer."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from celery import shared_task
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def generate_business_snapshot() -> dict:
    """Generate daily business snapshot — runs at 6 AM CST (12 PM UTC)."""
    from .models import BusinessSnapshot
    from .snapshot import generate_snapshot_content

    today = timezone.now().date()
    content = generate_snapshot_content()

    # Rough token estimate: ~4 chars per token
    token_count = len(content) // 4

    snapshot, created = BusinessSnapshot.objects.update_or_create(
        date=today,
        defaults={
            "content": content,
            "token_count": token_count,
        },
    )

    # Clean up old snapshots (keep 30 days)
    cutoff = today - timedelta(days=30)
    deleted, _ = BusinessSnapshot.objects.filter(date__lt=cutoff).delete()
    if deleted:
        logger.info("Cleaned up %d old snapshots", deleted)

    return {
        "date": str(today),
        "created": created,
        "token_count": token_count,
    }


@shared_task
def generate_weekly_memo() -> dict:
    """Generate weekly strategy memo — runs Sunday midnight UTC.

    Idempotent: only creates one memo per (week_start, week_end) pair.
    """
    from .models import WeeklyMemo

    now = timezone.now()
    today = now.date()
    week_ago = today - timedelta(days=7)

    # Check if memo already exists for this week
    existing = WeeklyMemo.objects.filter(
        week_start=week_ago, week_end=today,
    ).first()
    if existing:
        logger.info("Weekly memo already exists for %s–%s", week_ago, today)
        return {"memo_id": existing.pk, "tokens": existing.tokens_used, "cost": str(existing.cost)}

    # Gather data
    data_package = _gather_weekly_data(week_ago, today)

    from . import ai_client

    system_prompt = (
        "You are an executive assistant generating a weekly strategy memo "
        "from the user's business data.\n\n"
        "Your memo should be:\n"
        "- Concise and actionable (not a wall of text)\n"
        "- Structured with clear sections\n"
        "- Focused on what matters and what needs attention\n"
        "- Written in a direct, professional tone\n\n"
        "Sections:\n"
        "1. WEEK IN REVIEW — 3-5 bullet summary of what was accomplished\n"
        "2. FINANCIAL SNAPSHOT — Spend, revenue, burn rate, notable expenses\n"
        "3. PIPELINE UPDATE — Deal movements, follow-ups needed\n"
        "4. DEVELOPMENT PROGRESS — PRs, sessions, velocity trends\n"
        "5. ATTENTION REQUIRED — Overdue tasks, stale docs, deals needing action, risks\n"
        "6. PRIORITIES FOR NEXT WEEK — Top 3-5 recommended priorities based on the data\n\n"
        "Be specific. Use real numbers from the data. Flag anything concerning."
    )

    result = ai_client.chat(
        messages=[{"role": "user", "content": data_package}],
        system=system_prompt,
        max_tokens=4096,
    )

    if result is None:
        logger.error("Weekly memo generation failed — API unavailable")
        return {"error": "API unavailable"}

    memo_content = result["content"]
    total_tokens = result["input_tokens"] + result["output_tokens"]
    cost = result["cost"]

    # Save memo record (idempotent via unique constraint)
    try:
        memo = WeeklyMemo.objects.create(
            week_start=week_ago,
            week_end=today,
            content=memo_content,
            tokens_used=total_tokens,
            cost=cost,
        )
    except IntegrityError:
        # Race condition: another process created the memo
        memo = WeeklyMemo.objects.get(week_start=week_ago, week_end=today)
        return {"memo_id": memo.pk, "tokens": memo.tokens_used, "cost": str(memo.cost)}

    # Save to vault
    _save_memo_to_vault(memo, today)

    # Send to Slack
    _send_memo_to_slack(memo_content, today)

    return {
        "memo_id": memo.pk,
        "tokens": total_tokens,
        "cost": str(cost),
    }


def _gather_weekly_data(week_start: date, week_end: date) -> str:
    """Gather all data for the weekly memo."""
    from crm.models import Deal
    from pipeline.models import PullRequest
    from sessions.models import AgentSession
    from spend.models import Expense, Revenue, SubscriptionTracker, UsagePeriod
    from tasks.models import AsanaTask

    from .models import PredictiveAlert

    today = week_end
    lines = [f"# Weekly Data Report: {week_start} to {week_end}\n"]

    # PRs
    merged_prs = (
        PullRequest.objects.filter(
            state="merged",
            merged_at__date__gte=week_start,
            merged_at__date__lte=week_end,
        )
        .select_related("repository")
        .order_by("-merged_at")
    )
    lines.append(f"## PRs Merged This Week: {merged_prs.count()}")
    for pr in merged_prs:
        repo = pr.repository.name if pr.repository else "unknown"
        lines.append(f"- #{pr.number} {pr.title} ({repo})")

    # Sessions
    sessions = AgentSession.objects.filter(
        started_at__date__gte=week_start,
        started_at__date__lte=week_end,
    )
    lines.append(f"\n## Sessions Logged: {sessions.count()}")
    total_cost = sessions.aggregate(total=Sum("estimated_cost"))["total"] or Decimal("0")
    lines.append(f"- Total estimated cost: ${total_cost:.2f}")

    # Expenses
    expenses = Expense.objects.filter(
        date__gte=week_start, date__lte=week_end, is_refund=False,
    )
    expense_total = expenses.aggregate(total=Sum("total"))["total"] or Decimal("0")
    lines.append(f"\n## Expenses This Week: {expenses.count()} totaling ${expense_total:.2f}")
    for e in expenses.order_by("-total")[:5]:
        lines.append(f"- {e.vendor}: ${e.total:.2f} ({e.category})")

    # Revenue
    revenue = Revenue.objects.filter(date__gte=week_start, date__lte=week_end)
    rev_total = revenue.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    lines.append(f"\n## Revenue This Week: {revenue.count()} totaling ${rev_total:.2f}")
    for r in revenue:
        lines.append(f"- {r.source}: ${r.amount:.2f} — {r.description[:80]}")

    # CRM
    lines.append("\n## CRM Deal Status")
    deals = Deal.objects.select_related("contact").order_by("stage", "-updated_at")
    for d in deals.exclude(stage__in=["closed_lost"]):
        val = d.display_value or Decimal("0")
        lines.append(f"- {d.title} [{d.stage}]: ${val:.2f}")

    deals_needing_action = deals.filter(
        next_action_date__lte=today,
    ).exclude(stage__in=["closed_won", "closed_lost"])
    if deals_needing_action.exists():
        lines.append("\n### Deals Needing Action")
        for d in deals_needing_action:
            lines.append(f"- {d.title}: {d.next_action} (due {d.next_action_date})")

    # Tasks
    overdue = AsanaTask.objects.filter(
        completed=False, due_on__lt=today, due_on__isnull=False,
    )
    completed = AsanaTask.objects.filter(
        completed=True, completed_at__date__gte=week_start,
    )
    lines.append(f"\n## Tasks: {overdue.count()} overdue, {completed.count()} completed this week")

    # API spend
    api_spend = UsagePeriod.objects.filter(
        date__gte=week_start, date__lte=week_end,
    ).aggregate(total=Sum("cost_usd"))["total"] or Decimal("0")
    lines.append(f"\n## API Spend This Week: ${api_spend:.4f}")

    # Subscription renewals next 7 days
    renewals = SubscriptionTracker.objects.filter(
        is_active=True,
        renewal_date__gte=today,
        renewal_date__lte=today + timedelta(days=7),
    )
    if renewals.exists():
        lines.append("\n## Upcoming Renewals")
        for s in renewals:
            lines.append(f"- {s.name}: ${s.monthly_cost:.2f} on {s.renewal_date}")

    # Active alerts
    active_alerts = PredictiveAlert.objects.filter(is_resolved=False)
    if active_alerts.exists():
        lines.append("\n## Active Alerts")
        for a in active_alerts:
            lines.append(f"- [{a.severity}] {a.title}: {a.message[:100]}")

    return "\n".join(lines)


def _save_memo_to_vault(memo, today: date) -> None:
    """Save the weekly memo as a Document in the vault with file content."""
    try:
        from django.core.files.base import ContentFile

        from vault.models import Document

        title = f"Weekly Strategy Memo — {today.strftime('%b %d, %Y')}"
        filename = f"weekly-memo-{today.isoformat()}.md"
        content_bytes = memo.content.encode("utf-8")

        doc = Document(
            title=title,
            category="reports",
            description="AI-generated weekly strategy memo",
            file_size=len(content_bytes),
            file_type="text/markdown",
            filename=filename,
        )
        doc.file.save(filename, ContentFile(content_bytes), save=False)
        doc.save()

        memo.vault_document = doc
        memo.save(update_fields=["vault_document"])
        logger.info("Weekly memo saved to vault as document %d", doc.pk)
    except (ImportError, ValueError) as exc:
        logger.warning("Could not save memo to vault: %s", exc)


def _send_memo_to_slack(content: str, today: date) -> None:
    """Send memo to Slack."""
    slack_url = getattr(settings, "SLACK_WEBHOOK_URL", "")
    if not slack_url:
        logger.info("No SLACK_WEBHOOK_URL — skipping memo Slack delivery")
        return

    import requests

    message = (
        f"*Weekly Strategy Memo — {today.strftime('%A, %B %d, %Y')}*\n\n"
        f"{content}"
    )
    # Truncate if too long for Slack (max ~4000 chars)
    if len(message) > 3900:
        message = message[:3900] + "\n\n_...truncated. Full memo in Vault._"

    try:
        resp = requests.post(slack_url, json={"text": message}, timeout=10)
        resp.raise_for_status()
        logger.info("Weekly memo sent to Slack")
    except requests.RequestException as exc:
        logger.warning("Weekly memo Slack delivery failed: %s", exc)


@shared_task
def check_predictive_alerts() -> dict:
    """Check all predictive alert conditions — runs every 6 hours."""
    alerts_created = 0

    alerts_created += _check_spend_velocity()
    alerts_created += _check_stale_deals()
    alerts_created += _check_overdue_escalation()
    alerts_created += _check_context_staleness()
    alerts_created += _check_subscription_renewals()
    alerts_created += _check_pr_velocity()
    alerts_created += _check_revenue_gap()

    return {"alerts_created": alerts_created}


def _check_spend_velocity() -> int:
    """Alert if projected API spend exceeds budget by >20%."""
    from spend.models import SpendBudget, UsagePeriod

    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    first_of_month = today.replace(day=1)

    # Get last 7 days API spend
    weekly_spend = UsagePeriod.objects.filter(
        date__gte=week_ago,
    ).aggregate(total=Sum("cost_usd"))["total"] or Decimal("0")

    if weekly_spend <= 0:
        return 0

    daily_rate = weekly_spend / Decimal("7")
    days_in_month = 30
    projected = daily_rate * Decimal(str(days_in_month))

    # Get budget
    budget = SpendBudget.objects.filter(month=first_of_month).first()
    if not budget:
        return 0

    threshold = budget.budget_usd * Decimal("1.2")
    if projected > threshold:
        pct_over = int(((projected - budget.budget_usd) / budget.budget_usd) * 100)
        title = f"API spend trending {pct_over}% over budget"
        message = (
            f"Anthropic API spend is trending at ${projected:.2f}/mo — "
            f"{pct_over}% over your ${budget.budget_usd:.2f} budget"
        )
        return _create_alert_if_new("spend", "critical", title, message)
    return 0


def _check_stale_deals() -> int:
    """Alert for deals stale >14 days."""
    from crm.models import Deal

    threshold = timezone.now() - timedelta(days=14)
    stale_deals = Deal.objects.filter(
        updated_at__lt=threshold,
    ).exclude(stage__in=["closed_won", "closed_lost"])

    count = 0
    for deal in stale_deals:
        days = (timezone.now() - deal.updated_at).days
        title = f"Stale deal: {deal.title}"
        message = (
            f"Deal '{deal.title}' has been in {deal.stage} for {days} days "
            f"with no updates"
        )
        count += _create_alert_if_new("pipeline", "warning", title, message)
    return count


def _check_overdue_escalation() -> int:
    """Alert for tasks overdue >7 days."""
    from tasks.models import AsanaTask

    today = timezone.now().date()
    threshold = today - timedelta(days=7)
    severely_overdue = AsanaTask.objects.filter(
        completed=False,
        due_on__lt=threshold,
        due_on__isnull=False,
    ).order_by("due_on")

    if not severely_overdue.exists():
        return 0

    count = severely_overdue.count()
    top_3 = ", ".join(t.name[:40] for t in severely_overdue[:3])
    title = f"{count} task(s) overdue by more than a week"
    message = f"You have {count} tasks overdue by more than a week — top 3: {top_3}"
    return _create_alert_if_new("tasks", "warning", title, message)


def _check_context_staleness() -> int:
    """Alert for context docs not updated in >14 days."""
    from context.models import ContextDocument

    threshold = timezone.now() - timedelta(days=14)
    # Use last_modified (the actual content freshness), not last_synced
    very_stale = ContextDocument.objects.filter(
        is_active=True,
        last_modified__isnull=False,
        last_modified__lt=threshold,
    ).select_related("repository")

    count = 0
    for doc in very_stale:
        days = doc.days_since_modified or 0
        repo_name = doc.repository.name if doc.repository else "unknown"
        title = f"Stale context: {doc.title}"
        message = (
            f"{doc.file_path} in {repo_name} hasn't been updated in "
            f"{days} days — may be stale"
        )
        count += _create_alert_if_new("context", "info", title, message)
    return count


def _check_subscription_renewals() -> int:
    """Alert for subscriptions renewing in next 7 days."""
    from spend.models import SubscriptionTracker

    today = timezone.now().date()
    upcoming = SubscriptionTracker.objects.filter(
        is_active=True,
        renewal_date__gte=today,
        renewal_date__lte=today + timedelta(days=7),
    )

    count = 0
    for sub in upcoming:
        title = f"Renewal: {sub.name}"
        message = (
            f"{sub.name} (${sub.monthly_cost:.2f}) renews on {sub.renewal_date} — "
            f"review before renewal?"
        )
        count += _create_alert_if_new("subscriptions", "info", title, message)
    return count


def _check_pr_velocity() -> int:
    """Alert if PR velocity is >50% below 4-week average."""
    from pipeline.models import PullRequest

    now = timezone.now()
    week_ago = now - timedelta(days=7)
    # 4 full weeks prior to this week
    four_weeks_before_this = week_ago - timedelta(days=28)

    this_week = PullRequest.objects.filter(
        state="merged", merged_at__gte=week_ago,
    ).count()

    # 4-week average (the 4 weeks before this week)
    prior_4_weeks = PullRequest.objects.filter(
        state="merged",
        merged_at__gte=four_weeks_before_this,
        merged_at__lt=week_ago,
    ).count()
    avg_weekly = prior_4_weeks / 4 if prior_4_weeks > 0 else 0

    if avg_weekly > 0 and this_week < avg_weekly * 0.5:
        pct_down = int(((avg_weekly - this_week) / avg_weekly) * 100)
        title = f"PR velocity down {pct_down}%"
        message = (
            f"PR velocity is down {pct_down}% this week — "
            f"{this_week} merged vs {avg_weekly:.0f} average"
        )
        return _create_alert_if_new("velocity", "warning", title, message)
    return 0


def _check_revenue_gap() -> int:
    """Alert if monthly expenses exceed revenue."""
    from spend.models import Expense, Revenue

    today = timezone.now().date()
    first_of_month = today.replace(day=1)

    mtd_expenses = Expense.objects.filter(
        date__gte=first_of_month, is_refund=False,
    ).aggregate(total=Sum("total"))["total"] or Decimal("0")
    mtd_refunds = Expense.objects.filter(
        date__gte=first_of_month, is_refund=True,
    ).aggregate(total=Sum("total"))["total"] or Decimal("0")
    net_expenses = mtd_expenses - mtd_refunds

    mtd_revenue = Revenue.objects.filter(
        date__gte=first_of_month,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    if net_expenses > mtd_revenue and net_expenses > 0:
        gap = net_expenses - mtd_revenue
        title = "Expenses exceed revenue"
        message = (
            f"Monthly burn (${net_expenses:.2f}) exceeds monthly revenue "
            f"(${mtd_revenue:.2f}) — gap of ${gap:.2f}"
        )
        return _create_alert_if_new("revenue", "warning", title, message)
    return 0


def _create_alert_if_new(
    category: str,
    severity: str,
    title: str,
    message: str,
) -> int:
    """Create an alert only if a similar unresolved alert doesn't exist.

    Uses atomic + IntegrityError catch for concurrency safety.
    Returns 1 if created, 0 if duplicate.
    """
    from .models import PredictiveAlert

    try:
        with transaction.atomic():
            PredictiveAlert.objects.create(
                category=category,
                severity=severity,
                title=title,
                message=message,
            )
    except IntegrityError:
        # Duplicate active alert — unique constraint prevents insertion
        return 0

    # Send critical alerts to Slack
    if severity == "critical":
        _send_alert_to_slack(severity, title, message)

    logger.info("Predictive alert created: [%s] %s", severity, title)
    return 1


# ──────────────── Smart Watch ────────────────


@shared_task
def smart_watch_tick() -> dict:
    """Evaluate all enabled Smart Watch rules — runs every 15 minutes."""
    from django.db.models import F

    from core.telegram import TelegramNotifier

    from .models import SmartWatchEvent, SmartWatchRule
    from .smart_watch import EVALUATORS

    rules = SmartWatchRule.objects.filter(enabled=True).order_by("pk")
    rules_evaluated = rules.count()
    total_alerts = 0

    for rule in rules:
        if rule.in_cooldown:
            continue

        evaluator = EVALUATORS.get(rule.condition_type)
        if not evaluator:
            continue

        try:
            alerts = evaluator(rule)
        except (KeyError, AttributeError, ValueError, TypeError) as exc:
            logger.error("Smart Watch evaluator error for %s: %s", rule.name, exc)
            continue

        if not alerts:
            continue

        pending_notifications: list[str] = []

        with transaction.atomic():
            locked_rule = SmartWatchRule.objects.select_for_update().get(pk=rule.pk)
            if locked_rule.in_cooldown:
                continue

            for message, context in alerts:
                SmartWatchEvent.objects.create(
                    rule=locked_rule,
                    message=message,
                    severity=locked_rule.severity,
                    context=context,
                    notified=True,
                )

                if locked_rule.send_telegram:
                    emoji = {"info": "\u2139\ufe0f", "warning": "\u26a0\ufe0f", "critical": "\U0001f6a8"}.get(
                        locked_rule.severity, "\u26a0\ufe0f",
                    )
                    pending_notifications.append(f"{emoji} {message}")

                total_alerts += 1

            SmartWatchRule.objects.filter(pk=locked_rule.pk).update(
                last_triggered=timezone.now(),
                trigger_count=F("trigger_count") + len(alerts),
            )

        # Send notifications outside the DB lock
        for notification_msg in pending_notifications:
            TelegramNotifier.send(notification_msg)

    logger.info("Smart Watch tick: %d rules evaluated, %d alerts fired", rules_evaluated, total_alerts)
    return {"rules_evaluated": rules_evaluated, "alerts_fired": total_alerts}


def _send_alert_to_slack(severity: str, title: str, message: str) -> None:
    """Send critical alert to Slack."""
    from notifications.notifier import trigger_event

    try:
        trigger_event("budget_threshold", {
            "title": f"[{severity.upper()}] {title}",
            "message": message,
        })
    except (ConnectionError, OSError) as exc:
        logger.warning("Alert Slack delivery failed: %s", exc)
