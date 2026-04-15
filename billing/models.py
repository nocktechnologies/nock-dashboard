"""Billing models — SubscriptionPlan and Subscription."""

from __future__ import annotations

from django.db import models


class SubscriptionPlan(models.Model):
    TIER_FREE = "free"
    TIER_SOLO = "solo"
    TIER_FLEET = "fleet"
    TIER_CHOICES = [
        (TIER_FREE, "Free"),
        (TIER_SOLO, "Solo"),
        (TIER_FLEET, "Fleet"),
    ]

    name = models.CharField(max_length=50)
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, unique=True)
    stripe_price_id = models.CharField(max_length=120, blank=True)
    price_cents = models.PositiveIntegerField(default=0)
    features_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["price_cents"]

    def __str__(self) -> str:
        return f"{self.name} ({self.tier})"


class Subscription(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_CANCELED = "canceled"
    STATUS_PAST_DUE = "past_due"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_CANCELED, "Canceled"),
        (STATUS_PAST_DUE, "Past due"),
    ]

    workspace = models.OneToOneField(
        "workspaces.Workspace",
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    stripe_customer_id = models.CharField(max_length=120, blank=True)
    stripe_subscription_id = models.CharField(
        max_length=120, blank=True, null=True, unique=True
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE
    )
    current_period_end = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.workspace} — {self.plan.tier} ({self.status})"
