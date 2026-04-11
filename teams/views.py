import logging

from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.db.models import Avg, ExpressionWrapper, F, fields
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from core.auth import require_api_key
from core.telegram import TelegramNotifier
from core.utils import parse_json_body

from .models import AgentTeam, PromptExecution, PromptFile, TeamEvent, TeamMember, TeamTask

logger = logging.getLogger(__name__)

MAX_BODY_SIZE = 32_768  # 32 KB


def _check_body_size(request: HttpRequest) -> JsonResponse | None:
    if len(request.body) > MAX_BODY_SIZE:
        return JsonResponse(
            {"success": False, "message": "Request body too large", "data": None},
            status=400,
        )
    return None


def _team_to_dict(team: AgentTeam) -> dict:
    return {
        "id": team.id,
        "name": team.name,
        "mission": team.mission,
        "status": team.status,
        "member_count": team.member_count,
        "task_summary": team.task_summary,
        "created_at": team.created_at.isoformat(),
        "updated_at": team.updated_at.isoformat(),
    }


def _member_to_dict(member: TeamMember) -> dict:
    return {
        "id": member.id,
        "agent_name": member.agent_name,
        "role": member.role,
        "is_online": member.is_online,
        "last_heartbeat": member.last_heartbeat.isoformat() if member.last_heartbeat else None,
        "current_task": member.current_task.title if member.current_task else None,
        "agent_token_id": member.agent_token_id,
    }


def _task_to_dict(task: TeamTask) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority_label,
        "assigned_to": task.assigned_to.agent_name if task.assigned_to else None,
        "assigned_to_id": task.assigned_to_id,
        "repo": task.repo,
        "branch": task.branch,
        "pr_number": task.pr_number,
        "pr_url": task.pr_url,
        "context_brief_scope": task.context_brief_scope,
        "is_blocked": task.is_blocked,
        "depends_on": list(task.depends_on.values_list("id", flat=True)),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def _event_to_dict(event: TeamEvent) -> dict:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "description": event.description,
        "task_id": event.task_id,
        "member_id": event.member_id,
        "created_at": event.created_at.isoformat(),
    }


def _notify_team(message: str) -> None:
    """Send Telegram notification, swallowing errors."""
    try:
        TelegramNotifier.send(message)
    except (OSError, ValueError) as exc:
        logger.warning("Telegram notification failed for team event: %s", exc)


def _resolve_dependents(task: TeamTask) -> None:
    """After a task completes, unblock any dependents whose deps are all done."""
    notifications: list[str] = []
    dependents = TeamTask.objects.filter(depends_on=task).order_by("pk")
    for dep in dependents:
        if not dep.depends_on.exclude(status="completed").exists() and dep.status == "blocked":
                dep.status = "assigned" if dep.assigned_to else "pending"
                dep.save(update_fields=["status", "updated_at"])
                TeamEvent.objects.create(
                    team=dep.team,
                    event_type="task_unblocked",
                    description=f"Task unblocked: {dep.title}",
                    task=dep,
                    member=dep.assigned_to,
                )
                agent_name = dep.assigned_to.agent_name if dep.assigned_to else "unassigned"
                notifications.append(f"\U0001f513 Task unblocked: \"{dep.title}\" — ready for {agent_name}")
    # Defer Telegram notifications until after the transaction commits
    for msg in notifications:
        transaction.on_commit(lambda m=msg: _notify_team(m))


# ──────────────────────────────────────────────────────────────
# Team CRUD
# ──────────────────────────────────────────────────────────────


@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_api_key
def teams_list_create(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        qs = AgentTeam.objects.all()
        status_filter = request.GET.get("status", "")
        if status_filter:
            qs = qs.filter(status=status_filter)
        teams = [_team_to_dict(t) for t in qs]
        return JsonResponse({"success": True, "message": "ok", "data": {"teams": teams}})

    # POST — create team
    size_err = _check_body_size(request)
    if size_err:
        return size_err
    body, err = parse_json_body(request)
    if err:
        return err

    name = (body.get("name") or "").strip()[:200]
    mission = (body.get("mission") or "").strip()
    if not name or not mission:
        return JsonResponse(
            {"success": False, "message": "name and mission are required", "data": None},
            status=400,
        )

    team = AgentTeam.objects.create(name=name, mission=mission)
    return JsonResponse(
        {"success": True, "message": "Team created", "data": _team_to_dict(team)},
        status=201,
    )


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
@require_api_key
def team_detail(request: HttpRequest, team_id: int) -> JsonResponse:
    team = get_object_or_404(AgentTeam, pk=team_id)

    if request.method == "GET":
        data = _team_to_dict(team)
        data["members"] = [_member_to_dict(m) for m in team.members.all()]
        data["recent_events"] = [_event_to_dict(e) for e in team.events.all()[:20]]
        return JsonResponse({"success": True, "message": "ok", "data": data})

    if request.method == "PUT":
        size_err = _check_body_size(request)
        if size_err:
            return size_err
        body, err = parse_json_body(request)
        if err:
            return err

        update_fields = ["updated_at"]
        if "name" in body:
            team.name = (body["name"] or "").strip()[:200]
            update_fields.append("name")
        if "mission" in body:
            team.mission = (body["mission"] or "").strip()
            update_fields.append("mission")
        if "status" in body:
            valid = {c[0] for c in AgentTeam.STATUS_CHOICES}
            if body["status"] in valid:
                old_status = team.status
                team.status = body["status"]
                update_fields.append("status")
                if old_status != team.status:
                    if team.status == "active":
                        TeamEvent.objects.create(
                            team=team, event_type="mission_started",
                            description=f"Mission started: {team.name}",
                        )
                        _notify_team(f"\U0001f680 Mission started: \"{team.name}\"")
                    elif team.status == "completed":
                        summary = team.task_summary
                        TeamEvent.objects.create(
                            team=team, event_type="mission_completed",
                            description=f"Mission complete: {team.name} — {summary['completed']}/{summary['total']} tasks",
                        )
                        _notify_team(f"\U0001f3c1 Mission complete: \"{team.name}\" — {summary['completed']} tasks done")

        team.save(update_fields=update_fields)
        return JsonResponse({"success": True, "message": "Team updated", "data": _team_to_dict(team)})

    # DELETE — soft delete (set status=completed)
    team.status = "completed"
    team.save(update_fields=["status", "updated_at"])
    return JsonResponse({"success": True, "message": "Team archived", "data": None})


# ──────────────────────────────────────────────────────────────
# Members
# ──────────────────────────────────────────────────────────────


@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_api_key
def members_list_create(request: HttpRequest, team_id: int) -> JsonResponse:
    team = get_object_or_404(AgentTeam, pk=team_id)

    if request.method == "GET":
        members = [_member_to_dict(m) for m in team.members.all()]
        return JsonResponse({"success": True, "message": "ok", "data": {"members": members}})

    size_err = _check_body_size(request)
    if size_err:
        return size_err
    body, err = parse_json_body(request)
    if err:
        return err

    agent_name = (body.get("agent_name") or "").strip()[:100]
    if not agent_name:
        return JsonResponse(
            {"success": False, "message": "agent_name is required", "data": None},
            status=400,
        )

    role = body.get("role", "worker")
    valid_roles = {c[0] for c in TeamMember.ROLE_CHOICES}
    if role not in valid_roles:
        role = "worker"

    if team.members.filter(agent_name=agent_name).exists():
        return JsonResponse(
            {"success": False, "message": f"Agent '{agent_name}' already on this team", "data": None},
            status=409,
        )

    agent_token_id = body.get("agent_token_id")
    member = TeamMember.objects.create(
        team=team, agent_name=agent_name, role=role,
        agent_token_id=agent_token_id,
    )
    TeamEvent.objects.create(
        team=team, event_type="agent_joined",
        description=f"{agent_name} joined as {role}",
        member=member,
    )
    return JsonResponse(
        {"success": True, "message": "Member added", "data": _member_to_dict(member)},
        status=201,
    )


@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
@require_api_key
def member_detail(request: HttpRequest, team_id: int, member_id: int) -> JsonResponse:
    team = get_object_or_404(AgentTeam, pk=team_id)
    member = get_object_or_404(TeamMember, pk=member_id, team=team)

    if request.method == "PUT":
        size_err = _check_body_size(request)
        if size_err:
            return size_err
        body, err = parse_json_body(request)
        if err:
            return err

        update_fields = []
        if "role" in body:
            valid_roles = {c[0] for c in TeamMember.ROLE_CHOICES}
            if body["role"] in valid_roles:
                member.role = body["role"]
                update_fields.append("role")
        if "agent_token_id" in body:
            member.agent_token_id = body["agent_token_id"]
            update_fields.append("agent_token_id")

        if update_fields:
            member.save(update_fields=update_fields)
        return JsonResponse({"success": True, "message": "Member updated", "data": _member_to_dict(member)})

    # DELETE
    TeamEvent.objects.create(
        team=team, event_type="agent_left",
        description=f"{member.agent_name} removed from team",
    )
    member.delete()
    return JsonResponse({"success": True, "message": "Member removed", "data": None})


# ──────────────────────────────────────────────────────────────
# Tasks
# ──────────────────────────────────────────────────────────────


@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_api_key
def tasks_list_create(request: HttpRequest, team_id: int) -> JsonResponse:
    team = get_object_or_404(AgentTeam, pk=team_id)

    if request.method == "GET":
        qs = team.tasks.all()
        status_filter = request.GET.get("status", "")
        if status_filter:
            qs = qs.filter(status=status_filter)
        priority_filter = request.GET.get("priority", "")
        if priority_filter:
            mapped = TeamTask.PRIORITY_MAP.get(priority_filter)
            if mapped is not None:
                qs = qs.filter(priority=mapped)
        assigned_filter = request.GET.get("assigned_to", "")
        if assigned_filter:
            qs = qs.filter(assigned_to_id=assigned_filter)
        tasks = [_task_to_dict(t) for t in qs]
        return JsonResponse({"success": True, "message": "ok", "data": {"tasks": tasks}})

    size_err = _check_body_size(request)
    if size_err:
        return size_err
    body, err = parse_json_body(request)
    if err:
        return err

    title = (body.get("title") or "").strip()[:500]
    if not title:
        return JsonResponse(
            {"success": False, "message": "title is required", "data": None},
            status=400,
        )

    priority_str = body.get("priority", "medium")
    priority = TeamTask.PRIORITY_MAP.get(priority_str, TeamTask.PRIORITY_MEDIUM)

    assigned_to_id = body.get("assigned_to")
    assigned_member = None
    if assigned_to_id:
        assigned_member = team.members.filter(pk=assigned_to_id).first()

    task = TeamTask.objects.create(
        team=team,
        title=title,
        description=(body.get("description") or "").strip(),
        priority=priority,
        assigned_to=assigned_member,
        repo=(body.get("repo") or "").strip()[:200],
        branch=(body.get("branch") or "").strip()[:200],
        context_brief_scope=(body.get("context_brief_scope") or "").strip()[:50],
        status="assigned" if assigned_member else "pending",
    )

    # Handle depends_on
    depends_on_ids = body.get("depends_on", [])
    if isinstance(depends_on_ids, list) and depends_on_ids:
        deps = TeamTask.objects.filter(pk__in=depends_on_ids, team=team)
        task.depends_on.set(deps)
        if task.is_blocked:
            task.status = "blocked"
            task.save(update_fields=["status"])

    if assigned_member:
        TeamEvent.objects.create(
            team=team, event_type="task_assigned",
            description=f"Task \"{title}\" assigned to {assigned_member.agent_name}",
            task=task, member=assigned_member,
        )

    return JsonResponse(
        {"success": True, "message": "Task created", "data": _task_to_dict(task)},
        status=201,
    )


@csrf_exempt
@require_http_methods(["GET", "PUT"])
@require_api_key
def task_detail(request: HttpRequest, team_id: int, task_id: int) -> JsonResponse:
    team = get_object_or_404(AgentTeam, pk=team_id)
    task = get_object_or_404(TeamTask, pk=task_id, team=team)

    if request.method == "GET":
        data = _task_to_dict(task)
        data["events"] = [
            _event_to_dict(e) for e in TeamEvent.objects.filter(task=task).order_by("-created_at")[:20]
        ]
        return JsonResponse({"success": True, "message": "ok", "data": data})

    size_err = _check_body_size(request)
    if size_err:
        return size_err
    body, err = parse_json_body(request)
    if err:
        return err

    update_fields = ["updated_at"]
    if "status" in body:
        # Only allow safe status updates via PUT; use /start/ and /complete/ for lifecycle transitions
        safe_statuses = {"pending", "assigned", "blocked", "in_review"}
        if body["status"] in safe_statuses:
            task.status = body["status"]
            update_fields.append("status")
    if "assigned_to" in body:
        if body["assigned_to"]:
            member = team.members.filter(pk=body["assigned_to"]).first()
            if member:
                task.assigned_to = member
                update_fields.append("assigned_to_id")
        else:
            task.assigned_to = None
            update_fields.append("assigned_to_id")
    if "pr_number" in body:
        task.pr_number = body["pr_number"]
        update_fields.append("pr_number")
    if "pr_url" in body:
        task.pr_url = (body["pr_url"] or "")[:500]
        update_fields.append("pr_url")
    if "branch" in body:
        task.branch = (body["branch"] or "")[:200]
        update_fields.append("branch")
    if "priority" in body:
        mapped = TeamTask.PRIORITY_MAP.get(body["priority"])
        if mapped is not None:
            task.priority = mapped
            update_fields.append("priority")

    task.save(update_fields=update_fields)
    return JsonResponse({"success": True, "message": "Task updated", "data": _task_to_dict(task)})


@csrf_exempt
@require_http_methods(["POST"])
@require_api_key
def task_start(request: HttpRequest, team_id: int, task_id: int) -> JsonResponse:
    team = get_object_or_404(AgentTeam, pk=team_id)

    with transaction.atomic():
        task = get_object_or_404(TeamTask.objects.select_for_update(), pk=task_id, team=team)

        # Validate status transition
        if task.status not in ("pending", "assigned"):
            return JsonResponse(
                {"success": False, "message": f"Cannot start task in '{task.status}' status", "data": None},
                status=409,
            )

        # Check dependencies under lock
        blocking = list(task.blocking_tasks.values_list("title", flat=True))
        if blocking:
            return JsonResponse(
                {
                    "success": False,
                    "message": f"Cannot start — blocked by: {', '.join(blocking)}",
                    "data": {"blocking_tasks": blocking},
                },
                status=409,
            )

        task.status = "in_progress"
        task.started_at = timezone.now()
        task.save(update_fields=["status", "started_at", "updated_at"])

        TeamEvent.objects.create(
            team=team, event_type="task_started",
            description=f"Task started: {task.title}",
            task=task, member=task.assigned_to,
        )

        if task.assigned_to:
            task.assigned_to.current_task = task
            task.assigned_to.save(update_fields=["current_task"])

    return JsonResponse({"success": True, "message": "Task started", "data": _task_to_dict(task)})


@csrf_exempt
@require_http_methods(["POST"])
@require_api_key
def task_complete(request: HttpRequest, team_id: int, task_id: int) -> JsonResponse:
    team = get_object_or_404(AgentTeam, pk=team_id)

    with transaction.atomic():
        task = get_object_or_404(TeamTask.objects.select_for_update(), pk=task_id, team=team)

        if task.status == "completed":
            return JsonResponse(
                {"success": False, "message": "Task already completed", "data": None},
                status=409,
            )

        task.status = "completed"
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "completed_at", "updated_at"])

        agent_name = task.assigned_to.agent_name if task.assigned_to else "unassigned"
        TeamEvent.objects.create(
            team=team, event_type="task_completed",
            description=f"Task completed: {task.title} by {agent_name}",
            task=task, member=task.assigned_to,
        )

        if task.assigned_to and task.assigned_to.current_task_id == task.id:
            task.assigned_to.current_task = None
            task.assigned_to.save(update_fields=["current_task"])

        _resolve_dependents(task)

    _notify_team(f"\u2705 Task completed: \"{task.title}\" by {agent_name}")

    # Check if all tasks are done → mission complete (with row lock to prevent race)
    with transaction.atomic():
        team_locked = AgentTeam.objects.select_for_update().get(pk=team.pk)
        summary = team_locked.task_summary
        if summary["total"] > 0 and summary["completed"] == summary["total"] and team_locked.status != "completed":
            team_locked.status = "completed"
            team_locked.save(update_fields=["status", "updated_at"])
            TeamEvent.objects.create(
                team=team_locked, event_type="mission_completed",
                description=f"All {summary['total']} tasks complete — mission done",
            )
            _notify_team(f"\U0001f3c1 Mission complete: \"{team_locked.name}\" — {summary['total']} tasks done")

    return JsonResponse({"success": True, "message": "Task completed", "data": _task_to_dict(task)})


# ──────────────────────────────────────────────────────────────
# Events
# ──────────────────────────────────────────────────────────────


@csrf_exempt
@require_GET
@require_api_key
def events_list(request: HttpRequest, team_id: int) -> JsonResponse:
    team = get_object_or_404(AgentTeam, pk=team_id)
    events = team.events.all()[:50]
    data = [_event_to_dict(e) for e in events]
    return JsonResponse({"success": True, "message": "ok", "data": {"events": data}})


# ──────────────────────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────────────────────


@csrf_exempt
@require_GET
@require_api_key
def active_teams(request: HttpRequest) -> JsonResponse:
    """All active teams with summary — for Nerve Center panel."""
    teams = AgentTeam.objects.filter(status="active")
    data = [_team_to_dict(t) for t in teams]
    return JsonResponse({"success": True, "message": "ok", "data": {"teams": data}})


# ──────────────────────────────────────────────────────────────
# Page views
# ──────────────────────────────────────────────────────────────


@login_required
def teams_page(request: HttpRequest) -> HttpResponse:
    """Teams deep dive page."""
    teams = AgentTeam.objects.exclude(status="completed").order_by("-updated_at")
    return render(request, "teams/index.html", {"teams": teams})


def _safe_int(value: object, default: int) -> int:
    """Coerce to int or return default — avoids ValueError on bad input."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


# ──────────────────────────────────────────────────────────────
# Prompt serializers
# ──────────────────────────────────────────────────────────────


def _prompt_to_dict(prompt: PromptFile, *, include_content: bool = False) -> dict:
    data: dict = {
        "id": prompt.id,
        "title": prompt.title,
        "slug": prompt.slug,
        "target_repo": prompt.target_repo,
        "target_branch_prefix": prompt.target_branch_prefix,
        "complexity": prompt.complexity,
        "estimated_minutes": prompt.estimated_minutes,
        "status": prompt.status,
        "priority": prompt.priority,
        "tags": prompt.tags,
        "author": prompt.author,
        "version": prompt.version,
        "is_executable": prompt.is_executable,
        "expected_branch": prompt.expected_branch,
        "team_task_id": prompt.team_task_id,
        "executed_by": prompt.executed_by,
        "executed_at": prompt.executed_at.isoformat() if prompt.executed_at else None,
        "pr_number": prompt.pr_number,
        "pr_url": prompt.pr_url,
        "depends_on_prompts": list(prompt.depends_on_prompts.values_list("slug", flat=True)),
        "created_at": prompt.created_at.isoformat(),
        "updated_at": prompt.updated_at.isoformat(),
    }
    if include_content:
        data["content"] = prompt.content
        data["execution_notes"] = prompt.execution_notes
    return data


def _execution_to_dict(ex: PromptExecution) -> dict:
    return {
        "id": ex.id,
        "agent_name": ex.agent_name,
        "started_at": ex.started_at.isoformat(),
        "completed_at": ex.completed_at.isoformat() if ex.completed_at else None,
        "result": ex.result,
        "pr_number": ex.pr_number,
        "pr_url": ex.pr_url,
        "review_cycles": ex.review_cycles,
        "max_review_cycles": ex.max_review_cycles,
        "notes": ex.notes,
    }


def _resolve_template(prompt: PromptFile) -> str:
    """Resolve template variables in prompt content for agent consumption."""
    template = (
        "# PROMPT: {title}\n\n"
        "**Repo:** {target_repo}\n"
        "**Branch:** {branch} (from main)\n"
        "**PR Target:** main\n\n"
        "---\n\n"
        "## CONTEXT\n\n"
        "{content}\n\n"
        "## CONVENTIONS\n\n"
        "- Follow existing patterns in the repo\n"
        "- Run all tests before committing\n"
        "- Branch: `{branch}` from `main`\n\n"
        "## RUN PLUGINS BEFORE COMMITTING\n\n"
        "Run code-simplifier and security-guidance plugins before committing.\n"
    )
    return template.format(
        title=prompt.title,
        target_repo=prompt.target_repo,
        branch=prompt.expected_branch,
        content=prompt.content,
    )


# ──────────────────────────────────────────────────────────────
# Prompt CRUD
# ──────────────────────────────────────────────────────────────


@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_api_key
def prompts_list_create(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        qs = PromptFile.objects.all()
        if status := request.GET.get("status"):
            qs = qs.filter(status=status)
        if repo := request.GET.get("repo"):
            qs = qs.filter(target_repo__icontains=repo)
        if complexity := request.GET.get("complexity"):
            qs = qs.filter(complexity=complexity)
        if author := request.GET.get("author"):
            qs = qs.filter(author=author)
        if tag := request.GET.get("tag"):
            qs = qs.filter(tags__contains=tag)
        if search := request.GET.get("search"):
            qs = qs.filter(models.Q(title__icontains=search) | models.Q(tags__contains=search))
        prompts = [_prompt_to_dict(p) for p in qs]
        return JsonResponse({"success": True, "message": "ok", "data": {"prompts": prompts}})

    # POST — create prompt
    size_err = _check_body_size(request)
    if size_err:
        return size_err
    body, err = parse_json_body(request)
    if err:
        return err

    title = (body.get("title") or "").strip()[:300]
    content = (body.get("content") or "").strip()
    target_repo = (body.get("target_repo") or "").strip()[:200]
    if not title or not content or not target_repo:
        return JsonResponse(
            {"success": False, "message": "title, content, and target_repo are required", "data": None},
            status=400,
        )

    complexity = body.get("complexity", "standard")
    if complexity not in {c[0] for c in PromptFile.COMPLEXITY_CHOICES}:
        complexity = "standard"

    slug = (body.get("slug") or "").strip()[:100]
    if not slug:
        from django.utils.text import slugify
        slug = slugify(title)[:100]

    base_slug = slug
    counter = 1
    while PromptFile.objects.filter(slug=slug).exists():
        slug = f"{base_slug[:95]}-{counter}"
        counter += 1

    prompt = PromptFile.objects.create(
        title=title,
        slug=slug,
        content=content,
        target_repo=target_repo,
        target_branch_prefix=(body.get("target_branch_prefix") or "feature/").strip()[:100],
        complexity=complexity,
        estimated_minutes=_safe_int(body.get("estimated_minutes", 60), 60),
        priority=max(1, min(100, _safe_int(body.get("priority", 50), 50))),
        tags=body.get("tags", []) if isinstance(body.get("tags"), list) else [],
        author=(body.get("author") or "mara").strip()[:100],
        status=body.get("status", "draft") if body.get("status") in {"draft", "ready"} else "draft",
    )

    dep_slugs = body.get("depends_on_prompts", [])
    if isinstance(dep_slugs, list) and dep_slugs:
        deps = PromptFile.objects.filter(slug__in=dep_slugs)
        prompt.depends_on_prompts.set(deps)

    _notify_team(f"\U0001f4dd Prompt created: \"{prompt.title}\" ({prompt.complexity})")

    return JsonResponse(
        {"success": True, "message": "Prompt created", "data": _prompt_to_dict(prompt, include_content=True)},
        status=201,
    )


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
@require_api_key
def prompt_detail(request: HttpRequest, slug: str) -> JsonResponse:
    prompt = get_object_or_404(PromptFile, slug=slug)

    if request.method == "GET":
        data = _prompt_to_dict(prompt, include_content=True)
        data["executions"] = [_execution_to_dict(e) for e in prompt.executions.all()[:20]]
        return JsonResponse({"success": True, "message": "ok", "data": data})

    if request.method == "DELETE":
        prompt.status = "archived"
        prompt.save(update_fields=["status", "updated_at"])
        return JsonResponse({"success": True, "message": "Prompt archived", "data": None})

    # PUT
    size_err = _check_body_size(request)
    if size_err:
        return size_err
    body, err = parse_json_body(request)
    if err:
        return err

    update_fields = ["updated_at"]
    if "title" in body:
        prompt.title = (body["title"] or "").strip()[:300]
        update_fields.append("title")
    if "content" in body:
        prompt.content = (body["content"] or "").strip()
        update_fields.append("content")
    if "status" in body:
        valid = {c[0] for c in PromptFile.STATUS_CHOICES}
        if body["status"] in valid:
            prompt.status = body["status"]
            update_fields.append("status")
    if "priority" in body:
        try:
            prompt.priority = max(1, min(100, int(body["priority"])))
            update_fields.append("priority")
        except (TypeError, ValueError):
            pass
    if "complexity" in body and body["complexity"] in {c[0] for c in PromptFile.COMPLEXITY_CHOICES}:
        prompt.complexity = body["complexity"]
        update_fields.append("complexity")
    if "tags" in body and isinstance(body["tags"], list):
        prompt.tags = body["tags"]
        update_fields.append("tags")
    if "target_repo" in body:
        prompt.target_repo = (body["target_repo"] or "").strip()[:200]
        update_fields.append("target_repo")
    if "estimated_minutes" in body:
        try:
            prompt.estimated_minutes = int(body["estimated_minutes"])
            update_fields.append("estimated_minutes")
        except (TypeError, ValueError):
            pass

    prompt.save(update_fields=update_fields)
    return JsonResponse(
        {"success": True, "message": "Prompt updated", "data": _prompt_to_dict(prompt, include_content=True)}
    )


# ──────────────────────────────────────────────────────────────
# Queue Management
# ──────────────────────────────────────────────────────────────


@csrf_exempt
@require_GET
@require_api_key
def prompt_queue(request: HttpRequest) -> JsonResponse:
    """List executable prompts — status=ready with all dependencies met."""
    ready = PromptFile.objects.filter(status="ready").order_by("-priority", "created_at")
    executable = [p for p in ready if p.is_executable]
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {"prompts": [_prompt_to_dict(p) for p in executable]},
    })


@csrf_exempt
@require_http_methods(["POST"])
@require_api_key
def prompt_execute(request: HttpRequest, slug: str) -> JsonResponse:
    """Mark prompt as in_progress, create PromptExecution, return resolved content."""
    size_err = _check_body_size(request)
    if size_err:
        return size_err
    body, err = parse_json_body(request)
    if err:
        return err

    with transaction.atomic():
        prompt = get_object_or_404(PromptFile.objects.select_for_update(), slug=slug)

        if not prompt.is_executable:
            return JsonResponse(
                {"success": False, "message": f"Prompt not executable (status={prompt.status})", "data": None},
                status=409,
            )

        agent_name = (body.get("agent_name") or "").strip()[:100]
        if not agent_name:
            return JsonResponse(
                {"success": False, "message": "agent_name is required", "data": None},
                status=400,
            )

        prompt.status = "in_progress"
        prompt.executed_by = agent_name
        prompt.executed_at = timezone.now()
        prompt.save(update_fields=["status", "executed_by", "executed_at", "updated_at"])

        execution = PromptExecution.objects.create(prompt=prompt, agent_name=agent_name)

        if prompt.team_task_id:
            TeamTask.objects.filter(
                pk=prompt.team_task_id, status__in=("pending", "assigned"),
            ).update(status="in_progress", started_at=timezone.now())

    resolved = _resolve_template(prompt)
    _notify_team(f"\U0001f680 Prompt started: \"{prompt.title}\" by {agent_name}")

    data = _prompt_to_dict(prompt, include_content=True)
    data["resolved_content"] = resolved
    data["execution_id"] = execution.id
    return JsonResponse({"success": True, "message": "Prompt execution started", "data": data})


@csrf_exempt
@require_http_methods(["POST"])
@require_api_key
def prompt_complete(request: HttpRequest, slug: str) -> JsonResponse:
    """Mark prompt as completed, update execution record."""
    size_err = _check_body_size(request)
    if size_err:
        return size_err
    body, err = parse_json_body(request)
    if err:
        return err

    with transaction.atomic():
        prompt = get_object_or_404(PromptFile.objects.select_for_update(), slug=slug)

        if prompt.status not in ("in_progress", "queued"):
            return JsonResponse(
                {"success": False, "message": f"Cannot complete prompt in '{prompt.status}' status", "data": None},
                status=409,
            )

        prompt.status = "completed"
        update_fields = ["status", "updated_at"]

        if "pr_number" in body:
            prompt.pr_number = body["pr_number"]
            update_fields.append("pr_number")
        if "pr_url" in body:
            prompt.pr_url = (body["pr_url"] or "")[:500]
            update_fields.append("pr_url")
        if "execution_notes" in body:
            prompt.execution_notes = (body["execution_notes"] or "").strip()
            update_fields.append("execution_notes")

        prompt.save(update_fields=update_fields)

        execution = prompt.executions.order_by("-started_at").first()
        if execution:
            execution.result = "success"
            execution.completed_at = timezone.now()
            if prompt.pr_number:
                execution.pr_number = prompt.pr_number
                execution.pr_url = prompt.pr_url
            execution.save(update_fields=["result", "completed_at", "pr_number", "pr_url"])

        if prompt.team_task_id:
            task = TeamTask.objects.select_for_update().filter(
                pk=prompt.team_task_id,
            ).exclude(status="completed").first()
            if task:
                task.status = "completed"
                task.completed_at = timezone.now()
                if prompt.pr_number:
                    task.pr_number = prompt.pr_number
                    task.pr_url = prompt.pr_url
                task.save(update_fields=["status", "completed_at", "pr_number", "pr_url", "updated_at"])
                _resolve_dependents(task)

    pr_info = f" — PR #{prompt.pr_number}" if prompt.pr_number else ""
    _notify_team(f"\u2705 Prompt completed: \"{prompt.title}\"{pr_info}")

    for blocked in prompt.blocked_by.filter(status="ready"):
        if blocked.is_executable:
            transaction.on_commit(
                lambda t=blocked.title: _notify_team(f"\U0001f513 Prompt unblocked: \"{t}\" — ready for execution")
            )

    return JsonResponse(
        {"success": True, "message": "Prompt completed", "data": _prompt_to_dict(prompt, include_content=True)}
    )


@csrf_exempt
@require_http_methods(["POST"])
@require_api_key
def prompt_review(request: HttpRequest, slug: str) -> JsonResponse:
    """Log a review cycle on the prompt's current execution."""
    size_err = _check_body_size(request)
    if size_err:
        return size_err
    body, err = parse_json_body(request)
    if err:
        return err

    prompt = get_object_or_404(PromptFile, slug=slug)
    execution = prompt.executions.order_by("-started_at").first()
    if not execution:
        return JsonResponse(
            {"success": False, "message": "No active execution found", "data": None},
            status=404,
        )

    PromptExecution.objects.filter(pk=execution.pk).update(review_cycles=F("review_cycles") + 1)
    execution.refresh_from_db(fields=["review_cycles"])

    notes = (body.get("notes") or "").strip()
    if notes:
        execution.notes = f"{execution.notes}\n---\nCycle {execution.review_cycles}: {notes}".strip()
        execution.save(update_fields=["notes"])

    if execution.review_cycles >= execution.max_review_cycles:
        execution.result = "review_requested"
        execution.save(update_fields=["result"])
        _notify_team(f"\u26a0\ufe0f PR #{prompt.pr_number or '?'} exceeded max review cycles — needs review")
    else:
        _notify_team(
            f"\U0001f504 PR #{prompt.pr_number or '?'} needs revision "
            f"({execution.review_cycles}/{execution.max_review_cycles})"
        )

    return JsonResponse({
        "success": True,
        "message": "Review cycle logged",
        "data": _execution_to_dict(execution),
    })


@csrf_exempt
@require_GET
@require_api_key
def prompts_ready_for_kevin(request: HttpRequest) -> JsonResponse:
    """Prompts where execution is complete and all reviews passed."""
    completed = PromptFile.objects.filter(status="completed", pr_number__isnull=False).order_by("-updated_at")
    prompts = [_prompt_to_dict(p) for p in completed]
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {"prompts": prompts, "count": len(prompts)},
    })


@csrf_exempt
@require_GET
@require_api_key
def prompt_stats(request: HttpRequest) -> JsonResponse:
    """Queue depth, in-progress count, completed this week, avg execution time."""
    from datetime import timedelta
    now = timezone.now()
    week_ago = now - timedelta(days=7)

    ready_count = PromptFile.objects.filter(status="ready").count()
    in_progress = PromptFile.objects.filter(status="in_progress").count()
    completed_week = PromptFile.objects.filter(status="completed", updated_at__gte=week_ago).count()
    total = PromptFile.objects.exclude(status="archived").count()
    draft_count = PromptFile.objects.filter(status="draft").count()

    avg_minutes = None
    duration_expr = ExpressionWrapper(
        F("completed_at") - F("started_at"), output_field=fields.DurationField()
    )
    result = PromptExecution.objects.filter(
        result="success", completed_at__gte=week_ago, completed_at__isnull=False,
    ).annotate(duration=duration_expr).aggregate(avg_duration=Avg("duration"))
    if result["avg_duration"]:
        avg_minutes = round(result["avg_duration"].total_seconds() / 60, 1)

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "total": total,
            "draft": draft_count,
            "ready": ready_count,
            "in_progress": in_progress,
            "completed_this_week": completed_week,
            "avg_execution_minutes": avg_minutes,
        },
    })


# ──────────────────────────────────────────────────────────────
# Prompt Library page
# ──────────────────────────────────────────────────────────────


@login_required
def prompts_page(request: HttpRequest) -> HttpResponse:
    """Prompt library page."""
    return render(request, "teams/prompts.html")
