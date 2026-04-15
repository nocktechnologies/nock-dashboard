from decimal import Decimal

from django.db import models
from django.utils import timezone


class AgentSession(models.Model):
    AGENT_CHOICES = [
        ("claude_code", "Claude Code"),
        ("codex", "Codex Desktop"),
        ("copilot", "GitHub Copilot"),
        ("gemini", "Gemini"),
        ("kimi", "Kimi"),
        ("chatgpt", "ChatGPT"),
        ("claude_chat", "Claude Chat"),
        ("other", "Other"),
    ]

    STATUS_CHOICES = [
        ("active", "Active"),
        ("idle", "Idle"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("paused", "Paused"),
        ("tracking", "Tracking"),
    ]

    MACHINE_CHOICES = [
        ("windows", "Windows Primary"),
        ("mac", "Mac Secondary"),
        ("other", "Other"),
    ]

    agent = models.CharField(max_length=50, choices=AGENT_CHOICES)
    machine = models.CharField(max_length=50, choices=MACHINE_CHOICES, default="mac")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    branch = models.CharField(max_length=255, blank=True)
    task_description = models.TextField(blank=True)
    repository = models.ForeignKey(
        "pipeline.Repository",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
    )
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    last_activity = models.DateTimeField(auto_now=True)
    tokens_input = models.BigIntegerField(default=0)
    tokens_output = models.BigIntegerField(default=0)
    estimated_cost = models.DecimalField(
        max_digits=10, decimal_places=4, default=Decimal("0")
    )
    commits_generated = models.IntegerField(default=0)
    pr_generated = models.ForeignKey(
        "pipeline.PullRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generating_session",
    )
    notes = models.TextField(blank=True)
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="agent_sessions",
    )

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.get_agent_display()} on {self.get_machine_display()} — {self.branch} ({self.status})"


class SessionLog(models.Model):
    LEVEL_CHOICES = [
        ("info", "Info"),
        ("warning", "Warning"),
        ("error", "Error"),
        ("success", "Success"),
    ]

    session = models.ForeignKey(
        AgentSession,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="session_logs",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.level}: {self.message[:50]}"


class TerminalHeartbeat(models.Model):
    """Latest state snapshot from Nock Terminal desktop app.

    Single-row table — each heartbeat overwrites the previous one.
    Not a history table. For historical session data, use AgentSession.
    """

    machine = models.CharField(max_length=50, default="mac", unique=True)
    sessions = models.JSONField(
        default=list, help_text="Array of active session states from Terminal"
    )
    active_ports = models.JSONField(
        default=list, help_text="Array of port numbers detected by Terminal"
    )
    terminal_version = models.CharField(max_length=50, blank=True)
    received_at = models.DateTimeField(auto_now=True)
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="terminal_heartbeats",
    )

    class Meta:
        ordering = ["-received_at"]
        verbose_name = "terminal heartbeat"
        verbose_name_plural = "terminal heartbeats"

    def __str__(self) -> str:
        return f"Terminal ({self.machine}) — {self.session_count} sessions — {self.received_at}"

    @property
    def is_stale(self) -> bool:
        """Heartbeat older than 2 minutes is considered stale (Terminal offline)."""
        if not self.received_at:
            return True
        return (timezone.now() - self.received_at).total_seconds() > 120

    @property
    def session_count(self) -> int:
        return len(self.sessions) if isinstance(self.sessions, list) else 0
