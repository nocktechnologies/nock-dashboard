"""ASGI entry point for NockCC.

Three routing concerns live here:

1. **Django HTTP** — the existing Daphne-served Django app (everything
   under ``/`` that isn't ``/mcp/``).
2. **MCP Streamable HTTP** — the remote MCP transport at ``/mcp``,
   mounted as a Starlette sub-app so claude.ai custom connectors and any
   other MCP client can reach it. See ``mcp_server/http_app.py``.
3. **WebSockets** — Channels ``AuthMiddlewareStack`` for the remote chat
   feature in ``remote/``.

The MCP session manager needs its ``run()`` context to be active for the
duration of the process. Starlette's ``Mount`` does NOT forward lifespan
events to mounted sub-apps, so the session manager's lifespan is wired
onto the **outer** HTTP router below — not inside ``build_http_app()``.
"""
import contextlib
import os
from collections.abc import AsyncIterator

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Mount, Route

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

# Django ASGI callable — initializes apps, settings, middleware stack.
# Must happen before any import that touches Django models.
django_asgi_app = get_asgi_application()

from mcp_server.http_app import build_http_app  # noqa: E402
from remote.routing import websocket_urlpatterns  # noqa: E402

# Build the MCP sub-app and grab its session manager. The manager's
# lifecycle is driven by the outer ``http_router``'s lifespan below.
_mcp_http_app, _mcp_session_manager = build_http_app()


@contextlib.asynccontextmanager
async def _mcp_lifespan(app: Starlette) -> AsyncIterator[None]:
    """Wrap the MCP session manager's ``run()`` as the HTTP app's lifespan.

    This must run at the outer router level because Starlette's ``Mount``
    silently drops lifespan events for sub-apps.
    """
    async with _mcp_session_manager.run():
        yield


async def _mcp_trailing_slash_redirect(request: Request) -> RedirectResponse:
    """308 from ``/mcp`` → ``/mcp/``.

    claude.ai's custom connector probes the bare ``/mcp`` (no trailing
    slash). Starlette's ``Mount("/mcp", ...)`` compiles its path regex
    as ``/mcp/{path:path}``, which matches ``/mcp/`` and ``/mcp/foo``
    but NOT the bare ``/mcp`` — without this route the probe 404s.

    308 preserves the HTTP method and request body, so a POST /mcp
    redirects cleanly to POST /mcp/ without claude.ai having to repeat
    the handshake logic.
    """
    query = request.url.query
    target = "/mcp/" + (f"?{query}" if query else "")
    return RedirectResponse(url=target, status_code=308)


# Path-based HTTP dispatch: ``/mcp`` → MCP sub-app, everything else → Django.
# Route ordering matters — the explicit Route("/mcp") for the bare path
# has to come BEFORE Mount("/mcp", ...) because Starlette matches routes
# in declaration order and Mount's regex is too greedy to leave /mcp
# uncovered. Starlette's ``Mount`` strips the prefix from
# ``scope["path"]`` before forwarding, so the MCP sub-app sees ``/`` for
# a request to ``/mcp/`` and ``/health`` for ``/mcp/health``.
http_router = Starlette(
    routes=[
        Route(
            "/mcp",
            _mcp_trailing_slash_redirect,
            methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        ),
        Mount("/mcp", app=_mcp_http_app),
        Mount("/", app=django_asgi_app),
    ],
    lifespan=_mcp_lifespan,
)

application = ProtocolTypeRouter(
    {
        "http": http_router,
        # No AllowedHostsOriginValidator — the agent is a non-browser client
        # that authenticates via token in the query string, not via Origin header.
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
        # Channels' ProtocolTypeRouter doesn't implicitly handle lifespan.
        # Route lifespan events to the same Starlette http_router so
        # ``_mcp_lifespan`` actually fires and ``session_manager.run()``
        # starts its anyio task group before the first MCP request lands.
        # Without this, every POST to /mcp/ fails with
        #     Task group is not initialized. Make sure to use run().
        "lifespan": http_router,
    },
)
