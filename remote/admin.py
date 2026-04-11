from django.contrib import admin

from .models import (
    AgentStatus,
    AgentToken,
    CommandAuditLog,
    CommandRequest,
    PushSubscription,
    SessionOutputBuffer,
)


@admin.register(AgentToken)
class AgentTokenAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "created_at", "last_used_at"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    readonly_fields = ["token_hash", "created_at"]


@admin.register(AgentStatus)
class AgentStatusAdmin(admin.ModelAdmin):
    list_display = [
        "agent_token",
        "is_online",
        "machine_name",
        "last_heartbeat",
        "connected_at",
    ]
    list_filter = ["is_online"]
    search_fields = ["machine_name"]
    readonly_fields = ["channel_name"]


@admin.register(CommandRequest)
class CommandRequestAdmin(admin.ModelAdmin):
    list_display = [
        "command_type",
        "status",
        "session_id",
        "created_at",
        "sent_at",
        "completed_at",
    ]
    list_filter = ["command_type", "status"]
    search_fields = ["session_id"]
    readonly_fields = ["hmac_signature", "created_at"]


@admin.register(SessionOutputBuffer)
class SessionOutputBufferAdmin(admin.ModelAdmin):
    list_display = ["session_id", "line_number", "stream", "timestamp"]
    list_filter = ["stream"]
    search_fields = ["session_id", "content"]


@admin.register(CommandAuditLog)
class CommandAuditLogAdmin(admin.ModelAdmin):
    list_display = ["action", "source_ip", "timestamp", "duration_ms"]
    list_filter = ["action"]
    search_fields = ["action", "source_ip"]
    readonly_fields = ["timestamp"]


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ["user", "endpoint", "created_at"]
    list_filter = ["user"]
    search_fields = ["endpoint"]
    readonly_fields = ["created_at"]
