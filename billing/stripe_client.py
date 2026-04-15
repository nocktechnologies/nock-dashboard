"""Thin wrapper around Stripe SDK calls.

All Stripe API calls go through this module so tests can mock at a single
boundary rather than patching deep into the stripe package.
"""

from __future__ import annotations

import stripe
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

_PAID_TIERS = {"solo", "fleet"}


def _price_id_for_tier(tier: str) -> str:
    # Price IDs are read from settings (env vars) rather than SubscriptionPlan.stripe_price_id.
    # SubscriptionPlan.stripe_price_id is the canonical DB record (used for display/webhooks);
    # settings are the live operational value at checkout time. Keep them in sync via the
    # seed migration (0002_seed_plans.py) and STRIPE_*_PRICE_ID env vars.
    mapping = {
        "solo": getattr(settings, "STRIPE_SOLO_PRICE_ID", ""),
        "fleet": getattr(settings, "STRIPE_FLEET_PRICE_ID", ""),
    }
    price_id = mapping.get(tier, "")
    if not price_id:
        raise ValueError(f"No Stripe price_id configured for tier: {tier!r}")
    return price_id


def create_checkout_session(
    workspace,
    tier: str,
    success_url: str,
    cancel_url: str,
) -> stripe.checkout.Session:
    """Create a Stripe Checkout Session for the given workspace and tier.

    Raises:
        ValueError: if tier is free or has no configured price_id.
        stripe.StripeError: on Stripe API errors.
    """
    if tier not in _PAID_TIERS:
        raise ValueError(f"Cannot create checkout session for tier: {tier!r}")

    stripe.api_key = settings.STRIPE_SECRET_KEY
    price_id = _price_id_for_tier(tier)

    params: dict = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {
            "workspace_id": str(workspace.pk),
            "tier": tier,
        },
    }

    # Reuse existing Stripe customer if we already have one.
    # ObjectDoesNotExist covers workspace.subscription when no Subscription row exists.
    try:
        existing_sub = workspace.subscription
        if existing_sub.stripe_customer_id:
            params["customer"] = existing_sub.stripe_customer_id
    except ObjectDoesNotExist:
        pass

    return stripe.checkout.Session.create(**params)
