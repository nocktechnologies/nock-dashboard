from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


def get_default_task_priority() -> str:
    return getattr(settings, "PROJECTS_DEFAULT_PRIORITY", "medium")


def get_default_task_status() -> str:
    return getattr(settings, "PROJECTS_DEFAULT_STATUS", "todo")


class Project(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    description = models.TextField(blank=True, default="")
    color = models.CharField(max_length=20, default="blue")
    is_active = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False)
    asana_gid = models.CharField(max_length=50, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "projects"
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            self.slug = self._build_unique_slug()
        super().save(*args, **kwargs)

    def _build_unique_slug(self) -> str:
        base_slug = slugify(self.name) or "project"
        slug = base_slug
        suffix = 2

        while Project.objects.exclude(pk=self.pk).filter(slug=slug).exists():
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        return slug


class Section(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="sections")
    name = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)
    asana_gid = models.CharField(max_length=50, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "projects"
        ordering = ["project_id", "order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "name"], name="projects_section_unique_name"),
        ]

    def __str__(self) -> str:
        return f"{self.project.name} / {self.name}"


class Task(models.Model):
    PRIORITY_LOW = "low"
    PRIORITY_MEDIUM = "medium"
    PRIORITY_HIGH = "high"
    PRIORITY_URGENT = "urgent"

    STATUS_TODO = "todo"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_BLOCKED = "blocked"
    STATUS_DONE = "done"

    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Low"),
        (PRIORITY_MEDIUM, "Medium"),
        (PRIORITY_HIGH, "High"),
        (PRIORITY_URGENT, "Urgent"),
    ]

    STATUS_CHOICES = [
        (STATUS_TODO, "To Do"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_BLOCKED, "Blocked"),
        (STATUS_DONE, "Done"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    section = models.ForeignKey(
        Section,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    asana_gid = models.CharField(max_length=50, unique=True, null=True, blank=True)
    name = models.CharField(max_length=500)
    description = models.TextField(blank=True, default="")
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default=get_default_task_priority,
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default=get_default_task_status,
    )
    due_date = models.DateField(null=True, blank=True)
    assignee = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Free-text assignee name or identifier",
    )
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0)
    tags = models.JSONField(default=list, blank=True, help_text="List of string tags")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "projects"
        ordering = ["order", "-priority", "due_date", "created_at", "id"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_overdue(self) -> bool:
        if self.completed or not self.due_date:
            return False

        return self.due_date < timezone.localdate()

    def clean(self) -> None:
        super().clean()
        if self.section_id and self.section and self.section.project_id != self.project_id:
            raise ValidationError({"section": "Section must belong to the same project as the task."})

    def save(self, *args, **kwargs) -> None:
        if self.status == self.STATUS_DONE:
            self.completed = True
            if self.completed_at is None:
                self.completed_at = timezone.now()
        else:
            self.completed = False
            self.completed_at = None

        self.full_clean()
        super().save(*args, **kwargs)


class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    text = models.TextField()
    author = models.CharField(max_length=255, default="system")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "projects"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"Comment on {self.task.name} by {self.author}"
