from django.contrib import admin

from workspaces.models import Workspace, WorkspaceMembership


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "owner", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["name", "slug", "owner__email"]
    readonly_fields = ["slug", "created_at"]


@admin.register(WorkspaceMembership)
class WorkspaceMembershipAdmin(admin.ModelAdmin):
    list_display = ["workspace", "user", "role", "invited_at", "accepted_at"]
    list_filter = ["role", "workspace"]
    search_fields = ["user__email", "workspace__name"]
