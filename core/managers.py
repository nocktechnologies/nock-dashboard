"""TenantManager — workspace-scoped querysets.

Usage in models:
    objects = models.Manager()          # default: unscoped (Celery, webhooks, admin)
    tenant_objects = TenantManager()    # opt-in: scoped to request.workspace

In views:
    qs = MyModel.tenant_objects.for_request(request)
    qs = MyModel.tenant_objects.for_workspace(workspace)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from django.http import HttpRequest

    from workspaces.models import Workspace


class TenantManager(models.Manager):
    """Manager that filters by workspace. Superusers bypass all filtering."""

    def for_workspace(self, workspace: "Workspace") -> models.QuerySet:
        """Return queryset filtered to a specific workspace."""
        return self.get_queryset().filter(workspace=workspace)

    def for_request(self, request: "HttpRequest") -> models.QuerySet:
        """Return queryset for the workspace attached to request.

        Returns empty queryset if request.workspace is None (anon or
        unresolved workspace). Superusers get all rows.
        """
        workspace = getattr(request, "workspace", None)
        if workspace is None:
            return self.get_queryset().none()
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.is_superuser:
            return self.get_queryset().all()
        return self.for_workspace(workspace)

    def for_user(self, user: object) -> models.QuerySet:
        """Return queryset for all workspaces the user is a member of."""
        from workspaces.models import WorkspaceMembership

        workspace_ids = WorkspaceMembership.objects.filter(
            user=user,
            accepted_at__isnull=False,
        ).values_list("workspace_id", flat=True)
        return self.get_queryset().filter(workspace_id__in=workspace_ids)
