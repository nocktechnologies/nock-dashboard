from django.contrib import admin

from .models import AgentSession, SessionLog, TerminalHeartbeat


class SessionLogInline(admin.TabularInline):
    model = SessionLog
    extra = 0
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)


@admin.register(AgentSession)
class AgentSessionAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "agent",
        "machine",
        "status",
        "branch",
        "started_at",
        "ended_at",
        "estimated_cost",
    )
    list_filter = ("status", "agent", "machine")
    search_fields = ("branch", "task_description", "notes")
    raw_id_fields = ("repository", "pr_generated")
    inlines = (SessionLogInline,)


@admin.register(SessionLog)
class SessionLogAdmin(admin.ModelAdmin):
    list_display = ("__str__", "level", "session", "created_at")
    list_filter = ("level",)
    search_fields = ("message",)
    raw_id_fields = ("session",)


@admin.register(TerminalHeartbeat)
class TerminalHeartbeatAdmin(admin.ModelAdmin):
    list_display = ("machine", "session_count", "received_at", "is_stale")
    readonly_fields = ("sessions", "active_ports", "received_at")
