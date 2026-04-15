"""Shared fixtures for billing tests."""

from __future__ import annotations

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.utils import timezone

from workspaces.models import Workspace, WorkspaceMembership

User = get_user_model()


def make_verified_user(username: str, email: str, password: str = "TestPass123!"):
    user = User.objects.create_user(username=username, email=email, password=password)
    EmailAddress.objects.create(user=user, email=email, primary=True, verified=True)
    return user


@pytest.fixture
def user(db):
    return make_verified_user("billinguser", "billing@example.com")


@pytest.fixture
def workspace(db, user):
    ws = Workspace.objects.create(name="Billing Workspace", owner=user)
    WorkspaceMembership.objects.create(
        workspace=ws,
        user=user,
        role=WorkspaceMembership.ROLE_OWNER,
        accepted_at=timezone.now(),
    )
    return ws


@pytest.fixture
def plan_free(db):
    from billing.models import SubscriptionPlan

    plan, _ = SubscriptionPlan.objects.get_or_create(
        tier=SubscriptionPlan.TIER_FREE,
        defaults={"name": "Free", "stripe_price_id": "", "price_cents": 0},
    )
    return plan


@pytest.fixture
def plan_solo(db):
    from billing.models import SubscriptionPlan

    plan, _ = SubscriptionPlan.objects.get_or_create(
        tier=SubscriptionPlan.TIER_SOLO,
        defaults={
            "name": "Solo",
            "stripe_price_id": "price_solo_test",
            "price_cents": 4900,
        },
    )
    return plan


@pytest.fixture
def plan_fleet(db):
    from billing.models import SubscriptionPlan

    plan, _ = SubscriptionPlan.objects.get_or_create(
        tier=SubscriptionPlan.TIER_FLEET,
        defaults={
            "name": "Fleet",
            "stripe_price_id": "price_fleet_test",
            "price_cents": 9700,
        },
    )
    return plan


@pytest.fixture
def subscription_active(db, workspace, plan_solo):
    from datetime import timedelta

    from django.utils import timezone

    from billing.models import Subscription

    return Subscription.objects.create(
        workspace=workspace,
        plan=plan_solo,
        stripe_customer_id="cus_test123",
        stripe_subscription_id="sub_test123",
        status=Subscription.STATUS_ACTIVE,
        current_period_end=timezone.now() + timedelta(days=30),
    )
