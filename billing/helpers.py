"""Billing tier limit helpers.

Tier limits are hardcoded here — features_json on SubscriptionPlan is for
display purposes only and is never parsed for enforcement.
"""

from __future__ import annotations

_TIER_LIMITS: dict[str, dict] = {
    "free": {"agents": 1, "sessions_per_month": 10},
    "solo": {"agents": 5, "sessions_per_month": None},
    "fleet": {"agents": None, "sessions_per_month": None},
}


def get_tier_limits(tier: str) -> dict:
    """Return limit dict for the given tier.

    Keys:
        agents (int | None): max agents; None = unlimited.
        sessions_per_month (int | None): max sessions/month; None = unlimited.

    Raises:
        ValueError: for unknown tier strings.
    """
    try:
        return _TIER_LIMITS[tier]
    except KeyError:
        raise ValueError(f"Unknown tier: {tier!r}") from None


def get_entitlement_limits(subscription: object | None) -> dict:
    """Return effective limits for a subscription, respecting status.

    Only active subscriptions receive paid-tier limits. Canceled, past_due,
    and missing subscriptions all fall back to free-tier limits. Callers
    should use this rather than calling get_tier_limits() directly.
    """
    if subscription is None:
        return _TIER_LIMITS["free"]

    # Import here to avoid circular imports at module load.
    from billing.models import Subscription

    if subscription.status != Subscription.STATUS_ACTIVE:
        return _TIER_LIMITS["free"]

    tier = getattr(subscription.plan, "tier", "free")
    return _TIER_LIMITS.get(tier, _TIER_LIMITS["free"])
