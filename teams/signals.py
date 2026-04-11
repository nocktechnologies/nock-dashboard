"""Cross-reference pipeline events with team tasks.

Called from pipeline.tasks after PR events are processed.
"""

import contextlib
import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone as tz

from core.telegram import TelegramNotifier

from .models import AgentTeam, PromptExecution, PromptFile, TeamEvent, TeamTask

logger = logging.getLogger(__name__)


def on_pr_opened(repo_full_name: str, branch: str, pr_number: int, pr_url: str) -> None:
    """When a PR is opened, check if any TeamTask's branch matches."""
    tasks = TeamTask.objects.filter(
        branch=branch, repo=repo_full_name,
    ).exclude(status="completed").select_related("team", "assigned_to").order_by("pk")

    for task in tasks:
        with transaction.atomic():
            update_fields = ["pr_number", "pr_url", "updated_at"]
            task.pr_number = pr_number
            task.pr_url = pr_url
            if task.status == "in_progress":
                task.status = "in_review"
                update_fields.append("status")
            task.save(update_fields=update_fields)

            TeamEvent.objects.create(
                team=task.team,
                event_type="pr_opened",
                description=f"PR #{pr_number} opened for task: {task.title}",
                task=task,
                member=task.assigned_to,
            )

        repo_short = repo_full_name.split("/")[-1] if "/" in repo_full_name else repo_full_name
        try:
            TelegramNotifier.send(
                f"\U0001f4cb PR opened for task: \"{task.title}\" — PR #{pr_number} on {repo_short}"
            )
        except (OSError, ValueError) as exc:
            logger.warning("Telegram notify failed for PR opened: %s", exc)

    # Also link to PromptFile by matching branch pattern
    _link_pr_to_prompt(repo_full_name, branch, pr_number, pr_url)


def on_pr_merged(repo_full_name: str, pr_number: int) -> None:
    """When a PR is merged, find matching TeamTask and auto-complete it."""
    tasks = TeamTask.objects.filter(
        pr_number=pr_number, repo=repo_full_name,
    ).exclude(status="completed").select_related("team", "assigned_to").order_by("pk")

    for task in tasks:
        with transaction.atomic():
            task.status = "completed"
            task.completed_at = tz.now()
            task.save(update_fields=["status", "completed_at", "updated_at"])

            TeamEvent.objects.create(
                team=task.team,
                event_type="pr_merged",
                description=f"PR #{pr_number} merged — task \"{task.title}\" auto-completed",
                task=task,
                member=task.assigned_to,
            )

            if task.assigned_to and task.assigned_to.current_task_id == task.id:
                task.assigned_to.current_task = None
                task.assigned_to.save(update_fields=["current_task"])

            _resolve_dependents_after_merge(task)

        try:
            TelegramNotifier.send(
                f"\U0001f500 PR #{pr_number} merged — task \"{task.title}\" auto-completed"
            )
        except (OSError, ValueError) as exc:
            logger.warning("Telegram notify failed for PR merged: %s", exc)

        # Check if all tasks done — use select_for_update to prevent race
        _check_mission_complete(task.team_id)


def on_review_alert(repo_full_name: str, pr_number: int, reviewer: str, status: str) -> None:
    """When a review alert is created for a linked PR, log it as a team event."""
    tasks = TeamTask.objects.filter(
        pr_number=pr_number, repo=repo_full_name,
    ).exclude(status="completed").select_related("team").order_by("pk")

    for task in tasks:
        TeamEvent.objects.create(
            team=task.team,
            event_type="review_completed",
            description=f"{reviewer} {status} task \"{task.title}\"'s PR #{pr_number}",
            task=task,
        )


def _check_mission_complete(team_id: int) -> None:
    """Check if all tasks are done and mark mission complete, with row lock."""
    completed = False
    team_name = ""
    total = 0
    with transaction.atomic():
        team = AgentTeam.objects.select_for_update().get(pk=team_id)
        if team.status == "completed":
            return
        summary = team.task_summary
        if summary["total"] > 0 and summary["completed"] == summary["total"]:
            team.status = "completed"
            team.save(update_fields=["status", "updated_at"])
            TeamEvent.objects.create(
                team=team, event_type="mission_completed",
                description=f"All {summary['total']} tasks complete — mission done",
            )
            completed = True
            team_name = team.name
            total = summary["total"]
    # Telegram outside transaction, only if mission actually completed
    if completed:
        with contextlib.suppress(OSError, ValueError):
            TelegramNotifier.send(
                f"\U0001f3c1 Mission complete: \"{team_name}\" — {total} tasks done"
            )


def _resolve_dependents_after_merge(task: TeamTask) -> None:
    """After a task completes via PR merge, unblock dependents."""
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
            with contextlib.suppress(OSError, ValueError):
                TelegramNotifier.send(
                    f"\U0001f513 Task unblocked: \"{dep.title}\" — ready for {agent_name}"
                )


# ──────────────────────────────────────────────────────────────
# Prompt Queue webhook integration
# ──────────────────────────────────────────────────────────────


def _link_pr_to_prompt(
    repo_full_name: str, branch: str, pr_number: int, pr_url: str
) -> None:
    """When a PR is opened, check if its branch matches a PromptFile's expected branch."""
    prompt_ids = list(
        PromptFile.objects.filter(
            target_repo=repo_full_name, status__in=("in_progress", "queued", "ready"),
        ).order_by("pk").values_list("pk", flat=True)
    )

    for pk in prompt_ids:
        with transaction.atomic():
            prompt = PromptFile.objects.select_for_update().filter(pk=pk).first()
            if not prompt or prompt.expected_branch != branch:
                continue
            prompt.pr_number = pr_number
            prompt.pr_url = pr_url
            prompt.save(update_fields=["pr_number", "pr_url", "updated_at"])

            execution = prompt.executions.order_by("-started_at").first()
            if execution:
                execution.pr_number = pr_number
                execution.pr_url = pr_url
                execution.save(update_fields=["pr_number", "pr_url"])

            with contextlib.suppress(OSError, ValueError):
                TelegramNotifier.send(
                    f"\U0001f4cb PR #{pr_number} opened for prompt: \"{prompt.title}\""
                )


def on_prompt_pr_review(repo_full_name: str, pr_number: int, status: str) -> None:
    """Handle review events for prompt-linked PRs."""
    prompts = PromptFile.objects.filter(
        pr_number=pr_number, target_repo=repo_full_name,
    ).exclude(status__in=("completed", "archived")).order_by("pk")

    for prompt in prompts:
        execution = prompt.executions.order_by("-started_at").first()
        if not execution:
            continue

        if status == "changes_requested":
            PromptExecution.objects.filter(pk=execution.pk).update(
                review_cycles=F("review_cycles") + 1
            )
            execution.refresh_from_db(fields=["review_cycles"])

            if execution.review_cycles >= execution.max_review_cycles:
                execution.result = "review_requested"
                execution.save(update_fields=["result"])
                with contextlib.suppress(OSError, ValueError):
                    TelegramNotifier.send(
                        f"\u26a0\ufe0f PR #{pr_number} exceeded max review cycles — needs review"
                    )
            else:
                with contextlib.suppress(OSError, ValueError):
                    TelegramNotifier.send(
                        f"\U0001f504 PR #{pr_number} needs revision "
                        f"({execution.review_cycles}/{execution.max_review_cycles})"
                    )

        elif status == "approved":
            with contextlib.suppress(OSError, ValueError):
                TelegramNotifier.send(
                    f"\u2705 PR #{pr_number} approved for prompt: \"{prompt.title}\""
                )


def on_prompt_pr_merged(repo_full_name: str, pr_number: int) -> None:
    """When a prompt's PR is merged, complete the prompt and check dependents."""
    prompt_ids = list(
        PromptFile.objects.filter(
            pr_number=pr_number, target_repo=repo_full_name,
        ).exclude(status__in=("completed", "archived")).order_by("pk").values_list("pk", flat=True)
    )

    for pk in prompt_ids:
        with transaction.atomic():
            prompt = PromptFile.objects.select_for_update().get(pk=pk)
            if prompt.status in ("completed", "archived"):
                continue
            prompt.status = "completed"
            prompt.save(update_fields=["status", "updated_at"])

            execution = prompt.executions.order_by("-started_at").first()
            if execution and not execution.result:
                execution.result = "success"
                execution.completed_at = tz.now()
                execution.save(update_fields=["result", "completed_at"])

        with contextlib.suppress(OSError, ValueError):
            TelegramNotifier.send(
                f"\u2705 Prompt completed: \"{prompt.title}\" — PR #{pr_number} merged"
            )

        for blocked in prompt.blocked_by.filter(status="ready"):
            if blocked.is_executable:
                with contextlib.suppress(OSError, ValueError):
                    TelegramNotifier.send(
                        f"\U0001f513 Prompt unblocked: \"{blocked.title}\" — ready for execution"
                    )
