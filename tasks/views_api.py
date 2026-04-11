# tasks/views_api.py
"""
Asana Write-Back + Cross-Project Read API.

Every endpoint is gated by `require_brain_access` (same auth pipeline as
Brain and Research endpoints — API key, DRF token, or staff session).

Write flow — MUST stay Asana-first:
    1. validate request
    2. call Asana
    3. if Asana succeeds -> mirror to local AsanaTask cache
    4. if Asana fails   -> return error, DO NOT touch local DB

The cross-project read endpoints hit local DB only — they are designed to
feed the morning-brief and heartbeat crons, so they need to be fast and
must not fan out to Asana.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from django.db import transaction
from django.db.models import Case, Count, IntegerField, Value, When
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from core.auth import require_brain_access
from core.utils import parse_json_body

from .asana_client import AsanaClientError
from .asana_client import add_comment as asana_add_comment
from .asana_client import add_task_to_section as asana_add_task_to_section
from .asana_client import create_task as asana_create_task
from .asana_client import delete_task as asana_delete_task
from .asana_client import get_sections as asana_get_sections
from .asana_client import parse_task as asana_parse_task
from .asana_client import update_task as asana_update_task
from .models import AsanaProject, AsanaSection, AsanaTask

MAX_BODY = 256 * 1024  # 256 KB — Asana task notes can be up to ~65KB
VALID_PRIORITIES = {"low", "medium", "high"}


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

def _task_to_dict(task: AsanaTask) -> dict[str, Any]:
    return {
        "id": task.pk,
        "asana_gid": task.asana_gid,
        "name": task.name,
        "project": task.project.name if task.project_id else None,
        "project_gid": task.project.asana_gid if task.project_id else None,
        "section": task.section_name,
        "assignee": task.assignee_name or None,
        "due_on": task.due_on.isoformat() if task.due_on else None,
        "completed": task.completed,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "priority": task.priority,
        "notes_preview": task.notes_preview,
        "permalink_url": task.permalink_url,
        "is_overdue": task.is_overdue,
        "linked_pr_number": task.linked_pr.number if task.linked_pr_id else None,
        "deleted_at": task.deleted_at.isoformat() if task.deleted_at else None,
        "last_synced": task.last_synced.isoformat() if task.last_synced else None,
    }


def _section_to_dict(section: AsanaSection) -> dict[str, Any]:
    return {
        "id": section.pk,
        "asana_gid": section.asana_gid,
        "name": section.name,
        "order": section.order,
        "project": section.project.name if section.project_id else None,
        "project_gid": section.project.asana_gid if section.project_id else None,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _bad_request(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse(
        {"success": False, "message": message, "data": None},
        status=status,
    )


def _parse_body(request: HttpRequest) -> tuple[dict[str, Any] | None, JsonResponse | None]:
    if len(request.body) > MAX_BODY:
        return None, _bad_request("Request body too large", status=413)
    body, err = parse_json_body(request)
    if err:
        return None, err
    if not isinstance(body, dict):
        return None, _bad_request("JSON body must be an object")
    return body, None


def _get_task_or_404(asana_gid: str) -> tuple[AsanaTask | None, JsonResponse | None]:
    """Look up a live (not soft-deleted) task by Asana gid.

    Soft-deleted tasks are treated as 404 so mutating endpoints can't hand
    Asana a gid that no longer exists upstream — which would come back as a
    502 from whatever write helper we called next.
    """
    try:
        task = (
            AsanaTask.objects.select_related("project", "linked_pr")
            .filter(deleted_at__isnull=True)
            .get(asana_gid=asana_gid)
        )
    except AsanaTask.DoesNotExist:
        return None, _bad_request("Task not found", status=404)
    return task, None


def _coerce_typed_values(parsed: dict[str, Any]) -> dict[str, Any]:
    """Convert ISO-8601 strings returned by asana_parse_task into Python types.

    ``asana_parse_task`` is shared with the read sync, which hands its output
    straight to ``update_or_create(defaults=...)`` — Django's ORM handles the
    string→date/datetime coercion on save. The write-back views assign these
    values directly to a model instance (so they show up in the response
    envelope before refresh_from_db), which means callers like
    ``_task_to_dict`` and ``AsanaTask.is_overdue`` end up with raw strings
    instead of ``date``/``datetime`` and blow up on ``.isoformat()`` / date
    comparison.

    This helper does the coercion up front so every caller downstream sees
    typed values.
    """
    out = dict(parsed)

    due_on = out.get("due_on")
    if isinstance(due_on, str) and due_on:
        try:
            out["due_on"] = datetime.strptime(due_on, "%Y-%m-%d").date()
        except ValueError:
            out["due_on"] = None
    elif due_on in ("", None):
        out["due_on"] = None

    completed_at = out.get("completed_at")
    if isinstance(completed_at, str) and completed_at:
        # Asana returns "2026-04-10T12:34:56.789Z"; fromisoformat in 3.11+
        # accepts trailing "Z" if we swap it for "+00:00".
        try:
            dt = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, UTC)
            out["completed_at"] = dt
        except ValueError:
            out["completed_at"] = None
    elif completed_at in ("", None):
        out["completed_at"] = None

    return out


def _apply_asana_fields_to_task(task: AsanaTask, raw: dict[str, Any]) -> list[str]:
    """Copy parsed Asana fields back onto a local AsanaTask.

    Returns the list of field names that were actually updated so callers
    can pass a tight update_fields= to .save().
    """
    parsed = _coerce_typed_values(asana_parse_task(raw))
    parsed.pop("asana_gid", None)

    updated: list[str] = []
    for field, value in parsed.items():
        if getattr(task, field, None) != value:
            setattr(task, field, value)
            updated.append(field)
    return updated


def _validate_priority(raw: Any) -> tuple[str | None, JsonResponse | None]:
    """Priority is a local-only field — never sent to Asana.

    Empty / missing priority is allowed and returns (None, None).
    """
    if raw is None or raw == "":
        return None, None
    value = str(raw).lower().strip()
    if value not in VALID_PRIORITIES:
        return None, _bad_request(
            f"Invalid priority. Must be one of: {', '.join(sorted(VALID_PRIORITIES))}",
        )
    return value, None


# ---------------------------------------------------------------------------
# Write endpoints
# ---------------------------------------------------------------------------

@ratelimit(key="ip", rate="30/m", method="POST", block=False)
@require_http_methods(["POST"])
@require_brain_access
def create_task_view(request: HttpRequest) -> JsonResponse:
    """POST /api/tasks/create/ — create a task in Asana + local DB."""
    body, err = _parse_body(request)
    if err:
        return err
    assert body is not None

    project_gid = str(body.get("project_gid", "")).strip()
    name = str(body.get("name", "")).strip()
    if not project_gid or not name:
        return _bad_request("project_gid and name are required")

    try:
        project = AsanaProject.objects.get(asana_gid=project_gid)
    except AsanaProject.DoesNotExist:
        return _bad_request(
            f"Project with gid '{project_gid}' not registered in NockCC",
            status=404,
        )

    priority, perr = _validate_priority(body.get("priority"))
    if perr:
        return perr

    section_gid = str(body.get("section_gid", "")).strip() or None
    notes = body.get("notes")
    due_on = body.get("due_on")
    assignee = body.get("assignee")

    # Pre-validate section against the local cache BEFORE touching Asana. If
    # we delegated to Asana's create and the follow-up addTask-to-section call
    # failed, the caller would see a 502 for a task that already exists in
    # Asana, and a naive retry would create a duplicate. Failing fast here
    # keeps create atomic from the caller's perspective.
    if section_gid:
        try:
            section = AsanaSection.objects.select_related("project").get(
                asana_gid=section_gid,
            )
        except AsanaSection.DoesNotExist:
            return _bad_request(
                f"Section '{section_gid}' not found. Sync sections first or pass a valid gid.",
                status=404,
            )
        if section.project_id != project.pk:
            return _bad_request(
                "Section belongs to a different project — cannot place task there",
            )

    try:
        created = asana_create_task(
            project_gid=project_gid,
            name=name,
            notes=str(notes) if notes is not None else None,
            due_on=str(due_on) if due_on else None,
            assignee=str(assignee) if assignee else None,
            section_gid=section_gid,
        )
    except AsanaClientError as exc:
        return _bad_request(f"Asana create failed: {exc}", status=502)
    except ValueError as exc:
        # Raised by _get_pat() when ASANA_PAT is missing.
        return _bad_request(str(exc), status=500)

    parsed = _coerce_typed_values(asana_parse_task(created))
    gid = parsed.pop("asana_gid")
    # Priority is local-only — caller-specified value wins over anything the
    # Asana parse returned (Asana free tier doesn't have a priority field, so
    # parsed["priority"] will normally be None anyway).
    if priority is not None:
        parsed["priority"] = priority

    with transaction.atomic():
        task, _ = AsanaTask.objects.update_or_create(
            asana_gid=gid,
            defaults={"project": project, **parsed},
        )

    return JsonResponse(
        {"success": True, "message": "Task created", "data": _task_to_dict(task)},
        status=201,
    )


@ratelimit(key="ip", rate="60/m", method=["PUT", "PATCH"], block=False)
@require_http_methods(["PUT", "PATCH"])
@require_brain_access
def update_task_view(request: HttpRequest, asana_gid: str) -> JsonResponse:
    """PUT /api/tasks/<gid>/update/ — partial update of an Asana task."""
    task, err404 = _get_task_or_404(asana_gid)
    if err404:
        return err404
    assert task is not None

    body, err = _parse_body(request)
    if err:
        return err
    assert body is not None

    # Priority is local-only — never forwarded to Asana.
    priority_changed = "priority" in body
    new_priority: str | None = task.priority
    if priority_changed:
        new_priority, perr = _validate_priority(body.get("priority"))
        if perr:
            return perr

    asana_kwargs: dict[str, Any] = {}
    for field in ("name", "notes", "due_on", "completed", "assignee"):
        if field in body:
            asana_kwargs[field] = body[field]

    if not asana_kwargs and not priority_changed:
        return _bad_request("No updatable fields provided")

    # Only call Asana if there's something for Asana to update.
    if asana_kwargs:
        try:
            updated_raw = asana_update_task(asana_gid, **asana_kwargs)
        except AsanaClientError as exc:
            return _bad_request(f"Asana update failed: {exc}", status=502)
        except ValueError as exc:
            return _bad_request(str(exc), status=500)

        with transaction.atomic():
            locked = AsanaTask.objects.select_for_update().get(pk=task.pk)
            updated_fields = _apply_asana_fields_to_task(locked, updated_raw)
            if priority_changed:
                locked.priority = new_priority
                updated_fields.append("priority")
            if updated_fields:
                locked.save(update_fields=updated_fields)
            task = locked
    else:
        # Priority-only update — no Asana call.
        with transaction.atomic():
            locked = AsanaTask.objects.select_for_update().get(pk=task.pk)
            locked.priority = new_priority
            locked.save(update_fields=["priority"])
            task = locked

    task.refresh_from_db()
    return JsonResponse(
        {"success": True, "message": "Task updated", "data": _task_to_dict(task)},
    )


def _toggle_completed(request: HttpRequest, asana_gid: str, completed: bool) -> JsonResponse:
    task, err404 = _get_task_or_404(asana_gid)
    if err404:
        return err404
    assert task is not None

    try:
        updated_raw = asana_update_task(asana_gid, completed=completed)
    except AsanaClientError as exc:
        return _bad_request(f"Asana update failed: {exc}", status=502)
    except ValueError as exc:
        return _bad_request(str(exc), status=500)

    with transaction.atomic():
        locked = AsanaTask.objects.select_for_update().get(pk=task.pk)
        updated_fields = _apply_asana_fields_to_task(locked, updated_raw)
        if updated_fields:
            locked.save(update_fields=updated_fields)
        task = locked

    return JsonResponse(
        {
            "success": True,
            "message": "Task completed" if completed else "Task reopened",
            "data": _task_to_dict(task),
        },
    )


@ratelimit(key="ip", rate="60/m", method="POST", block=False)
@require_http_methods(["POST"])
@require_brain_access
def complete_task_view(request: HttpRequest, asana_gid: str) -> JsonResponse:
    """POST /api/tasks/<gid>/complete/"""
    return _toggle_completed(request, asana_gid, completed=True)


@ratelimit(key="ip", rate="60/m", method="POST", block=False)
@require_http_methods(["POST"])
@require_brain_access
def uncomplete_task_view(request: HttpRequest, asana_gid: str) -> JsonResponse:
    """POST /api/tasks/<gid>/uncomplete/"""
    return _toggle_completed(request, asana_gid, completed=False)


@ratelimit(key="ip", rate="60/m", method="POST", block=False)
@require_http_methods(["POST"])
@require_brain_access
def move_task_view(request: HttpRequest, asana_gid: str) -> JsonResponse:
    """POST /api/tasks/<gid>/move/ — move a task to a new section."""
    task, err404 = _get_task_or_404(asana_gid)
    if err404:
        return err404
    assert task is not None

    body, err = _parse_body(request)
    if err:
        return err
    assert body is not None

    section_gid = str(body.get("section_gid", "")).strip()
    if not section_gid:
        return _bad_request("section_gid is required")

    try:
        section = AsanaSection.objects.select_related("project").get(asana_gid=section_gid)
    except AsanaSection.DoesNotExist:
        return _bad_request(
            f"Section '{section_gid}' not found. Sync sections first or pass a valid gid.",
            status=404,
        )

    if section.project_id != task.project_id:
        return _bad_request(
            "Cannot move a task across projects — section belongs to a different project",
        )

    try:
        asana_add_task_to_section(asana_gid, section_gid)
    except AsanaClientError as exc:
        return _bad_request(f"Asana move failed: {exc}", status=502)
    except ValueError as exc:
        return _bad_request(str(exc), status=500)

    with transaction.atomic():
        locked = AsanaTask.objects.select_for_update().get(pk=task.pk)
        locked.section_name = section.name
        locked.save(update_fields=["section_name"])
        task = locked

    return JsonResponse(
        {"success": True, "message": "Task moved", "data": _task_to_dict(task)},
    )


@ratelimit(key="ip", rate="30/m", method="POST", block=False)
@require_http_methods(["POST"])
@require_brain_access
def comment_task_view(request: HttpRequest, asana_gid: str) -> JsonResponse:
    """POST /api/tasks/<gid>/comment/ — add a comment story to a task."""
    task, err404 = _get_task_or_404(asana_gid)
    if err404:
        return err404
    assert task is not None

    body, err = _parse_body(request)
    if err:
        return err
    assert body is not None

    text = str(body.get("text", "")).strip()
    if not text:
        return _bad_request("text is required")

    try:
        story = asana_add_comment(asana_gid, text)
    except AsanaClientError as exc:
        return _bad_request(f"Asana comment failed: {exc}", status=502)
    except ValueError as exc:
        return _bad_request(str(exc), status=500)

    return JsonResponse(
        {
            "success": True,
            "message": "Comment added",
            "data": {
                "task_gid": asana_gid,
                "story_gid": story.get("gid"),
                "text": story.get("text", text),
                "created_at": story.get("created_at"),
            },
        },
        status=201,
    )


@ratelimit(key="ip", rate="30/m", method="DELETE", block=False)
@require_http_methods(["DELETE"])
@require_brain_access
def delete_task_view(request: HttpRequest, asana_gid: str) -> JsonResponse:
    """DELETE /api/tasks/<gid>/delete/ — delete in Asana + soft-delete local."""
    task, err404 = _get_task_or_404(asana_gid)
    if err404:
        return err404
    assert task is not None

    try:
        asana_delete_task(asana_gid)
    except AsanaClientError as exc:
        return _bad_request(f"Asana delete failed: {exc}", status=502)
    except ValueError as exc:
        return _bad_request(str(exc), status=500)

    with transaction.atomic():
        locked = AsanaTask.objects.select_for_update().get(pk=task.pk)
        locked.deleted_at = timezone.now()
        locked.save(update_fields=["deleted_at"])
        task = locked

    return JsonResponse(
        {"success": True, "message": "Task deleted", "data": _task_to_dict(task)},
    )


# ---------------------------------------------------------------------------
# Cross-project read endpoints (local DB only)
# ---------------------------------------------------------------------------

def _incomplete_qs():
    return (
        AsanaTask.objects.filter(completed=False, deleted_at__isnull=True)
        .select_related("project", "linked_pr")
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


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


@ratelimit(key="ip", rate="120/m", method="GET", block=False)
@require_http_methods(["GET"])
@require_brain_access
def list_tasks_view(request: HttpRequest) -> JsonResponse:
    """GET /api/tasks/all/ — all incomplete tasks across all projects.

    Filters: project_gid, priority, due_before, due_after, overdue, completed, limit.
    """
    include_completed = request.GET.get("completed", "").lower() == "true"
    qs = _incomplete_qs() if not include_completed else (
        AsanaTask.objects.filter(deleted_at__isnull=True)
        .select_related("project", "linked_pr")
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

    project_gid = request.GET.get("project_gid", "").strip()
    if project_gid:
        qs = qs.filter(project__asana_gid=project_gid)

    priority = request.GET.get("priority", "").strip().lower()
    if priority:
        if priority not in VALID_PRIORITIES:
            return _bad_request(
                f"Invalid priority. Must be one of: {', '.join(sorted(VALID_PRIORITIES))}",
            )
        qs = qs.filter(priority=priority)

    due_before = _parse_date(request.GET.get("due_before"))
    if due_before:
        qs = qs.filter(due_on__lte=due_before, due_on__isnull=False)

    due_after = _parse_date(request.GET.get("due_after"))
    if due_after:
        qs = qs.filter(due_on__gte=due_after, due_on__isnull=False)

    if request.GET.get("overdue", "").lower() == "true":
        qs = qs.filter(due_on__lt=timezone.localdate(), due_on__isnull=False)

    try:
        limit = max(1, min(int(request.GET.get("limit", "100")), 500))
    except (TypeError, ValueError):
        limit = 100

    qs = qs.order_by("due_on", "-priority_rank", "name", "pk")[:limit]

    tasks = list(qs)
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "total": len(tasks),
            "tasks": [_task_to_dict(t) for t in tasks],
        },
    })


@ratelimit(key="ip", rate="120/m", method="GET", block=False)
@require_http_methods(["GET"])
@require_brain_access
def overdue_tasks_view(request: HttpRequest) -> JsonResponse:
    """GET /api/tasks/overdue/ — overdue incomplete tasks, most overdue first."""
    today = timezone.localdate()
    qs = (
        _incomplete_qs()
        .filter(due_on__lt=today, due_on__isnull=False)
        .order_by("due_on", "-priority_rank", "pk")
    )
    tasks = list(qs)
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "total": len(tasks),
            "today": today.isoformat(),
            "tasks": [
                {
                    **_task_to_dict(t),
                    "days_overdue": (today - t.due_on).days if t.due_on else None,
                }
                for t in tasks
            ],
        },
    })


@ratelimit(key="ip", rate="120/m", method="GET", block=False)
@require_http_methods(["GET"])
@require_brain_access
def today_tasks_view(request: HttpRequest) -> JsonResponse:
    """GET /api/tasks/today/ — tasks due today across all projects."""
    today = timezone.localdate()
    qs = (
        _incomplete_qs()
        .filter(due_on=today)
        .order_by("-priority_rank", "project__name", "pk")
    )
    tasks = list(qs)
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "total": len(tasks),
            "today": today.isoformat(),
            "tasks": [_task_to_dict(t) for t in tasks],
        },
    })


@ratelimit(key="ip", rate="60/m", method="GET", block=False)
@require_http_methods(["GET"])
@require_brain_access
def summary_view(request: HttpRequest) -> JsonResponse:
    """GET /api/tasks/summary/ — cross-project roll-up for morning briefs."""
    today = timezone.localdate()
    week_ahead = today + timedelta(days=7)

    live_tasks = AsanaTask.objects.filter(deleted_at__isnull=True)
    total = live_tasks.count()
    incomplete = live_tasks.filter(completed=False).count()
    completed = live_tasks.filter(completed=True).count()
    overdue = live_tasks.filter(
        completed=False, due_on__lt=today, due_on__isnull=False,
    ).count()
    due_today = live_tasks.filter(completed=False, due_on=today).count()
    due_this_week = live_tasks.filter(
        completed=False, due_on__gte=today, due_on__lte=week_ahead,
    ).count()

    by_priority = dict(
        live_tasks.filter(completed=False)
        .values("priority")
        .annotate(count=Count("id"))
        .values_list("priority", "count")
    )

    by_project = []
    for project in AsanaProject.objects.filter(is_active=True).order_by("name"):
        proj_qs = live_tasks.filter(project=project)
        by_project.append({
            "project": project.name,
            "project_gid": project.asana_gid,
            "total": proj_qs.count(),
            "incomplete": proj_qs.filter(completed=False).count(),
            "completed": proj_qs.filter(completed=True).count(),
            "overdue": proj_qs.filter(
                completed=False, due_on__lt=today, due_on__isnull=False,
            ).count(),
            "last_synced": project.last_synced.isoformat() if project.last_synced else None,
        })

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "today": today.isoformat(),
            "total_tasks": total,
            "incomplete": incomplete,
            "completed": completed,
            "overdue": overdue,
            "due_today": due_today,
            "due_this_week": due_this_week,
            "by_priority": {
                "high": by_priority.get("high", 0),
                "medium": by_priority.get("medium", 0),
                "low": by_priority.get("low", 0),
                "none": by_priority.get(None, 0) + by_priority.get("", 0),
            },
            "by_project": by_project,
        },
    })


@ratelimit(key="ip", rate="120/m", method="GET", block=False)
@require_http_methods(["GET"])
@require_brain_access
def sections_view(request: HttpRequest, project_gid: str) -> JsonResponse:
    """GET /api/tasks/sections/<project_gid>/ — list local section cache for a project.

    If ``?refresh=true``, forces a fresh pull from Asana before returning.
    """
    try:
        project = AsanaProject.objects.get(asana_gid=project_gid)
    except AsanaProject.DoesNotExist:
        return _bad_request(
            f"Project with gid '{project_gid}' not registered in NockCC",
            status=404,
        )

    if request.GET.get("refresh", "").lower() == "true":
        try:
            raw_sections = asana_get_sections(project_gid)
        except AsanaClientError as exc:
            return _bad_request(f"Asana sections fetch failed: {exc}", status=502)
        except ValueError as exc:
            return _bad_request(str(exc), status=500)

        incoming_gids: list[str] = []
        with transaction.atomic():
            for idx, raw in enumerate(raw_sections):
                gid = raw.get("gid")
                if not gid:
                    continue
                incoming_gids.append(gid)
                AsanaSection.objects.update_or_create(
                    asana_gid=gid,
                    defaults={
                        "project": project,
                        "name": str(raw.get("name", ""))[:255],
                        "order": idx,
                    },
                )
            # Prune sections that have disappeared upstream so a "refresh"
            # request actually reflects Asana. Otherwise the move endpoint
            # would keep validating against stale rows.
            AsanaSection.objects.filter(project=project).exclude(
                asana_gid__in=incoming_gids,
            ).delete()

    sections = list(project.sections.all().order_by("order", "name"))
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "project": project.name,
            "project_gid": project.asana_gid,
            "total": len(sections),
            "sections": [_section_to_dict(s) for s in sections],
        },
    })
