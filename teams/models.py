from django.db import models
from django.db.models import Count, Q, QuerySet
from django.utils.text import slugify


class AgentTeam(models.Model):
    STATUS_CHOICES = [
        ("planning", "Planning"),
        ("active", "Active"),
        ("paused", "Paused"),
        ("completed", "Completed"),
    ]

    name = models.CharField(max_length=200)
    mission = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="planning")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]

    def __str__(self) -> str:
        return f"{self.name} ({self.status})"

    @property
    def member_count(self) -> int:
        return self.members.count()

    @property
    def task_summary(self) -> dict:
        return self.tasks.aggregate(
            total=Count("id"),
            pending=Count("id", filter=Q(status="pending")),
            in_progress=Count("id", filter=Q(status="in_progress")),
            blocked=Count("id", filter=Q(status="blocked")),
            completed=Count("id", filter=Q(status="completed")),
        )


class TeamMember(models.Model):
    ROLE_CHOICES = [
        ("lead", "Lead"),
        ("worker", "Worker"),
        ("reviewer", "Reviewer"),
    ]

    team = models.ForeignKey(AgentTeam, on_delete=models.CASCADE, related_name="members")
    agent_name = models.CharField(max_length=100)
    agent_token = models.ForeignKey(
        "remote.AgentToken", on_delete=models.SET_NULL, null=True, blank=True
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="worker")
    is_online = models.BooleanField(default=False)
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    current_task = models.ForeignKey(
        "TeamTask", on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_agent"
    )

    class Meta:
        unique_together = ["team", "agent_name"]
        ordering = ["role", "agent_name"]

    def __str__(self) -> str:
        return f"{self.agent_name} ({self.role}) on {self.team.name}"


class TeamTask(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("assigned", "Assigned"),
        ("in_progress", "In Progress"),
        ("blocked", "Blocked"),
        ("in_review", "In Review"),
        ("completed", "Completed"),
    ]

    PRIORITY_LOW = 1
    PRIORITY_MEDIUM = 2
    PRIORITY_HIGH = 3
    PRIORITY_CRITICAL = 4

    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Low"),
        (PRIORITY_MEDIUM, "Medium"),
        (PRIORITY_HIGH, "High"),
        (PRIORITY_CRITICAL, "Critical"),
    ]

    # Maps string labels from API to integer values
    PRIORITY_MAP = {"low": PRIORITY_LOW, "medium": PRIORITY_MEDIUM, "high": PRIORITY_HIGH, "critical": PRIORITY_CRITICAL}
    PRIORITY_REVERSE = {v: k for k, v in PRIORITY_MAP.items()}

    team = models.ForeignKey(AgentTeam, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    priority = models.IntegerField(choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    assigned_to = models.ForeignKey(
        TeamMember, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks"
    )
    repo = models.CharField(max_length=200, blank=True)
    branch = models.CharField(max_length=200, blank=True)
    pr_number = models.IntegerField(null=True, blank=True)
    pr_url = models.URLField(max_length=500, blank=True)
    depends_on = models.ManyToManyField("self", symmetrical=False, blank=True, related_name="blocks")
    context_brief_scope = models.CharField(max_length=50, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-priority", "created_at", "id"]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"

    @property
    def priority_label(self) -> str:
        return self.PRIORITY_REVERSE.get(self.priority, "medium")

    @property
    def is_blocked(self) -> bool:
        """True if any dependency is not completed."""
        return self.depends_on.exclude(status="completed").exists()

    @property
    def blocking_tasks(self) -> QuerySet["TeamTask"]:
        """Return tasks this task is waiting on."""
        return self.depends_on.exclude(status="completed")


class TeamEvent(models.Model):
    EVENT_TYPES = [
        ("task_assigned", "Task Assigned"),
        ("task_started", "Task Started"),
        ("task_completed", "Task Completed"),
        ("task_blocked", "Task Blocked"),
        ("task_unblocked", "Task Unblocked"),
        ("pr_opened", "PR Opened"),
        ("pr_merged", "PR Merged"),
        ("review_completed", "Review Completed"),
        ("agent_joined", "Agent Joined"),
        ("agent_left", "Agent Left"),
        ("mission_started", "Mission Started"),
        ("mission_completed", "Mission Completed"),
    ]

    team = models.ForeignKey(AgentTeam, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=30, choices=EVENT_TYPES)
    description = models.TextField()
    task = models.ForeignKey(TeamTask, on_delete=models.SET_NULL, null=True, blank=True)
    member = models.ForeignKey(TeamMember, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.get_event_type_display()} — {self.description[:50]}"


class PromptFile(models.Model):
    COMPLEXITY_CHOICES = [
        ("quick", "Quick Task"),
        ("standard", "Standard Build"),
        ("deep", "Deep Build"),
    ]

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("ready", "Ready"),
        ("queued", "Queued"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("archived", "Archived"),
    ]

    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=100, unique=True)
    content = models.TextField(help_text="Full prompt content in markdown")
    target_repo = models.CharField(max_length=200, help_text="e.g., kkwills13/nock-command-center")
    target_branch_prefix = models.CharField(
        max_length=100, default="feature/", help_text="Branch prefix for the build"
    )
    complexity = models.CharField(max_length=20, choices=COMPLEXITY_CHOICES, default="standard")
    estimated_minutes = models.IntegerField(default=60)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    priority = models.IntegerField(default=50, help_text="1-100, higher = more urgent")

    # Linking
    team_task = models.OneToOneField(
        TeamTask, on_delete=models.SET_NULL, null=True, blank=True, related_name="prompt"
    )
    depends_on_prompts = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="blocked_by"
    )

    # Metadata
    tags = models.JSONField(default=list, blank=True)
    author = models.CharField(max_length=100, default="mara")
    version = models.IntegerField(default=1)

    # Execution tracking
    executed_by = models.CharField(max_length=100, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    pr_number = models.IntegerField(null=True, blank=True)
    pr_url = models.URLField(max_length=500, blank=True)
    execution_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-priority", "created_at", "id"]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"

    def save(self, *args, **kwargs) -> None:  # type: ignore[override]
        if not self.slug:
            base = slugify(self.title)[:100] or "prompt"
            slug = base
            counter = 1
            while PromptFile.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base[:95]}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def is_executable(self) -> bool:
        """Can this prompt be picked up by an agent right now?"""
        if self.status != "ready":
            return False
        return not self.depends_on_prompts.exclude(status="completed").exists()

    @property
    def expected_branch(self) -> str:
        return f"{self.target_branch_prefix}{self.slug}"


class PromptExecution(models.Model):
    """Log of every time a prompt was executed."""

    RESULT_CHOICES = [
        ("success", "Success"),
        ("review_requested", "Changes Requested"),
        ("failed", "Failed"),
        ("abandoned", "Abandoned"),
    ]

    prompt = models.ForeignKey(PromptFile, on_delete=models.CASCADE, related_name="executions")
    agent_name = models.CharField(max_length=100)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, null=True, blank=True)
    pr_number = models.IntegerField(null=True, blank=True)
    pr_url = models.URLField(max_length=500, blank=True)
    review_cycles = models.IntegerField(default=0, help_text="How many review-fix cycles")
    max_review_cycles = models.IntegerField(default=3, help_text="Stop after this many cycles")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at", "id"]

    def __str__(self) -> str:
        return f"{self.prompt.title} by {self.agent_name} ({self.result or 'running'})"
