import uuid

from django.db import models
from django.utils import timezone
from fernet_fields import EncryptedCharField

# Maps GitHub login (lowercased) → reviewer type for ReviewAlert
REVIEWER_MAP: dict[str, str] = {
    "coderabbitai[bot]": "coderabbit",
    "coderabbitai": "coderabbit",
    "copilot[bot]": "copilot",
    "github-copilot[bot]": "copilot",
    "gemini-code-review[bot]": "gemini",
    "gemini[bot]": "gemini",
}


def classify_reviewer(login: str) -> str:
    """Map a GitHub login to a reviewer type."""
    login_lower = login.lower()
    reviewer_type = REVIEWER_MAP.get(login_lower)
    if reviewer_type:
        return reviewer_type
    if "[bot]" in login_lower:
        return "ci"
    return "human"


class Repository(models.Model):
    name = models.CharField(max_length=255)
    owner = models.CharField(max_length=255)
    github_id = models.BigIntegerField(unique=True)
    default_branch = models.CharField(max_length=255, default="main")
    webhook_secret = EncryptedCharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="repositories",
    )

    class Meta:
        verbose_name_plural = "repositories"
        ordering = ["owner", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"],
                name="unique_repository_owner_name",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.owner}/{self.name}"


class PullRequest(models.Model):
    class State(models.TextChoices):
        OPEN = "open", "Open"
        MERGED = "merged", "Merged"
        CLOSED = "closed", "Closed"

    class CodeRabbitStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        REVIEWING = "reviewing", "Reviewing"
        APPROVED = "approved", "Approved"
        CHANGES_REQUESTED = "changes_requested", "Changes Requested"
        NOT_APPLICABLE = "not_applicable", "Not Applicable"

    class CIStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        PASSED = "passed", "Passed"
        FAILED = "failed", "Failed"

    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name="pull_requests",
    )
    github_pr_id = models.BigIntegerField(db_index=True)
    number = models.IntegerField()
    title = models.CharField(max_length=500)
    branch = models.CharField(max_length=255)
    author = models.CharField(max_length=255)
    state = models.CharField(max_length=10, choices=State.choices)
    coderabbit_status = models.CharField(
        max_length=20,
        choices=CodeRabbitStatus.choices,
        default=CodeRabbitStatus.PENDING,
    )
    ci_status = models.CharField(
        max_length=10,
        choices=CIStatus.choices,
        default=CIStatus.PENDING,
    )
    tests_passed = models.IntegerField(null=True, blank=True)
    tests_failed = models.IntegerField(null=True, blank=True)
    files_changed = models.IntegerField(default=0)
    additions = models.IntegerField(default=0)
    deletions = models.IntegerField(default=0)
    opened_at = models.DateTimeField()
    merged_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)
    generating_agent = models.CharField(max_length=100, blank=True)
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pull_requests",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["repository", "number"],
                name="unique_repository_pr_number",
            ),
        ]
        ordering = ["-opened_at"]

    def __str__(self) -> str:
        return f"{self.repository.name} #{self.number}: {self.title}"


class PREvent(models.Model):
    pull_request = models.ForeignKey(
        PullRequest,
        on_delete=models.CASCADE,
        related_name="events",
    )
    event_type = models.CharField(max_length=100)
    actor = models.CharField(max_length=255)
    payload = models.JSONField(default=dict)
    # Dedicated field for DB-level delivery idempotency (unique on non-empty values)
    delivery_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pr_events",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["delivery_id"],
                condition=~models.Q(delivery_id=""),
                name="unique_pr_event_delivery_id",
            ),
        ]

    @property
    def display_event_type(self) -> str:
        return self.event_type.replace("_", " ").title()

    def __str__(self) -> str:
        return f"PR #{self.pull_request.number} — {self.event_type} by {self.actor}"


class Branch(models.Model):
    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name="branches",
    )
    name = models.CharField(max_length=255)
    last_commit_sha = models.CharField(max_length=40)
    last_commit_message = models.TextField(blank=True)
    last_commit_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="branches",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["repository", "name"],
                name="unique_repository_branch_name",
            ),
        ]
        verbose_name_plural = "branches"

    def __str__(self) -> str:
        return f"{self.repository.name}/{self.name}"


class BranchEvent(models.Model):
    """Lightweight push-event log used for idempotency tracking on process_push."""

    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name="branch_events",
    )
    delivery_id = models.CharField(max_length=100, db_index=True)
    ref = models.CharField(max_length=255)
    deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="branch_events",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["repository", "delivery_id"],
                name="unique_branch_event_delivery",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.repository} — {self.ref} ({self.delivery_id})"


class ReviewAlert(models.Model):
    class Reviewer(models.TextChoices):
        CODERABBIT = "coderabbit", "CodeRabbit"
        COPILOT = "copilot", "GitHub Copilot"
        GEMINI = "gemini", "Gemini"
        HUMAN = "human", "Human"
        CI = "ci", "CI Check"

    class Status(models.TextChoices):
        APPROVED = "approved", "Approved"
        CHANGES_REQUESTED = "changes_requested", "Changes Requested"
        COMMENTED = "commented", "Commented"
        SUCCESS = "success", "CI Success"
        FAILURE = "failure", "CI Failure"
        NEUTRAL = "neutral", "CI Neutral"

    repo = models.CharField(max_length=200, db_index=True)
    pr_number = models.PositiveIntegerField()
    pr_title = models.CharField(max_length=500)
    pr_url = models.URLField(max_length=500)
    branch = models.CharField(max_length=200, blank=True)
    reviewer = models.CharField(max_length=20, choices=Reviewer.choices)
    reviewer_login = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=Status.choices)
    body_preview = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False, db_index=True)
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="review_alerts",
    )

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self) -> str:
        return f"{self.reviewer} {self.status} on {self.repo}#{self.pr_number}"


class PipelineEvent(models.Model):
    """Structured event log for the autonomous development pipeline.

    Every significant action taken by Kit, agents, or the pipeline itself
    gets logged here as an immutable audit trail.
    """

    class Category(models.TextChoices):
        PROMPT = "prompt", "Prompt Queue"
        BUILD = "build", "Build"
        TEST = "test", "Test"
        LINT = "lint", "Lint/Quality"
        GIT = "git", "Git Operations"
        PR = "pr", "Pull Request"
        REVIEW = "review", "Code Review"
        REVIEW_FIX = "review_fix", "Review Fix"
        TICKET = "ticket", "Ticket"
        ESCALATION = "escalation", "Escalation"
        PIPELINE = "pipeline", "Pipeline Control"
        SESSION = "session", "Session"
        CHECKPOINT = "checkpoint", "Checkpoint"
        CLOSE = "close", "Session Close"
        NOTIFICATION = "notification", "Notification"
        ERROR = "error", "Error"

    class Severity(models.TextChoices):
        INFO = "info", "Info"
        SUCCESS = "success", "Success"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"
        CRITICAL = "critical", "Critical"

    class Lane(models.TextChoices):
        PROMPT = "prompt", "Prompt Queue (Lane 1)"
        TICKET = "ticket", "Ticket Queue (Lane 2)"
        AUDIT = "audit", "Periodic Audit"
        MANUAL = "manual", "Manual Operation"

    class Agent(models.TextChoices):
        KIT = "kit", "Kit (Claude Code)"
        CODEX = "codex", "Codex (OpenAI)"
        CODERABBIT = "coderabbit", "CodeRabbit"
        COPILOT = "copilot", "Copilot"
        GEMINI = "gemini", "Gemini"
        MARA = "mara", "Mara"
        SYSTEM = "system", "NockCC System"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    workflow_id = models.CharField(
        max_length=200,
        db_index=True,
        help_text="Matches workflow_id from .workflow-state.json",
    )
    repo = models.CharField(
        max_length=100,
        db_index=True,
        help_text="e.g., nock-command-center, claude-terminal, project-nexus",
    )

    category = models.CharField(max_length=20, choices=Category.choices)
    severity = models.CharField(
        max_length=10, choices=Severity.choices, default=Severity.INFO,
    )

    title = models.CharField(
        max_length=200,
        help_text="Short description: 'PR #48 opened on nock-command-center'",
    )
    details = models.TextField(blank=True, default="")

    lane = models.CharField(
        max_length=10, choices=Lane.choices, default=Lane.MANUAL,
    )
    agent = models.CharField(
        max_length=15, choices=Agent.choices, default=Agent.KIT,
    )

    pr_number = models.IntegerField(null=True, blank=True)
    branch = models.CharField(max_length=200, blank=True, default="")
    asana_task_id = models.CharField(max_length=50, blank=True, default="")

    duration_seconds = models.IntegerField(
        null=True, blank=True, help_text="How long this step took",
    )
    token_count = models.IntegerField(
        null=True, blank=True, help_text="Tokens consumed for this step",
    )
    files_changed = models.IntegerField(
        null=True, blank=True, help_text="Number of files created or modified",
    )
    test_count = models.IntegerField(
        null=True, blank=True, help_text="Number of tests after this step",
    )
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pipeline_events",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["workflow_id", "-created_at"],
                name="idx_event_wf_ts",
            ),
            models.Index(
                fields=["repo", "-created_at"],
                name="idx_event_repo_ts",
            ),
            models.Index(
                fields=["category", "severity"],
                name="idx_event_cat_sev",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.severity}] {self.category}: {self.title}"
