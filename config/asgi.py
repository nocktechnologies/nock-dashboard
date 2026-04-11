"""ASGI entry point for Nock Dashboard.

Two routing concerns live here:

1. **Django HTTP** — the Daphne/uvicorn-served Django app serves every
   HTTP path. Under the hood this is Django's standard ``get_asgi_application()``
   wired through Channels' ``ProtocolTypeRouter``.
2. **WebSockets** — Channels ``AuthMiddlewareStack`` for the remote chat
   feature in ``remote/``. Websocket upgrades hit the channels URL router
   instead of the Django HTTP handler.

The product fork does not host an MCP server. The upstream NockCC ASGI
app wrapped Django inside a Starlette outer router to mount an MCP
Streamable HTTP transport at ``/mcp``; that indirection is gone from
this fork because it has no MCP sub-app to mount.
"""
import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

# Django ASGI callable — initializes apps, settings, middleware stack.
# Must happen before any import that touches Django models.
django_asgi_app = get_asgi_application()

from remote.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # No AllowedHostsOriginValidator — the agent is a non-browser client
        # that authenticates via token in the query string, not via Origin header.
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    },
)
