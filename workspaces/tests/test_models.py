"""Tests for Workspace and WorkspaceMembership models."""
import pytest
from django.db import IntegrityError

from workspaces.models import Workspace, WorkspaceMembership


@pytest.mark.django_db
class TestWorkspaceModel:
    def test_slug_auto_generated_on_create(self, user_a):
        ws = Workspace.objects.create(name="My Company", owner=user_a)
        assert ws.slug == "my-company"

    def test_slug_unique_collision_resolved(self, user_a, user_b):
        ws1 = Workspace.objects.create(name="Acme", owner=user_a)
        ws2 = Workspace.objects.create(name="Acme", owner=user_b)
        assert ws1.slug == "acme"
        assert ws2.slug == "acme-1"

    def test_str_returns_name(self, user_a):
        ws = Workspace.objects.create(name="Test Corp", owner=user_a)
        assert str(ws) == "Test Corp"


@pytest.mark.django_db
class TestWorkspaceMembershipModel:
    def test_unique_constraint_prevents_duplicate(self, workspace_a, user_a):
        from django.utils import timezone
        with pytest.raises(IntegrityError):
            WorkspaceMembership.objects.create(
                workspace=workspace_a,
                user=user_a,
                role=WorkspaceMembership.ROLE_MEMBER,
                accepted_at=timezone.now(),
            )

    def test_str_representation(self, workspace_a, user_a):
        m = WorkspaceMembership.objects.get(workspace=workspace_a, user=user_a)
        assert "usera" in str(m) or "Workspace A" in str(m)
