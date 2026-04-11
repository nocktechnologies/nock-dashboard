from django.contrib import admin

from .models import AsanaProject, AsanaSection, AsanaTask


@admin.register(AsanaProject)
class AsanaProjectAdmin(admin.ModelAdmin):
    list_display = ["name", "asana_gid", "color", "is_active", "last_synced"]
    list_filter = ["is_active", "color"]
    search_fields = ["name", "asana_gid"]
    readonly_fields = ["created_at", "last_synced"]


@admin.register(AsanaSection)
class AsanaSectionAdmin(admin.ModelAdmin):
    list_display = ["name", "project", "asana_gid", "order", "updated_at"]
    list_filter = ["project"]
    search_fields = ["name", "asana_gid"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(AsanaTask)
class AsanaTaskAdmin(admin.ModelAdmin):
    list_display = [
        "name", "project", "section_name", "due_on",
        "priority", "completed", "assignee_name", "deleted_at",
    ]
    list_filter = ["project", "completed", "priority"]
    search_fields = ["name", "assignee_name"]
    raw_id_fields = ["linked_pr"]
    readonly_fields = ["last_synced", "deleted_at"]
