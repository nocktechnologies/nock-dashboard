"""Shared fixtures for workspaces tests."""
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from allauth.account.models import EmailAddress

from workspaces.models import Workspace, WorkspaceMembership

User = get_user_model()


def make_verified_user(username, email, password="TestPass123!"):
    user = User.objects.create_user(username=username, email=email, password=password)
    EmailAddress.objects.create(user=user, email=email, primary=True, verified=True)
    return user


@pytest.fixture
def user_a(db):
    return make_verified_user("usera", "usera@example.com")


@pytest.fixture
def user_b(db):
    return make_verified_user("userb", "userb@example.com")


@pytest.fixture
def superuser(db):
    u = User.objects.create_superuser("admin", "admin@example.com", "AdminPass123!")
    EmailAddress.objects.create(user=u, email=u.email, primary=True, verified=True)
    return u


@pytest.fixture
def workspace_a(db, user_a):
    ws = Workspace.objects.create(name="Workspace A", owner=user_a)
    WorkspaceMembership.objects.create(
        workspace=ws, user=user_a, role=WorkspaceMembership.ROLE_OWNER, accepted_at=timezone.now()
    )
    return ws


@pytest.fixture
def workspace_b(db, user_b):
    ws = Workspace.objects.create(name="Workspace B", owner=user_b)
    WorkspaceMembership.objects.create(
        workspace=ws, user=user_b, role=WorkspaceMembership.ROLE_OWNER, accepted_at=timezone.now()
    )
    return ws
