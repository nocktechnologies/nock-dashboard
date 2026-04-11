from django.db import models


class NotificationChannel(models.Model):
    CHANNEL_TYPE_CHOICES = [
        ("slack", "Slack"),
        ("discord", "Discord"),
        ("webhook", "Webhook"),
    ]

    name = models.CharField(max_length=100)
    channel_type = models.CharField(max_length=20, choices=CHANNEL_TYPE_CHOICES)
    webhook_url = models.URLField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.channel_type})"


class NotificationRule(models.Model):
    TRIGGER_EVENT_CHOICES = [
        ("pr_merged", "PR Merged"),
        ("pr_opened", "PR Opened"),
        ("ci_failed", "CI Failed"),
        ("ci_passed", "CI Passed"),
        ("coderabbit_approved", "CodeRabbit Approved"),
        ("coderabbit_changes_requested", "CodeRabbit Changes Requested"),
        ("push", "Push"),
        ("asana_comment", "Asana Comment"),
        ("budget_threshold", "Budget Threshold"),
        ("context_stale", "Context Stale"),
        ("session_started", "Session Started"),
        ("session_ended", "Session Ended"),
    ]

    name = models.CharField(max_length=100)
    trigger_event = models.CharField(max_length=50, choices=TRIGGER_EVENT_CHOICES)
    channel = models.ForeignKey(
        NotificationChannel,
        on_delete=models.CASCADE,
        related_name="rules",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["trigger_event", "name"]

    def __str__(self) -> str:
        return f"{self.name} → {self.get_trigger_event_display()}"


class NotificationLog(models.Model):
    rule = models.ForeignKey(
        NotificationRule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
    )
    channel = models.ForeignKey(
        NotificationChannel,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self) -> str:
        status = "OK" if self.success else "FAIL"
        return f"[{status}] {self.event_type} → {self.channel.name}"
