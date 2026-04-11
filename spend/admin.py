from django.contrib import admin

from .models import Expense, Revenue, SpendBudget, SubscriptionTracker, UsagePeriod


@admin.register(UsagePeriod)
class UsagePeriodAdmin(admin.ModelAdmin):
    list_display = ("date", "model", "input_tokens", "output_tokens", "cost_usd", "request_count")
    list_filter = ("model", "date")
    ordering = ("-date", "model")


@admin.register(SpendBudget)
class SpendBudgetAdmin(admin.ModelAdmin):
    list_display = ("month", "budget_usd", "alert_threshold_pct", "alert_sent")
    ordering = ("-month",)


@admin.register(SubscriptionTracker)
class SubscriptionTrackerAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "monthly_cost", "renewal_date", "is_active")
    list_filter = ("provider", "is_active")
    ordering = ("-is_active", "name")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("date", "vendor", "category", "total", "payment_method", "is_refund")
    list_filter = ("category", "payment_method", "is_refund", "date")
    search_fields = ("vendor", "description", "reference")
    ordering = ("-date", "vendor")


@admin.register(Revenue)
class RevenueAdmin(admin.ModelAdmin):
    list_display = ("date", "source", "description", "amount", "client")
    list_filter = ("source", "date")
    search_fields = ("description", "client", "reference")
    ordering = ("-date", "source")
