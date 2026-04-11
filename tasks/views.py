from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Case, IntegerField, Value, When
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from .filters import AsanaTaskFilter
from .models import AsanaProject, AsanaTask


@login_required
def task_feed(request: HttpRequest) -> HttpResponse:
    view_mode = request.GET.get("view", "feed")
    today = timezone.localdate()
    week_ahead = today + timedelta(days=7)

    # Common queryset
    incomplete_qs = (
        AsanaTask.objects.filter(completed=False)
        .select_related("project", "linked_pr__repository")
        .annotate(
            priority_rank=Case(
                When(priority="high", then=Value(3)),
                When(priority="medium", then=Value(2)),
                When(priority="low", then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
    )

    # Completion stats per project
    projects = AsanaProject.objects.filter(is_active=True).order_by("name")
    stats = []
    for proj in projects:
        total = AsanaTask.objects.filter(project=proj).count()
        done = AsanaTask.objects.filter(project=proj, completed=True).count()
        overdue = AsanaTask.objects.filter(
            project=proj, completed=False, due_on__lt=today, due_on__isnull=False,
        ).count()
        last_activity = AsanaTask.objects.filter(
            project=proj, asana_updated_at__isnull=False,
        ).order_by("-asana_updated_at", "-pk").values_list(
            "asana_updated_at", flat=True
        ).first()
        stats.append({
            "project": proj,
            "total": total,
            "done": done,
            "overdue": overdue,
            "last_activity": last_activity,
        })

    if view_mode == "dashboard":
        # --- Dashboard mode ---
        # Overdue tasks
        overdue_tasks = (
            incomplete_qs.filter(due_on__lt=today, due_on__isnull=False)
            .order_by("due_on", "-priority_rank", "pk")
        )

        # Due this week (grouped by project)
        due_this_week = (
            incomplete_qs.filter(due_on__gte=today, due_on__lte=week_ahead)
            .order_by("project__name", "due_on", "pk")
        )

        # Recent completions
        recent_completed = (
            AsanaTask.objects.filter(completed=True)
            .select_related("project")
            .order_by("-completed_at", "-pk")[:10]
        )

        return render(request, "tasks/feed.html", {
            "view_mode": view_mode,
            "stats": stats,
            "projects": projects,
            "today": today,
            "overdue_tasks": overdue_tasks,
            "due_this_week": due_this_week,
            "recent_completed": recent_completed,
        })

    # --- Feed mode (original) ---
    f = AsanaTaskFilter(request.GET, queryset=incomplete_qs.order_by("due_on", "-priority_rank", "name", "pk"))
    sort = request.GET.get("sort", "due_on")
    sort_map = {
        "due_on": ("due_on", "-priority_rank", "name", "pk"),
        "-due_on": ("-due_on", "-priority_rank", "name", "pk"),
        "name": ("name", "-priority_rank", "pk"),
        "-name": ("-name", "-priority_rank", "pk"),
    }
    tasks = f.qs.order_by(*sort_map[sort]) if sort in sort_map else f.qs

    params_without_sort = request.GET.copy()
    params_without_sort.pop("sort", None)

    return render(request, "tasks/feed.html", {
        "filter": f,
        "tasks": tasks,
        "sort": sort,
        "stats": stats,
        "projects": projects,
        "query_without_sort": params_without_sort.urlencode(),
        "today": today,
        "view_mode": view_mode,
    })


@login_required
def handoffs(request: HttpRequest) -> HttpResponse:
    projects = AsanaProject.objects.filter(is_active=True).order_by("name")
    handoff_tasks = []
    for proj in projects:
        task = (
            AsanaTask.objects.filter(
                project=proj,
                name__icontains="handoff",
            )
            .order_by("-asana_updated_at")
            .first()
        )
        handoff_tasks.append({"project": proj, "task": task})

    return render(request, "tasks/handoffs.html", {
        "handoff_tasks": handoff_tasks,
    })
