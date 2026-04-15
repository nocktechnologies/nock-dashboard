"""Tests for Stripe webhook handler."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client


def _make_event(event_type: str, obj_data: dict) -> MagicMock:
    """Build a mock stripe Event with the given type and data object."""
    event = MagicMock()
    event.__getitem__ = lambda self, k: {
        "type": event_type,
        "data": {"object": obj_data},
    }[k]
    event.get = lambda k, default=None: {
        "type": event_type,
        "data": {"object": obj_data},
    }.get(k, default)
    event.type = event_type
    event.data = MagicMock()
    event.data.object = obj_data
    return event


WEBHOOK_URL = "/billing/webhook/"


@pytest.mark.django_db
class TestStripeWebhook:
    def setup_method(self):
        self.client = Client()

    def _post(self, payload: dict, sig: str = "valid_sig") -> object:
        return self.client.post(
            WEBHOOK_URL,
            data=json.dumps(payload).encode(),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=sig,
        )

    @patch("billing.views.stripe.Webhook.construct_event")
    def test_invalid_signature_returns_400(self, mock_construct):
        import stripe as stripe_lib

        mock_construct.side_effect = stripe_lib.SignatureVerificationError(
            "bad sig", "sig_header"
        )
        resp = self._post({"type": "checkout.session.completed"})
        assert resp.status_code == 400

    def test_missing_signature_header_returns_400(self):
        resp = self.client.post(
            WEBHOOK_URL,
            data=b"{}",
            content_type="application/json",
            # no HTTP_STRIPE_SIGNATURE header
        )
        assert resp.status_code == 400

    @patch("billing.views.stripe.Webhook.construct_event")
    def test_checkout_session_completed_creates_subscription(
        self, mock_construct, workspace, plan_solo, db
    ):
        session_obj = {
            "id": "cs_test",
            "subscription": "sub_new123",
            "customer": "cus_new123",
            "metadata": {"workspace_id": str(workspace.id), "tier": "solo"},
        }
        mock_construct.return_value = _make_event("checkout.session.completed", session_obj)

        resp = self._post({"type": "checkout.session.completed"})
        assert resp.status_code == 200

        from billing.models import Subscription

        sub = Subscription.objects.get(workspace=workspace)
        assert sub.stripe_subscription_id == "sub_new123"
        assert sub.stripe_customer_id == "cus_new123"
        assert sub.status == Subscription.STATUS_ACTIVE
        assert sub.plan == plan_solo

    @patch("billing.views.stripe.Webhook.construct_event")
    def test_invoice_paid_sets_status_active(self, mock_construct, subscription_active):
        subscription_active.status = "past_due"
        subscription_active.save()

        invoice_obj = {"subscription": subscription_active.stripe_subscription_id}
        mock_construct.return_value = _make_event("invoice.paid", invoice_obj)

        resp = self._post({"type": "invoice.paid"})
        assert resp.status_code == 200

        subscription_active.refresh_from_db()
        assert subscription_active.status == "active"

    @patch("billing.views.stripe.Webhook.construct_event")
    def test_invoice_payment_failed_sets_past_due(self, mock_construct, subscription_active):
        invoice_obj = {"subscription": subscription_active.stripe_subscription_id}
        mock_construct.return_value = _make_event("invoice.payment_failed", invoice_obj)

        resp = self._post({"type": "invoice.payment_failed"})
        assert resp.status_code == 200

        subscription_active.refresh_from_db()
        assert subscription_active.status == "past_due"

    @patch("billing.views.stripe.Webhook.construct_event")
    def test_subscription_deleted_sets_canceled(self, mock_construct, subscription_active):
        sub_obj = {"id": subscription_active.stripe_subscription_id}
        mock_construct.return_value = _make_event("customer.subscription.deleted", sub_obj)

        resp = self._post({"type": "customer.subscription.deleted"})
        assert resp.status_code == 200

        subscription_active.refresh_from_db()
        assert subscription_active.status == "canceled"

    @patch("billing.views.stripe.Webhook.construct_event")
    def test_unknown_event_type_returns_200_noop(self, mock_construct, db):
        mock_construct.return_value = _make_event("some.unknown.event", {})
        resp = self._post({"type": "some.unknown.event"})
        assert resp.status_code == 200

    @patch("billing.views.stripe.Webhook.construct_event")
    def test_checkout_completed_missing_tier_creates_no_subscription(
        self, mock_construct, workspace, plan_solo, db
    ):
        """checkout.session.completed with missing/invalid tier must not create a subscription."""
        session_obj = {
            "id": "cs_test_bad",
            "subscription": "sub_bad123",
            "customer": "cus_bad123",
            "metadata": {"workspace_id": str(workspace.id), "tier": ""},
        }
        mock_construct.return_value = _make_event("checkout.session.completed", session_obj)

        resp = self._post({"type": "checkout.session.completed"})
        assert resp.status_code == 200

        from billing.models import Subscription

        assert not Subscription.objects.filter(workspace=workspace).exists()

    @patch("billing.views.stripe.Webhook.construct_event")
    def test_checkout_completed_idempotent_on_replay(
        self, mock_construct, workspace, plan_solo, subscription_active
    ):
        """Same checkout event delivered twice must not error or duplicate."""
        session_obj = {
            "id": "cs_test",
            "subscription": subscription_active.stripe_subscription_id,
            "customer": subscription_active.stripe_customer_id,
            "metadata": {"workspace_id": str(workspace.id), "tier": "solo"},
        }
        mock_construct.return_value = _make_event("checkout.session.completed", session_obj)

        resp1 = self._post({"type": "checkout.session.completed"})
        resp2 = self._post({"type": "checkout.session.completed"})
        assert resp1.status_code == 200
        assert resp2.status_code == 200

        from billing.models import Subscription

        assert Subscription.objects.filter(workspace=workspace).count() == 1
