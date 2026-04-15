"""Billing views — Checkout, success/cancel, and Stripe webhook."""

from __future__ import annotations

import logging

import stripe
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from billing import stripe_client
from billing.models import Subscription, SubscriptionPlan
from workspaces.models import Workspace, WorkspaceMembership

logger = logging.getLogger(__name__)

_PAID_TIERS = {"solo", "fleet"}


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------


_BILLING_ROLES = {WorkspaceMembership.ROLE_OWNER, WorkspaceMembership.ROLE_ADMIN}


@login_required
@require_POST
def checkout_create(request: HttpRequest) -> HttpResponse:
    """POST /billing/checkout/ — create a Stripe Checkout Session and redirect."""
    tier = request.POST.get("tier", "").strip()
    if tier not in _PAID_TIERS:
        return HttpResponseBadRequest("Invalid tier.")

    workspace = getattr(request, "workspace", None)
    if workspace is None:
        return HttpResponseBadRequest("No workspace associated with this account.")

    # Only owners and admins may initiate billing for a workspace.
    has_billing_role = WorkspaceMembership.objects.filter(
        workspace=workspace,
        user=request.user,
        role__in=_BILLING_ROLES,
    ).exists()
    if not has_billing_role:
        return HttpResponse(status=403)

    # Block duplicate checkout if an active subscription already exists.
    existing_sub = Subscription.objects.filter(
        workspace=workspace,
        status=Subscription.STATUS_ACTIVE,
    ).first()
    if existing_sub:
        return HttpResponseBadRequest("Workspace already has an active subscription.")

    success_url = request.build_absolute_uri("/billing/success/")
    cancel_url = request.build_absolute_uri("/billing/cancel/")

    try:
        session = stripe_client.create_checkout_session(
            workspace=workspace,
            tier=tier,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    return redirect(session.url)


def checkout_success(request: HttpRequest) -> HttpResponse:
    """GET /billing/success/ — post-checkout success landing page."""
    return render(request, "billing/success.html")


def checkout_cancel(request: HttpRequest) -> HttpResponse:
    """GET /billing/cancel/ — post-checkout cancel landing page."""
    return render(request, "billing/cancel.html")


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------


@csrf_exempt
@require_POST
def stripe_webhook(request: HttpRequest) -> HttpResponse:
    """POST /billing/webhook/ — receive and process Stripe webhook events.

    Uses raw request.body for signature verification — must not be consumed
    by any middleware before reaching this view.
    """
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    if not sig_header:
        return HttpResponse(status=400)

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.SignatureVerificationError:
        logger.warning("Stripe webhook signature verification failed")
        return HttpResponse(status=400)
    except ValueError:
        return HttpResponse(status=400)

    event_type = event.type
    obj = event.data.object

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(obj)
    elif event_type == "invoice.paid":
        _handle_invoice_paid(obj)
    elif event_type == "invoice.payment_failed":
        _handle_invoice_payment_failed(obj)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(obj)
    else:
        logger.debug("Unhandled Stripe event type: %s", event_type)

    return HttpResponse(status=200)


# ---------------------------------------------------------------------------
# Webhook handlers
# ---------------------------------------------------------------------------


_VALID_TIERS = {"solo", "fleet"}


def _handle_checkout_completed(session) -> None:
    """checkout.session.completed — create or update the workspace Subscription."""
    metadata = session.get("metadata") or {}
    workspace_id = metadata.get("workspace_id")
    tier = metadata.get("tier", "")
    stripe_sub_id = session.get("subscription")
    stripe_customer_id = session.get("customer")

    if not workspace_id or not stripe_sub_id:
        logger.warning("checkout.session.completed missing workspace_id or subscription")
        return

    if tier not in _VALID_TIERS:
        logger.warning("checkout.session.completed: invalid tier %r — rejecting event", tier)
        return

    try:
        workspace = Workspace.objects.get(pk=workspace_id)
    except Workspace.DoesNotExist:
        logger.warning("checkout.session.completed: workspace %s not found", workspace_id)
        return

    plan = SubscriptionPlan.objects.filter(tier=tier).first()
    if not plan:
        logger.warning("checkout.session.completed: no plan for tier %r", tier)
        return

    Subscription.objects.update_or_create(
        workspace=workspace,
        defaults={
            "stripe_subscription_id": stripe_sub_id,
            "stripe_customer_id": stripe_customer_id or "",
            "plan": plan,
            "status": Subscription.STATUS_ACTIVE,
        },
    )


def _handle_invoice_paid(invoice) -> None:
    """invoice.paid — mark subscription as active."""
    stripe_sub_id = invoice.get("subscription")
    if not stripe_sub_id:
        return
    Subscription.objects.filter(stripe_subscription_id=stripe_sub_id).update(
        status=Subscription.STATUS_ACTIVE
    )


def _handle_invoice_payment_failed(invoice) -> None:
    """invoice.payment_failed — mark subscription as past_due."""
    stripe_sub_id = invoice.get("subscription")
    if not stripe_sub_id:
        return
    Subscription.objects.filter(stripe_subscription_id=stripe_sub_id).update(
        status=Subscription.STATUS_PAST_DUE
    )


def _handle_subscription_deleted(subscription) -> None:
    """customer.subscription.deleted — mark subscription as canceled."""
    stripe_sub_id = subscription.get("id")
    if not stripe_sub_id:
        return
    Subscription.objects.filter(stripe_subscription_id=stripe_sub_id).update(
        status=Subscription.STATUS_CANCELED
    )
