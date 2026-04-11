from django.contrib import admin

from .models import Project, Section, Task, TaskComment


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "color", "is_active", "is_archived", "created_at"]
    list_filter = ["is_active", "is_archived", "color"]
    search_fields = ["name", "description"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ["name", "project", "order"]
    list_filter = ["project"]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "project",
        "section",
        "priority",
        "status",
        "due_date",
        "assignee",
        "completed",
    ]
    list_filter = ["project", "priority", "status", "completed"]
    search_fields = ["name", "description"]
    date_hierarchy = "due_date"


@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    list_display = ["task", "author", "created_at"]
    list_filter = ["author"]
