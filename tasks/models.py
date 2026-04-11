from django.db import models
from django.utils import timezone


class AsanaProject(models.Model):
    asana_gid = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    color = models.CharField(max_length=20, default="blue")
    is_active = models.BooleanField(default=True)
    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class AsanaSection(models.Model):
    """A section within an Asana project (e.g. '📋 Living Documents').

    Cached locally from the Asana API so the /api/tasks/move/ endpoint can
    resolve section gids without a round-trip and so clients can enumerate
    available sections per project.
    """

    asana_gid = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    project = models.ForeignKey(
        AsanaProject,
        on_delete=models.CASCADE,
        related_name="sections",
    )
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["project__name", "order", "name"]

    def __str__(self) -> str:
        return f"{self.project.name} / {self.name}"


class AsanaTask(models.Model):
    asana_gid = models.CharField(max_length=50, unique=True)
    project = models.ForeignKey(
        AsanaProject,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    name = models.CharField(max_length=500)
    section_name = models.CharField(max_length=255, blank=True)
    assignee_name = models.CharField(max_length=255, blank=True)
    due_on = models.DateField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    priority = models.CharField(max_length=20, null=True, blank=True)
    notes_preview = models.TextField(blank=True)
    permalink_url = models.URLField(max_length=500, blank=True)
    linked_pr = models.ForeignKey(
        "pipeline.PullRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_tasks",
    )
    last_synced = models.DateTimeField(auto_now=True)
    last_comment_gid = models.CharField(max_length=50, blank=True, default="")
    asana_updated_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Soft-delete timestamp set when task is deleted via the write-back API.",
    )

    class Meta:
        # Default ordering is lexicographic on priority; views override this
        # with a Case/When priority_rank annotation for business-priority order.
        ordering = ["due_on", "-priority"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_overdue(self) -> bool:
        if self.completed or not self.due_on:
            return False
        return self.due_on < timezone.localdate()
