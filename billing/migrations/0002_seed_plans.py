"""Seed the three SubscriptionPlan rows (free / solo / fleet).

Uses get_or_create by tier so this migration is idempotent on re-runs
and safe against manually pre-created rows.
"""

from __future__ import annotations

from django.db import migrations


def seed_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model("billing", "SubscriptionPlan")

    # Stripe price IDs are read from settings at migration time; fall back to ""
    # so a fresh DB without STRIPE_* env vars still migrates cleanly.
    try:
        from django.conf import settings

        solo_price_id = getattr(settings, "STRIPE_SOLO_PRICE_ID", "")
        fleet_price_id = getattr(settings, "STRIPE_FLEET_PRICE_ID", "")
    except Exception:  # noqa: BLE001
        solo_price_id = ""
        fleet_price_id = ""

    plans = [
        {"tier": "free", "name": "Free", "stripe_price_id": "", "price_cents": 0},
        {
            "tier": "solo",
            "name": "Solo",
            "stripe_price_id": solo_price_id,
            "price_cents": 4900,
        },
        {
            "tier": "fleet",
            "name": "Fleet",
            "stripe_price_id": fleet_price_id,
            "price_cents": 9700,
        },
    ]

    for plan_data in plans:
        SubscriptionPlan.objects.get_or_create(
            tier=plan_data["tier"],
            defaults={
                "name": plan_data["name"],
                "stripe_price_id": plan_data["stripe_price_id"],
                "price_cents": plan_data["price_cents"],
            },
        )


def unseed_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model("billing", "SubscriptionPlan")
    SubscriptionPlan.objects.filter(tier__in=["free", "solo", "fleet"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_plans, reverse_code=unseed_plans),
    ]
