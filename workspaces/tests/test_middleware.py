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

    def test_superuser_override_via_header(self, workspace_a, workspace_b, user_a):
        # Superusers can target any workspace via X-Workspace-Slug regardless of membership.
        # user_a has membership in workspace_a only; the header selects workspace_b.
        user_a.is_superuser = True
        user_a.save()
        request = self.factory.get("/", HTTP_X_WORKSPACE_SLUG=workspace_b.slug)
        request.user = user_a
        self.middleware(request)
        assert request.workspace == workspace_b

    def test_staff_only_header_override_ignored(self, workspace_a, workspace_b, user_a):
        # Staff (non-superuser) should NOT get the workspace header override.
        user_a.is_staff = True
        user_a.is_superuser = False
        user_a.save()
        request = self.factory.get("/", HTTP_X_WORKSPACE_SLUG=workspace_b.slug)
        request.user = user_a
        self.middleware(request)
        # user_a has no membership in workspace_b, so falls back to workspace_a
        assert request.workspace == workspace_a

    def test_non_staff_header_override_ignored(self, workspace_a, workspace_b, user_a):
        request = self.factory.get("/", HTTP_X_WORKSPACE_SLUG=workspace_b.slug)
        request.user = user_a
        self.middleware(request)
        # Should NOT resolve to workspace_b (user_a has no membership in workspace_b and isn't superuser)
        assert request.workspace != workspace_b
