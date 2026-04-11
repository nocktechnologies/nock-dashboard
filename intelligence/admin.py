from django.contrib import admin

from .models import (
    AdvisorConversation,
    AdvisorMessage,
    BusinessSnapshot,
    PredictiveAlert,
    SmartWatchEvent,
    SmartWatchRule,
    WeeklyMemo,
)


@admin.register(BusinessSnapshot)
class BusinessSnapshotAdmin(admin.ModelAdmin):
    list_display = ("date", "token_count", "generated_at")
    list_filter = ("date",)
    readonly_fields = ("generated_at",)


@admin.register(AdvisorConversation)
class AdvisorConversationAdmin(admin.ModelAdmin):
    list_display = ("pk", "title", "created_at", "updated_at")
    search_fields = ("title",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(AdvisorMessage)
class AdvisorMessageAdmin(admin.ModelAdmin):
    list_display = ("pk", "conversation", "role", "tokens_used", "cost", "created_at")
    list_filter = ("role",)
    readonly_fields = ("created_at",)


@admin.register(PredictiveAlert)
class PredictiveAlertAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "severity", "is_resolved", "created_at")
    list_filter = ("category", "severity", "is_resolved")
    readonly_fields = ("created_at",)


@admin.register(WeeklyMemo)
class WeeklyMemoAdmin(admin.ModelAdmin):
    list_display = ("week_start", "week_end", "tokens_used", "cost", "generated_at")
    readonly_fields = ("generated_at",)


@admin.register(SmartWatchRule)
class SmartWatchRuleAdmin(admin.ModelAdmin):
    list_display = (
        "name", "condition_type", "enabled", "severity",
        "last_triggered", "trigger_count", "cooldown_minutes",
    )
    list_filter = ("severity", "enabled", "condition_type")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at", "last_triggered", "trigger_count")


@admin.register(SmartWatchEvent)
class SmartWatchEventAdmin(admin.ModelAdmin):
    list_display = ("rule", "severity", "message", "created_at", "notified")
    list_filter = ("severity", "notified")
    readonly_fields = ("created_at",)
    raw_id_fields = ("rule",)
