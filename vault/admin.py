from django.contrib import admin

from .models import Document, SessionReport


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "filename", "file_size", "uploaded_at")
    list_filter = ("category",)
    search_fields = ("title", "tags", "description")
    ordering = ("-uploaded_at",)


@admin.register(SessionReport)
class SessionReportAdmin(admin.ModelAdmin):
    list_display = ("project_name", "title", "branch", "captured_at", "machine")
    list_filter = ("project_name", "machine")
    search_fields = ("project_name", "title", "content")
    readonly_fields = ("received_at",)
