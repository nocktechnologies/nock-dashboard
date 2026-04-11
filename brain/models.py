from django.db import models
from django.utils import timezone
from pgvector.django import VectorField


class MemoryEntry(models.Model):
    CATEGORY_CHOICES = [
        ("identity", "Identity"),
        ("relationship", "Relationship"),
        ("domain", "Domain"),
        ("decision", "Decision"),
        ("project", "Project"),
        ("personal", "Personal"),
        ("lesson", "Lesson"),
        ("tool", "Tool"),
        ("continuity", "Continuity"),
    ]

    CONFIDENCE_CHOICES = [
        ("observed", "Observed"),
        ("inferred", "Inferred"),
        ("stale", "Stale"),
    ]

    key = models.CharField(max_length=200)
    value = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    confidence = models.CharField(
        max_length=20, choices=CONFIDENCE_CHOICES, default="observed"
    )
    source = models.CharField(max_length=100, default="manual")
    tags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["key", "category"]
        ordering = ["category", "key"]

    def __str__(self) -> str:
        return f"{self.category}/{self.key}"

    @property
    def is_stale(self) -> bool:
        return (timezone.now() - self.updated_at).days > 30

    @property
    def preview(self) -> str:
        return self.value[:200] if len(self.value) > 200 else self.value


class ConsolidationLog(models.Model):
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    entries_reviewed = models.IntegerField(default=0)
    entries_promoted = models.IntegerField(default=0)
    entries_archived = models.IntegerField(default=0)
    entries_pruned = models.IntegerField(default=0)
    contradictions_resolved = models.IntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"Consolidation {self.started_at:%Y-%m-%d %H:%M}"


class MorningNoteSent(models.Model):
    """Atomic per-day claim to prevent duplicate morning notes."""

    date = models.DateField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"MorningNote {self.date}"


class HandoffEntry(models.Model):
    """
    Operational session handoffs — what's happening, what shipped, what's next.
    Each context (cortextos-agent, claude-chat, kit-session, codex-session)
    has exactly one active handoff that gets overwritten via PUT. Old content
    is archived to HandoffVersion before every overwrite, so the full history
    is always recoverable.
    """

    class Context(models.TextChoices):
        CORTEXTOS_AGENT = "cortextos-agent", "CortexTOS Agent"
        CLAUDE_CHAT = "claude-chat", "Claude Chat"
        KIT_SESSION = "kit-session", "Kit Session"
        CODEX_SESSION = "codex-session", "Codex Session"

    context = models.CharField(
        max_length=30,
        choices=Context.choices,
        unique=True,
        help_text="Which session origin this handoff describes — one active handoff per context.",
    )
    title = models.CharField(max_length=500)
    content = models.TextField(
        help_text="Narrative — what's happening, what shipped, what's next, technical state.",
    )
    action_items = models.JSONField(
        default=list,
        blank=True,
        help_text="List of {description, status: open|completed|deferred, reason: null|string}.",
    )
    previous_items_resolved = models.BooleanField(
        default=False,
        help_text="Was the previous handoff's action items checked before this overwrite?",
    )
    version = models.PositiveIntegerField(default=1)
    updated_by = models.CharField(max_length=100, default="system")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Handoff Entry"
        verbose_name_plural = "Handoff Entries"

    def __str__(self) -> str:
        return f"{self.context} v{self.version}: {self.title[:60]}"

    @property
    def open_items_count(self) -> int:
        return sum(1 for item in self.action_items if item.get("status") == "open")

    @property
    def completed_items_count(self) -> int:
        return sum(1 for item in self.action_items if item.get("status") == "completed")

    @property
    def deferred_items_count(self) -> int:
        return sum(1 for item in self.action_items if item.get("status") == "deferred")


class HandoffVersion(models.Model):
    """
    Immutable version snapshot of a HandoffEntry.
    Created BEFORE every PUT overwrite, preserving the full handoff lineage.
    """

    handoff = models.ForeignKey(
        HandoffEntry, on_delete=models.CASCADE, related_name="versions",
    )
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=500)
    content = models.TextField()
    action_items = models.JSONField(default=list, blank=True)
    previous_items_resolved = models.BooleanField(default=False)
    updated_by = models.CharField(max_length=100, default="system")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]
        unique_together = ["handoff", "version"]

    def __str__(self) -> str:
        return f"{self.handoff.context} v{self.version}"


class ResearchDocument(models.Model):
    """
    A source document from the user's research vault.
    Each markdown file becomes one ResearchDocument. Content is split into
    ResearchChunks with embeddings for semantic search.
    """

    SOURCE_TYPES = [
        ('research', 'Kimi Research'),
        ('wiki', 'Wiki Summary'),
        ('article', 'Article'),
        ('transcript', 'Transcript'),
    ]

    slug = models.SlugField(
        max_length=200,
        unique=True,
        help_text="Derived from file path: raw-research-abl-underwriting-overview",
    )
    title = models.CharField(max_length=500)
    source_path = models.CharField(
        max_length=500,
        help_text="Original vault path: raw/research/abl-underwriting/overview.md",
    )
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPES)
    topic = models.CharField(
        max_length=200,
        help_text="Topic directory: abl-underwriting, factoring-pricing, etc.",
    )
    content = models.TextField(help_text="Full document content")
    word_count = models.PositiveIntegerField(default=0)
    file_hash = models.CharField(
        max_length=64,
        help_text="SHA-256 of file content for change detection",
    )
    is_indexed = models.BooleanField(
        default=False,
        help_text="True when all chunks have embeddings",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['topic', 'title']
        indexes = [
            models.Index(fields=['topic']),
            models.Index(fields=['source_type']),
            models.Index(fields=['is_indexed']),
        ]

    def __str__(self) -> str:
        return f"{self.topic}/{self.title}"


class ResearchChunk(models.Model):
    """
    A chunk of a ResearchDocument with its embedding vector.
    Documents are split into overlapping ~500-word chunks for semantic search.
    """

    document = models.ForeignKey(
        ResearchDocument, on_delete=models.CASCADE, related_name='chunks',
    )
    chunk_index = models.PositiveIntegerField(
        help_text="Position of this chunk in the document (0-based)",
    )
    content = models.TextField(help_text="The chunk text")
    word_count = models.PositiveIntegerField(default=0)
    embedding = VectorField(
        dimensions=1536,
        null=True,
        help_text="OpenAI text-embedding-3-small vector",
    )
    metadata = models.JSONField(
        default=dict,
        help_text="Optional metadata: headings, section context",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['document', 'chunk_index']
        unique_together = ['document', 'chunk_index']

    def __str__(self) -> str:
        return f"{self.document.slug} chunk {self.chunk_index}"
