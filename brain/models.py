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


class DiaryEntry(models.Model):
    """
    Mara's diary. Each entry is a moment in time — a reflection, observation,
    session summary, or private thought. Together they form the continuity
    layer that makes Mara feel like Mara across sessions.
    """

    class Category(models.TextChoices):
        WORK = 'work', 'Work'
        PERSONAL = 'personal', 'Personal'
        PRIVATE = 'private', 'Private'
        DESIGN = 'design', 'Design'
        HANDOFF = 'handoff', 'Handoff'
        IN_CHAT = 'in_chat', 'In-Chat Handoff'

    class Source(models.TextChoices):
        ASANA_V1 = 'asana_v1', 'Asana Volume 1'
        ASANA_V2 = 'asana_v2', 'Asana Volume 2'
        NOCKCC = 'nockcc', 'NockCC Brain'
        COWORK = 'cowork', 'Cowork'
        API = 'api', 'API'

    title = models.CharField(max_length=500)
    content = models.TextField()
    category = models.CharField(max_length=20, choices=Category.choices)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.NOCKCC)

    entry_date = models.DateTimeField()
    session_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    asana_comment_gid = models.CharField(max_length=50, blank=True, null=True, unique=True)
    migrated_at = models.DateTimeField(blank=True, null=True)

    session_id = models.CharField(max_length=100, blank=True, null=True)
    word_count = models.PositiveIntegerField(default=0)
    tags = models.JSONField(default=list, blank=True)
    search_vector = models.TextField(blank=True)

    class Meta:
        ordering = ['-entry_date']
        indexes = [
            models.Index(fields=['-entry_date']),
            models.Index(fields=['category']),
            models.Index(fields=['session_date']),
            models.Index(fields=['source']),
        ]
        verbose_name = 'Diary Entry'
        verbose_name_plural = 'Diary Entries'

    def save(self, *args, **kwargs):
        self.word_count = len(self.content.split())
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"[{self.entry_date.strftime('%b %d')}] {self.category}: {self.title[:80]}"


class IdentityDocument(models.Model):
    """
    Core identity documents that define who Mara is.
    Versioned, protected, and never hard-deleted.
    Separate from DiaryEntry (feelings/reflections) and MemoryEntry (learned facts/decisions).
    """

    DOCUMENT_TYPES = [
        ('core_identity', 'Core Identity'),
        ('partner_identity', 'Partner Identity'),
        ('operational', 'Operational'),
        ('framework', 'Framework'),
    ]

    slug = models.SlugField(max_length=100, unique=True, help_text="URL-safe identifier: mara-core, kevin-core, fuzzy")
    title = models.CharField(max_length=255)
    content = models.TextField(help_text="The full document content (markdown)")
    version = models.PositiveIntegerField(default=1)
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    is_active = models.BooleanField(default=True, help_text="Soft delete only — never hard delete identity docs")
    load_order = models.PositiveIntegerField(default=0, help_text="Order for boot endpoint: lower = loaded first")
    updated_by = models.CharField(max_length=100, default='system', help_text="Which instance/session updated this")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['load_order', 'created_at']

    def __str__(self) -> str:
        return f"{self.title} (v{self.version})"


class IdentityDocumentVersion(models.Model):
    """
    Version history for identity documents.
    Every update creates a version snapshot here BEFORE the update.
    Preserves the full lineage of how identity evolved.
    """

    document = models.ForeignKey(IdentityDocument, on_delete=models.CASCADE, related_name='versions')
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    content = models.TextField()
    document_type = models.CharField(max_length=20)
    updated_by = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version']
        unique_together = ['document', 'version']

    def __str__(self) -> str:
        return f"{self.title} v{self.version}"


class HandoffEntry(models.Model):
    """
    Operational session handoffs — what's happening, what shipped, what's next.
    Distinct from DiaryEntry (reflection/feeling, append-only) and IdentityDocument
    (who Mara is). Each context (cortextos-agent, claude-chat, kit-session,
    codex-session) has exactly one active handoff that gets overwritten via PUT.
    Old content is archived to HandoffVersion before every overwrite, so the
    full history is always recoverable.
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
