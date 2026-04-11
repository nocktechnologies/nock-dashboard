from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


def validate_file_size(value: object) -> None:
    """Reject uploads larger than MAX_UPLOAD_SIZE."""
    if value.size > MAX_UPLOAD_SIZE:
        raise ValidationError(
            f"File size {value.size} bytes exceeds the {MAX_UPLOAD_SIZE // (1024 * 1024)} MB limit."
        )


class Document(models.Model):
    CATEGORIES = [
        ("formation", "Business Formation"),
        ("legal", "Legal & Contracts"),
        ("financial", "Financial"),
        ("insurance", "Insurance"),
        ("tax", "Tax Documents"),
        ("trademark", "Trademark & IP"),
        ("reports", "Reports & Memos"),
        ("other", "Other"),
    ]

    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORIES)
    file = models.FileField(
        upload_to="vault/",
        blank=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["pdf", "png", "jpg", "jpeg", "doc", "docx", "xls", "xlsx"]
            ),
            validate_file_size,
        ],
    )
    filename = models.CharField(max_length=200)
    file_size = models.IntegerField(default=0)  # bytes
    file_type = models.CharField(max_length=50, blank=True)  # mime type
    description = models.TextField(blank=True)
    tags = models.CharField(max_length=500, blank=True)  # comma-separated
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return self.title

    @property
    def file_size_display(self) -> str:
        if self.file_size < 1024:
            return f"{self.file_size} B"
        if self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        return f"{self.file_size / (1024 * 1024):.1f} MB"

    @property
    def is_image(self) -> bool:
        return self.file_type.startswith("image/") if self.file_type else False

    @property
    def is_pdf(self) -> bool:
        return self.file_type == "application/pdf"

    @property
    def tag_list(self) -> list[str]:
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]


class SessionReport(models.Model):
    """Captured session summary from Nock Terminal.

    When a Claude Code session ends and Terminal detects a summary in the output,
    it captures the text and posts it here. These are separate from vault Documents —
    auto-generated, text-only, browsable from the mobile app.
    """

    project_name = models.CharField(max_length=200)
    title = models.CharField(max_length=300, blank=True)
    content = models.TextField(help_text="Markdown content of the session report")
    branch = models.CharField(max_length=255, blank=True)
    captured_at = models.DateTimeField(help_text="When Terminal captured this report")
    received_at = models.DateTimeField(auto_now_add=True)
    machine = models.CharField(max_length=50, default="mac")

    class Meta:
        ordering = ["-captured_at"]

    def __str__(self) -> str:
        return f"{self.project_name} — {self.captured_at:%Y-%m-%d %H:%M}"

    @property
    def content_preview(self) -> str:
        """First 200 characters for list views."""
        if len(self.content) <= 200:
            return self.content
        return self.content[:200] + "..."
