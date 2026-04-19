import calendar as cal_module
import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db import DatabaseError
from django.db.models import Case, IntegerField, Q, Sum, Value, When
from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from core.auth import require_api_key
from pipeline.models import PipelineEvent, PREvent, PullRequest, Repository, ReviewAlert
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


@require_GET
@login_required
def calendar_view(request: HttpRequest) -> HttpResponse:
    """Calendar view — tasks by due date, sprint info, milestones."""
    from tasks.models import AsanaTask  # noqa: PLC0415

    today = timezone.localdate()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
        if not (1 <= month <= 12) or not (2020 <= year <= 2030):
            raise ValueError
    except (ValueError, TypeError):
        year, month = today.year, today.month

    # Month boundaries
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    # Prev / next month navigation
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    # Tasks with due dates in this month, grouped by day
    tasks_qs = (
        AsanaTask.objects.filter(due_on__gte=first_day, due_on__lte=last_day)
        .order_by("due_on", "name")
        .select_related("project")
    )
    tasks_by_day: dict[int, list] = {}
    for task in tasks_qs:
        tasks_by_day.setdefault(task.due_on.day, []).append(task)

    # Build week grid (0 = padding day outside this month)
    weeks = []
    for week in cal_module.monthcalendar(year, month):
        week_data = []
        for day_num in week:
            if day_num == 0:
                week_data.append({"day": 0, "tasks": [], "is_today": False})
            else:
                is_today = (
                    year == today.year
                    and month == today.month
                    and day_num == today.day
                )
                week_data.append({
                    "day": day_num,
                    "tasks": tasks_by_day.get(day_num, []),
                    "is_today": is_today,
                })
        weeks.append(week_data)

    return render(request, "dashboard/calendar.html", {
        "year": year,
        "month": month,
        "month_name": cal_module.month_name[month],
        "weeks": weeks,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
        "today": today,
        "tasks_count": tasks_qs.count(),
        "day_names": list(cal_module.day_abbr),
    })


# ---------------------------------------------------------------------------
# Task 135 — Health beacon (/api/live/health/ SSE)
# ---------------------------------------------------------------------------

def _read_fleet_health() -> tuple[str, bool, list]:
    """Read hollis.health.json. Returns (fleet_status, is_stale, agents)."""
    health_path = os.path.expanduser("~/.claude-remote/default/state/hollis.health.json")
    try:
        with open(health_path) as f:
            data = json.load(f)
        ts_str = data.get("timestamp", "")
        is_stale = True
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    raise ValueError("naive timestamp")
                is_stale = (datetime.now(dt_timezone.utc) - ts).total_seconds() > 300
            except (ValueError, TypeError):
                logger.debug("hollis.health.json has unparseable/naive timestamp %r; treating as stale", ts_str)
        agents = data.get("agents", [])
        summary = data.get("summary", {})
        if is_stale:
            fleet_status = "unknown"
        elif summary.get("red", 0) > 0:
            fleet_status = "red"
        elif summary.get("warn", 0) > 0:
            fleet_status = "warn"
        else:
            fleet_status = "green"
        return fleet_status, is_stale, agents
    except (OSError, json.JSONDecodeError, KeyError):
        return "unknown", True, []


def _compute_health_status(
    stale_sessions: list,
    stale_heartbeats: list,
    failed_ci: list,
    idle_prs: list,
    errors: list,
    review_alerts: list,
    fleet_status: str = "green",
    fleet_stale: bool = False,
    fleet_agents: list | None = None,
) -> tuple[str, int]:
    """Return (status_label, incident_count) for the health beacon."""
    fleet_agents = fleet_agents or []
    fleet_critical = fleet_status == "red" and not fleet_stale
    fleet_watch = fleet_status in ("warn", "unknown") or fleet_stale
    if fleet_stale or fleet_status == "unknown":
        fleet_count = 1
    elif fleet_status == "green":
        fleet_count = 0
    elif fleet_status == "red":
        fleet_count = max(1, sum(1 for a in fleet_agents if isinstance(a, dict) and a.get("status") == "red"))
    else:
        fleet_count = max(1, sum(1 for a in fleet_agents if isinstance(a, dict) and a.get("status") == "warn"))

    total = (
        len(stale_sessions)
        + len(stale_heartbeats)
        + len(failed_ci)
        + len(idle_prs)
        + len(errors)
        + len(review_alerts)
        + fleet_count
    )
    if stale_sessions or fleet_critical or total >= 5:
        return "CRITICAL", total
    if failed_ci or errors:
        return "DEGRADED", total
    if stale_heartbeats or idle_prs or review_alerts or fleet_watch:
        return "WATCH", total
    return "HEALTHY", 0


@login_required
@require_GET
def health_stream(request: HttpRequest) -> StreamingHttpResponse:
    """SSE stream emitting fleet health status every 10 seconds."""

    def event_stream():
        deadline = time.monotonic() + 3600
        try:
            while time.monotonic() < deadline:
                now = timezone.now()
                fresh_cutoff = now - timedelta(hours=2)
                heartbeat_cutoff = now - timedelta(minutes=5)
                six_hours_ago = now - timedelta(hours=6)
                day_ago = now - timedelta(hours=24)

                live_machines = set(
                    TerminalHeartbeat.objects.filter(received_at__gte=heartbeat_cutoff)
                    .values_list("machine", flat=True)
                )
                stale_sessions = list(
                    AgentSession.objects.filter(
                        status="active", last_activity__lt=fresh_cutoff
                    ).exclude(machine__in=live_machines)
                )
                stale_heartbeats = [
                    hb for hb in TerminalHeartbeat.objects.all() if hb.is_stale
                ]
                failed_ci = list(
                    PullRequest.objects.filter(
                        state=PullRequest.State.OPEN,
                        ci_status=PullRequest.CIStatus.FAILED,
                    )
                )
                idle_prs = list(
                    PullRequest.objects.filter(
                        state=PullRequest.State.OPEN,
                        last_updated__lt=six_hours_ago,
                    ).exclude(ci_status=PullRequest.CIStatus.FAILED)
                )
                errors = list(
                    PipelineEvent.objects.filter(
                        severity__in=[
                            PipelineEvent.Severity.ERROR,
                            PipelineEvent.Severity.CRITICAL,
                        ],
                        created_at__gte=day_ago,
                    ).order_by("-created_at")[:50]
                )
                review_alerts = list(
                    ReviewAlert.objects.filter(
                        status=ReviewAlert.Status.CHANGES_REQUESTED,
                        is_read=False,
                    )[:20]
                )

                fleet_status, fleet_stale, fleet_agents = _read_fleet_health()
                status, count = _compute_health_status(
                    stale_sessions, stale_heartbeats, failed_ci, idle_prs, errors, review_alerts,
                    fleet_status=fleet_status,
                    fleet_stale=fleet_stale,
                    fleet_agents=fleet_agents,
                )
                agent_pills = []
                for raw in fleet_agents:
                    if not isinstance(raw, dict):
                        continue
                    raw_flags = raw.get("flags")
                    if raw_flags is None:
                        flags: list[str] = []
                    elif isinstance(raw_flags, list):
                        flags = [str(f) for f in raw_flags]
                    else:
                        flags = [str(raw_flags)]
                    agent_pills.append({
                        "name": str(raw.get("agent") or ""),
                        "status": str(raw.get("status") or "unknown"),
                        "flags": flags,
                    })
                payload = {"status": status, "incident_count": count, "agents": agent_pills}
                yield f"event: health\ndata: {json.dumps(payload)}\n\n"

                time.sleep(10)
        except GeneratorExit:
            return

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
