import contextlib
import hashlib
import hmac
import json
import logging
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from core.auth import require_api_key
from core.utils import parse_json_body

from .models import PipelineEvent, PullRequest, Repository, ReviewAlert
from .tasks import (
    process_check_run,
    process_pull_request_event,
    process_pull_request_review,
    process_push,
)

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(ratelimit(key="ip", rate="60/m", method="POST", block=True), name="dispatch")
class GitHubWebhookView(View):
    def post(self, request: HttpRequest) -> JsonResponse:
        event_type = request.headers.get("X-GitHub-Event")
        delivery_id = request.headers.get("X-GitHub-Delivery", "")
        signature = request.headers.get("X-Hub-Signature-256", "")

        if not event_type:
            return JsonResponse(
                {"success": False, "message": "Missing X-GitHub-Event header", "data": {}},
                status=400,
            )

        # Ping is sent on webhook registration — no signature or delivery check needed
        if event_type == "ping":
            logger.info("GitHub ping received (delivery=%s)", delivery_id)
            return JsonResponse({"success": True, "message": "pong", "data": {}})

        if not delivery_id:
            return JsonResponse(
                {"success": False, "message": "Missing X-GitHub-Delivery header", "data": {}},
                status=400,
            )

        if not signature:
            logger.warning("Webhook received without signature (delivery=%s)", delivery_id)
            return JsonResponse(
                {"success": False, "message": "Missing signature", "data": {}},
                status=403,
            )

        raw_body = request.body

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            return JsonResponse(
                {"success": False, "message": "Invalid JSON", "data": {}},
                status=400,
            )

        repo_data = payload.get("repository", {})
        full_name = repo_data.get("full_name", "")
        owner, _, name = full_name.partition("/")

        try:
            repo = Repository.objects.get(owner=owner, name=name, is_active=True)
        except Repository.DoesNotExist:
            logger.info("Webhook for untracked repo %s (delivery=%s)", full_name, delivery_id)
            return JsonResponse(
                {"success": False, "message": "Repository not tracked", "data": {}},
                status=404,
            )

        # Timing-safe HMAC-SHA256 signature verification
        expected = "sha256=" + hmac.new(
            repo.webhook_secret.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            logger.warning(
                "Invalid webhook signature for %s (delivery=%s)", full_name, delivery_id
            )
            return JsonResponse(
                {"success": False, "message": "Invalid signature", "data": {}},
                status=403,
            )

        logger.info(
            "Webhook received: event=%s repo=%s delivery=%s",
            event_type,
            full_name,
            delivery_id,
        )

        self._route(event_type, payload, delivery_id)

        return JsonResponse({"success": True, "message": "accepted", "data": {}})

    def _route(self, event_type: str, payload: dict, delivery_id: str) -> None:
        if event_type == "pull_request":
            action = payload.get("action", "")
            process_pull_request_event.delay(payload, action, delivery_id)
        elif event_type == "pull_request_review":
            process_pull_request_review.delay(payload, delivery_id)
        elif event_type == "check_run":
            process_check_run.delay(payload, delivery_id)
        elif event_type == "push":
            process_push.delay(payload, delivery_id)
        else:
            logger.debug("Unhandled event type: %s", event_type)


@login_required
def pipeline_list(request: HttpRequest) -> HttpResponse:
    from .filters import PullRequestFilter

    qs = (
        PullRequest.tenant_objects.for_request(request).select_related("repository")
        .order_by("-opened_at")
    )
    f = PullRequestFilter(request.GET, queryset=qs)

    # Sort param
    sort = request.GET.get("sort", "-opened_at")
    allowed_sorts = {"opened_at", "-opened_at", "number", "-number", "state", "-state"}
    prs = f.qs.order_by(sort) if sort in allowed_sorts else f.qs

    # Build query string without sort param to avoid duplicate sort= in links
    params_without_sort = request.GET.copy()
    params_without_sort.pop("sort", None)
    query_without_sort = params_without_sort.urlencode()

    return render(request, "pipeline/list.html", {
        "filter": f,
        "prs": prs,
        "sort": sort,
        "repos": Repository.tenant_objects.for_request(request).filter(is_active=True).order_by("owner", "name"),
        "query_without_sort": query_without_sort,
    })


@login_required
def pr_detail(request: HttpRequest, repo_owner: str, repo_name: str, pr_number: int) -> HttpResponse:
    repo = get_object_or_404(Repository.tenant_objects.for_request(request), owner=repo_owner, name=repo_name)
    pr = get_object_or_404(
        PullRequest.tenant_objects.for_request(request).select_related("repository"),
        repository=repo,
        number=pr_number,
    )
    events = pr.events.order_by("created_at")
    return render(request, "pipeline/detail.html", {"pr": pr, "events": events})


@csrf_exempt
@require_GET
@require_api_key
def pipeline_prs_api(request: HttpRequest) -> JsonResponse:
    """JSON API for CLI — returns list of PRs with filters."""
    qs = PullRequest.objects.select_related("repository").order_by("-opened_at")

    repo_filter = request.GET.get("repo", "")
    if repo_filter:
        qs = qs.filter(repository__name=repo_filter)

    state_filter = request.GET.get("state", "")
    if state_filter:
        qs = qs.filter(state=state_filter)

    MAX_PR_LIMIT = 100
    try:
        limit = int(request.GET.get("limit", 20))
    except ValueError:
        return JsonResponse(
            {"success": False, "message": "limit must be an integer", "data": None},
            status=400,
        )
    limit = max(1, min(limit, MAX_PR_LIMIT))

    prs = qs[:limit]

    data = [
        {
            "number": pr.number,
            "title": pr.title,
            "repository": str(pr.repository),
            "branch": pr.branch,
            "author": pr.author,
            "state": pr.state,
            "ci_status": pr.ci_status,
            "coderabbit_status": pr.coderabbit_status,
            "opened_at": pr.opened_at.isoformat() if pr.opened_at else None,
            "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
        }
        for pr in prs
    ]

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {"total": qs.count(), "prs": data},
    })


@csrf_exempt
@require_GET
@require_api_key
def review_alerts_list(request: HttpRequest) -> JsonResponse:
    """List review alerts with optional filters."""
    qs = ReviewAlert.objects.order_by("-created_at")

    repo = request.GET.get("repo", "")
    if repo:
        qs = qs.filter(repo=repo)

    pr_number = request.GET.get("pr_number", "")
    if pr_number:
        with contextlib.suppress(ValueError):
            qs = qs.filter(pr_number=int(pr_number))

    reviewer = request.GET.get("reviewer", "")
    if reviewer:
        qs = qs.filter(reviewer=reviewer)

    is_read = request.GET.get("is_read", "")
    if is_read == "true":
        qs = qs.filter(is_read=True)
    elif is_read == "false":
        qs = qs.filter(is_read=False)

    MAX_ALERT_LIMIT = 100
    try:
        limit = int(request.GET.get("limit", 25))
    except ValueError:
        limit = 25
    limit = max(1, min(limit, MAX_ALERT_LIMIT))

    alerts = qs[:limit]
    data = [
        {
            "id": a.id,
            "repo": a.repo,
            "pr_number": a.pr_number,
            "pr_title": a.pr_title,
            "pr_url": a.pr_url,
            "branch": a.branch,
            "reviewer": a.reviewer,
            "reviewer_login": a.reviewer_login,
            "status": a.status,
            "body_preview": a.body_preview,
            "is_read": a.is_read,
            "created_at": a.created_at.isoformat(),
        }
        for a in alerts
    ]
    return JsonResponse({"success": True, "message": "ok", "data": {"alerts": data}})


@csrf_exempt
@require_POST
@require_api_key
def review_alerts_read(request: HttpRequest) -> JsonResponse:
    """Mark review alerts as read."""
    body, err = parse_json_body(request)
    if err:
        return err

    if body.get("all"):
        count = ReviewAlert.objects.filter(is_read=False).update(is_read=True)
        return JsonResponse({"success": True, "message": "ok", "data": {"marked": count}})

    ids = body.get("ids", [])
    if not isinstance(ids, list) or not ids:
        return JsonResponse(
            {"success": False, "message": "Provide 'ids' list or 'all': true", "data": None},
            status=400,
        )

    try:
        validated_ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "message": "'ids' must be a list of integers", "data": None},
            status=400,
        )

    count = ReviewAlert.objects.filter(id__in=validated_ids, is_read=False).update(is_read=True)
    return JsonResponse({"success": True, "message": "ok", "data": {"marked": count}})


@csrf_exempt
@require_GET
@require_api_key
def review_alerts_summary(request: HttpRequest) -> JsonResponse:
    """Unread count + grouped by PR for Nerve Center panel."""
    unread = ReviewAlert.objects.filter(is_read=False)
    unread_count = unread.count()

    recent = unread.order_by("-created_at")[:10]
    alerts = [
        {
            "id": a.id,
            "repo": a.repo,
            "pr_number": a.pr_number,
            "pr_title": a.pr_title,
            "pr_url": a.pr_url,
            "reviewer": a.reviewer,
            "status": a.status,
            "created_at": a.created_at.isoformat(),
        }
        for a in recent
    ]

    # Group counts by PR
    by_pr = (
        unread.values("repo", "pr_number", "pr_title")
        .annotate(alert_count=Count("id"))
        .order_by("-alert_count")[:10]
    )
    grouped = [
        {
            "repo": g["repo"],
            "pr_number": g["pr_number"],
            "pr_title": g["pr_title"],
            "alert_count": g["alert_count"],
        }
        for g in by_pr
    ]

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "unread_count": unread_count,
            "alerts": alerts,
            "by_pr": grouped,
        },
    })


@csrf_exempt
@require_POST
@require_api_key
def telegram_test(request: HttpRequest) -> JsonResponse:
    """Send a test Telegram notification."""
    from core.telegram import TelegramNotifier

    result = TelegramNotifier.send("\u2705 NockCC test notification — Telegram is working!")
    if result and result.get("ok"):
        return JsonResponse({"success": True, "message": "Test message sent", "data": None})
    return JsonResponse(
        {"success": False, "message": "Failed to send test message", "data": None},
        status=502,
    )


# ---------------------------------------------------------------------------
# Pipeline Event Log
# ---------------------------------------------------------------------------


def _event_to_dict(event: PipelineEvent) -> dict:
    return {
        "id": str(event.id),
        "created_at": event.created_at.isoformat(),
        "workflow_id": event.workflow_id,
        "repo": event.repo,
        "category": event.category,
        "severity": event.severity,
        "title": event.title,
        "details": event.details,
        "lane": event.lane,
        "agent": event.agent,
        "pr_number": event.pr_number,
        "branch": event.branch,
        "asana_task_id": event.asana_task_id,
        "duration_seconds": event.duration_seconds,
        "token_count": event.token_count,
        "files_changed": event.files_changed,
        "test_count": event.test_count,
    }


def _safe_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


@csrf_exempt
@require_POST
@require_api_key
def log_event(request: HttpRequest) -> JsonResponse:
    """Log a pipeline event. Called by Kit via curl during builds."""
    if len(request.body) > 65_536:
        return JsonResponse(
            {"success": False, "message": "Request body too large", "data": None},
            status=413,
        )

    body, err = parse_json_body(request)
    if err:
        return err

    workflow_id = (body.get("workflow_id") or "").strip()[:200]
    repo = (body.get("repo") or "").strip()[:100]
    category = (body.get("category") or "").strip()
    title = (body.get("title") or "").strip()[:200]

    if not all([workflow_id, repo, category, title]):
        return JsonResponse(
            {"success": False, "message": "workflow_id, repo, category, and title are required", "data": None},
            status=400,
        )

    valid_categories = {c.value for c in PipelineEvent.Category}
    if category not in valid_categories:
        return JsonResponse(
            {
                "success": False,
                "message": f"Invalid category '{category}'. Must be one of: {', '.join(sorted(valid_categories))}",
                "data": None,
            },
            status=400,
        )

    severity = (body.get("severity") or "info").strip()
    valid_severities = {s.value for s in PipelineEvent.Severity}
    if severity not in valid_severities:
        return JsonResponse(
            {
                "success": False,
                "message": f"Invalid severity '{severity}'. Must be one of: {', '.join(sorted(valid_severities))}",
                "data": None,
            },
            status=400,
        )

    lane = (body.get("lane") or "manual").strip()
    if lane not in {la.value for la in PipelineEvent.Lane}:
        lane = "manual"

    agent = (body.get("agent") or "kit").strip()
    if agent not in {a.value for a in PipelineEvent.Agent}:
        agent = "kit"

    event = PipelineEvent.objects.create(
        workflow_id=workflow_id,
        repo=repo,
        category=category,
        severity=severity,
        title=title,
        details=(body.get("details") or "").strip(),
        lane=lane,
        agent=agent,
        pr_number=_safe_int(body.get("pr_number")),
        branch=(body.get("branch") or "").strip()[:200],
        asana_task_id=(body.get("asana_task_id") or "").strip()[:50],
        duration_seconds=_safe_int(body.get("duration_seconds")),
        token_count=_safe_int(body.get("token_count")),
        files_changed=_safe_int(body.get("files_changed")),
        test_count=_safe_int(body.get("test_count")),
    )

    return JsonResponse(
        {"success": True, "message": "Event logged", "data": _event_to_dict(event)},
        status=201,
    )


@csrf_exempt
@require_GET
@require_api_key
def list_events(request: HttpRequest) -> JsonResponse:
    """Query pipeline events with filters."""
    qs = PipelineEvent.objects.order_by("-created_at")

    workflow_id = request.GET.get("workflow_id", "")
    if workflow_id:
        qs = qs.filter(workflow_id=workflow_id)

    repo = request.GET.get("repo", "")
    if repo:
        qs = qs.filter(repo=repo)

    category = request.GET.get("category", "")
    if category:
        qs = qs.filter(category=category)

    severity = request.GET.get("severity", "")
    if severity:
        qs = qs.filter(severity__in=severity.split(","))

    lane = request.GET.get("lane", "")
    if lane:
        qs = qs.filter(lane=lane)

    agent = request.GET.get("agent", "")
    if agent:
        qs = qs.filter(agent=agent)

    since = request.GET.get("since", "")
    if since:
        dt = parse_datetime(since)
        if dt:
            qs = qs.filter(created_at__gte=dt)

    MAX_EVENT_LIMIT = 200
    try:
        limit = int(request.GET.get("limit", 50))
    except ValueError:
        limit = 50
    limit = max(1, min(limit, MAX_EVENT_LIMIT))

    events = list(qs[:limit])

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {"count": len(events), "events": [_event_to_dict(e) for e in events]},
    })


@csrf_exempt
@require_GET
@require_api_key
def event_summary(request: HttpRequest) -> JsonResponse:
    """Aggregated event summary for morning notes and Telegram alerts."""
    hours = 24
    with contextlib.suppress(ValueError):
        hours = max(1, min(int(request.GET.get("hours", 24)), 720))

    since = timezone.now() - timedelta(hours=hours)
    qs = PipelineEvent.objects.filter(created_at__gte=since)

    total = qs.count()

    by_category = dict(
        qs.values_list("category")
        .annotate(count=Count("id"))
        .order_by("category")
    )

    by_severity = dict(
        qs.values_list("severity")
        .annotate(count=Count("id"))
        .order_by("severity")
    )

    errors = [
        _event_to_dict(e)
        for e in qs.filter(severity__in=["error", "critical"]).order_by("-created_at")[:10]
    ]

    escalations = [
        _event_to_dict(e)
        for e in qs.filter(category="escalation").order_by("-created_at")[:10]
    ]

    prs_opened = [
        _event_to_dict(e)
        for e in qs.filter(category="pr", title__icontains="opened").order_by("-created_at")[:10]
    ]

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "period_hours": hours,
            "total": total,
            "by_category": by_category,
            "by_severity": by_severity,
            "errors": errors,
            "escalations": escalations,
            "prs_opened": prs_opened,
        },
    })
