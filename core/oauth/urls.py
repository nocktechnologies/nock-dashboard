"""URL patterns for the OAuth 2.1 shim.

Mounted twice in ``config/urls.py``:

- ``/.well-known/`` prefix for the two discovery endpoints
- ``/oauth/``       prefix for the registration/authorize/token endpoints
"""
from django.urls import path

from core.oauth import views

app_name = "oauth"

# Discovery endpoints — mounted under /.well-known/ in config/urls.py
wellknown_urlpatterns = [
    path(
        "oauth-protected-resource/mcp",
        views.resource_metadata,
        name="resource-metadata",
    ),
    path(
        "oauth-authorization-server",
        views.authorization_server_metadata_view,
        name="authorization-server-metadata",
    ),
]

# OAuth flow endpoints — mounted under /oauth/ in config/urls.py
oauth_urlpatterns = [
    path("register", views.register, name="register"),
    path("authorize", views.authorize, name="authorize"),
    path("token", views.token, name="token"),
]
