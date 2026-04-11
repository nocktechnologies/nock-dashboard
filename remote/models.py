from django.conf import settings
from django.db import models


class AgentToken(models.Model):
    """Auth token for Mac agent daemon.

    The raw token is shown once at creation; only its SHA-256 hash is stored.
    """

    name = models.CharField(max_length=100)
    token_hash = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        status = "active" if self.is_active else "inactive"
        return f"{self.name} ({status})"


class AgentStatus(models.Model):
    """Tracks connected agent state."""

    agent_token = models.OneToOneField(
        AgentToken, on_delete=models.CASCADE, related_name="status"
    )
    is_online = models.BooleanField(default=False)
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    machine_name = models.CharField(max_length=100, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    connected_at = models.DateTimeField(null=True, blank=True)
    disconnected_at = models.DateTimeField(null=True, blank=True)
    channel_name = models.CharField(max_length=255, blank=True)
    active_sessions = models.IntegerField(default=0)

    class Meta:
        ordering = ["-connected_at", "-id"]
        verbose_name_plural = "agent statuses"

    def __str__(self) -> str:
        status = "online" if self.is_online else "offline"
        return f"{self.agent_token.name} ({status})"


class CommandRequest(models.Model):
    """Command queued from phone for Mac agent execution."""

    class CommandType(models.TextChoices):
        START_SESSION = "start_session", "Start Claude Code Session"
        STOP_SESSION = "stop_session", "Stop Session"
        SEND_PROMPT = "send_prompt", "Send Prompt"
        LIST_PROCESSES = "list_processes", "List Processes"
        KILL_ALL = "kill_all", "Kill All Sessions"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent to Agent"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    command_type = models.CharField(max_length=20, choices=CommandType.choices)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.QUEUED
    )
    result = models.TextField(blank=True)
    hmac_signature = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    session_id = models.CharField(max_length=100, blank=True, db_index=True)
    conversation = models.ForeignKey(
        "ConversationThread",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commands",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="remote_commands",
    )

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.get_command_type_display()} ({self.get_status_display()})"


class SessionOutputBuffer(models.Model):
    """Ring buffer for streaming output from Mac agent."""

    class Stream(models.TextChoices):
        STDOUT = "stdout", "stdout"
        STDERR = "stderr", "stderr"

    session_id = models.CharField(max_length=100, db_index=True)
    line_number = models.IntegerField()
    content = models.TextField()
    stream = models.CharField(max_length=6, choices=Stream.choices)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session_id", "line_number"],
                name="unique_output_session_line",
            ),
        ]
        ordering = ["session_id", "line_number"]

    def __str__(self) -> str:
        return f"{self.session_id}:{self.line_number} ({self.stream})"


class ConversationThread(models.Model):
    """A persistent chat conversation grouping multiple commands/prompts."""

    repo = models.CharField(max_length=100)
    title = models.CharField(max_length=200, blank=True)
    session_id = models.CharField(max_length=100, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversations",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-updated_at", "-id"]

    def __str__(self) -> str:
        return f"{self.repo}: {self.title or 'Untitled'} (#{self.pk})"


class CommandAuditLog(models.Model):
    """Audit trail for every command action."""

    command = models.ForeignKey(
        CommandRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=50)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    payload_hash = models.CharField(max_length=64, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return f"{self.action} at {self.timestamp}"


class PushSubscription(models.Model):
    """Web Push API subscription for a user's browser."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.URLField(max_length=500)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "endpoint"],
                name="unique_push_subscription",
            ),
        ]

    def __str__(self) -> str:
        return f"Push subscription for {self.user.username}"
