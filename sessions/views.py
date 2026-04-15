import datetime
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from core.auth import require_api_key
from core.utils import parse_json_body
from pipeline.models import Repository

from .models import AgentSession, SessionLog, TerminalHeartbeat

logger = logging.getLogger(__name__)


def _session_to_dict(session: AgentSession, include_logs: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": session.pk,
        "agent": session.agent,
        "agent_display": session.get_agent_display(),
        "machine": session.machine,
        "machine_display": session.get_machine_display(),
        "status": session.status,
        "branch": session.branch,
        "task_description": session.task_description,
        "repository": session.repository.name if session.repository else None,
        "started_at": session.started_at.isoformat(),
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "last_activity": session.last_activity.isoformat(),
        "tokens_input": session.tokens_input,
        "tokens_output": session.tokens_output,
        "estimated_cost": str(session.estimated_cost),
        "commits_generated": session.commits_generated,
        "pr_generated": session.pr_generated_id,
        "notes": session.notes,
    }
    if include_logs:
        data["logs"] = [
            {
                "id": log.pk,
                "level": log.level,
                "message": log.message,
                "created_at": log.created_at.isoformat(),
            }
            for log in session.logs.order_by("-created_at")[:50]
        ]
    return data


def _log_to_dict(log: SessionLog) -> dict[str, Any]:
    return {
        "id": log.pk,
        "session_id": log.session_id,
        "level": log.level,
        "message": log.message,
        "created_at": log.created_at.isoformat(),
    }


def _get_session_or_404(session_id: int) -> tuple[AgentSession | None, JsonResponse | None]:
    try:
        session = (
            AgentSession.objects.select_related("repository")
            .get(pk=session_id)
        )
        return session, None
    except AgentSession.DoesNotExist:
        return None, JsonResponse(
            {"success": False, "message": "Session not found", "data": None},
            status=404,
        )


VALID_AGENTS = {c[0] for c in AgentSession.AGENT_CHOICES}
VALID_MACHINES = {c[0] for c in AgentSession.MACHINE_CHOICES}
VALID_STATUSES = {c[0] for c in AgentSession.STATUS_CHOICES}


@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_api_key
def session_list_create(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return _list_sessions(request)
    return _create_session(request)


def _list_sessions(request: HttpRequest) -> JsonResponse:
    qs = AgentSession.objects.select_related("repository").order_by("-started_at")

    status_filter = request.GET.get("status")
    if status_filter and status_filter != "all":
        if status_filter not in VALID_STATUSES:
            return JsonResponse(
                {"success": False, "message": f"Invalid status: {status_filter}", "data": None},
                status=400,
            )
        qs = qs.filter(status=status_filter)

    agent_filter = request.GET.get("agent")
    if agent_filter:
        qs = qs.filter(agent=agent_filter)

    machine_filter = request.GET.get("machine")
    if machine_filter:
        qs = qs.filter(machine=machine_filter)

    try:
        limit = int(request.GET.get("limit", 20))
        offset = int(request.GET.get("offset", 0))
    except ValueError:
        return JsonResponse(
            {"success": False, "message": "limit and offset must be integers", "data": None},
            status=400,
        )

    total = qs.count()
    sessions = qs[offset : offset + limit]

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "sessions": [_session_to_dict(s) for s in sessions],
        },
    })


def _create_session(request: HttpRequest) -> JsonResponse:
    body, err = parse_json_body(request)
    if err:
        return err

    assert body is not None  # guarded by err check

    agent = body.get("agent", "")
    if agent not in VALID_AGENTS:
        return JsonResponse(
            {"success": False, "message": f"Invalid agent: {agent}", "data": None},
            status=400,
        )

    machine = body.get("machine", "mac")
    if machine not in VALID_MACHINES:
        return JsonResponse(
            {"success": False, "message": f"Invalid machine: {machine}", "data": None},
            status=400,
        )

    repo = None
    repo_identifier = body.get("repository")
    if repo_identifier:
        try:
            if "/" in repo_identifier:
                owner, name = repo_identifier.split("/", 1)
                repo = Repository.objects.get(owner=owner, name=name)
            else:
                repo = Repository.objects.get(name=repo_identifier)
        except Repository.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": f"Repository not found: {repo_identifier}", "data": None},
                status=400,
            )
        except Repository.MultipleObjectsReturned:
            return JsonResponse(
                {
                    "success": False,
                    "message": f"Multiple repositories found for: {repo_identifier}. Use owner/name format.",
                    "data": None,
                },
                status=400,
            )

    session = AgentSession.objects.create(
        agent=agent,
        machine=machine,
        branch=body.get("branch", ""),
        task_description=body.get("task_description", ""),
        repository=repo,
    )

    return JsonResponse(
        {
            "success": True,
            "message": "Session created",
            "data": _session_to_dict(session),
        },
        status=201,
    )


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
@require_api_key
def session_detail(request: HttpRequest, session_id: int) -> JsonResponse:
    if request.method == "GET":
        return _get_session(session_id)
    return _update_session(request, session_id)


def _get_session(session_id: int) -> JsonResponse:
    session, err = _get_session_or_404(session_id)
    if err:
        return err
    assert session is not None

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": _session_to_dict(session, include_logs=True),
    })


def _update_session(request: HttpRequest, session_id: int) -> JsonResponse:
    body, err = parse_json_body(request)
    if err:
        return err
    assert body is not None

    updatable_str = {"status", "branch", "task_description", "notes"}
    updatable_int = {"tokens_input", "tokens_output", "commits_generated"}

    # Validate before acquiring lock
    for field in updatable_str:
        if field in body and field == "status" and body[field] not in VALID_STATUSES:
            return JsonResponse(
                {"success": False, "message": f"Invalid status: {body[field]}", "data": None},
                status=400,
            )

    for field in updatable_int:
        if field in body:
            try:
                int(body[field])
            except (ValueError, TypeError):
                return JsonResponse(
                    {"success": False, "message": f"{field} must be an integer", "data": None},
                    status=400,
                )

    if "estimated_cost" in body:
        try:
            Decimal(str(body["estimated_cost"]))
        except (InvalidOperation, ValueError, TypeError):
            return JsonResponse(
                {"success": False, "message": "estimated_cost must be a valid decimal", "data": None},
                status=400,
            )

    with transaction.atomic():
        try:
            session = (
                AgentSession.objects.select_for_update()
                .get(pk=session_id)
            )
        except AgentSession.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Session not found", "data": None},
                status=404,
            )

        for field in updatable_str:
            if field in body:
                setattr(session, field, body[field])

        for field in updatable_int:
            if field in body:
                setattr(session, field, int(body[field]))

        if "estimated_cost" in body:
            session.estimated_cost = Decimal(str(body["estimated_cost"]))

        session.save()

    return JsonResponse({
        "success": True,
        "message": "Session updated",
        "data": _session_to_dict(session),
    })


@csrf_exempt
@require_http_methods(["POST"])
@require_api_key
def session_end(request: HttpRequest, session_id: int) -> JsonResponse:
    body, err = parse_json_body(request)
    if err:
        return err
    assert body is not None

    with transaction.atomic():
        try:
            session = (
                AgentSession.objects.select_for_update()
                .get(pk=session_id)
            )
        except AgentSession.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Session not found", "data": None},
                status=404,
            )

        end_status = body.get("status", "completed")
        if end_status not in VALID_STATUSES:
            return JsonResponse(
                {"success": False, "message": f"Invalid status: {end_status}", "data": None},
                status=400,
            )
        session.status = end_status
        session.ended_at = timezone.now()
        if "notes" in body:
            session.notes = body["notes"]
        session.save()

    return JsonResponse({
        "success": True,
        "message": "Session ended",
        "data": _session_to_dict(session),
    })


@csrf_exempt
@require_http_methods(["POST"])
@require_api_key
def session_log(request: HttpRequest, session_id: int) -> JsonResponse:
    session, err = _get_session_or_404(session_id)
    if err:
        return err
    assert session is not None

    body, err = parse_json_body(request)
    if err:
        return err
    assert body is not None

    level = body.get("level", "")
    valid_levels = {c[0] for c in SessionLog.LEVEL_CHOICES}
    if level not in valid_levels:
        return JsonResponse(
            {"success": False, "message": f"Invalid level: {level}", "data": None},
            status=400,
        )

    message = body.get("message", "")
    if not message:
        return JsonResponse(
            {"success": False, "message": "message is required", "data": None},
            status=400,
        )

    log = SessionLog.objects.create(
        session=session,
        level=level,
        message=message,
    )

    return JsonResponse(
        {
            "success": True,
            "message": "Log entry created",
            "data": _log_to_dict(log),
        },
        status=201,
    )


@require_GET
@require_api_key
def session_active(request: HttpRequest) -> JsonResponse:
    sessions = (
        AgentSession.objects.filter(status="active")
        .select_related("repository")
        .order_by("-started_at")
    )
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": [_session_to_dict(s) for s in sessions],
    })


@require_http_methods(["POST"])
@login_required
def cleanup_stale_sessions_view(request: HttpRequest) -> JsonResponse:
    """Manually trigger stale session cleanup."""
    from .tasks import cleanup_stale_sessions

    count = cleanup_stale_sessions()
    return JsonResponse({
        "success": True,
        "message": f"Cleaned up {count} stale session(s).",
        "data": {"cleaned": count},
    })


def _fresh_active_cutoff() -> "datetime.datetime":
    return timezone.now() - timedelta(hours=2)


@require_GET
@login_required
def session_list_page(request: HttpRequest) -> HttpResponse:
    """Full sessions list page with filters and active-now section."""
    qs = AgentSession.tenant_objects.for_request(request).select_related("repository").order_by("-started_at")

    # Filters
    agent_filter = request.GET.get("agent", "")
    machine_filter = request.GET.get("machine", "")
    status_filter = request.GET.get("status", "")

    if agent_filter:
        qs = qs.filter(agent=agent_filter)
    if machine_filter:
        qs = qs.filter(machine=machine_filter)
    if status_filter:
        qs = qs.filter(status=status_filter)

    # Active sessions: only those with activity within the last 2 hours
    fresh_cutoff = _fresh_active_cutoff()
    active_qs = (
        AgentSession.tenant_objects.for_request(request).filter(status="active", last_activity__gte=fresh_cutoff)
        .select_related("repository")
        .order_by("-last_activity")
    )
    if agent_filter:
        active_qs = active_qs.filter(agent=agent_filter)
    if machine_filter:
        active_qs = active_qs.filter(machine=machine_filter)

    return render(request, "sessions/list.html", {
        "sessions": qs,
        "active_sessions": active_qs,
        "agent_choices": AgentSession.AGENT_CHOICES,
        "machine_choices": AgentSession.MACHINE_CHOICES,
        "status_choices": AgentSession.STATUS_CHOICES,
        "filters": {
            "agent": agent_filter,
            "machine": machine_filter,
            "status": status_filter,
        },
    })


# ---------------------------------------------------------------------------
# Terminal Bridge — Heartbeat & Status
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
@require_api_key
def terminal_heartbeat(request: HttpRequest) -> JsonResponse:
    """Receive heartbeat from Nock Terminal desktop app.

    Overwrites the single TerminalHeartbeat record (upsert pattern).
    Terminal posts this every 30-60 seconds.
    """
    if len(request.body) > 256 * 1024:
        return JsonResponse(
            {"success": False, "message": "Request body too large", "data": None},
            status=413,
        )

    body, err = parse_json_body(request)
    if err:
        return err
    if not isinstance(body, dict):
        return JsonResponse(
            {"success": False, "message": "JSON body must be an object", "data": None},
            status=400,
        )

    sessions_data = body.get("sessions", [])
    if not isinstance(sessions_data, list):
        return JsonResponse(
            {"success": False, "message": "sessions must be an array", "data": None},
            status=400,
        )
    if len(sessions_data) > 50:
        return JsonResponse(
            {"success": False, "message": "sessions array exceeds maximum length", "data": None},
            status=400,
        )

    # Validate each session entry has required fields
    required_fields = {"project", "status"}
    for i, session in enumerate(sessions_data):
        if not isinstance(session, dict):
            return JsonResponse(
                {"success": False, "message": f"sessions[{i}] must be an object", "data": None},
                status=400,
            )
        missing = required_fields - set(session.keys())
        if missing:
            return JsonResponse(
                {
                    "success": False,
                    "message": f"sessions[{i}] missing fields: {sorted(missing)}",
                    "data": None,
                },
                status=400,
            )

    active_ports = body.get("active_ports", [])
    if not isinstance(active_ports, list):
        return JsonResponse(
            {"success": False, "message": "active_ports must be an array", "data": None},
            status=400,
        )
    if len(active_ports) > 100:
        return JsonResponse(
            {"success": False, "message": "active_ports array exceeds maximum length", "data": None},
            status=400,
        )

    machine = str(body.get("machine", "mac"))[:50]
    terminal_version = str(body.get("terminal_version", ""))[:50]

    # Upsert — update existing or create. Single row per machine.
    heartbeat, _created = TerminalHeartbeat.objects.update_or_create(
        machine=machine,
        defaults={
            "sessions": sessions_data,
            "active_ports": active_ports,
            "terminal_version": terminal_version,
        },
    )

    return JsonResponse({
        "success": True,
        "message": "heartbeat received",
        "data": {
            "machine": heartbeat.machine,
            "session_count": heartbeat.session_count,
            "received_at": heartbeat.received_at.isoformat(),
        },
    })


@csrf_exempt
@require_GET
@require_api_key
def terminal_status(request: HttpRequest) -> JsonResponse:
    """Return latest Terminal heartbeat state for mobile app display."""
    data = [
        {
            "machine": hb.machine,
            "sessions": hb.sessions,
            "active_ports": hb.active_ports,
            "terminal_version": hb.terminal_version,
            "received_at": hb.received_at.isoformat(),
            "is_stale": hb.is_stale,
            "session_count": hb.session_count,
        }
        for hb in TerminalHeartbeat.objects.order_by("-received_at")
    ]

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": data,
    })
