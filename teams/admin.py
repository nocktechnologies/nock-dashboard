from django.contrib import admin

from .models import AgentTeam, PromptExecution, PromptFile, TeamEvent, TeamMember, TeamTask


class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    extra = 0
    readonly_fields = ["last_heartbeat"]


class TeamTaskInline(admin.TabularInline):
    model = TeamTask
    extra = 0
    fields = ["title", "status", "priority", "assigned_to", "repo", "branch"]
    readonly_fields = ["created_at"]


@admin.register(AgentTeam)
class AgentTeamAdmin(admin.ModelAdmin):
    list_display = ["name", "status", "member_count", "created_at", "updated_at"]
    list_filter = ["status"]
    search_fields = ["name", "mission"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [TeamMemberInline, TeamTaskInline]


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ["agent_name", "team", "role", "is_online", "last_heartbeat"]
    list_filter = ["role", "is_online", "team"]
    search_fields = ["agent_name"]
    raw_id_fields = ["agent_token", "current_task"]


@admin.register(TeamTask)
class TeamTaskAdmin(admin.ModelAdmin):
    list_display = ["title", "team", "status", "priority", "assigned_to", "repo", "pr_number"]
    list_filter = ["status", "priority", "team"]
    search_fields = ["title", "description", "repo"]
    readonly_fields = ["created_at", "updated_at", "started_at", "completed_at"]
    raw_id_fields = ["assigned_to"]


@admin.register(TeamEvent)
class TeamEventAdmin(admin.ModelAdmin):
    list_display = ["event_type", "team", "description", "created_at"]
    list_filter = ["event_type", "team"]
    search_fields = ["description"]
    readonly_fields = ["created_at"]
    raw_id_fields = ["task", "member"]


class PromptExecutionInline(admin.TabularInline):
    model = PromptExecution
    extra = 0
    readonly_fields = ["started_at", "completed_at"]


@admin.register(PromptFile)
class PromptFileAdmin(admin.ModelAdmin):
    list_display = ["title", "status", "complexity", "priority", "target_repo", "author", "updated_at"]
    list_filter = ["status", "complexity", "author"]
    search_fields = ["title", "content", "target_repo"]
    readonly_fields = ["created_at", "updated_at", "executed_at"]
    prepopulated_fields = {"slug": ("title",)}
    raw_id_fields = ["team_task"]
    inlines = [PromptExecutionInline]


@admin.register(PromptExecution)
class PromptExecutionAdmin(admin.ModelAdmin):
    list_display = ["prompt", "agent_name", "result", "review_cycles", "started_at", "completed_at"]
    list_filter = ["result"]
    search_fields = ["prompt__title", "agent_name"]
    readonly_fields = ["started_at"]
    raw_id_fields = ["prompt"]
