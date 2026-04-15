"""Tests for billing tier limit helpers."""

from __future__ import annotations

import pytest

from billing.helpers import get_entitlement_limits, get_tier_limits


class TestGetTierLimits:
    def test_free_tier_limits(self):
        limits = get_tier_limits("free")
        assert limits["agents"] == 1
        assert limits["sessions_per_month"] == 10

    def test_solo_tier_limits(self):
        limits = get_tier_limits("solo")
        assert limits["agents"] == 5
        assert limits["sessions_per_month"] is None  # unlimited

    def test_fleet_tier_limits(self):
        limits = get_tier_limits("fleet")
        assert limits["agents"] is None  # unlimited
        assert limits["sessions_per_month"] is None  # unlimited

    def test_unknown_tier_raises_value_error(self):
        with pytest.raises(ValueError, match="unknown"):
            get_tier_limits("unknown")


@pytest.mark.django_db
class TestGetEntitlementLimits:
    def test_none_subscription_returns_free_limits(self):
        limits = get_entitlement_limits(None)
        assert limits["agents"] == 1
        assert limits["sessions_per_month"] == 10

    def test_active_solo_subscription_returns_solo_limits(self, subscription_active):
        limits = get_entitlement_limits(subscription_active)
        assert limits["agents"] == 5
        assert limits["sessions_per_month"] is None

    def test_canceled_subscription_returns_free_limits(self, subscription_active):
        from billing.models import Subscription

        subscription_active.status = Subscription.STATUS_CANCELED
        subscription_active.save()
        limits = get_entitlement_limits(subscription_active)
        assert limits["agents"] == 1
        assert limits["sessions_per_month"] == 10

    def test_past_due_subscription_returns_free_limits(self, subscription_active):
        from billing.models import Subscription

        subscription_active.status = Subscription.STATUS_PAST_DUE
        subscription_active.save()
        limits = get_entitlement_limits(subscription_active)
        assert limits["agents"] == 1
        assert limits["sessions_per_month"] == 10
