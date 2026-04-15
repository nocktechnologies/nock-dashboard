from django.db import models
from django.utils import timezone


class ContextDocument(models.Model):
    DOC_TYPE_CHOICES = [
        ("claude_md", "CLAUDE.md"),
        ("architecture", "Architecture Doc"),
        ("skill_file", "Skill File"),
        ("design_doc", "Design Document"),
        ("changelog", "Changelog"),
        ("master_ref", "Master Reference"),
        ("other", "Other"),
    ]

    repository = models.ForeignKey(
        "pipeline.Repository",
        on_delete=models.CASCADE,
        related_name="context_docs",
    )
    doc_type = models.CharField(max_length=50, choices=DOC_TYPE_CHOICES)
    file_path = models.CharField(max_length=500)
    title = models.CharField(max_length=255)
    last_content_hash = models.CharField(max_length=64, blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)
    last_modified = models.DateTimeField(null=True, blank=True)
    line_count = models.IntegerField(default=0)
    is_stale = models.BooleanField(default=False)
    staleness_threshold_days = models.IntegerField(default=7)
    is_active = models.BooleanField(default=True)
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="context_documents",
    )

    class Meta:
        ordering = ["repository", "file_path"]
        constraints = [
            models.UniqueConstraint(
                fields=["repository", "file_path"],
                name="unique_context_doc_repo_path",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.repository.name}/{self.file_path}"

    @property
    def days_since_modified(self) -> int | None:
        if not self.last_modified:
            return None
        return (timezone.now() - self.last_modified).days

    def update_staleness(self) -> None:
        """Recompute is_stale based on last_modified and threshold."""
        from datetime import timedelta

        if not self.last_modified:
            self.is_stale = False
            return
        delta = timezone.now() - self.last_modified
        self.is_stale = delta > timedelta(days=self.staleness_threshold_days)


class ContextSnapshot(models.Model):
    document = models.ForeignKey(
        ContextDocument,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    content_hash = models.CharField(max_length=64)
    commit_sha = models.CharField(max_length=40, blank=True)
    line_count = models.IntegerField(default=0)
    diff_summary = models.TextField(blank=True)
    captured_at = models.DateTimeField(auto_now_add=True)
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="context_snapshots",
    )

    class Meta:
        ordering = ["-captured_at", "-pk"]

    def __str__(self) -> str:
        return f"{self.document.title} @ {self.captured_at}"
