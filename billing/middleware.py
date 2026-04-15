"""SubscriptionMiddleware — attaches request.subscription for authenticated workspaces.

Must be positioned AFTER WorkspaceMiddleware in MIDDLEWARE so that
request.workspace is already resolved when this middleware runs.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse


class SubscriptionMiddleware:
    """Attach request.subscription to every request.

    - request.workspace is None → request.subscription = None (no DB query).
    - workspace has no Subscription row → request.subscription = None (free tier).
    - workspace has a Subscription → request.subscription = that object.

    Views that enforce tier limits should treat subscription=None as free tier.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.subscription = self._resolve(request)
        return self.get_response(request)

    def _resolve(self, request: HttpRequest) -> object:
        workspace = getattr(request, "workspace", None)
        if workspace is None:
            return None

        from billing.models import Subscription

        return (
            Subscription.objects.filter(workspace=workspace)
            .select_related("plan")
            .first()
        )
