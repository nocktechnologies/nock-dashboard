"""Business snapshot generator — queries all NockCC data into a markdown summary."""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


def generate_snapshot_content() -> str:
    """Generate a comprehensive markdown summary of all business data.

    Returns a markdown string suitable for injection into AI system prompts.
    """
    from context.models import ContextDocument
    from crm.models import Deal
    from pipeline.models import PullRequest
    from remote.models import AgentStatus
    from sessions.models import AgentSession
    from spend.models import Expense, Revenue, SubscriptionTracker, UsagePeriod
    from tasks.models import AsanaTask
    from vault.models import Document

    now = timezone.now()
    today = now.date()
    first_of_month = today.replace(day=1)
    week_ago = today - timedelta(days=7)

    sections = []

    # ──────────────── FINANCIAL ────────────────
    # Expenses
    mtd_expenses = Expense.objects.filter(
        date__gte=first_of_month, is_refund=False,
    ).aggregate(total=Sum("total"))["total"] or Decimal("0")

    mtd_refunds = Expense.objects.filter(
        date__gte=first_of_month, is_refund=True,
    ).aggregate(total=Sum("total"))["total"] or Decimal("0")

    total_expenses_all = Expense.objects.filter(
        is_refund=False,
    ).aggregate(total=Sum("total"))["total"] or Decimal("0")

    total_refunds_all = Expense.objects.filter(
        is_refund=True,
    ).aggregate(total=Sum("total"))["total"] or Decimal("0")

    expense_by_category = list(
        Expense.objects.filter(date__gte=first_of_month, is_refund=False)
        .values("category")
        .annotate(total=Sum("total"))
        .order_by("-total")
    )

    # Revenue
    mtd_revenue = Revenue.objects.filter(
        date__gte=first_of_month,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    total_revenue_all = Revenue.objects.aggregate(
        total=Sum("amount"),
    )["total"] or Decimal("0")

    # API spend
    mtd_api_spend = UsagePeriod.objects.filter(
        date__gte=first_of_month,
    ).aggregate(total=Sum("cost_usd"))["total"] or Decimal("0")

    # Subscriptions
    active_subs = list(
        SubscriptionTracker.objects.filter(is_active=True).order_by("name")
    )
    monthly_burn = sum(s.monthly_cost for s in active_subs)

    upcoming_renewals = SubscriptionTracker.objects.filter(
        is_active=True,
        renewal_date__gte=today,
        renewal_date__lte=today + timedelta(days=7),
    ).order_by("renewal_date")

    fin_lines = [
        "## Financial Summary",
        f"- **Total spend to date:** ${total_expenses_all - total_refunds_all:.2f}",
        f"- **Total revenue to date:** ${total_revenue_all:.2f}",
        f"- **MTD expenses:** ${mtd_expenses:.2f} (refunds: ${mtd_refunds:.2f})",
        f"- **MTD revenue:** ${mtd_revenue:.2f}",
        f"- **Net position this month:** ${mtd_revenue - (mtd_expenses - mtd_refunds):.2f}",
        f"- **Monthly subscription burn:** ${monthly_burn:.2f}",
        f"- **MTD API spend:** ${mtd_api_spend:.4f}",
        "",
        "### Expenses by Category (this month)",
    ]
    for cat in expense_by_category:
        fin_lines.append(f"- {cat['category']}: ${cat['total']:.2f}")

    fin_lines.append("")
    fin_lines.append("### Active Subscriptions")
    for sub in active_subs:
        renewal = f" (renews {sub.renewal_date})" if sub.renewal_date else ""
        fin_lines.append(f"- {sub.name} ({sub.provider}): ${sub.monthly_cost:.2f}/mo{renewal}")

    if upcoming_renewals.exists():
        fin_lines.append("")
        fin_lines.append("### Renewals in Next 7 Days")
        for r in upcoming_renewals:
            fin_lines.append(f"- {r.name}: ${r.monthly_cost:.2f} on {r.renewal_date}")

    sections.append("\n".join(fin_lines))

    # ──────────────── CRM / PIPELINE ────────────────
    deals = Deal.objects.select_related("contact").order_by("stage", "-updated_at")
    pipeline_value = deals.exclude(
        stage__in=["closed_won", "closed_lost"],
    ).aggregate(total=Sum("estimated_value"))["total"] or Decimal("0")

    deal_by_stage = list(
        deals.values("stage")
        .annotate(count=Count("pk"), total=Sum("estimated_value"))
        .order_by("stage")
    )

    deals_needing_action = deals.filter(
        next_action_date__lte=today,
    ).exclude(stage__in=["closed_won", "closed_lost"])

    crm_lines = [
        "## CRM & Pipeline",
        f"- **Total pipeline value:** ${pipeline_value:.2f}",
        "",
        "### Deals by Stage",
    ]
    for s in deal_by_stage:
        val = s["total"] or Decimal("0")
        crm_lines.append(f"- {s['stage']}: {s['count']} deal(s), ${val:.2f}")

    crm_lines.append("")
    crm_lines.append("### All Open Deals")
    for d in deals.exclude(stage__in=["closed_won", "closed_lost"]):
        contact_name = d.contact.name if d.contact else "No contact"
        next_action = (
            f" — Next: {d.next_action} ({d.next_action_date})"
            if d.next_action else ""
        )
        crm_lines.append(
            f"- **{d.title}** [{d.stage}] — {contact_name}, "
            f"${d.display_value or 0:.2f}{next_action}"
        )

    if deals_needing_action.exists():
        crm_lines.append("")
        crm_lines.append("### Deals Needing Action Today")
        for d in deals_needing_action:
            crm_lines.append(
                f"- {d.title}: {d.next_action} (due {d.next_action_date})"
            )

    sections.append("\n".join(crm_lines))

    # ──────────────── DEVELOPMENT ────────────────
    prs_this_week = PullRequest.objects.filter(
        state="merged", merged_at__date__gte=week_ago,
    )
    prs_last_week = PullRequest.objects.filter(
        state="merged",
        merged_at__date__gte=week_ago - timedelta(days=7),
        merged_at__date__lt=week_ago,
    )
    open_prs = PullRequest.objects.filter(state="open").select_related("repository")
    active_sessions = AgentSession.objects.filter(status="active")

    recent_prs = (
        PullRequest.objects.filter(state="merged")
        .select_related("repository")
        .order_by("-merged_at")[:10]
    )

    dev_lines = [
        "## Development",
        f"- **PRs merged this week:** {prs_this_week.count()}",
        f"- **PRs merged last week:** {prs_last_week.count()}",
        f"- **Open PRs:** {open_prs.count()}",
        f"- **Active agent sessions:** {active_sessions.count()}",
        "",
        "### Recent Merged PRs",
    ]
    for pr in recent_prs:
        repo_name = pr.repository.name if pr.repository else "unknown"
        dev_lines.append(
            f"- #{pr.number} {pr.title} ({repo_name}) — merged {pr.merged_at.date() if pr.merged_at else 'N/A'}"
        )

    # Context doc health
    total_docs = ContextDocument.objects.filter(is_active=True).count()
    healthy_docs = ContextDocument.objects.filter(is_active=True, is_stale=False).count()
    stale_docs = ContextDocument.objects.filter(is_active=True, is_stale=True)

    dev_lines.append("")
    dev_lines.append(f"### Context Document Health: {healthy_docs}/{total_docs} healthy")
    for doc in stale_docs:
        days = doc.days_since_modified
        dev_lines.append(
            f"- STALE: {doc.title} ({doc.repository.name}/{doc.file_path}) — "
            f"{days} days since modified"
        )

    sections.append("\n".join(dev_lines))

    # ──────────────── OPERATIONS ────────────────
    overdue_tasks = AsanaTask.objects.filter(
        completed=False, due_on__lt=today, due_on__isnull=False,
    ).order_by("due_on")
    due_this_week = AsanaTask.objects.filter(
        completed=False,
        due_on__gte=today,
        due_on__lte=today + timedelta(days=7),
    ).order_by("due_on")
    completed_this_week = AsanaTask.objects.filter(
        completed=True,
        completed_at__date__gte=week_ago,
    ).count()

    agent_online = AgentStatus.objects.filter(is_online=True)

    ops_lines = [
        "## Operations",
        f"- **Overdue tasks:** {overdue_tasks.count()}",
        f"- **Tasks due this week:** {due_this_week.count()}",
        f"- **Tasks completed this week:** {completed_this_week}",
        f"- **Agent status:** {'Online' if agent_online.exists() else 'Offline'}",
        f"- **Documents in vault:** {Document.objects.count()}",
    ]

    if overdue_tasks.exists():
        ops_lines.append("")
        ops_lines.append("### Overdue Tasks")
        for t in overdue_tasks[:10]:
            days_over = (today - t.due_on).days
            ops_lines.append(
                f"- {t.name} (due {t.due_on}, {days_over} days overdue)"
            )

    if due_this_week.exists():
        ops_lines.append("")
        ops_lines.append("### Due This Week")
        for t in due_this_week[:10]:
            ops_lines.append(f"- {t.name} (due {t.due_on})")

    sections.append("\n".join(ops_lines))

    # ──────────────── ASSEMBLE ────────────────
    header = (
        f"# Nock Technologies Business Snapshot — {today.strftime('%B %d, %Y')}\n"
        f"Generated at {now.strftime('%I:%M %p %Z')}\n"
    )

    return header + "\n\n" + "\n\n".join(sections)
