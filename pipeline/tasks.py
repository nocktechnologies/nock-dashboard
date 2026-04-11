import logging
import re
from datetime import timedelta

import requests
from celery import shared_task
from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_datetime

from .models import (
    Branch,
    BranchEvent,
    PREvent,
    PullRequest,
    Repository,
    ReviewAlert,
    classify_reviewer,
)

logger = logging.getLogger(__name__)


_REVIEW_DEDUP_SECONDS = 60


def _recent_review_alert_exists(repo: str, pr_number: int, reviewer_login: str, status: str) -> bool:
    """Return True if a matching ReviewAlert was created in the last 60 seconds."""
    from django.utils import timezone as tz
    cutoff = tz.now() - timedelta(seconds=_REVIEW_DEDUP_SECONDS)
    return ReviewAlert.objects.filter(
        repo=repo,
        pr_number=pr_number,
        reviewer_login=reviewer_login,
        status=status,
        created_at__gte=cutoff,
    ).exists()


def _create_review_alert(
    *,
    repo: str,
    pr_number: int,
    pr_title: str,
    pr_url: str,
    branch: str,
    reviewer_login: str,
    status: str,
    body: str,
    reviewer_type_override: str = "",
) -> ReviewAlert | None:
    """Create a ReviewAlert if not a duplicate, then send Telegram notification.

    Uses a two-layer dedup strategy: an application-level time-window check
    (fast path) plus a DB-level savepoint to catch concurrent race conditions.
    """
    if _recent_review_alert_exists(repo, pr_number, reviewer_login, status):
        logger.info("Dedup: skipping review alert %s/%s on %s#%s", reviewer_login, status, repo, pr_number)
        return None

    reviewer_type = reviewer_type_override or classify_reviewer(reviewer_login)
    try:
        with transaction.atomic():
            alert = ReviewAlert.objects.create(
                repo=repo,
                pr_number=pr_number,
                pr_title=pr_title[:500],
                pr_url=pr_url[:500],
                branch=branch[:200],
                reviewer=reviewer_type,
                reviewer_login=reviewer_login[:200],
                status=status,
                body_preview=body[:500],
            )
    except IntegrityError:
        logger.info("Dedup (DB): concurrent review alert %s/%s on %s#%s", reviewer_login, status, repo, pr_number)
        return None

    transaction.on_commit(lambda: _send_review_telegram(alert))
    transaction.on_commit(lambda: _link_review_to_team_task(alert))
    return alert


def _send_review_telegram(alert: ReviewAlert) -> None:
    """Format and send Telegram notification for a ReviewAlert."""
    try:
        from core.telegram import TelegramNotifier
    except ImportError:
        return

    repo_short = alert.repo.split("/")[-1] if "/" in alert.repo else alert.repo
    title = alert.pr_title[:60]

    emoji_map = {
        "approved": "\u2705",
        "changes_requested": "\u26a0\ufe0f",
        "commented": "\U0001f4ac",
        "success": "\u2705",
        "failure": "\u274c",
        "neutral": "\u2796",
    }
    emoji = emoji_map.get(alert.status, "\U0001f514")

    reviewer_display = {
        "coderabbit": "CodeRabbit",
        "copilot": "Copilot",
        "gemini": "Gemini",
        "ci": alert.reviewer_login,
        "human": alert.reviewer_login,
    }.get(alert.reviewer, alert.reviewer_login)

    if alert.status == "approved":
        action = f"approved PR #{alert.pr_number}"
        extra = "\u2192 Ready to merge"
    elif alert.status == "changes_requested":
        action = f"requested changes on PR #{alert.pr_number}"
        extra = "\u2192 Comments to address"
    elif alert.status == "commented":
        action = f"commented on PR #{alert.pr_number}"
        extra = ""
    elif alert.status == "success":
        action = f"passed on PR #{alert.pr_number}"
        extra = ""
        emoji = "\u2705"
        reviewer_display = "All checks"
    elif alert.status == "failure":
        action = f"failed on PR #{alert.pr_number}"
        extra = f"\u2192 Check: {alert.reviewer_login}"
        reviewer_display = "CI"
    else:
        action = f"{alert.status} on PR #{alert.pr_number}"
        extra = ""

    lines = [
        f"{emoji} *{reviewer_display}* {action}",
        f"`{repo_short}` \u2014 {title}",
    ]
    if extra:
        lines.append(extra)

    TelegramNotifier.send("\n".join(lines))


def _send_push_telegram(
    repo_name: str,
    branch_name: str,
    pusher: str,
    commit_count: int,
    commit_msg: str,
) -> None:
    """Send Telegram notification for a push event."""
    try:
        from core.telegram import TelegramNotifier
    except ImportError:
        return

    repo_short = repo_name.split("/")[-1] if "/" in repo_name else repo_name
    s = "s" if commit_count != 1 else ""
    lines = [
        f"\U0001f4e6 *{pusher}* pushed {commit_count} commit{s} to `{branch_name}`",
        f"`{repo_short}` \u2014 {commit_msg}",
    ]
    TelegramNotifier.send("\n".join(lines))


def _notify(event_type: str, data: dict) -> None:
    """Fire notification without crashing the task on failure."""
    try:
        from notifications.notifier import trigger_event
        trigger_event(event_type, data)
    except (ImportError, requests.RequestException, OSError) as exc:
        logger.warning("Notification dispatch failed for %s: %s", event_type, exc)


# Concluded check_run states that are not success — all treated as FAILED
_FAILED_CONCLUSIONS = frozenset(
    {"failure", "neutral", "skipped", "cancelled", "timed_out", "action_required", "stale"}
)


def _create_pr_event(**kwargs) -> None:
    """Create a PREvent inside a savepoint.

    Suppresses IntegrityError only when it's a delivery_id uniqueness violation
    (concurrent duplicate delivery). All other IntegrityErrors are re-raised.
    """
    try:
        with transaction.atomic():
            PREvent.objects.create(**kwargs)
    except IntegrityError as exc:
        err = str(exc).lower()
        if "unique_pr_event_delivery_id" in err or (
            "delivery_id" in err and "unique" in err
        ):
            logger.info("Duplicate PREvent delivery_id=%s — skipped", kwargs.get("delivery_id", ""))
        else:
            raise


def _delivery_seen(delivery_id: str) -> bool:
    """Return True if a PREvent for this delivery ID already exists (must be called inside atomic).

    Uses the dedicated delivery_id field (not the JSON payload) for a DB-indexed lookup.
    """
    if not delivery_id:
        return False
    return PREvent.objects.filter(delivery_id=delivery_id).exists()


def _get_repo(payload: dict) -> Repository | None:
    repo_data = payload.get("repository", {})
    full_name = repo_data.get("full_name", "")
    owner, _, name = full_name.partition("/")
    return Repository.objects.filter(owner=owner, name=name, is_active=True).order_by("pk").first()


def _get_or_create_pr(repo: Repository, pr_data: dict) -> tuple[PullRequest, bool]:
    return PullRequest.objects.select_for_update().get_or_create(
        repository=repo,
        number=pr_data["number"],
        defaults={
            "github_pr_id": pr_data["id"],
            "title": pr_data["title"],
            "branch": pr_data["head"]["ref"],
            "author": pr_data["user"]["login"],
            "state": PullRequest.State.OPEN,
            "files_changed": pr_data.get("changed_files", 0),
            "additions": pr_data.get("additions", 0),
            "deletions": pr_data.get("deletions", 0),
            "opened_at": parse_datetime(pr_data["created_at"]),
        },
    )


def _parse_test_counts(text: str | None) -> tuple[int | None, int | None]:
    """Extract passed/failed counts from pytest output in check_run text."""
    if not text:
        return None, None
    m_passed = re.search(r"(\d+) passed", text)
    m_failed = re.search(r"(\d+) failed", text)
    return (int(m_passed.group(1)) if m_passed else None), (int(m_failed.group(1)) if m_failed else None)


@shared_task
def process_pull_request_event(payload: dict, action: str, delivery_id: str = "") -> None:
    repo = _get_repo(payload)
    if not repo:
        logger.warning("process_pull_request_event: repo not found")
        return

    pr_data = payload["pull_request"]

    with transaction.atomic():
        # Idempotency check inside the atomic block to prevent race conditions
        if _delivery_seen(delivery_id):
            logger.info("Duplicate delivery %s skipped", delivery_id)
            return

        if action == "opened":
            pr, _ = PullRequest.objects.select_for_update().get_or_create(
                repository=repo,
                number=pr_data["number"],
                defaults={
                    "github_pr_id": pr_data["id"],
                    "title": pr_data["title"],
                    "branch": pr_data["head"]["ref"],
                    "author": pr_data["user"]["login"],
                    "state": PullRequest.State.OPEN,
                    "files_changed": pr_data.get("changed_files", 0),
                    "additions": pr_data.get("additions", 0),
                    "deletions": pr_data.get("deletions", 0),
                    "opened_at": parse_datetime(pr_data["created_at"]),
                },
            )
            _create_pr_event(
                pull_request=pr,
                event_type="opened",
                actor=pr_data["user"]["login"],
                delivery_id=delivery_id,
                payload={"delivery_id": delivery_id, "action": action},
            )

            # Cross-reference with team tasks
            _link_pr_to_team_task(
                repo_full=f"{repo.owner}/{repo.name}",
                branch=pr_data["head"]["ref"],
                pr_number=pr_data["number"],
                pr_url=pr_data.get("html_url", ""),
            )

        elif action == "closed":
            try:
                pr = PullRequest.objects.select_for_update().get(
                    repository=repo, number=pr_data["number"]
                )
            except PullRequest.DoesNotExist:
                logger.warning("PR #%s not found on closed event", pr_data["number"])
                return
            if pr_data.get("merged"):
                pr.state = PullRequest.State.MERGED
                pr.merged_at = parse_datetime(pr_data["merged_at"])
            else:
                pr.state = PullRequest.State.CLOSED
                pr.closed_at = parse_datetime(pr_data["closed_at"])
            pr.save(update_fields=["state", "merged_at", "closed_at"])
            _create_pr_event(
                pull_request=pr,
                event_type="closed",
                actor=payload.get("sender", {}).get("login", ""),
                delivery_id=delivery_id,
                payload={"delivery_id": delivery_id, "merged": pr_data.get("merged", False)},
            )

            # Trigger notification
            if pr_data.get("merged"):
                _notify("pr_merged", {
                    "title": f"PR #{pr.number} Merged",
                    "message": pr.title,
                    "repo": str(repo),
                    "author": pr.author,
                })
                _complete_team_task_on_merge(
                    repo_full=f"{repo.owner}/{repo.name}",
                    pr_number=pr_data["number"],
                )

        elif action == "reopened":
            try:
                pr = PullRequest.objects.select_for_update().get(
                    repository=repo, number=pr_data["number"]
                )
            except PullRequest.DoesNotExist:
                return
            pr.state = PullRequest.State.OPEN
            pr.closed_at = None
            pr.merged_at = None
            pr.save(update_fields=["state", "closed_at", "merged_at"])
            _create_pr_event(
                pull_request=pr,
                event_type="reopened",
                actor=payload.get("sender", {}).get("login", ""),
                delivery_id=delivery_id,
                payload={"delivery_id": delivery_id},
            )

        elif action == "edited":
            try:
                pr = PullRequest.objects.select_for_update().get(
                    repository=repo, number=pr_data["number"]
                )
            except PullRequest.DoesNotExist:
                return
            pr.title = pr_data["title"]
            pr.save(update_fields=["title"])
            _create_pr_event(
                pull_request=pr,
                event_type="edited",
                actor=payload.get("sender", {}).get("login", ""),
                delivery_id=delivery_id,
                payload={"delivery_id": delivery_id, "title": pr_data["title"]},
            )

        elif action == "synchronize":
            try:
                pr = PullRequest.objects.select_for_update().get(
                    repository=repo, number=pr_data["number"]
                )
            except PullRequest.DoesNotExist:
                return
            pr.additions = pr_data.get("additions", pr.additions)
            pr.deletions = pr_data.get("deletions", pr.deletions)
            pr.files_changed = pr_data.get("changed_files", pr.files_changed)
            pr.save(update_fields=["additions", "deletions", "files_changed"])
            _create_pr_event(
                pull_request=pr,
                event_type="synchronize",
                actor=payload.get("sender", {}).get("login", ""),
                delivery_id=delivery_id,
                payload={"delivery_id": delivery_id},
            )

        else:
            logger.debug("Unhandled PR action: %s", action)


@shared_task
def process_pull_request_review(payload: dict, delivery_id: str = "") -> None:
    repo = _get_repo(payload)
    if not repo:
        return

    pr_data = payload["pull_request"]
    review = payload["review"]
    reviewer = review.get("user", {})
    reviewer_login = reviewer.get("login", "").lower()
    review_state = review.get("state", "").lower()

    is_coderabbit = "coderabbit" in reviewer_login

    with transaction.atomic():
        if _delivery_seen(delivery_id):
            logger.info("Duplicate delivery %s skipped", delivery_id)
            return

        pr, _ = _get_or_create_pr(repo, pr_data)

        if is_coderabbit:
            if review_state == "approved":
                pr.coderabbit_status = PullRequest.CodeRabbitStatus.APPROVED
            elif review_state == "changes_requested":
                pr.coderabbit_status = PullRequest.CodeRabbitStatus.CHANGES_REQUESTED
            elif review_state == "commented":
                pr.coderabbit_status = PullRequest.CodeRabbitStatus.REVIEWING
            pr.save(update_fields=["coderabbit_status"])

        _create_pr_event(
            pull_request=pr,
            event_type="review_submitted",
            actor=reviewer.get("login", ""),
            delivery_id=delivery_id,
            payload={
                "delivery_id": delivery_id,
                "state": review_state,
                "body": review.get("body", ""),
                "is_coderabbit": is_coderabbit,
            },
        )

        # Map review_state to ReviewAlert status
        status_map = {"approved": "approved", "changes_requested": "changes_requested", "commented": "commented"}
        alert_status = status_map.get(review_state)
        if alert_status:
            pr_html_url = payload.get("pull_request", {}).get("html_url", "")
            repo_full = payload.get("repository", {}).get("full_name", "")
            _create_review_alert(
                repo=repo_full,
                pr_number=pr_data["number"],
                pr_title=pr_data["title"],
                pr_url=pr_html_url,
                branch=pr_data["head"]["ref"],
                reviewer_login=reviewer_login,
                status=alert_status,
                body=review.get("body", "") or "",
            )


@shared_task
def process_check_run(payload: dict, delivery_id: str = "") -> None:
    repo = _get_repo(payload)
    if not repo:
        return

    check_run = payload.get("check_run", {})
    prs = check_run.get("pull_requests", [])
    if not prs:
        return

    pr_number = prs[0]["number"]
    conclusion = check_run.get("conclusion")
    status = check_run.get("status", "")

    # Check status first: queued/in_progress → RUNNING regardless of conclusion
    # completed: map conclusion explicitly; anything other than success is FAILED
    if status in ("queued", "in_progress"):
        ci_status = PullRequest.CIStatus.RUNNING
    elif conclusion == "success":
        ci_status = PullRequest.CIStatus.PASSED
    elif conclusion in _FAILED_CONCLUSIONS:
        ci_status = PullRequest.CIStatus.FAILED
    else:
        ci_status = PullRequest.CIStatus.RUNNING

    output_text = check_run.get("output", {}).get("text")
    tests_passed, tests_failed = _parse_test_counts(output_text)

    with transaction.atomic():
        if _delivery_seen(delivery_id):
            logger.info("Duplicate delivery %s skipped", delivery_id)
            return

        try:
            pr = PullRequest.objects.select_for_update().get(
                repository=repo, number=pr_number
            )
        except PullRequest.DoesNotExist:
            logger.warning("PR #%s not found for check_run", pr_number)
            return

        update_fields = ["ci_status"]
        pr.ci_status = ci_status
        if tests_passed is not None:
            pr.tests_passed = tests_passed
            update_fields.append("tests_passed")
        if tests_failed is not None:
            pr.tests_failed = tests_failed
            update_fields.append("tests_failed")
        pr.save(update_fields=update_fields)

        if ci_status == PullRequest.CIStatus.FAILED:
            _notify("ci_failed", {
                "title": f"CI Failed: PR #{pr.number}",
                "message": pr.title,
                "repo": str(repo),
                "conclusion": conclusion or "",
            })

        _create_pr_event(
            pull_request=pr,
            event_type="ci_completed",
            actor=check_run.get("app", {}).get("slug", ""),
            delivery_id=delivery_id,
            payload={
                "delivery_id": delivery_id,
                "conclusion": conclusion,
                "status": status,
                "name": check_run.get("name", ""),
            },
        )

        # Create ReviewAlert for completed check runs (success or failure)
        if status == "completed" and conclusion in ("success", "failure", "neutral"):
            ci_status_map = {"success": "success", "failure": "failure", "neutral": "neutral"}
            check_name = check_run.get("name", "CI")
            repo_full = payload.get("repository", {}).get("full_name", "")
            pr_url = f"https://github.com/{repo_full}/pull/{pr_number}"
            _create_review_alert(
                repo=repo_full,
                pr_number=pr_number,
                pr_title=pr.title,
                pr_url=pr_url,
                branch=pr.branch,
                reviewer_login=check_name,
                status=ci_status_map[conclusion],
                body="",
                reviewer_type_override="ci",
            )


@shared_task
def process_push(payload: dict, delivery_id: str = "") -> None:
    repo = _get_repo(payload)
    if not repo:
        return

    ref = payload.get("ref", "")
    if not ref.startswith("refs/heads/"):
        return

    branch_name = ref[len("refs/heads/"):]
    deleted = payload.get("deleted", False)
    head_commit = payload.get("head_commit") or {}

    with transaction.atomic():
        # Idempotency: only track when delivery_id is present; skip empty delivery IDs
        if delivery_id:
            _, created = BranchEvent.objects.get_or_create(
                repository=repo,
                delivery_id=delivery_id,
                defaults={"ref": ref, "deleted": deleted},
            )
            if not created:
                logger.info("Duplicate push delivery %s skipped", delivery_id)
                return

        branch, _ = Branch.objects.select_for_update().get_or_create(
            repository=repo,
            name=branch_name,
            defaults={
                "last_commit_sha": head_commit.get("id", "")[:40],
                "last_commit_message": head_commit.get("message", ""),
                "last_commit_at": parse_datetime(head_commit["timestamp"])
                if head_commit.get("timestamp")
                else None,
                "is_active": not deleted,
            },
        )

        if deleted:
            branch.is_active = False
            branch.save(update_fields=["is_active"])
        else:
            branch.last_commit_sha = head_commit.get("id", branch.last_commit_sha)[:40]
            branch.last_commit_message = head_commit.get("message", branch.last_commit_message)
            if head_commit.get("timestamp"):
                branch.last_commit_at = parse_datetime(head_commit["timestamp"])
            branch.is_active = True
            branch.save(
                update_fields=["last_commit_sha", "last_commit_message", "last_commit_at", "is_active"]
            )

    # Notifications — outside the atomic block so they don't delay the transaction
    if not deleted:
        commits = payload.get("commits", [])
        commit_count = len(commits)
        pusher = payload.get("pusher", {}).get("name", "unknown")
        commit_msg = head_commit.get("message", "").split("\n")[0][:80]
        repo_name = payload.get("repository", {}).get("full_name", str(repo))

        _notify("push", {
            "title": f"Push to {branch_name}",
            "message": f"{pusher} pushed {commit_count} commit(s) to `{branch_name}`\n> {commit_msg}",
            "repo": repo_name,
            "branch": branch_name,
            "commits": commit_count,
        })
        _send_push_telegram(
            repo_name=repo_name,
            branch_name=branch_name,
            pusher=pusher,
            commit_count=commit_count,
            commit_msg=commit_msg,
        )


# ── Team task cross-reference helpers ──


def _link_pr_to_team_task(repo_full: str, branch: str, pr_number: int, pr_url: str) -> None:
    """Cross-reference a newly opened PR with team tasks."""
    try:
        from teams.signals import on_pr_opened
        on_pr_opened(repo_full, branch, pr_number, pr_url)
    except (ImportError, IntegrityError, OSError) as exc:
        logger.warning("Team task PR link failed: %s", exc)


def _complete_team_task_on_merge(repo_full: str, pr_number: int) -> None:
    """Auto-complete team tasks when their linked PR is merged."""
    try:
        from teams.signals import on_pr_merged
        on_pr_merged(repo_full, pr_number)
    except (ImportError, IntegrityError, OSError) as exc:
        logger.warning("Team task merge completion failed: %s", exc)
    try:
        from teams.signals import on_prompt_pr_merged
        on_prompt_pr_merged(repo_full, pr_number)
    except (ImportError, IntegrityError, OSError) as exc:
        logger.warning("Prompt PR merge completion failed: %s", exc)


def _link_review_to_team_task(alert: "ReviewAlert") -> None:
    """Link a review alert to a team task event."""
    try:
        from teams.signals import on_review_alert
        on_review_alert(alert.repo, alert.pr_number, alert.reviewer, alert.status)
    except (ImportError, IntegrityError, OSError) as exc:
        logger.warning("Team task review link failed: %s", exc)
    try:
        from teams.signals import on_prompt_pr_review
        on_prompt_pr_review(alert.repo, alert.pr_number, alert.status)
    except (ImportError, IntegrityError, OSError) as exc:
        logger.warning("Prompt PR review link failed: %s", exc)
