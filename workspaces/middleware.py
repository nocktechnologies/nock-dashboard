"""WorkspaceMiddleware — resolves request.workspace for authenticated users."""

from __future__ import annotations

from typing import Callable

from django.http import HttpRequest, HttpResponse

from workspaces.models import WorkspaceMembership


class WorkspaceMiddleware:
    """Attach request.workspace from the authenticated user's active membership.

    - Unauthenticated requests: request.workspace = None.
    - Authenticated users with accepted membership: request.workspace = that workspace.
    - Authenticated users with no accepted membership: request.workspace = None.
    - Superusers may pass X-Workspace-Slug header to override (for tooling/scripts).
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.workspace = self._resolve(request)
        return self.get_response(request)

    def _resolve(self, request: HttpRequest) -> object:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None

        # Superuser override via X-Workspace-Slug header (for scripts/tooling only).
        if user.is_superuser:
            slug = request.headers.get("X-Workspace-Slug")
            if slug:
                try:
                    from workspaces.models import Workspace
                    return Workspace.objects.get(slug=slug)
                except Workspace.DoesNotExist:
                    pass

        membership = (
            WorkspaceMembership.objects.filter(
                user=user,
                accepted_at__isnull=False,
            )
            .select_related("workspace")
            .first()
        )
        if membership is None:
            return None
        return membership.workspace
