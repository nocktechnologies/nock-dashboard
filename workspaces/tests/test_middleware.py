"""Tests for WorkspaceMiddleware."""
import pytest
from django.test import RequestFactory

from workspaces.middleware import WorkspaceMiddleware
from workspaces.models import Workspace, WorkspaceMembership


def make_response(request):
    from django.http import HttpResponse
    return HttpResponse("ok")


@pytest.mark.django_db
class TestWorkspaceMiddleware:
    def setup_method(self):
        self.factory = RequestFactory()
        self.middleware = WorkspaceMiddleware(make_response)

    def test_anonymous_request_gets_none_workspace(self):
        request = self.factory.get("/")
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()
        self.middleware(request)
        assert request.workspace is None

    def test_authenticated_user_with_membership_gets_workspace(self, workspace_a, user_a):
        request = self.factory.get("/")
        request.user = user_a
        self.middleware(request)
        assert request.workspace == workspace_a

    def test_authenticated_user_without_membership_gets_none(self, db, user_a):
        # Remove any existing memberships
        WorkspaceMembership.objects.filter(user=user_a).delete()
        request = self.factory.get("/")
        request.user = user_a
        self.middleware(request)
        assert request.workspace is None

    def test_staff_override_via_header(self, db, workspace_b, user_a):
        from django.utils import timezone
        user_a.is_staff = True
        user_a.save()
        # Give user_a membership in workspace_a too (they need one to log in, but override goes to workspace_b)
        WorkspaceMembership.objects.create(
            workspace=workspace_b, user=user_a,
            role=WorkspaceMembership.ROLE_MEMBER, accepted_at=timezone.now()
        )
        request = self.factory.get("/", HTTP_X_WORKSPACE_SLUG=workspace_b.slug)
        request.user = user_a
        self.middleware(request)
        assert request.workspace == workspace_b

    def test_non_staff_header_override_ignored(self, workspace_a, workspace_b, user_a):
        request = self.factory.get("/", HTTP_X_WORKSPACE_SLUG=workspace_b.slug)
        request.user = user_a
        self.middleware(request)
        # Should NOT resolve to workspace_b (user_a has no membership in workspace_b and isn't staff)
        assert request.workspace != workspace_b
