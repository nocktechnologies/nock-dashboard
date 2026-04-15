from django.contrib import admin

from billing.models import Subscription, SubscriptionPlan


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "tier", "price_cents", "stripe_price_id")
    readonly_fields = ("stripe_price_id",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("workspace", "plan", "status", "current_period_end", "created_at")
    readonly_fields = ("stripe_customer_id", "stripe_subscription_id", "created_at", "updated_at")
    list_select_related = ("workspace", "plan")
