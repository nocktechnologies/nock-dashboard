"""Workspace provisioning signals.

Hooks into allauth's user_signed_up signal to auto-create a Workspace
and owner Membership for every new user.
"""

from django.db import transaction
from django.utils import timezone


def _on_user_signed_up(sender, request, user, **kwargs) -> None:
    """Create a Workspace + owner Membership when a new user registers."""
    from workspaces.models import Workspace, WorkspaceMembership

    with transaction.atomic():
        # Idempotent: if they already own a workspace (e.g., created manually),
        # skip auto-creation to avoid duplicates.
        if Workspace.objects.filter(owner=user).exists():
            return

        name = f"{user.email.split('@')[0]}'s workspace"
        ws = Workspace(name=name, owner=user)
        ws.save()  # slug auto-generated in Workspace.save()

        WorkspaceMembership.objects.get_or_create(
            workspace=ws,
            user=user,
            defaults={"role": WorkspaceMembership.ROLE_OWNER, "accepted_at": timezone.now()},
        )


def _connect_signals() -> None:
    from allauth.account.signals import user_signed_up

    user_signed_up.connect(_on_user_signed_up, dispatch_uid="workspaces.auto_create")


_connect_signals()
