import logging
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db import DatabaseError
from django.db.models import Case, IntegerField, Q, Sum, Value, When
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from core.auth import require_api_key
from pipeline.models import PREvent, PullRequest, Repository
from sessions.models import AgentSession, TerminalHeartbeat
from spend.models import Revenue, UsagePeriod

logger = logging.getLogger(__name__)


@require_GET
def healthz(request: HttpRequest) -> JsonResponse:
    """Unauthenticated health check for Railway deployment."""
    return JsonResponse({"status": "ok"})


@login_required
def index(request: HttpRequest) -> HttpResponse:
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    pr_qs = PullRequest.tenant_objects.for_request(request)
    open_prs = pr_qs.filter(state=PullRequest.State.OPEN).select_related("repository")
    merged_this_week = pr_qs.filter(
        state=PullRequest.State.MERGED, merged_at__gte=week_ago
    ).count()

    last_5_merged = (
        pr_qs.filter(state=PullRequest.State.MERGED)
        .select_related("repository")
        .order_by("-merged_at")[:5]
    )

    failed_ci_prs = (
        pr_qs.filter(
            state=PullRequest.State.OPEN, ci_status=PullRequest.CIStatus.FAILED
        )
        .select_related("repository")
        .order_by("-opened_at")
    )

    # Average merge time (open→merge) for last 30 days
    # Materialise to a list to avoid double DB query (exists() + count())
    avg_merge_hours = None
    merged_list = list(
        pr_qs.filter(
            state=PullRequest.State.MERGED,
            merged_at__gte=month_ago,
            opened_at__isnull=False,
        )
    )
    if merged_list:
        total_seconds = sum(
            (pr.merged_at - pr.opened_at).total_seconds()
            for pr in merged_list
            if pr.merged_at and pr.opened_at
        )
        count = len(merged_list)
        if count:
            avg_merge_hours = round(total_seconds / count / 3600, 1)

    # Latest webhook received
    latest_event = PREvent.tenant_objects.for_request(request).order_by("-created_at").first()

    overdue_count = 0
    due_today_count = 0
    upcoming_tasks = []
    try:
        from tasks.models import AsanaTask
        today = now.date()
        task_qs = AsanaTask.tenant_objects.for_request(request)
        overdue_count = task_qs.filter(
            completed=False, due_on__lt=today, due_on__isnull=False
        ).count()
        due_today_count = task_qs.filter(
            completed=False, due_on=today
        ).count()
        upcoming_tasks = (
            task_qs.filter(completed=False)
            .select_related("project")
            .annotate(
                priority_rank=Case(
                    When(priority="high", then=Value(3)),
                    When(priority="medium", then=Value(2)),
                    When(priority="low", then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            )
            .order_by("due_on", "-priority_rank", "name", "pk")[:5]
        )
    except (ImportError, ModuleNotFoundError):
        logger.warning("tasks app not available for dashboard widget")
    except DatabaseError as exc:
        logger.warning("Could not load upcoming tasks: %s", exc)

    context = {
        "open_pr_count": open_prs.count(),
        "merged_this_week": merged_this_week,
        "last_5_merged": last_5_merged,
        "failed_ci_prs": failed_ci_prs,
        "total_repos": Repository.tenant_objects.for_request(request).filter(is_active=True).count(),
        "total_prs": pr_qs.count(),
        "avg_merge_hours": avg_merge_hours,
        "latest_event": latest_event,
        "upcoming_tasks": upcoming_tasks,
        "overdue_count": overdue_count,
        "due_today_count": due_today_count,
    }
    return render(request, "dashboard/index.html", context)


@csrf_exempt
@require_api_key
def pipeline_status_api(request: HttpRequest) -> JsonResponse:
    """JSON API for Alpine.js polling — returns live counts."""
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    latest_event = PREvent.objects.order_by("-created_at").first()
    open_prs = PullRequest.objects.filter(state=PullRequest.State.OPEN).count()
    merged_this_week = PullRequest.objects.filter(
        state=PullRequest.State.MERGED, merged_at__gte=week_ago
    ).count()

    # Average merge time (hours) for last 30 days
    avg_review_time = 0
    merged_list = list(
        PullRequest.objects.filter(
            state=PullRequest.State.MERGED,
            merged_at__gte=month_ago,
            opened_at__isnull=False,
        )
    )
    if merged_list:
        total_seconds = sum(
            (pr.merged_at - pr.opened_at).total_seconds()
            for pr in merged_list
            if pr.merged_at and pr.opened_at
        )
        avg_review_time = round(total_seconds / len(merged_list) / 3600, 1)

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "open_pr_count": open_prs,
            "open_prs": open_prs,
            "failed_ci_count": PullRequest.objects.filter(
                state=PullRequest.State.OPEN, ci_status=PullRequest.CIStatus.FAILED
            ).count(),
            "merged_this_week": merged_this_week,
            "avg_review_time": avg_review_time,
            "latest_event_at": latest_event.created_at.isoformat() if latest_event else None,
        },
    })


@csrf_exempt
@require_api_key
def active_sessions_api(request: HttpRequest) -> JsonResponse:
    """JSON API for dashboard widget — returns truly-active sessions.

    A session is shown if it is active AND has activity within the last
    2 hours, OR a Terminal Bridge heartbeat arrived within the last 5 min.
    Capped at 5 results, most-recent first.
    """
    now = timezone.now()
    fresh_cutoff = now - timedelta(hours=2)
    heartbeat_cutoff = now - timedelta(minutes=5)

    # Machines with a recent Terminal heartbeat
    live_machines = set(
        TerminalHeartbeat.objects.filter(received_at__gte=heartbeat_cutoff)
        .values_list("machine", flat=True)
    )

    sessions = (
        AgentSession.objects.filter(
            Q(status="active", last_activity__gte=fresh_cutoff)
            | Q(status="active", machine__in=live_machines)
        )
        .select_related("repository")
        .order_by("-last_activity", "-pk")[:5]
    )
    data = [
        {
            "id": s.pk,
            "agent": s.agent,
            "agent_display": s.get_agent_display(),
            "machine": s.machine,
            "machine_display": s.get_machine_display(),
            "status": s.status,
            "branch": s.branch,
            "started_at": s.started_at.isoformat(),
            "last_activity": s.last_activity.isoformat(),
        }
        for s in sessions
    ]
    return JsonResponse({"success": True, "message": "ok", "data": data})


@csrf_exempt
@require_GET
@require_api_key
def dashboard_summary_api(request: HttpRequest) -> JsonResponse:
    """JSON API for CLI — returns aggregated dashboard stats."""
    now = timezone.now()
    week_ago = now - timedelta(days=7)

    open_prs = PullRequest.objects.filter(state=PullRequest.State.OPEN).count()
    failed_ci = PullRequest.objects.filter(
        state=PullRequest.State.OPEN, ci_status=PullRequest.CIStatus.FAILED
    ).count()
    merged_this_week = PullRequest.objects.filter(
        state=PullRequest.State.MERGED, merged_at__gte=week_ago
    ).count()
    active_sessions = AgentSession.objects.filter(status="active").count()

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "open_prs": open_prs,
            "failed_ci": failed_ci,
            "merged_this_week": merged_this_week,
            "active_sessions": active_sessions,
            "todays_spend": str(
                UsagePeriod.objects.filter(date=now.date())
                .aggregate(total=Sum("cost_usd"))["total"] or Decimal("0")
            ),
        },
    })


@csrf_exempt
@require_GET
@require_api_key
def executive_dashboard_api(request: HttpRequest) -> JsonResponse:
    """JSON API for mobile app — aggregated executive dashboard."""
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    first_of_month = now.date().replace(day=1)

    # --- Financial Health ---
    mtd_spend = (
        UsagePeriod.objects.filter(date__gte=first_of_month)
        .aggregate(total=Sum("cost_usd"))["total"]
    ) or Decimal("0")

    from spend.models import Expense, SubscriptionTracker

    subs_total = (
        SubscriptionTracker.objects.filter(is_active=True)
        .aggregate(total=Sum("monthly_cost"))["total"]
    ) or Decimal("0")

    expense_total = (
        Expense.objects.filter(is_refund=False)
        .aggregate(total=Sum("total"))["total"]
    ) or Decimal("0")
    expense_refunds = (
        Expense.objects.filter(is_refund=True)
        .aggregate(total=Sum("total"))["total"]
    ) or Decimal("0")
    net_expenses = expense_total - expense_refunds

    total_revenue = (
        Revenue.objects.aggregate(total=Sum("amount"))["total"]
    ) or Decimal("0")

    total_spend = float(net_expenses) + float(mtd_spend)
    burn_rate = float(subs_total) + float(mtd_spend)
    net_position = float(total_revenue) - total_spend
    runway_months = (float(total_revenue) / burn_rate) if burn_rate > 0 else 99.0

    # --- Development ---
    merged_this_week = PullRequest.objects.filter(
        state=PullRequest.State.MERGED, merged_at__gte=week_ago
    ).count()
    open_prs = PullRequest.objects.filter(state=PullRequest.State.OPEN).count()
    active_sessions = AgentSession.objects.filter(status="active").count()

    # --- Operations ---
    overdue_tasks = 0
    due_this_week = 0
    try:
        from tasks.models import AsanaTask
        today = now.date()
        week_end = today + timedelta(days=7)
        overdue_tasks = AsanaTask.objects.filter(
            completed=False, due_on__lt=today, due_on__isnull=False
        ).count()
        due_this_week = AsanaTask.objects.filter(
            completed=False, due_on__gte=today, due_on__lte=week_end
        ).count()
    except (ImportError, DatabaseError):
        pass

    agent_status = "online" if active_sessions > 0 else "offline"

    # --- Growth ---
    from crm.models import Deal
    open_deals = Deal.objects.filter(~Q(stage__in=["closed_won", "closed_lost"]))
    pipeline_value = float(
        open_deals.aggregate(total=Sum("estimated_value"))["total"] or Decimal("0")
    )
    deals_by_stage = {}
    for key, label in Deal.STAGES:
        count = Deal.objects.filter(stage=key).count()
        if count > 0:
            deals_by_stage[label] = count

    today_date = now.date()
    week_end_date = today_date + timedelta(days=7)
    deals_needing_action = open_deals.filter(
        next_action_date__lte=week_end_date, next_action_date__isnull=False
    ).count()

    # --- Terminal Status ---
    terminal_data = [
        {
            "machine": hb.machine,
            "sessions": hb.sessions,
            "active_ports": hb.active_ports,
            "is_stale": hb.is_stale,
            "session_count": hb.session_count,
            "received_at": hb.received_at.isoformat(),
        }
        for hb in TerminalHeartbeat.objects.order_by("-received_at")
    ]

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "financial_health": {
                "total_spend": total_spend,
                "burn_rate": burn_rate,
                "revenue": float(total_revenue),
                "net_position": net_position,
                "runway_months": round(runway_months, 1),
            },
            "development": {
                "prs_this_week": merged_this_week,
                "velocity": merged_this_week + open_prs,
                "active_sessions": active_sessions,
                "tests_passing": 100,
                "context_health": 85,
            },
            "operations": {
                "overdue_tasks": overdue_tasks,
                "due_this_week": due_this_week,
                "stale_docs": 0,
                "agent_status": agent_status,
            },
            "growth": {
                "pipeline_value": pipeline_value,
                "deals_by_stage": deals_by_stage,
                "deals_needing_action": deals_needing_action,
            },
            "terminal": terminal_data,
        },
    })


# ---------------------------------------------------------------------------
# PM plugin dashboard — frontend views for the projects/ app
# ---------------------------------------------------------------------------
# These views live in dashboard/ (not inside the projects/ plugin) because the
# plugin is designed to be standalone-reusable — adding NockCC-specific
# templates to the plugin package would break that invariant. The views here
# import the plugin's models directly and render NockCC-themed templates that
# progressively enhance with Alpine.js by hitting the plugin's REST API at
# /api/pm/api/...


@login_required
def pm_dashboard(request: HttpRequest) -> HttpResponse:
    """Project management home — list of all projects with task counts.

    The initial payload is server-rendered so the page is useful even before
    Alpine.js mounts; Alpine then progressively enhances it with create-project
    and refresh actions.
    """
    from django.db.models import Count, Q  # noqa: PLC0415 — avoid module-time import churn

    from projects.models import Project, Task  # noqa: PLC0415

    today = timezone.localdate()
    projects = list(
        Project.objects.filter(is_active=True, is_archived=False)
        .annotate(
            task_count=Count("tasks", distinct=True),
            incomplete_count=Count(
                "tasks", filter=Q(tasks__completed=False), distinct=True,
            ),
            overdue_count=Count(
                "tasks",
                filter=Q(
                    tasks__completed=False,
                    tasks__due_date__lt=today,
                    tasks__due_date__isnull=False,
                ),
                distinct=True,
            ),
        )
        .order_by("name")
    )

    total_tasks = Task.objects.count()
    incomplete_tasks = Task.objects.filter(completed=False).count()
    overdue_tasks = Task.objects.filter(
        completed=False, due_date__lt=today, due_date__isnull=False,
    ).count()

    return render(request, "dashboard/pm_projects.html", {
        "projects": projects,
        "total_projects": len(projects),
        "total_tasks": total_tasks,
        "incomplete_tasks": incomplete_tasks,
        "overdue_tasks": overdue_tasks,
    })


@login_required
def pm_tasks_all(request: HttpRequest) -> HttpResponse:
    """Cross-project Tasks dashboard — every open task across every project.

    Server-renders a lightweight skeleton (project list for the filter dropdown)
    and then Alpine fetches the live task list from the PM plugin's REST API.
    Filters are client-side for responsiveness; the initial payload uses
    `/api/pm/api/tasks/?ordering=-priority&completed=false`.
    """
    from projects.models import Project  # noqa: PLC0415

    projects = list(
        Project.objects.filter(is_active=True, is_archived=False)
        .order_by("name")
        .values("slug", "name")
    )
    return render(request, "dashboard/pm_tasks_all.html", {
        "projects_for_filter": projects,
    })


@login_required
def pm_project_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """Project detail — sections + tasks with basic CRUD via Alpine.js.

    The page loads a minimal server-rendered skeleton and then Alpine fetches
    the full project payload from /api/pm/api/projects/<slug>/ on init to get
    the live task list. Create/complete/move actions go through the plugin's
    write endpoints (same auth chain, including X-API-Key and the dashboard's
    session cookie via SessionAuthentication + CSRF).
    """
    from django.http import Http404  # noqa: PLC0415

    from projects.models import Project  # noqa: PLC0415

    try:
        project = Project.objects.get(slug=slug, is_active=True, is_archived=False)
    except Project.DoesNotExist as exc:
        raise Http404("Project not found") from exc

    return render(request, "dashboard/pm_project_detail.html", {
        "project": project,
    })
