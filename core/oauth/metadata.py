"""Builders for RFC 9728 and RFC 8414 discovery JSON documents.

Both documents are computed from ``settings.OAUTH_ISSUER_URL`` so the
same codebase produces correct URLs in dev (``http://localhost:8000``)
and in prod (``https://cc.nocktechnologies.io``).
"""
from __future__ import annotations

from typing import Any

from django.conf import settings


def _issuer() -> str:
    """Normalize OAUTH_ISSUER_URL to have no trailing slash."""
    return getattr(settings, "OAUTH_ISSUER_URL", "").rstrip("/")


def protected_resource_metadata() -> dict[str, Any]:
    """RFC 9728 — OAuth 2.0 Protected Resource Metadata.

    Tells the client (claude.ai) which authorization servers are
    trusted for this resource and what bearer-token placement is
    supported. Served at ``/.well-known/oauth-protected-resource/mcp``.
    """
    issuer = _issuer()
    return {
        "resource": f"{issuer}/mcp",
        "authorization_servers": [issuer],
        "scopes_supported": ["mcp"],
        "bearer_methods_supported": ["header"],
        "resource_name": "NockCC MCP",
        "resource_documentation": f"{issuer}/mcp/health",
    }


def authorization_server_metadata() -> dict[str, Any]:
    """RFC 8414 — OAuth 2.0 Authorization Server Metadata.

    Tells the client where the authorize/token/registration endpoints
    live and which grant types / PKCE methods are supported. Served at
    ``/.well-known/oauth-authorization-server``.
    """
    issuer = _issuer()
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/oauth/authorize",
        "token_endpoint": f"{issuer}/oauth/token",
        "registration_endpoint": f"{issuer}/oauth/register",
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code"],
        # S256 only — plain PKCE is weaker and OAuth 2.1 deprecates it.
        "code_challenge_methods_supported": ["S256"],
        # Public clients: no client secret, PKCE is the only proof.
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp"],
        "service_documentation": f"{issuer}/mcp/health",
    }
