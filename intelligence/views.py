"""Views for the Intelligence layer."""
from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, transaction
from django.http import (
    HttpRequest,
    HttpResponse,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from core.auth import require_api_key

from .models import (
    AdvisorConversation,
    AdvisorMessage,
    BusinessSnapshot,
    PredictiveAlert,
    SmartWatchEvent,
    SmartWatchRule,
)

logger = logging.getLogger(__name__)


# ──────────────── Executive Dashboard ────────────────


@require_GET
@login_required
def executive_dashboard(request: HttpRequest) -> HttpResponse:
    """Executive dashboard — single-page, four-quadrant overview."""
    from .executive import get_executive_data

    try:
        data = get_executive_data()
    except DatabaseError as exc:
        logger.warning("Executive dashboard data error: %s", exc)
        data = {
            "financial": {},
            "development": {},
            "operations": {},
            "growth": {},
        }
    return render(request, "intelligence/executive.html", {"exec_data": data})


@csrf_exempt
@require_GET
@require_api_key
def executive_api(request: HttpRequest) -> JsonResponse:
    """API endpoint for executive dashboard data."""
    from .executive import get_executive_data

    try:
        data = get_executive_data()
    except DatabaseError as exc:
        logger.warning("Executive API error: %s", exc)
        return JsonResponse(
            {"success": False, "message": "Unable to load executive data", "data": None},
            status=500,
        )
    return JsonResponse({"success": True, "message": "ok", "data": data})


# ──────────────── AI Advisor ────────────────


@require_GET
@login_required
def advisor_page(request: HttpRequest) -> HttpResponse:
    """AI Business Advisor chat interface."""
    conversations = AdvisorConversation.objects.filter(
        owner=request.user,
    ).order_by("-updated_at", "-pk")[:20]
    return render(request, "intelligence/advisor.html", {
        "conversations": conversations,
    })


@csrf_exempt
@require_GET
@require_api_key
def conversations_list_api(request: HttpRequest) -> JsonResponse:
    """List advisor conversations scoped to the requesting user."""
    convos = AdvisorConversation.objects.filter(
        owner=request.user,
    ).order_by("-updated_at", "-pk")[:50]
    data = [
        {
            "id": c.pk,
            "title": c.title or f"Conversation {c.pk}",
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
            "message_count": c.messages.count(),
        }
        for c in convos
    ]
    return JsonResponse({"success": True, "message": "ok", "data": data})


@csrf_exempt
@require_GET
@require_api_key
def conversation_detail_api(request: HttpRequest, pk: int) -> JsonResponse:
    """Get conversation with messages — scoped to requesting user."""
    convo = get_object_or_404(AdvisorConversation, pk=pk, owner=request.user)
    messages = convo.messages.order_by("created_at", "pk")
    data = {
        "id": convo.pk,
        "title": convo.title or f"Conversation {convo.pk}",
        "messages": [
            {
                "id": m.pk,
                "role": m.role,
                "content": m.content,
                "tokens_used": m.tokens_used,
                "cost": str(m.cost),
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }
    return JsonResponse({"success": True, "message": "ok", "data": data})


@csrf_exempt
@require_POST
@require_api_key
def advisor_chat_api(request: HttpRequest) -> HttpResponse:
    """Send a message to the AI advisor and get a response."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse(
            {"success": False, "message": "Invalid JSON body", "data": None},
            status=400,
        )

    user_message = body.get("message", "").strip()
    raw_conversation_id = body.get("conversation_id")

    if not user_message:
        return JsonResponse(
            {"success": False, "message": "Message is required", "data": None},
            status=400,
        )

    # Validate conversation_id
    conversation_id: int | None = None
    if raw_conversation_id not in (None, ""):
        try:
            conversation_id = int(raw_conversation_id)
        except (TypeError, ValueError):
            return JsonResponse(
                {"success": False, "message": "conversation_id must be an integer", "data": None},
                status=400,
            )

    # Get or create conversation — scoped to requesting user
    if conversation_id is not None:
        try:
            with transaction.atomic():
                conversation = AdvisorConversation.objects.select_for_update().get(
                    pk=conversation_id, owner=request.user,
                )
                AdvisorMessage.objects.create(
                    conversation=conversation,
                    role="user",
                    content=user_message,
                )
        except AdvisorConversation.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Conversation not found", "data": None},
                status=404,
            )
    else:
        with transaction.atomic():
            title = user_message[:100] + ("..." if len(user_message) > 100 else "")
            conversation = AdvisorConversation.objects.create(
                title=title, owner=request.user,
            )
            AdvisorMessage.objects.create(
                conversation=conversation,
                role="user",
                content=user_message,
            )

    # Build message history
    history = list(
        conversation.messages.order_by("created_at", "pk")
        .values("role", "content")
    )

    # Get latest snapshot for system prompt
    snapshot = BusinessSnapshot.objects.order_by("-date").first()
    system_prompt = _build_advisor_system_prompt(snapshot)

    # Convert to API format
    api_messages = [{"role": m["role"], "content": m["content"]} for m in history]

    # Define tools for live data queries
    tools = _get_advisor_tools()

    # Call AI
    from . import ai_client
    result = ai_client.chat(
        messages=api_messages,
        system=system_prompt,
        tools=tools,
        max_tokens=4096,
    )

    if result is None:
        # API unavailable — return graceful fallback
        fallback = (
            "I'm unable to connect to the AI service right now. "
            "Please check that ANTHROPIC_API_KEY is configured and try again."
        )
        with transaction.atomic():
            AdvisorMessage.objects.create(
                conversation=conversation,
                role="assistant",
                content=fallback,
            )
        return JsonResponse({
            "success": True,
            "message": "ok",
            "data": {
                "conversation_id": conversation.pk,
                "response": fallback,
                "tokens_used": 0,
                "cost": "0.000000",
            },
        })

    # Handle tool use loop
    response_content = result["content"]
    total_input = result["input_tokens"]
    total_output = result["output_tokens"]

    if result["tool_uses"]:
        # Process tool calls and continue conversation
        response_content, extra_input, extra_output = _process_tool_calls(
            api_messages, system_prompt, tools, result,
        )
        total_input += extra_input
        total_output += extra_output

    total_cost = ai_client.calculate_cost(total_input, total_output)

    # Save assistant response
    with transaction.atomic():
        AdvisorMessage.objects.create(
            conversation=conversation,
            role="assistant",
            content=response_content,
            tokens_used=total_input + total_output,
            cost=total_cost,
        )

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "conversation_id": conversation.pk,
            "response": response_content,
            "tokens_used": total_input + total_output,
            "cost": str(total_cost),
        },
    })


def _build_advisor_system_prompt(snapshot: BusinessSnapshot | None) -> str:
    """Build the system prompt for the AI advisor."""
    base = (
        "You are the AI Business Advisor for Nock Technologies, a bootstrapped "
        "commercial finance technology company founded by Kevin Wills.\n\n"
        "You have access to real business data and can answer questions about "
        "finances, CRM deals, development velocity, operations, and strategy.\n\n"
        "Guidelines:\n"
        "- Be concise and specific — use real numbers\n"
        "- Flag anything concerning proactively\n"
        "- Give actionable recommendations\n"
        "- If you need more specific data, use the available tools\n"
        "- Format responses in clean markdown\n"
    )

    if snapshot:
        base += (
            f"\n\n## Current Business Data (as of {snapshot.date})\n\n"
            f"{snapshot.content}"
        )
    else:
        base += (
            "\n\nNote: No business snapshot is available yet. "
            "Use the tools to query live data when needed."
        )

    return base


def _get_advisor_tools() -> list[dict]:
    """Define tools the AI advisor can use for live data queries."""
    return [
        {
            "name": "get_expenses",
            "description": "Get expense records, optionally filtered by date range and category",
            "input_schema": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default 30)",
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by category (software, hardware, infrastructure, etc.)",
                    },
                },
            },
        },
        {
            "name": "get_deals",
            "description": "Get CRM deals, optionally filtered by stage",
            "input_schema": {
                "type": "object",
                "properties": {
                    "stage": {
                        "type": "string",
                        "description": "Filter by stage (prospect, contacted, proposal, negotiation, active, closed_won, closed_lost)",
                    },
                },
            },
        },
        {
            "name": "get_pr_history",
            "description": "Get pull request history for a given number of days",
            "input_schema": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default 14)",
                    },
                },
            },
        },
        {
            "name": "get_tasks",
            "description": "Get Asana tasks, optionally filtered by status",
            "input_schema": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter: 'overdue', 'due_this_week', 'completed_this_week', or 'all'",
                    },
                },
            },
        },
    ]


def _execute_tool(name: str, input_data: dict) -> str:
    """Execute an advisor tool and return JSON string result."""
    from datetime import timedelta

    now = timezone.now()
    today = now.date()

    if name == "get_expenses":
        from spend.models import Expense

        try:
            days = max(1, min(int(input_data.get("days", 30)), 365))
        except (TypeError, ValueError):
            days = 30
        qs = Expense.objects.filter(
            date__gte=today - timedelta(days=days),
        ).order_by("-date")
        category = input_data.get("category")
        if category:
            qs = qs.filter(category=category)
        expenses = [
            {
                "vendor": e.vendor,
                "description": e.description[:100],
                "category": e.category,
                "total": str(e.total),
                "is_refund": e.is_refund,
                "date": str(e.date),
            }
            for e in qs[:50]
        ]
        return json.dumps({"count": len(expenses), "expenses": expenses})

    if name == "get_deals":
        from crm.models import Deal

        qs = Deal.objects.select_related("contact").order_by("-updated_at")
        stage = input_data.get("stage")
        if stage:
            qs = qs.filter(stage=stage)
        deals = [
            {
                "title": d.title,
                "stage": d.stage,
                "contact": d.contact.name if d.contact else None,
                "estimated_value": str(d.estimated_value or 0),
                "next_action": d.next_action,
                "next_action_date": str(d.next_action_date) if d.next_action_date else None,
                "updated_at": str(d.updated_at.date()),
            }
            for d in qs[:30]
        ]
        return json.dumps({"count": len(deals), "deals": deals})

    if name == "get_pr_history":
        from pipeline.models import PullRequest

        try:
            days = max(1, min(int(input_data.get("days", 14)), 365))
        except (TypeError, ValueError):
            days = 14
        since = now - timedelta(days=days)
        prs = PullRequest.objects.filter(
            merged_at__gte=since, state="merged",
        ).select_related("repository").order_by("-merged_at")
        pr_data = [
            {
                "number": p.number,
                "title": p.title,
                "repo": p.repository.name if p.repository else "unknown",
                "merged_at": str(p.merged_at.date()) if p.merged_at else None,
                "author": p.author,
            }
            for p in prs[:50]
        ]
        return json.dumps({"count": len(pr_data), "prs": pr_data})

    if name == "get_tasks":
        from tasks.models import AsanaTask

        status = input_data.get("status", "all")
        if status == "overdue":
            qs = AsanaTask.objects.filter(
                completed=False, due_on__lt=today, due_on__isnull=False,
            )
        elif status == "due_this_week":
            qs = AsanaTask.objects.filter(
                completed=False,
                due_on__gte=today,
                due_on__lte=today + timedelta(days=7),
            )
        elif status == "completed_this_week":
            qs = AsanaTask.objects.filter(
                completed=True,
                completed_at__date__gte=today - timedelta(days=7),
            )
        else:
            # "all" — return all tasks (completed and incomplete)
            qs = AsanaTask.objects.all()
        qs = qs.order_by("due_on", "pk")
        tasks = [
            {
                "name": t.name,
                "project": t.project.name if t.project else None,
                "due_on": str(t.due_on) if t.due_on else None,
                "completed": t.completed,
                "priority": t.priority,
            }
            for t in qs[:30]
        ]
        return json.dumps({"count": len(tasks), "tasks": tasks})

    return json.dumps({"error": f"Unknown tool: {name}"})


def _process_tool_calls(
    messages: list[dict],
    system: str,
    tools: list[dict],
    initial_result: dict,
    max_rounds: int = 3,
) -> tuple[str, int, int]:
    """Process tool use in a loop, returning final text response.

    Returns (content, total_input_tokens, total_output_tokens).
    """
    from . import ai_client

    total_input = 0
    total_output = 0

    current_result = initial_result
    # Build up messages with tool results
    extended_messages = list(messages)

    for _round in range(max_rounds):
        if not current_result["tool_uses"]:
            break

        # Add assistant message with tool use
        assistant_content = []
        if current_result["content"]:
            assistant_content.append({
                "type": "text",
                "text": current_result["content"],
            })
        for tu in current_result["tool_uses"]:
            assistant_content.append({
                "type": "tool_use",
                "id": tu["id"],
                "name": tu["name"],
                "input": tu["input"],
            })

        extended_messages.append({
            "role": "assistant",
            "content": assistant_content,
        })

        # Execute tools and add results
        tool_results = []
        for tu in current_result["tool_uses"]:
            result_str = _execute_tool(tu["name"], tu["input"])
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": result_str,
            })

        extended_messages.append({
            "role": "user",
            "content": tool_results,
        })

        # Call AI again
        current_result = ai_client.chat(
            messages=extended_messages,
            system=system,
            tools=tools,
            max_tokens=4096,
        )
        if current_result is None:
            return "I encountered an error processing the data. Please try again.", total_input, total_output

        total_input += current_result["input_tokens"]
        total_output += current_result["output_tokens"]

    return current_result["content"], total_input, total_output


# ──────────────── Snapshot API ────────────────


@csrf_exempt
@require_GET
@require_api_key
def snapshot_latest_api(request: HttpRequest) -> JsonResponse:
    """Get the latest business snapshot."""
    snapshot = BusinessSnapshot.objects.order_by("-date").first()
    if not snapshot:
        return JsonResponse({
            "success": True,
            "message": "No snapshot available",
            "data": None,
        })
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "date": str(snapshot.date),
            "content": snapshot.content,
            "token_count": snapshot.token_count,
            "generated_at": snapshot.generated_at.isoformat(),
        },
    })


@csrf_exempt
@require_POST
@require_api_key
def snapshot_generate_api(request: HttpRequest) -> JsonResponse:
    """Force-regenerate the business snapshot (staff only)."""
    if not request.user.is_staff:
        return JsonResponse(
            {"success": False, "message": "Forbidden", "data": None},
            status=403,
        )
    from .tasks import generate_business_snapshot

    generate_business_snapshot.delay()
    return JsonResponse({"success": True, "message": "Snapshot generation started", "data": None})


@csrf_exempt
@require_POST
@require_api_key
def memo_generate_api(request: HttpRequest) -> JsonResponse:
    """Force-generate a weekly strategy memo (staff only)."""
    if not request.user.is_staff:
        return JsonResponse(
            {"success": False, "message": "Forbidden", "data": None},
            status=403,
        )
    from .tasks import generate_weekly_memo

    generate_weekly_memo.delay()
    return JsonResponse({
        "success": True,
        "message": "Weekly memo generation started",
        "data": None,
    })


# ──────────────── Alerts ────────────────


@csrf_exempt
@require_GET
@require_api_key
def alerts_api(request: HttpRequest) -> JsonResponse:
    """JSON API for mobile — returns predictive alerts."""
    category = request.GET.get("category", "")
    severity = request.GET.get("severity", "")
    resolved = request.GET.get("resolved", "")

    alerts = PredictiveAlert.objects.order_by("-created_at", "-pk")
    if category:
        alerts = alerts.filter(category=category)
    if severity:
        alerts = alerts.filter(severity=severity)
    if resolved == "true":
        alerts = alerts.filter(is_resolved=True)
    elif resolved == "false" or not resolved:
        alerts = alerts.filter(is_resolved=False)

    data = [
        {
            "id": a.pk,
            "title": a.title,
            "message": a.message,
            "category": a.category,
            "severity": a.severity,
            "is_resolved": a.is_resolved,
            "resolved": a.is_resolved,
            "created_at": a.created_at.isoformat(),
            "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        }
        for a in alerts[:50]
    ]
    return JsonResponse({"success": True, "message": "ok", "data": data})


@require_GET
@login_required
def alerts_page(request: HttpRequest) -> HttpResponse:
    """Predictive alerts page — active and recent."""
    category = request.GET.get("category", "")
    severity = request.GET.get("severity", "")

    alerts = PredictiveAlert.objects.order_by("-created_at", "-pk")
    if category:
        alerts = alerts.filter(category=category)
    if severity:
        alerts = alerts.filter(severity=severity)

    active_alerts = alerts.filter(is_resolved=False)
    resolved_alerts = alerts.filter(is_resolved=True)[:20]

    return render(request, "intelligence/alerts.html", {
        "active_alerts": active_alerts,
        "resolved_alerts": resolved_alerts,
        "selected_category": category,
        "selected_severity": severity,
        "categories": PredictiveAlert.Category.choices,
        "severities": PredictiveAlert.Severity.choices,
    })


# ──────────────── Smart Watch ────────────────


@csrf_exempt
@require_GET
@require_api_key
def smart_watch_rules_list(request: HttpRequest) -> JsonResponse:
    """List all Smart Watch rules."""
    rules = SmartWatchRule.objects.all()
    data = [
        {
            "id": r.pk,
            "name": r.name,
            "condition_type": r.condition_type,
            "threshold_minutes": r.threshold_minutes,
            "threshold_value": r.threshold_value,
            "severity": r.severity,
            "enabled": r.enabled,
            "send_telegram": r.send_telegram,
            "cooldown_minutes": r.cooldown_minutes,
            "last_triggered": r.last_triggered.isoformat() if r.last_triggered else None,
            "trigger_count": r.trigger_count,
            "in_cooldown": r.in_cooldown,
        }
        for r in rules
    ]
    return JsonResponse({"success": True, "message": "ok", "data": data})


@csrf_exempt
@require_POST
@require_api_key
def smart_watch_rules_create(request: HttpRequest) -> JsonResponse:
    """Create a new Smart Watch rule (staff only)."""
    if not request.user.is_staff:
        return JsonResponse(
            {"success": False, "message": "Forbidden", "data": None},
            status=403,
        )
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse(
            {"success": False, "message": "Invalid JSON body", "data": None},
            status=400,
        )

    name = body.get("name", "").strip()
    condition_type = body.get("condition_type", "")

    if not name or not condition_type:
        return JsonResponse(
            {"success": False, "message": "name and condition_type are required", "data": None},
            status=400,
        )

    valid_types = [c[0] for c in SmartWatchRule.ConditionType.choices]
    if condition_type not in valid_types:
        return JsonResponse(
            {"success": False, "message": f"Invalid condition_type. Valid: {valid_types}", "data": None},
            status=400,
        )

    if SmartWatchRule.objects.filter(name=name).exists():
        return JsonResponse(
            {"success": False, "message": f"Rule with name '{name}' already exists", "data": None},
            status=409,
        )

    rule = SmartWatchRule.objects.create(
        name=name,
        condition_type=condition_type,
        threshold_minutes=body.get("threshold_minutes", 240),
        threshold_value=body.get("threshold_value", 75),
        severity=body.get("severity", "warning"),
        message_template=body.get("message_template", "\u26a0\ufe0f Smart Watch alert: {name}"),
        enabled=body.get("enabled", True),
        send_telegram=body.get("send_telegram", True),
        send_slack=body.get("send_slack", False),
        cooldown_minutes=body.get("cooldown_minutes", 60),
    )
    return JsonResponse({
        "success": True,
        "message": "Rule created",
        "data": {"id": rule.pk, "name": rule.name},
    }, status=201)


@csrf_exempt
@require_api_key
def smart_watch_rules_update(request: HttpRequest, pk: int) -> JsonResponse:
    """Update a Smart Watch rule (PUT only, staff only)."""
    if not request.user.is_staff:
        return JsonResponse(
            {"success": False, "message": "Forbidden", "data": None},
            status=403,
        )
    if request.method != "PUT":
        return JsonResponse(
            {"success": False, "message": "Method not allowed", "data": None},
            status=405,
        )

    try:
        rule = SmartWatchRule.objects.get(pk=pk)
    except SmartWatchRule.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Rule not found", "data": None},
            status=404,
        )

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse(
            {"success": False, "message": "Invalid JSON body", "data": None},
            status=400,
        )

    updatable = [
        "name", "threshold_minutes", "threshold_value", "severity",
        "message_template", "enabled", "send_telegram", "send_slack",
        "cooldown_minutes",
    ]
    updated_fields = []
    for field in updatable:
        if field in body:
            setattr(rule, field, body[field])
            updated_fields.append(field)

    if updated_fields:
        rule.save(update_fields=updated_fields + ["updated_at"])

    return JsonResponse({
        "success": True,
        "message": f"Updated {len(updated_fields)} field(s)",
        "data": {"id": rule.pk, "name": rule.name, "updated": updated_fields},
    })


@csrf_exempt
@require_GET
@require_api_key
def smart_watch_events_list(request: HttpRequest) -> JsonResponse:
    """List recent Smart Watch events (last 50)."""
    events = SmartWatchEvent.objects.select_related("rule").order_by("-created_at", "-pk")[:50]
    data = [
        {
            "id": e.pk,
            "rule_name": e.rule.name,
            "message": e.message,
            "severity": e.severity,
            "context": e.context,
            "notified": e.notified,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]
    return JsonResponse({"success": True, "message": "ok", "data": data})


@csrf_exempt
@require_POST
@require_api_key
def smart_watch_force_tick(request: HttpRequest) -> JsonResponse:
    """Force a Smart Watch tick right now (staff only)."""
    if not request.user.is_staff:
        return JsonResponse(
            {"success": False, "message": "Forbidden", "data": None},
            status=403,
        )
    from .tasks import smart_watch_tick

    result = smart_watch_tick()
    return JsonResponse({"success": True, "message": "Tick completed", "data": result})


@csrf_exempt
@require_GET
@require_api_key
def smart_watch_status(request: HttpRequest) -> JsonResponse:
    """Smart Watch summary — rule count, events today, last tick time."""
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

    total_rules = SmartWatchRule.objects.count()
    enabled_rules = SmartWatchRule.objects.filter(enabled=True).count()
    events_today = SmartWatchEvent.objects.filter(created_at__gte=today_start).count()

    last_event = SmartWatchEvent.objects.order_by("-created_at", "-pk").first()

    # Use django_celery_beat's last run time if available, else fall back to last event
    last_tick = None
    try:
        from django_celery_beat.models import PeriodicTask
        beat_task = PeriodicTask.objects.filter(
            task="intelligence.tasks.smart_watch_tick",
        ).order_by("pk").first()
        if beat_task and beat_task.last_run_at:
            last_tick = beat_task.last_run_at.isoformat()
    except ImportError:
        pass
    if not last_tick and last_event:
        last_tick = last_event.created_at.isoformat()

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "total_rules": total_rules,
            "enabled_rules": enabled_rules,
            "events_today": events_today,
            "last_event_at": last_event.created_at.isoformat() if last_event else None,
            "last_tick_at": last_tick,
        },
    })
