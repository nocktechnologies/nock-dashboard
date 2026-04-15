"""Smart Watch evaluator functions.

Each evaluator takes a SmartWatchRule and returns a list of
(message, context_dict) tuples — one per alert to fire.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

if TYPE_CHECKING:
    from .models import SmartWatchRule


def check_pr_waiting(rule: SmartWatchRule) -> list[tuple[str, dict]]:
    """PRs open longer than threshold_minutes without a review."""
    from pipeline.models import PullRequest, ReviewAlert

    cutoff = timezone.now() - timedelta(minutes=rule.threshold_minutes)

    open_prs = PullRequest.objects.filter(
        state="open",
        opened_at__lt=cutoff,
    ).select_related("repository").order_by("opened_at", "pk")

    # Key by (repo, pr_number) to avoid cross-repo collisions
    reviewed_pr_keys = set(
        ReviewAlert.objects.filter(
            pr_number__in=open_prs.values_list("number", flat=True),
        ).values_list("repo", "pr_number"),
    )

    alerts: list[tuple[str, dict]] = []
    for pr in open_prs:
        repo_name = pr.repository.name if pr.repository else "unknown"
        repo_full = f"{pr.repository.owner}/{repo_name}" if pr.repository else "unknown"
        if (repo_full, pr.number) in reviewed_pr_keys:
            continue
        hours_waiting = int(
            (timezone.now() - pr.opened_at).total_seconds() / 3600,
        )
        msg = rule.message_template.format(
            pr_number=pr.number,
            repo=repo_name,
            branch=pr.branch,
            name=rule.name,
            project=repo_name,
            task_name="",
            value=hours_waiting,
            threshold=rule.threshold_minutes // 60,
        )
        alerts.append((msg, {"pr_id": pr.id, "pr_number": pr.number, "repo": repo_name}))
    return alerts


def check_session_long(rule: SmartWatchRule) -> list[tuple[str, dict]]:
    """Active sessions running longer than threshold_minutes."""
    from sessions.models import AgentSession

    cutoff = timezone.now() - timedelta(minutes=rule.threshold_minutes)

    long_sessions = AgentSession.objects.filter(
        status="active",
        started_at__lt=cutoff,
    ).select_related("repository").order_by("started_at", "pk")

    alerts: list[tuple[str, dict]] = []
    for session in long_sessions:
        duration_hours = (timezone.now() - session.started_at).total_seconds() / 3600
        repo_name = session.repository.name if session.repository else "unknown"
        msg = rule.message_template.format(
            project=repo_name,
            branch=session.branch or "",
            name=rule.name,
            pr_number="",
            repo=repo_name,
            task_name="",
            value=f"{duration_hours:.1f}h",
            threshold=rule.threshold_minutes // 60,
        )
        alerts.append((msg, {"session_id": session.id}))
    return alerts


def check_task_due_tomorrow(rule: SmartWatchRule) -> list[tuple[str, dict]]:
    """Incomplete Asana tasks due tomorrow."""
    from tasks.models import AsanaTask

    tomorrow = (timezone.now() + timedelta(days=1)).date()

    due_tasks = AsanaTask.objects.filter(
        completed=False,
        due_on=tomorrow,
    ).select_related("project").order_by("due_on", "pk")

    alerts: list[tuple[str, dict]] = []
    for task in due_tasks:
        project_name = task.project.name if task.project else ""
        msg = rule.message_template.format(
            task_name=task.name,
            name=rule.name,
            project=project_name,
            pr_number="",
            repo="",
            branch="",
            value=1,
            threshold=1,
        )
        alerts.append((msg, {"task_gid": task.asana_gid}))
    return alerts


def check_context_high(rule: SmartWatchRule) -> list[tuple[str, dict]]:
    """Terminal heartbeat sessions reporting context % above threshold.

    Checks the sessions JSONField in TerminalHeartbeat for
    context_percent values reported by the Terminal Bridge.
    """
    from sessions.models import TerminalHeartbeat

    recent = TerminalHeartbeat.objects.filter(
        received_at__gte=timezone.now() - timedelta(minutes=5),
    ).order_by("pk")

    alerts: list[tuple[str, dict]] = []
    for hb in recent:
        for session_data in hb.sessions or []:
            ctx_pct = session_data.get("context_percent")
            if ctx_pct is not None and ctx_pct > rule.threshold_value:
                project = session_data.get("project", "unknown")
                msg = rule.message_template.format(
                    project=project,
                    name=rule.name,
                    pr_number="",
                    repo="",
                    branch=session_data.get("branch", ""),
                    task_name="",
                    value=ctx_pct,
                    threshold=rule.threshold_value,
                )
                alerts.append((msg, {
                    "machine": hb.machine,
                    "context_percent": ctx_pct,
                    "project": project,
                }))
    return alerts


EVALUATORS: dict[str, Callable[..., list[tuple[str, dict]]]] = {
    "pr_waiting": check_pr_waiting,
    "session_long": check_session_long,
    "task_due_tomorrow": check_task_due_tomorrow,
    "context_high": check_context_high,
}
