"""Minimal OAuth 2.1 shim for the NockCC MCP Streamable HTTP transport.

claude.ai custom connectors refuse to talk to an MCP server that only
accepts a static bearer token — they expect OAuth 2.1 per the MCP spec
2025-03-26 (RFC 9728 resource metadata + RFC 8414 auth server metadata
+ RFC 7591 dynamic client registration + RFC 7636 PKCE).

This package is the minimum viable OAuth layer that lets claude.ai
complete its handshake against a **single-user** NockCC instance:

1. Serves the two discovery endpoints.
2. Implements dynamic client registration (auto-accept, no secrets).
3. Implements the authorize endpoint as an **auto-approve** redirect —
   no consent screen, because this NockCC instance has exactly one user.
4. Implements the token endpoint; the issued access token is literally
   ``settings.NOCKCC_API_KEY`` so the existing ``BearerAuthMiddleware``
   on ``/mcp/`` keeps working unchanged.

This is deliberately NOT a real multi-tenant OAuth server. Any client
that completes the flow gets the master API key, so the whole thing is
gated on ``NOCKCC_OAUTH_ENABLED=1`` and rate-limited to make abuse
expensive.
"""
