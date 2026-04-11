from django.contrib import admin

from .models import ContextDocument, ContextSnapshot


class ContextSnapshotInline(admin.TabularInline):
    model = ContextSnapshot
    extra = 0
    readonly_fields = ("content_hash", "commit_sha", "line_count", "diff_summary", "captured_at")
    ordering = ("-captured_at", "-pk")


@admin.register(ContextDocument)
class ContextDocumentAdmin(admin.ModelAdmin):
    list_display = ("__str__", "doc_type", "line_count", "is_stale", "last_modified", "last_synced")
    list_filter = ("doc_type", "is_stale", "is_active", "repository")
    search_fields = ("file_path", "title")
    inlines = [ContextSnapshotInline]


@admin.register(ContextSnapshot)
class ContextSnapshotAdmin(admin.ModelAdmin):
    list_display = ("document", "line_count", "diff_summary", "captured_at")
    list_filter = ("document__repository",)
    readonly_fields = ("content_hash", "commit_sha")
