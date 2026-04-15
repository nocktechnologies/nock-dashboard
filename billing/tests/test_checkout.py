"""Tests for Stripe Checkout flow (create, success, cancel)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from workspaces.models import WorkspaceMembership

User = get_user_model()

CHECKOUT_URL = "/billing/checkout/"
SUCCESS_URL = "/billing/success/"
CANCEL_URL = "/billing/cancel/"


def _login(client, user):
    client.force_login(user)


@pytest.mark.django_db
class TestCheckoutCreate:
    def setup_method(self):
        self.client = Client()

    @patch("billing.views.stripe_client.create_checkout_session")
    def test_checkout_redirects_to_stripe(self, mock_create, user, workspace):
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/pay/cs_test"
        mock_create.return_value = mock_session

        _login(self.client, user)
        # WorkspaceMiddleware needs accepted membership — fixture provides it
        resp = self.client.post(CHECKOUT_URL, {"tier": "solo"})

        assert resp.status_code == 302
        assert resp["Location"] == "https://checkout.stripe.com/pay/cs_test"
        mock_create.assert_called_once()

    def test_anonymous_user_redirected_to_login(self):
        resp = self.client.post(CHECKOUT_URL, {"tier": "solo"})
        assert resp.status_code == 302
        assert "/accounts/" in resp["Location"]

    @patch("billing.views.stripe_client.create_checkout_session")
    def test_invalid_tier_returns_400(self, mock_create, user, workspace):
        _login(self.client, user)
        resp = self.client.post(CHECKOUT_URL, {"tier": "premium"})
        assert resp.status_code == 400
        mock_create.assert_not_called()

    @patch("billing.views.stripe_client.create_checkout_session")
    def test_free_tier_checkout_returns_400(self, mock_create, user, workspace):
        """Free tier has no Stripe price — checkout is disallowed."""
        _login(self.client, user)
        resp = self.client.post(CHECKOUT_URL, {"tier": "free"})
        assert resp.status_code == 400
        mock_create.assert_not_called()

    def test_get_request_returns_405(self, user, workspace):
        _login(self.client, user)
        resp = self.client.get(CHECKOUT_URL)
        assert resp.status_code == 405

    @patch("billing.views.stripe_client.create_checkout_session")
    def test_member_role_cannot_initiate_checkout(self, mock_create, db, workspace):
        """Workspace members (non-owner/admin) must receive 403."""
        member = User.objects.create_user(
            username="memberuser", email="member@example.com", password="TestPass123!"
        )
        WorkspaceMembership.objects.create(
            workspace=workspace,
            user=member,
            role=WorkspaceMembership.ROLE_MEMBER,
            accepted_at=timezone.now(),
        )
        _login(self.client, member)
        resp = self.client.post(CHECKOUT_URL, {"tier": "solo"})
        assert resp.status_code == 403
        mock_create.assert_not_called()

    @patch("billing.views.stripe_client.create_checkout_session")
    def test_duplicate_active_subscription_blocked(self, mock_create, user, workspace, subscription_active):
        """Checkout must return 400 if workspace already has an active subscription."""
        _login(self.client, user)
        resp = self.client.post(CHECKOUT_URL, {"tier": "solo"})
        assert resp.status_code == 400
        mock_create.assert_not_called()


@pytest.mark.django_db
class TestCheckoutSuccessCancel:
    def setup_method(self):
        self.client = Client()

    def test_success_page_renders(self, user, workspace):
        _login(self.client, user)
        resp = self.client.get(SUCCESS_URL)
        assert resp.status_code == 200

    def test_cancel_page_renders(self, user, workspace):
        _login(self.client, user)
        resp = self.client.get(CANCEL_URL)
        assert resp.status_code == 200

    def test_anonymous_success_redirects_to_login(self):
        resp = self.client.get(SUCCESS_URL)
        assert resp.status_code == 302
        assert "/accounts/" in resp["Location"]

    def test_anonymous_cancel_redirects_to_login(self):
        resp = self.client.get(CANCEL_URL)
        assert resp.status_code == 302
        assert "/accounts/" in resp["Location"]
