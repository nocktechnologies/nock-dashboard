"""OAuth 2.1 views for the claude.ai custom-connector handshake.

Five endpoints total:

- ``GET /.well-known/oauth-protected-resource/mcp`` — RFC 9728
- ``GET /.well-known/oauth-authorization-server``   — RFC 8414
- ``POST /oauth/register``                          — RFC 7591 dynamic registration
- ``GET /oauth/authorize``                          — RFC 6749 + RFC 7636 (auto-approved)
- ``POST /oauth/token``                             — RFC 6749 token endpoint

The whole package is gated on ``settings.NOCKCC_OAUTH_ENABLED``. When
that flag is false, every endpoint returns 404 — the shim is dormant
and doesn't advertise OAuth support at all. Flip the flag in
``.env`` to enable.

Security model: this is a **single-user** instance. The authorize
endpoint auto-approves because there is exactly one person to ask.
The issued access token is literally ``settings.NOCKCC_API_KEY``, so
any client that completes the OAuth flow gets the master key.
Rate limiting and the explicit enable flag exist specifically because
of this — do not copy this pattern into a multi-tenant service.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from core.oauth.metadata import (
    authorization_server_metadata,
    protected_resource_metadata,
)
from core.oauth.storage import (
    StorageUnavailable,
    get_client,
    pop_code,
    put_client,
    put_code,
)

_ACCESS_TOKEN_TTL_SECONDS = 60 * 60  # 1 hour — claude.ai re-fetches as needed
_SCOPE = "mcp"
_SUPPORTED_SCOPES: frozenset[str] = frozenset({_SCOPE})
_SUPPORTED_GRANT_TYPES: frozenset[str] = frozenset({"authorization_code"})
_SUPPORTED_RESPONSE_TYPES: frozenset[str] = frozenset({"code"})


def _oauth_enabled() -> bool:
    return bool(getattr(settings, "NOCKCC_OAUTH_ENABLED", False))


def _disabled_response() -> JsonResponse:
    """Return a flat 404 when the OAuth shim is turned off."""
    return JsonResponse({"error": "not_found"}, status=404)


def _oauth_error(
    error: str,
    description: str,
    status: int = 400,
) -> JsonResponse:
    """RFC 6749 §5.2-style error body."""
    return JsonResponse(
        {"error": error, "error_description": description},
        status=status,
    )


def _json_body(request: HttpRequest) -> dict[str, Any] | None:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------------------
# RFC 9728 + RFC 8414 — discovery metadata
# ---------------------------------------------------------------------------


@require_GET
def resource_metadata(request: HttpRequest) -> JsonResponse:
    """Protected Resource Metadata (``/.well-known/oauth-protected-resource/mcp``)."""
    if not _oauth_enabled():
        return _disabled_response()
    return JsonResponse(protected_resource_metadata())


@require_GET
def authorization_server_metadata_view(request: HttpRequest) -> JsonResponse:
    """Authorization Server Metadata (``/.well-known/oauth-authorization-server``)."""
    if not _oauth_enabled():
        return _disabled_response()
    return JsonResponse(authorization_server_metadata())


# ---------------------------------------------------------------------------
# RFC 7591 — dynamic client registration
# ---------------------------------------------------------------------------


@csrf_exempt
@require_POST
@ratelimit(key="ip", rate="20/m", method="POST", block=True)
def register(request: HttpRequest) -> JsonResponse:
    """Accept any well-formed registration and return a fresh client_id.

    We don't persist real credentials — every "client" is a public
    PKCE client with no secret — but we do store the redirect_uris
    so the authorize and token endpoints can verify them later.
    """
    if not _oauth_enabled():
        return _disabled_response()

    body = _json_body(request)
    if body is None or not isinstance(body, dict):
        return _oauth_error("invalid_request", "Request body must be JSON")

    redirect_uris = body.get("redirect_uris")
    if not isinstance(redirect_uris, list) or not redirect_uris:
        return _oauth_error(
            "invalid_redirect_uri",
            "redirect_uris must be a non-empty array",
        )
    for uri in redirect_uris:
        if not isinstance(uri, str) or not uri.startswith(("http://", "https://")):
            return _oauth_error(
                "invalid_redirect_uri",
                f"Invalid redirect_uri: {uri!r}",
            )

    # RFC 7591 §2: ``grant_types`` and ``response_types`` declare what
    # the client WANTS to use. Real OAuth clients (claude.ai, Okta-
    # generated libs, etc.) always include ``refresh_token`` in
    # ``grant_types`` even when the server doesn't offer refresh
    # tokens. Rejecting the whole registration would break every
    # compliant client.
    #
    # The right pattern — matching Okta / Auth0 / Keycloak — is to
    # intersect the requested values with what the server actually
    # supports, store the filtered list, and return it back in the
    # registration response (per RFC 7591 §3.2.1). The client learns
    # from the response which grants the server will honor, and no
    # lie is stored server-side. If the intersection is empty the
    # client has no usable grants and we still fail with
    # ``invalid_client_metadata``.
    requested_grants = body.get("grant_types") or ["authorization_code"]
    if not isinstance(requested_grants, list) or any(
        not isinstance(g, str) for g in requested_grants
    ):
        return _oauth_error(
            "invalid_client_metadata",
            "grant_types must be an array of strings",
        )
    accepted_grants = [g for g in requested_grants if g in _SUPPORTED_GRANT_TYPES]
    if not accepted_grants:
        return _oauth_error(
            "invalid_client_metadata",
            "None of the requested grant_types are supported. "
            "Only 'authorization_code' is available.",
        )

    requested_response_types = body.get("response_types") or ["code"]
    if not isinstance(requested_response_types, list) or any(
        not isinstance(r, str) for r in requested_response_types
    ):
        return _oauth_error(
            "invalid_client_metadata",
            "response_types must be an array of strings",
        )
    accepted_response_types = [
        r for r in requested_response_types if r in _SUPPORTED_RESPONSE_TYPES
    ]
    if not accepted_response_types:
        return _oauth_error(
            "invalid_client_metadata",
            "None of the requested response_types are supported. "
            "Only 'code' is available.",
        )

    client_id = f"nockcc-{secrets.token_urlsafe(16)}"
    now = int(time.time())
    record = {
        "client_id": client_id,
        "client_name": body.get("client_name") or "nockcc-mcp-client",
        "redirect_uris": redirect_uris,
        # Return the SERVER-ACCEPTED subset per RFC 7591 §3.2.1 —
        # claude.ai learns from this response which grants are
        # actually usable, so no lie is stored or echoed.
        "grant_types": accepted_grants,
        "response_types": accepted_response_types,
        "token_endpoint_auth_method": "none",
        "client_id_issued_at": now,
    }
    try:
        put_client(client_id, record)
    except StorageUnavailable:
        return _oauth_error(
            "server_error",
            "OAuth storage temporarily unavailable — try again shortly",
            status=503,
        )
    # RFC 7591 §3.2.1 — return the registered metadata alongside the ID.
    return JsonResponse(record, status=201)


# ---------------------------------------------------------------------------
# RFC 6749 + RFC 7636 — authorization endpoint (auto-approved)
# ---------------------------------------------------------------------------


@require_GET
@ratelimit(key="ip", rate="20/m", method="GET", block=True)
def authorize(request: HttpRequest) -> HttpResponse:
    """Auto-approve the authorization request and redirect with a code.

    Because this NockCC instance is single-user, there's no consent
    screen to show. We validate the request (PKCE S256 required,
    client_id must be registered, redirect_uri must match), mint a
    short-lived code, and 302 back to the client immediately.
    """
    if not _oauth_enabled():
        return _disabled_response()

    params = request.GET
    response_type = params.get("response_type", "")
    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    code_challenge = params.get("code_challenge", "")
    code_challenge_method = params.get("code_challenge_method", "")
    state = params.get("state", "")
    # RFC 6749 §3.3: scope is a space-delimited list. Validate every
    # requested scope against the supported set and REJECT unknown
    # ones — echoing an unsupported scope back in the token response
    # would lie to the client about what the token is good for.
    scope_raw = params.get("scope", "").strip() or _SCOPE
    requested_scopes = scope_raw.split()
    unsupported = [s for s in requested_scopes if s not in _SUPPORTED_SCOPES]
    if unsupported:
        return _oauth_error(
            "invalid_scope",
            f"Unsupported scope(s): {' '.join(unsupported)}. "
            f"Only 'mcp' is recognized.",
        )
    scope = " ".join(requested_scopes)

    if response_type != "code":
        return _oauth_error(
            "unsupported_response_type",
            f"Only 'code' is supported, got {response_type!r}",
        )
    if not client_id:
        return _oauth_error("invalid_request", "client_id is required")
    if not redirect_uri:
        return _oauth_error("invalid_request", "redirect_uri is required")
    if code_challenge_method != "S256":
        return _oauth_error(
            "invalid_request",
            "code_challenge_method=S256 is required (plain PKCE is not accepted)",
        )
    if not code_challenge or len(code_challenge) < 43:
        return _oauth_error(
            "invalid_request",
            "code_challenge is required (base64url-encoded SHA-256 of the verifier)",
        )

    try:
        client = get_client(client_id)
    except StorageUnavailable:
        return _oauth_error(
            "server_error",
            "OAuth storage temporarily unavailable — try again shortly",
            status=503,
        )
    if client is None:
        return _oauth_error("invalid_client", "Unknown client_id", status=401)
    if redirect_uri not in client["redirect_uris"]:
        return _oauth_error(
            "invalid_request",
            "redirect_uri is not registered for this client",
        )

    code = secrets.token_urlsafe(32)
    try:
        put_code(
            code,
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": scope,
                "issued_at": int(time.time()),
            },
        )
    except StorageUnavailable:
        return _oauth_error(
            "server_error",
            "OAuth storage temporarily unavailable — try again shortly",
            status=503,
        )

    callback_params = {"code": code}
    if state:
        callback_params["state"] = state
    separator = "&" if "?" in redirect_uri else "?"
    return HttpResponseRedirect(f"{redirect_uri}{separator}{urlencode(callback_params)}")


# ---------------------------------------------------------------------------
# RFC 6749 — token endpoint
# ---------------------------------------------------------------------------


def _verify_pkce(verifier: str, challenge: str) -> bool:
    """S256 verification per RFC 7636 §4.6.

    ``base64url(sha256(verifier)) == challenge``. Constant-time compare
    because even the PKCE step can leak key material if you get sloppy.
    """
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(computed, challenge)


@csrf_exempt
@require_POST
@ratelimit(key="ip", rate="20/m", method="POST", block=True)
def token(request: HttpRequest) -> JsonResponse:
    """Exchange an authorization code for an access token.

    The access token we return is literally ``NOCKCC_API_KEY``. That
    way the existing BearerAuthMiddleware on /mcp/ accepts it with no
    changes — we're piggy-backing on the same ``compare_digest`` path.
    """
    if not _oauth_enabled():
        return _disabled_response()

    # RFC 6749 §4.1.3 — the token endpoint accepts application/x-www-form-urlencoded
    data = request.POST
    grant_type = data.get("grant_type", "")
    code = data.get("code", "")
    redirect_uri = data.get("redirect_uri", "")
    client_id = data.get("client_id", "")
    code_verifier = data.get("code_verifier", "")

    if grant_type != "authorization_code":
        return _oauth_error(
            "unsupported_grant_type",
            f"Only 'authorization_code' is supported, got {grant_type!r}",
        )
    if not all([code, redirect_uri, client_id, code_verifier]):
        return _oauth_error(
            "invalid_request",
            "code, redirect_uri, client_id, and code_verifier are all required",
        )

    try:
        record = pop_code(code)  # single-use: pop_code DELETEs as it reads
    except StorageUnavailable:
        return _oauth_error(
            "server_error",
            "OAuth storage temporarily unavailable — try again shortly",
            status=503,
        )
    if record is None:
        return _oauth_error(
            "invalid_grant",
            "Authorization code is invalid, expired, or already used",
        )
    if record["client_id"] != client_id:
        return _oauth_error("invalid_grant", "client_id does not match issued code")
    if record["redirect_uri"] != redirect_uri:
        return _oauth_error(
            "invalid_grant",
            "redirect_uri does not match issued code",
        )
    if not _verify_pkce(code_verifier, record["code_challenge"]):
        return _oauth_error("invalid_grant", "PKCE code_verifier failed S256 check")

    access_token = getattr(settings, "NOCKCC_API_KEY", "") or ""
    if not access_token:
        return _oauth_error(
            "server_error",
            "API key not configured on server",
            status=500,
        )

    return JsonResponse(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": _ACCESS_TOKEN_TTL_SECONDS,
            "scope": record.get("scope", _SCOPE),
        },
    )
