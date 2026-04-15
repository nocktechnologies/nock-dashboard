"""Tests for billing models — SubscriptionPlan and Subscription."""

from __future__ import annotations

import pytest
from django.db import IntegrityError

from billing.models import Subscription, SubscriptionPlan


@pytest.mark.django_db
class TestSubscriptionPlan:
    def test_free_plan_seeded(self):
        # The seed migration creates the Free plan; verify it has the expected properties.
        plan = SubscriptionPlan.objects.get(tier=SubscriptionPlan.TIER_FREE)
        assert plan.tier == "free"
        assert plan.price_cents == 0
        assert plan.stripe_price_id == ""

    def test_solo_plan_seeded(self):
        plan = SubscriptionPlan.objects.get(tier=SubscriptionPlan.TIER_SOLO)
        assert plan.tier == "solo"
        assert plan.price_cents == 4900

    def test_fleet_plan_seeded(self):
        plan = SubscriptionPlan.objects.get(tier=SubscriptionPlan.TIER_FLEET)
        assert plan.tier == "fleet"
        assert plan.price_cents == 9700

    def test_tier_uniqueness_constraint(self, plan_solo):
        with pytest.raises(IntegrityError):
            SubscriptionPlan.objects.create(
                name="Solo Duplicate",
                tier=SubscriptionPlan.TIER_SOLO,
                stripe_price_id="price_other",
                price_cents=4900,
            )

    def test_str_representation(self, plan_solo):
        assert str(plan_solo) == "Solo (solo)"


@pytest.mark.django_db
class TestSubscription:
    def test_create_subscription(self, workspace, plan_solo):
        sub = Subscription.objects.create(
            workspace=workspace,
            plan=plan_solo,
            stripe_customer_id="cus_abc",
            stripe_subscription_id="sub_abc",
            status=Subscription.STATUS_ACTIVE,
        )
        assert sub.status == "active"
        assert sub.workspace == workspace

    def test_default_status_is_active(self, workspace, plan_solo):
        sub = Subscription.objects.create(workspace=workspace, plan=plan_solo)
        assert sub.status == Subscription.STATUS_ACTIVE

    def test_one_to_one_per_workspace(self, workspace, plan_solo):
        Subscription.objects.create(workspace=workspace, plan=plan_solo, stripe_subscription_id="sub_1")
        with pytest.raises(IntegrityError):
            Subscription.objects.create(workspace=workspace, plan=plan_solo, stripe_subscription_id="sub_2")

    def test_status_transition_to_past_due(self, subscription_active):
        subscription_active.status = Subscription.STATUS_PAST_DUE
        subscription_active.save()
        subscription_active.refresh_from_db()
        assert subscription_active.status == "past_due"

    def test_status_transition_to_canceled(self, subscription_active):
        subscription_active.status = Subscription.STATUS_CANCELED
        subscription_active.save()
        subscription_active.refresh_from_db()
        assert subscription_active.status == "canceled"

    def test_plan_delete_protected(self, subscription_active, plan_solo):
        from django.db.models import ProtectedError

        with pytest.raises(ProtectedError):
            plan_solo.delete()

    def test_reverse_relation_from_workspace(self, subscription_active, workspace):
        assert workspace.subscription == subscription_active

    def test_str_representation(self, subscription_active, workspace):
        assert str(workspace.subscription).startswith("Billing Workspace")
