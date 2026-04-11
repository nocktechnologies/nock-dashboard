from django.contrib import admin

from .models import (
    ConsolidationLog,
    DiaryEntry,
    HandoffEntry,
    HandoffVersion,
    IdentityDocument,
    IdentityDocumentVersion,
    MemoryEntry,
    ResearchChunk,
    ResearchDocument,
)


@admin.register(MemoryEntry)
class MemoryEntryAdmin(admin.ModelAdmin):
    list_display = ("__str__", "category", "confidence", "source", "updated_at")
    list_filter = ("category", "confidence", "source")
    search_fields = ("key", "value")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ConsolidationLog)
class ConsolidationLogAdmin(admin.ModelAdmin):
    list_display = (
        "started_at", "completed_at", "entries_reviewed",
        "entries_promoted", "entries_archived", "entries_pruned",
    )
    readonly_fields = (
        "started_at", "completed_at", "entries_reviewed",
        "entries_promoted", "entries_archived", "entries_pruned",
        "contradictions_resolved", "notes",
    )


@admin.register(DiaryEntry)
class DiaryEntryAdmin(admin.ModelAdmin):
    list_display = ("__str__", "category", "source", "session_date", "word_count", "entry_date")
    list_filter = ("category", "source", "session_date")
    search_fields = ("title", "content", "tags")
    readonly_fields = ("created_at", "updated_at", "word_count", "asana_comment_gid", "migrated_at")
    date_hierarchy = "session_date"


@admin.register(IdentityDocument)
class IdentityDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "version", "document_type", "is_active", "load_order", "updated_at")
    list_filter = ("document_type", "is_active")
    search_fields = ("title", "slug", "content")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("version", "created_at", "updated_at")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(IdentityDocumentVersion)
class IdentityDocumentVersionAdmin(admin.ModelAdmin):
    list_display = ("document", "version", "title", "updated_by", "created_at")
    list_filter = ("document",)
    readonly_fields = ("document", "version", "title", "content", "document_type", "updated_by", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(HandoffEntry)
class HandoffEntryAdmin(admin.ModelAdmin):
    list_display = ("context", "title", "version", "open_items_count", "completed_items_count", "deferred_items_count", "updated_at")
    list_filter = ("context", "previous_items_resolved")
    search_fields = ("title", "content", "context")
    readonly_fields = ("version", "created_at", "updated_at")

    def has_delete_permission(self, request, obj=None):
        # Handoffs are append-only at the version level — never hard delete the active row.
        return False


@admin.register(HandoffVersion)
class HandoffVersionAdmin(admin.ModelAdmin):
    list_display = ("handoff", "version", "title", "updated_by", "created_at")
    list_filter = ("handoff__context",)
    readonly_fields = (
        "handoff", "version", "title", "content", "action_items",
        "previous_items_resolved", "updated_by", "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ResearchDocument)
class ResearchDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "topic", "source_type", "word_count", "is_indexed", "updated_at")
    list_filter = ("source_type", "topic", "is_indexed")
    search_fields = ("title", "content", "topic", "slug")
    # Every content-affecting field is readonly. Editing any of these through
    # the admin would desync file_hash / chunks / is_indexed and silently serve
    # stale embeddings. The source of truth is the vault + the management
    # commands (ingest_research + embed_research); admin is view-only.
    readonly_fields = (
        "slug",
        "title",
        "source_path",
        "source_type",
        "topic",
        "content",
        "word_count",
        "file_hash",
        "is_indexed",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        # New documents must come from the ingest_research command so that
        # file_hash and chunks stay consistent.
        return False


@admin.register(ResearchChunk)
class ResearchChunkAdmin(admin.ModelAdmin):
    list_display = ("document", "chunk_index", "word_count", "has_embedding")
    list_filter = ("document__topic", "document__source_type")
    search_fields = ("content", "document__slug", "document__title")
    readonly_fields = ("document", "chunk_index", "content", "word_count", "metadata", "created_at")
    # Don't render the 1536-float embedding vector in the form — just show the flag below.
    exclude = ("embedding",)

    def has_embedding(self, obj: ResearchChunk) -> bool:
        return obj.embedding is not None
    has_embedding.boolean = True  # type: ignore[attr-defined]
    has_embedding.short_description = "Embedded"  # type: ignore[attr-defined]
