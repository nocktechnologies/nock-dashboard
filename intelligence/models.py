"""Models for the Intelligence layer — AI-powered business analysis."""
from __future__ import annotations

from django.conf import settings
from django.db import models


class BusinessSnapshot(models.Model):
    """Daily snapshot of all business data for AI advisor context."""

    date = models.DateField(unique=True)
    content = models.TextField(help_text="Markdown summary of all business data")
    generated_at = models.DateTimeField(auto_now_add=True)
    token_count = models.IntegerField(
        default=0,
        help_text="Approximate token count for cost awareness",
    )

    class Meta:
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"Snapshot {self.date}"


class AdvisorConversation(models.Model):
    """Chat conversation with the AI Business Advisor."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="advisor_conversations",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title or f"Conversation {self.pk}"


class AdvisorMessage(models.Model):
    """Single message in an advisor conversation."""

    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    conversation = models.ForeignKey(
        AdvisorConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    tokens_used = models.IntegerField(default=0)
    cost = models.DecimalField(max_digits=8, decimal_places=6, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:50]}"


class PredictiveAlert(models.Model):
    """AI-generated predictive alerts for business operations."""

    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    class Category(models.TextChoices):
        SPEND = "spend", "Spend"
        PIPELINE = "pipeline", "Pipeline"
        TASKS = "tasks", "Tasks"
        CONTEXT = "context", "Context"
        SUBSCRIPTIONS = "subscriptions", "Subscriptions"
        VELOCITY = "velocity", "Velocity"
        REVENUE = "revenue", "Revenue"

    category = models.CharField(max_length=20, choices=Category.choices)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "title"],
                condition=models.Q(is_resolved=False),
                name="unique_active_alert_per_category_title",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.severity}] {self.title}"


class WeeklyMemo(models.Model):
    """Record of generated weekly strategy memos."""

    week_start = models.DateField()
    week_end = models.DateField()
    content = models.TextField()
    tokens_used = models.IntegerField(default=0)
    cost = models.DecimalField(max_digits=8, decimal_places=6, default=0)
    vault_document = models.ForeignKey(
        "vault.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Document saved in the vault",
    )
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-week_start"]
        constraints = [
            models.UniqueConstraint(
                fields=["week_start", "week_end"],
                name="unique_memo_per_week",
            ),
        ]

    def __str__(self) -> str:
        return f"Memo {self.week_start} – {self.week_end}"


# ──────────────── Smart Watch ────────────────


class SmartWatchRule(models.Model):
    """Configurable health-check rule evaluated by the Smart Watch loop."""

    class ConditionType(models.TextChoices):
        PR_WAITING = "pr_waiting", "PR Waiting for Review"
        SESSION_LONG = "session_long", "Session Running Long"
        TASK_DUE_TOMORROW = "task_due_tomorrow", "Task Due Tomorrow"
        CONTEXT_HIGH = "context_high", "Context % High"
        BRAIN_STALE = "brain_stale", "Brain Entry Stale"
        NO_ACTIVITY = "no_activity", "No Activity in Period"
        CUSTOM = "custom", "Custom"

    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    name = models.CharField(max_length=200, unique=True)
    condition_type = models.CharField(max_length=30, choices=ConditionType.choices)
    threshold_minutes = models.IntegerField(
        default=240,
        help_text="Threshold in minutes for time-based rules",
    )
    threshold_value = models.IntegerField(
        default=75,
        help_text="Threshold value for percentage-based rules",
    )
    severity = models.CharField(
        max_length=20, choices=Severity.choices, default=Severity.WARNING,
    )
    message_template = models.TextField(
        help_text=(
            "Message template. Variables: {pr_number}, {repo}, {branch}, "
            "{project}, {task_name}, {value}, {threshold}"
        ),
        default="\u26a0\ufe0f Smart Watch alert: {name}",
    )
    enabled = models.BooleanField(default=True)
    send_telegram = models.BooleanField(default=True)
    send_slack = models.BooleanField(default=False)
    cooldown_minutes = models.IntegerField(
        default=60,
        help_text="Don't re-alert for the same condition within this window",
    )
    last_triggered = models.DateTimeField(null=True, blank=True)
    trigger_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["severity", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({'enabled' if self.enabled else 'disabled'})"

    @property
    def in_cooldown(self) -> bool:
        if not self.last_triggered:
            return False
        from django.utils import timezone as tz

        elapsed = (tz.now() - self.last_triggered).total_seconds() / 60
        return elapsed < self.cooldown_minutes


class SmartWatchEvent(models.Model):
    """Record of a Smart Watch alert that was fired."""

    rule = models.ForeignKey(
        SmartWatchRule, on_delete=models.CASCADE, related_name="events",
    )
    message = models.TextField()
    severity = models.CharField(max_length=20)
    context = models.JSONField(default=dict, blank=True)
    notified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"[{self.severity}] {self.message[:60]}"
