import hashlib
import hmac
import json
import logging
import time
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods
from django_ratelimit.decorators import ratelimit

from core.auth import require_api_key
from core.utils import parse_json_body

from .models import AgentStatus, CommandRequest, ConversationThread, SessionOutputBuffer

logger = logging.getLogger(__name__)


def _sign_payload(payload: dict) -> str:
    """HMAC-SHA256 sign a command payload."""
    key = getattr(settings, "AGENT_HMAC_KEY", "") or ""
    payload_bytes = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(key.encode(), payload_bytes, hashlib.sha256).hexdigest()


def _command_to_dict(cmd: CommandRequest) -> dict[str, Any]:
    return {
        "id": cmd.pk,
        "command_type": cmd.command_type,
        "command_type_display": cmd.get_command_type_display(),
        "payload": cmd.payload,
        "status": cmd.status,
        "status_display": cmd.get_status_display(),
        "result": cmd.result,
        "session_id": cmd.session_id,
        "created_at": cmd.created_at.isoformat(),
        "sent_at": cmd.sent_at.isoformat() if cmd.sent_at else None,
        "completed_at": cmd.completed_at.isoformat() if cmd.completed_at else None,
    }


def _get_online_agent() -> AgentStatus | None:
    """Return the first online agent, or None."""
    return (
        AgentStatus.objects.filter(is_online=True)
        .select_related("agent_token")
        .order_by("-connected_at")
        .first()
    )


def _push_to_agent(agent_status: AgentStatus, command: CommandRequest) -> bool:
    """Push a command to the agent via channel layer. Returns True on success."""
    channel_layer = get_channel_layer()
    group_name = f"agent_{agent_status.agent_token.pk}"
    try:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "agent.command",
                "data": {
                    "type": "command",
                    "command_id": command.pk,
                    "command_type": command.command_type,
                    "payload": command.payload,
                    "hmac_signature": command.hmac_signature,
                },
            },
        )
        return True
    except Exception:
        logger.exception("Failed to push command %s to agent", command.pk)
        return False


VALID_COMMAND_TYPES = {ct.value for ct in CommandRequest.CommandType}


@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_api_key
@ratelimit(key="user", rate="10/m", method="POST", block=True)
def command_list_create(request: HttpRequest) -> JsonResponse:
    """List recent commands or queue a new one."""
    if request.method == "GET":
        return _list_commands(request)
    return _create_command(request)


def _list_commands(request: HttpRequest) -> JsonResponse:
    qs = CommandRequest.objects.order_by("-created_at")

    status_filter = request.GET.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter)

    type_filter = request.GET.get("command_type")
    if type_filter:
        qs = qs.filter(command_type=type_filter)

    try:
        limit = int(request.GET.get("limit", 20))
    except ValueError:
        return JsonResponse(
            {"success": False, "message": "limit must be an integer", "data": None},
            status=400,
        )
    limit = max(1, min(limit, 100))

    commands = qs[:limit]
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "total": qs.count(),
            "commands": [_command_to_dict(c) for c in commands],
        },
    })


def _create_command(request: HttpRequest) -> JsonResponse:
    body, err = parse_json_body(request)
    if err:
        return err
    assert body is not None

    command_type = body.get("command_type", "")
    if command_type not in VALID_COMMAND_TYPES:
        return JsonResponse(
            {"success": False, "message": f"Invalid command_type: {command_type}", "data": None},
            status=400,
        )

    payload = body.get("payload", {})
    if not isinstance(payload, dict):
        return JsonResponse(
            {"success": False, "message": "payload must be a JSON object", "data": None},
            status=400,
        )

    signature = _sign_payload(payload)

    cmd = CommandRequest.objects.create(
        command_type=command_type,
        payload=payload,
        hmac_signature=signature,
        created_by=request.user,
    )

    # Try to push to agent if online
    agent = _get_online_agent()
    if agent and _push_to_agent(agent, cmd):
        cmd.status = CommandRequest.Status.SENT
        cmd.sent_at = timezone.now()
        cmd.save(update_fields=["status", "sent_at"])

    return JsonResponse(
        {"success": True, "message": "Command queued", "data": _command_to_dict(cmd)},
        status=201,
    )


@csrf_exempt
@require_GET
@require_api_key
def command_detail(request: HttpRequest, command_id: int) -> JsonResponse:
    """Get a single command's detail."""
    try:
        cmd = CommandRequest.objects.get(pk=command_id)
    except CommandRequest.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Command not found", "data": None},
            status=404,
        )

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": _command_to_dict(cmd),
    })


@csrf_exempt
@require_http_methods(["DELETE"])
@require_api_key
def command_cancel(request: HttpRequest, command_id: int) -> JsonResponse:
    """Cancel a queued command."""
    try:
        cmd = CommandRequest.objects.get(pk=command_id)
    except CommandRequest.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Command not found", "data": None},
            status=404,
        )

    if cmd.status != CommandRequest.Status.QUEUED:
        return JsonResponse(
            {
                "success": False,
                "message": f"Cannot cancel command with status: {cmd.get_status_display()}",
                "data": None,
            },
            status=409,
        )

    cmd.status = CommandRequest.Status.CANCELLED
    cmd.completed_at = timezone.now()
    cmd.save(update_fields=["status", "completed_at"])

    return JsonResponse({
        "success": True,
        "message": "Command cancelled",
        "data": _command_to_dict(cmd),
    })


@csrf_exempt
@require_GET
@require_api_key
def agent_status(request: HttpRequest) -> JsonResponse:
    """Get the current agent online/offline status."""
    agents = AgentStatus.objects.select_related("agent_token").order_by("-connected_at")
    agent_data = []
    for a in agents:
        agent_data.append({
            "name": a.agent_token.name,
            "is_online": a.is_online,
            "machine_name": a.machine_name,
            "last_heartbeat": a.last_heartbeat.isoformat() if a.last_heartbeat else None,
            "connected_at": a.connected_at.isoformat() if a.connected_at else None,
            "disconnected_at": a.disconnected_at.isoformat() if a.disconnected_at else None,
            "active_sessions": a.active_sessions,
        })

    response = JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "agents": agent_data,
            "any_online": any(a.is_online for a in agents),
        },
    })
    response["Cache-Control"] = "no-store"
    return response


@csrf_exempt
@require_GET
@require_api_key
def session_output(request: HttpRequest, session_id: str) -> JsonResponse:
    """Return all captured output lines for a session (for command history)."""
    lines = (
        SessionOutputBuffer.objects.filter(session_id=session_id)
        .order_by("line_number")[:500]
    )
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "session_id": session_id,
            "lines": [
                {
                    "line": line.line_number,
                    "content": line.content,
                    "stream": line.stream,
                }
                for line in lines
            ],
        },
    })


@csrf_exempt
@require_GET
@require_api_key
def stream_output(request: HttpRequest, session_id: str) -> StreamingHttpResponse:
    """SSE endpoint for streaming session output."""
    last_event_id = request.headers.get("Last-Event-ID", "0")
    try:
        last_line = int(last_event_id)
    except ValueError:
        last_line = 0

    def event_stream():
        current_line = last_line
        idle_count = 0
        max_idle = 300  # 5 minutes of no data → stop

        while idle_count < max_idle:
            lines = (
                SessionOutputBuffer.objects.filter(
                    session_id=session_id,
                    line_number__gt=current_line,
                )
                .order_by("line_number")[:50]
            )
            lines = list(lines)

            if lines:
                idle_count = 0
                for line in lines:
                    current_line = line.line_number
                    data = json.dumps({
                        "line": line.line_number,
                        "content": line.content,
                        "stream": line.stream,
                        "timestamp": line.timestamp.isoformat(),
                    })
                    yield f"id: {line.line_number}\nevent: output\ndata: {data}\n\n"
            else:
                idle_count += 1
                yield ": heartbeat\n\n"
                time.sleep(1)

        yield "event: timeout\ndata: {}\n\n"

    response = StreamingHttpResponse(
        event_stream(),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@csrf_exempt
@require_http_methods(["POST"])
@require_api_key
@ratelimit(key="user", rate="120/m", method="POST", block=True)
def output_push(request: HttpRequest, session_id: str) -> JsonResponse:
    """Accept output lines from the CLI --track mode and store in SessionOutputBuffer.

    This endpoint is CLI-only — requires X-API-Key header, rejects browser-session auth.
    """
    # Enforce API-key-only auth: reject requests that only have a browser session
    if not request.headers.get("X-API-Key"):
        return JsonResponse(
            {"success": False, "message": "API key required", "data": None},
            status=403,
        )

    from sessions.models import AgentSession

    try:
        sid = int(session_id)
    except (ValueError, TypeError):
        return JsonResponse(
            {"success": False, "message": "Invalid session ID", "data": None},
            status=400,
        )
    # AgentSession has no per-user ownership — access is gated by API key auth.
    if not AgentSession.objects.filter(pk=sid).exists():
        return JsonResponse(
            {"success": False, "message": "Session not found", "data": None},
            status=404,
        )

    body, err = parse_json_body(request)
    if err:
        return err
    assert body is not None

    # Support both single line and batch push
    lines = body.get("lines")
    if lines is not None:
        if not isinstance(lines, list):
            return JsonResponse(
                {"success": False, "message": "lines must be a list", "data": None},
                status=400,
            )
    else:
        # Single line format
        line_number = body.get("line_number")
        content = body.get("content")
        stream = body.get("stream", "stdout")

        if line_number is None or content is None:
            return JsonResponse(
                {"success": False, "message": "line_number and content are required", "data": None},
                status=400,
            )

        lines = [{"line_number": line_number, "content": content, "stream": stream}]

    valid_streams = {s.value for s in SessionOutputBuffer.Stream}
    session_id_str = str(sid)
    created = 0
    for item in lines:
        if not isinstance(item, dict):
            continue
        ln = item.get("line_number")
        ct = item.get("content", "")
        st = item.get("stream", "stdout")
        if ln is None or not isinstance(ln, int):
            continue
        if st not in valid_streams:
            st = "stdout"
        _, was_created = SessionOutputBuffer.objects.get_or_create(
            session_id=session_id_str,
            line_number=ln,
            defaults={"content": ct, "stream": st},
        )
        if was_created:
            created += 1

    return JsonResponse({
        "success": True,
        "message": f"{created} line(s) stored",
        "data": {"session_id": session_id_str, "lines_stored": created},
    })


@csrf_exempt
@require_http_methods(["POST"])
@require_api_key
def kill_all(request: HttpRequest) -> JsonResponse:
    """Emergency kill switch — cancel all pending commands and tell agent to kill all."""
    # Cancel all non-terminal commands
    now = timezone.now()
    updated = CommandRequest.objects.filter(
        status__in=[
            CommandRequest.Status.QUEUED,
            CommandRequest.Status.SENT,
            CommandRequest.Status.RUNNING,
        ]
    ).update(status=CommandRequest.Status.CANCELLED, completed_at=now)

    # Send kill_all to agent
    agent = _get_online_agent()
    sent = False
    if agent:
        kill_cmd = CommandRequest.objects.create(
            command_type=CommandRequest.CommandType.KILL_ALL,
            payload={},
            hmac_signature=_sign_payload({}),
            created_by=request.user,
            status=CommandRequest.Status.SENT,
            sent_at=now,
        )
        sent = _push_to_agent(agent, kill_cmd)

    return JsonResponse({
        "success": True,
        "message": f"Cancelled {updated} commands" + (", kill signal sent" if sent else ""),
        "data": {
            "cancelled_count": updated,
            "kill_sent": sent,
        },
    })


# -- Page views --


@require_GET
@login_required
def control_page(request: HttpRequest) -> HttpResponse:
    """Main remote control page."""
    return render(request, "remote/control.html")


@require_GET
@login_required
def session_detail_page(request: HttpRequest, session_id: str) -> HttpResponse:
    """Session output detail page."""
    return render(request, "remote/session_detail.html", {"session_id": session_id})


@require_GET
@login_required
def notifications_page(request: HttpRequest) -> HttpResponse:
    """Push notification preferences page."""
    from .models import PushSubscription

    subscriptions = PushSubscription.objects.filter(user=request.user)
    vapid_public = getattr(settings, "VAPID_PUBLIC_KEY", "")
    return render(request, "remote/notifications.html", {
        "subscriptions": subscriptions,
        "vapid_public_key": vapid_public,
    })


@csrf_exempt
@require_http_methods(["POST"])
@require_api_key
def push_subscribe(request: HttpRequest) -> JsonResponse:
    """Subscribe to push notifications."""
    from .models import PushSubscription

    body, err = parse_json_body(request)
    if err:
        return err
    assert body is not None

    endpoint = body.get("endpoint", "")
    p256dh = body.get("keys", {}).get("p256dh", "")
    auth = body.get("keys", {}).get("auth", "")

    if not endpoint or not p256dh or not auth:
        return JsonResponse(
            {"success": False, "message": "Missing subscription fields", "data": None},
            status=400,
        )

    PushSubscription.objects.update_or_create(
        user=request.user,
        endpoint=endpoint,
        defaults={"p256dh": p256dh, "auth": auth},
    )

    return JsonResponse({
        "success": True,
        "message": "Push subscription saved",
        "data": None,
    })


@csrf_exempt
@require_http_methods(["POST"])
@require_api_key
def push_unsubscribe(request: HttpRequest) -> JsonResponse:
    """Unsubscribe from push notifications."""
    from .models import PushSubscription

    body, err = parse_json_body(request)
    if err:
        return err
    assert body is not None

    endpoint = body.get("endpoint", "")
    deleted, _ = PushSubscription.objects.filter(
        user=request.user, endpoint=endpoint
    ).delete()

    return JsonResponse({
        "success": True,
        "message": f"Removed {deleted} subscription(s)",
        "data": None,
    })


# -- Chat / Conversation views --


def _conversation_to_dict(conv: ConversationThread) -> dict[str, Any]:
    return {
        "id": conv.pk,
        "repo": conv.repo,
        "title": conv.title,
        "session_id": conv.session_id,
        "is_active": conv.is_active,
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
    }


@require_GET
@login_required
def chat_page(request: HttpRequest) -> HttpResponse:
    """Chat-style interface for Claude Code conversations."""
    conversation_id = request.GET.get("c")
    return render(request, "remote/chat.html", {
        "initial_conversation_id": conversation_id or "",
    })


@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_api_key
@ratelimit(key="user", rate="10/m", method="POST", block=True)
def conversation_list_create(request: HttpRequest) -> JsonResponse:
    """List conversations or create a new one with first prompt."""
    if request.method == "GET":
        return _list_conversations(request)
    return _create_conversation(request)


def _list_conversations(request: HttpRequest) -> JsonResponse:
    qs = ConversationThread.objects.filter(created_by=request.user).order_by("-updated_at")

    try:
        limit = int(request.GET.get("limit", 20))
    except ValueError:
        return JsonResponse(
            {"success": False, "message": "limit must be an integer", "data": None},
            status=400,
        )
    limit = max(1, min(limit, 50))

    conversations = qs[:limit]
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "conversations": [_conversation_to_dict(c) for c in conversations],
        },
    })


def _create_conversation(request: HttpRequest) -> JsonResponse:
    body, err = parse_json_body(request)
    if err:
        return err
    assert body is not None

    repo = body.get("repo", "")
    prompt = body.get("prompt", "")

    if not repo or not prompt:
        return JsonResponse(
            {"success": False, "message": "repo and prompt are required", "data": None},
            status=400,
        )

    # Create conversation
    title = prompt[:80] + ("..." if len(prompt) > 80 else "")
    conv = ConversationThread.objects.create(
        repo=repo,
        title=title,
        created_by=request.user,
    )

    # Create and dispatch start_session command
    payload = {"repo": repo, "prompt": prompt}
    signature = _sign_payload(payload)
    cmd = CommandRequest.objects.create(
        command_type=CommandRequest.CommandType.START_SESSION,
        payload=payload,
        hmac_signature=signature,
        created_by=request.user,
        conversation=conv,
    )

    agent = _get_online_agent()
    if agent and _push_to_agent(agent, cmd):
        cmd.status = CommandRequest.Status.SENT
        cmd.sent_at = timezone.now()
        cmd.save(update_fields=["status", "sent_at"])

    return JsonResponse({
        "success": True,
        "message": "Conversation started",
        "data": {
            "conversation": _conversation_to_dict(conv),
            "command": _command_to_dict(cmd),
        },
    }, status=201)


@csrf_exempt
@require_GET
@require_api_key
def conversation_detail(request: HttpRequest, conversation_id: int) -> JsonResponse:
    """Get a conversation with its commands."""
    try:
        conv = ConversationThread.objects.get(pk=conversation_id, created_by=request.user)
    except ConversationThread.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Conversation not found", "data": None},
            status=404,
        )

    commands = conv.commands.order_by("created_at")
    cmd_list = [_command_to_dict(c) for c in commands]

    # If conversation has a session_id, include output lines
    output_lines: list[dict] = []
    if conv.session_id:
        lines = (
            SessionOutputBuffer.objects.filter(session_id=conv.session_id)
            .order_by("line_number")[:1000]
        )
        output_lines = [
            {"line": row.line_number, "content": row.content, "stream": row.stream}
            for row in lines
        ]

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "conversation": _conversation_to_dict(conv),
            "commands": cmd_list,
            "output_lines": output_lines,
        },
    })


@csrf_exempt
@require_http_methods(["POST"])
@require_api_key
@ratelimit(key="user", rate="10/m", method="POST", block=True)
def conversation_send(request: HttpRequest, conversation_id: int) -> JsonResponse:
    """Send a follow-up prompt in an existing conversation."""
    try:
        conv = ConversationThread.objects.get(pk=conversation_id, created_by=request.user)
    except ConversationThread.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Conversation not found", "data": None},
            status=404,
        )

    if not conv.session_id:
        return JsonResponse(
            {"success": False, "message": "Conversation has no active session yet", "data": None},
            status=409,
        )

    body, err = parse_json_body(request)
    if err:
        return err
    assert body is not None

    prompt = body.get("prompt", "")
    if not prompt:
        return JsonResponse(
            {"success": False, "message": "prompt is required", "data": None},
            status=400,
        )

    payload = {"session_id": conv.session_id, "prompt": prompt}
    signature = _sign_payload(payload)
    cmd = CommandRequest.objects.create(
        command_type=CommandRequest.CommandType.SEND_PROMPT,
        payload=payload,
        hmac_signature=signature,
        created_by=request.user,
        conversation=conv,
        session_id=conv.session_id,
    )

    # Update conversation timestamp
    conv.save(update_fields=["updated_at"])

    agent = _get_online_agent()
    if agent and _push_to_agent(agent, cmd):
        cmd.status = CommandRequest.Status.SENT
        cmd.sent_at = timezone.now()
        cmd.save(update_fields=["status", "sent_at"])

    return JsonResponse({
        "success": True,
        "message": "Prompt sent",
        "data": {"command": _command_to_dict(cmd)},
    }, status=201)
