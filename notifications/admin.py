from django.contrib import admin

from .models import NotificationChannel, NotificationLog, NotificationRule


@admin.register(NotificationChannel)
class NotificationChannelAdmin(admin.ModelAdmin):
    list_display = ("name", "channel_type", "is_active", "created_at")
    list_filter = ("channel_type", "is_active")


@admin.register(NotificationRule)
class NotificationRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "trigger_event", "channel", "is_active")
    list_filter = ("trigger_event", "is_active")


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("event_type", "channel", "success", "sent_at")
    list_filter = ("success", "event_type")
    ordering = ("-sent_at",)
