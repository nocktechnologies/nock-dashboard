"""Executive dashboard data aggregation."""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_executive_data() -> dict:
    """Aggregate all four quadrants of the executive dashboard."""
    from context.models import ContextDocument
    from crm.models import Deal
    from pipeline.models import PullRequest
    from remote.models import AgentStatus, CommandRequest
    from sessions.models import AgentSession
    from spend.models import Expense, Revenue, SubscriptionTracker
    from tasks.models import AsanaTask
    from vault.models import Document

    from .models import PredictiveAlert

    now = timezone.now()
    today = now.date()
    first_of_month = today.replace(day=1)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    # Previous month for trend comparison
    if first_of_month.month == 1:
        prev_month_start = first_of_month.replace(year=first_of_month.year - 1, month=12)
    else:
        prev_month_start = first_of_month.replace(month=first_of_month.month - 1)
    prev_month_end = first_of_month - timedelta(days=1)

    # ──────────── Q1: Financial Health ────────────
    mtd_expenses = Expense.objects.filter(
        date__gte=first_of_month, is_refund=False,
    ).aggregate(total=Sum("total"))["total"] or Decimal("0")
    mtd_refunds = Expense.objects.filter(
        date__gte=first_of_month, is_refund=True,
    ).aggregate(total=Sum("total"))["total"] or Decimal("0")
    total_spend = Expense.objects.filter(
        is_refund=False,
    ).aggregate(total=Sum("total"))["total"] or Decimal("0")
    total_spend_refunds = Expense.objects.filter(
        is_refund=True,
    ).aggregate(total=Sum("total"))["total"] or Decimal("0")
    net_total_spend = total_spend - total_spend_refunds

    mtd_revenue = Revenue.objects.filter(
        date__gte=first_of_month,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    monthly_burn = SubscriptionTracker.objects.filter(
        is_active=True,
    ).aggregate(total=Sum("monthly_cost"))["total"] or Decimal("0")

    net_mtd = mtd_revenue - (mtd_expenses - mtd_refunds)

    # Trend: compare this month's net to last month
    prev_expenses = Expense.objects.filter(
        date__gte=prev_month_start, date__lte=prev_month_end, is_refund=False,
    ).aggregate(total=Sum("total"))["total"] or Decimal("0")
    prev_refunds = Expense.objects.filter(
        date__gte=prev_month_start, date__lte=prev_month_end, is_refund=True,
    ).aggregate(total=Sum("total"))["total"] or Decimal("0")
    prev_revenue = Revenue.objects.filter(
        date__gte=prev_month_start, date__lte=prev_month_end,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    prev_net = prev_revenue - (prev_expenses - prev_refunds)

    if prev_net != 0:
        financial_trend = "up" if net_mtd > prev_net else ("down" if net_mtd < prev_net else "flat")
    else:
        financial_trend = "up" if net_mtd > 0 else ("down" if net_mtd < 0 else "flat")

    # Runway: not computed until a cash/reserves data source exists
    runway_months = None

    financial = {
        "total_spend": str(net_total_spend),
        "monthly_burn": str(monthly_burn),
        "revenue_mtd": str(mtd_revenue),
        "net_position": str(net_mtd),
        "runway_months": runway_months,
        "trend": financial_trend,
    }

    # ──────────── Q2: Development Velocity ────────────
    prs_this_week = PullRequest.objects.filter(
        state="merged", merged_at__gte=week_ago,
    ).count()
    prs_last_week = PullRequest.objects.filter(
        state="merged",
        merged_at__gte=two_weeks_ago,
        merged_at__lt=week_ago,
    ).count()

    if prs_last_week > 0:
        pr_trend = "up" if prs_this_week > prs_last_week else (
            "down" if prs_this_week < prs_last_week else "flat"
        )
    else:
        pr_trend = "up" if prs_this_week > 0 else "flat"

    active_sessions = AgentSession.objects.filter(status="active").count()
    active_commands = CommandRequest.objects.filter(
        status__in=["queued", "sent", "running"],
    ).count()

    total_docs = ContextDocument.objects.filter(is_active=True).count()
    healthy_docs = ContextDocument.objects.filter(
        is_active=True, is_stale=False,
    ).count()

    development = {
        "prs_merged_this_week": prs_this_week,
        "pr_trend": pr_trend,
        "prs_merged_last_week": prs_last_week,
        "active_sessions": active_sessions,
        "active_commands": active_commands,
        "context_docs_total": total_docs,
        "context_docs_healthy": healthy_docs,
    }

    # ──────────── Q3: Operations ────────────
    overdue_count = AsanaTask.objects.filter(
        completed=False, due_on__lt=today, due_on__isnull=False,
    ).count()
    due_this_week = AsanaTask.objects.filter(
        completed=False,
        due_on__gte=today,
        due_on__lte=today + timedelta(days=7),
    ).count()
    stale_docs = ContextDocument.objects.filter(
        is_active=True,
        is_stale=True,
    ).count()
    agent_online = AgentStatus.objects.filter(is_online=True).exists()

    # Last daily digest
    from notifications.models import NotificationLog
    last_digest = NotificationLog.objects.filter(
        event_type="daily_digest", success=True,
    ).order_by("-sent_at").first()

    # Active alerts count
    active_alerts = PredictiveAlert.objects.filter(is_resolved=False).count()

    operations = {
        "overdue_tasks": overdue_count,
        "due_this_week": due_this_week,
        "stale_docs": stale_docs,
        "agent_online": agent_online,
        "last_digest": last_digest.sent_at.isoformat() if last_digest else None,
        "active_alerts": active_alerts,
    }

    # ──────────── Q4: Growth ────────────
    pipeline_value = Deal.objects.exclude(
        stage__in=["closed_won", "closed_lost"],
    ).aggregate(total=Sum("estimated_value"))["total"] or Decimal("0")

    deals_by_stage = list(
        Deal.objects.values("stage")
        .annotate(count=Count("pk"))
        .order_by("stage")
    )

    deals_needing_action = Deal.objects.filter(
        next_action_date__lte=today,
    ).exclude(
        stage__in=["closed_won", "closed_lost"],
    ).count()

    active_clients = Deal.objects.filter(stage="active").count()
    vault_count = Document.objects.count()

    growth = {
        "pipeline_value": str(pipeline_value),
        "deals_by_stage": deals_by_stage,
        "deals_needing_action": deals_needing_action,
        "active_clients": active_clients,
        "vault_documents": vault_count,
    }

    return {
        "financial": financial,
        "development": development,
        "operations": operations,
        "growth": growth,
        "generated_at": now.isoformat(),
    }
