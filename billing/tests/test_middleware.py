"""Tests for SubscriptionMiddleware."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory

from billing.middleware import SubscriptionMiddleware


def make_response(request):
    return HttpResponse("ok")


@pytest.mark.django_db
class TestSubscriptionMiddleware:
    def setup_method(self):
        self.factory = RequestFactory()
        self.middleware = SubscriptionMiddleware(make_response)

    def test_no_workspace_sets_subscription_to_none(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()
        request.workspace = None
        self.middleware(request)
        assert request.subscription is None

    def test_workspace_with_subscription_attached(self, workspace, subscription_active):
        request = self.factory.get("/")
        request.workspace = workspace
        self.middleware(request)
        assert request.subscription == subscription_active

    def test_workspace_without_subscription_returns_none(self, workspace):
        request = self.factory.get("/")
        request.workspace = workspace
        # No Subscription row created — treat as free
        self.middleware(request)
        assert request.subscription is None

    def test_middleware_does_not_hit_db_when_workspace_is_none(self, django_assert_num_queries):
        request = self.factory.get("/")
        request.workspace = None
        with django_assert_num_queries(0):
            self.middleware(request)
        assert request.subscription is None
