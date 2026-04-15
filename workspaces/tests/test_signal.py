"""Tests for workspace auto-creation on allauth signup."""
import pytest
from django.contrib.auth import get_user_model

from workspaces.models import Workspace, WorkspaceMembership

User = get_user_model()


@pytest.mark.django_db
class TestSignupAutoCreatesWorkspace:
    def test_signup_creates_workspace_and_owner_membership(self, db):
        from allauth.account.signals import user_signed_up
        user = User.objects.create_user("newuser", "new@example.com", "pass")
        user_signed_up.send(sender=user.__class__, request=None, user=user)
        ws = Workspace.objects.get(owner=user)
        assert ws.name == "new's workspace"
        membership = WorkspaceMembership.objects.get(workspace=ws, user=user)
        assert membership.role == WorkspaceMembership.ROLE_OWNER
        assert membership.accepted_at is not None

    def test_two_signups_create_separate_workspaces(self, db):
        from allauth.account.signals import user_signed_up
        user1 = User.objects.create_user("u1", "u1@example.com", "pass")
        user2 = User.objects.create_user("u2", "u2@example.com", "pass")
        user_signed_up.send(sender=user1.__class__, request=None, user=user1)
        user_signed_up.send(sender=user2.__class__, request=None, user=user2)
        assert Workspace.objects.filter(owner=user1).count() == 1
        assert Workspace.objects.filter(owner=user2).count() == 1
        ws1 = Workspace.objects.get(owner=user1)
        ws2 = Workspace.objects.get(owner=user2)
        assert ws1 != ws2

    def test_signal_is_idempotent(self, db):
        from allauth.account.signals import user_signed_up
        user = User.objects.create_user("idempotent", "idem@example.com", "pass")
        user_signed_up.send(sender=user.__class__, request=None, user=user)
        user_signed_up.send(sender=user.__class__, request=None, user=user)
        assert Workspace.objects.filter(owner=user).count() == 1
