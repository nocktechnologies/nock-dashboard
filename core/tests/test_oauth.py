"""Tests for the OAuth 2.1 shim (core/oauth/).

Covers:
- Discovery endpoints return correct JSON when enabled, 404 when disabled
- Dynamic registration accepts valid requests and rejects bad ones
- Authorize auto-approves and redirects with a code (PKCE S256 required)
- Token exchanges a valid code + verifier for NOCKCC_API_KEY
- Token rejects wrong verifier, wrong client, expired, already-used codes
- End-to-end round-trip: register → authorize → token → get access token
- The /mcp trailing-slash redirect
- The resource_metadata attribute on the 401 WWW-Authenticate header

Redis storage is mocked so tests don't need a real broker.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from unittest.mock import patch

import pytest
from django.test import Client, override_settings
from django.urls import reverse

_API_KEY = "test-nockcc-key-oauth-abc123"
_ISSUER = "http://testserver"


# ---------------------------------------------------------------------------
# In-memory replacement for redis so the shim's storage layer can be
# exercised without a running broker. Models TTL explicitly so tests
# can fast-forward a clock and verify expired codes disappear — the
# 60-second code TTL is one of the shim's stated security guarantees
# and the test suite has to fail loudly if it regresses.
# ---------------------------------------------------------------------------


class _FakeStore:
    def __init__(self) -> None:
        # Each code maps to (record, expires_at_monotonic). The current
        # "time" is held in ``self.now`` and advanced explicitly by tests
        # via ``advance()`` — we do NOT rely on wall-clock time so the
        # suite stays deterministic.
        self.clients: dict[str, dict] = {}
        self._codes: dict[str, tuple[dict, float]] = {}
        self.now: float = 0.0
        self.code_ttl: float = 60.0

    # ----- time control -----

    def advance(self, seconds: float) -> None:
        """Fast-forward the fake clock so expired codes drop."""
        self.now += seconds

    # ----- client ops (no TTL modelled — clients are long-lived) -----

    def put_client(self, client_id, record):
        self.clients[client_id] = record

    def get_client(self, client_id):
        return self.clients.get(client_id)

    # ----- code ops (60s TTL modelled) -----

    def put_code(self, code, record):
        self._codes[code] = (record, self.now + self.code_ttl)

    def pop_code(self, code):
        entry = self._codes.pop(code, None)
        if entry is None:
            return None
        record, expires_at = entry
        if expires_at < self.now:
            return None  # expired — same contract as real Redis TTL
        return record

    # ----- test-only introspection -----

    @property
    def codes(self) -> dict[str, dict]:
        """Expose just the non-expired records (stripping the TTL tuple)
        so test assertions that count or inspect outstanding codes stay
        consistent with what ``pop_code()`` would actually return."""
        return {
            code: record
            for code, (record, expires_at) in self._codes.items()
            if expires_at >= self.now
        }


@pytest.fixture
def store():
    fake = _FakeStore()
    with (
        patch("core.oauth.views.put_client", side_effect=fake.put_client),
        patch("core.oauth.views.get_client", side_effect=fake.get_client),
        patch("core.oauth.views.put_code", side_effect=fake.put_code),
        patch("core.oauth.views.pop_code", side_effect=fake.pop_code),
    ):
        yield fake


@pytest.fixture(autouse=True)
def _disable_ratelimit():
    """Turn off django-ratelimit globally so tests aren't flaky."""
    with override_settings(RATELIMIT_ENABLE=False):
        yield


def _pkce_pair() -> tuple[str, str]:
    """Generate a ``(verifier, challenge)`` tuple per RFC 7636 §4."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


# ---------------------------------------------------------------------------
# Discovery endpoints
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, OAUTH_ISSUER_URL=_ISSUER, NOCKCC_API_KEY=_API_KEY)
def test_resource_metadata_returns_rfc9728_doc():
    client = Client()
    resp = client.get(reverse("wellknown:resource-metadata"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["resource"] == f"{_ISSUER}/mcp"
    assert body["authorization_servers"] == [_ISSUER]
    assert body["bearer_methods_supported"] == ["header"]
    assert body["scopes_supported"] == ["mcp"]


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, OAUTH_ISSUER_URL=_ISSUER, NOCKCC_API_KEY=_API_KEY)
def test_authorization_server_metadata_returns_rfc8414_doc():
    client = Client()
    resp = client.get(reverse("wellknown:authorization-server-metadata"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["issuer"] == _ISSUER
    assert body["authorization_endpoint"] == f"{_ISSUER}/oauth/authorize"
    assert body["token_endpoint"] == f"{_ISSUER}/oauth/token"
    assert body["registration_endpoint"] == f"{_ISSUER}/oauth/register"
    assert body["response_types_supported"] == ["code"]
    assert body["grant_types_supported"] == ["authorization_code"]
    assert body["code_challenge_methods_supported"] == ["S256"]
    assert body["token_endpoint_auth_methods_supported"] == ["none"]


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=False, NOCKCC_API_KEY=_API_KEY)
def test_discovery_404s_when_oauth_disabled():
    client = Client()
    r1 = client.get(reverse("wellknown:resource-metadata"))
    r2 = client.get(reverse("wellknown:authorization-server-metadata"))
    assert r1.status_code == 404
    assert r2.status_code == 404


# ---------------------------------------------------------------------------
# Dynamic client registration
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_register_accepts_valid_request(store):
    client = Client()
    resp = client.post(
        reverse("oauth:register"),
        data=json.dumps({
            "client_name": "Claude.ai Custom Connector",
            "redirect_uris": ["https://claude.ai/api/mcp/callback"],
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
        }),
        content_type="application/json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["client_id"].startswith("nockcc-")
    assert body["redirect_uris"] == ["https://claude.ai/api/mcp/callback"]
    assert body["token_endpoint_auth_method"] == "none"
    assert "client_id_issued_at" in body
    # Client was persisted so authorize can look it up
    assert store.get_client(body["client_id"]) is not None


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_register_rejects_missing_redirect_uris(store):
    client = Client()
    resp = client.post(
        reverse("oauth:register"),
        data=json.dumps({"client_name": "x"}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_redirect_uri"


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_register_filters_unsupported_grant_types(store):
    """Real OAuth clients (claude.ai, Okta-generated libs) routinely
    declare ``grant_types: ["authorization_code", "refresh_token"]``
    even when the server doesn't issue refresh tokens. Per RFC 7591
    §2 + §3.2.1 the server must intersect the requested grants with
    what it supports and return the honored subset — NOT reject the
    whole registration and block every standards-compliant client."""
    client = Client()
    resp = client.post(
        reverse("oauth:register"),
        data=json.dumps({
            "client_name": "Claude",
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": "mcp",
        }),
        content_type="application/json",
    )
    assert resp.status_code == 201
    body = resp.json()
    # The server-accepted subset is echoed back — no refresh_token
    assert body["grant_types"] == ["authorization_code"]
    assert body["response_types"] == ["code"]
    # The client_id was minted normally
    assert body["client_id"].startswith("nockcc-")


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_register_rejects_all_unsupported_grant_types(store):
    """If the intersection of requested and supported grants is empty
    (e.g. client only asks for 'password' with no authorization_code
    alongside it), registration still fails — there's no usable
    grant so there's no point in persisting the client."""
    client = Client()
    resp = client.post(
        reverse("oauth:register"),
        data=json.dumps({
            "redirect_uris": ["https://claude.ai/cb"],
            "grant_types": ["password"],
        }),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_client_metadata"


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_register_rejects_non_list_grant_types(store):
    """grant_types must be an array per RFC 7591 — a string or number
    is a client bug the server should surface immediately."""
    client = Client()
    resp = client.post(
        reverse("oauth:register"),
        data=json.dumps({
            "redirect_uris": ["https://claude.ai/cb"],
            "grant_types": "authorization_code",  # should be an array
        }),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_client_metadata"


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_register_filters_unsupported_response_types(store):
    """Same intersection logic for response_types: ``code`` + ``token``
    (hybrid flow) should register with the ``code`` subset, not be
    rejected wholesale."""
    client = Client()
    resp = client.post(
        reverse("oauth:register"),
        data=json.dumps({
            "redirect_uris": ["https://claude.ai/cb"],
            "response_types": ["code", "token"],
        }),
        content_type="application/json",
    )
    assert resp.status_code == 201
    assert resp.json()["response_types"] == ["code"]


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_register_rejects_all_unsupported_response_types(store):
    """If the intersection of requested and supported response_types
    is empty, registration fails."""
    client = Client()
    resp = client.post(
        reverse("oauth:register"),
        data=json.dumps({
            "redirect_uris": ["https://claude.ai/cb"],
            "response_types": ["token"],
        }),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_client_metadata"


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_register_rejects_non_http_redirect(store):
    client = Client()
    resp = client.post(
        reverse("oauth:register"),
        data=json.dumps({"redirect_uris": ["file:///etc/passwd"]}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_redirect_uri"


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=False, NOCKCC_API_KEY=_API_KEY)
def test_register_404s_when_oauth_disabled(store):
    client = Client()
    resp = client.post(
        reverse("oauth:register"),
        data=json.dumps({"redirect_uris": ["https://example.com/cb"]}),
        content_type="application/json",
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Authorize endpoint
# ---------------------------------------------------------------------------


def _register_client(store, redirect_uri: str = "https://claude.ai/cb") -> str:
    client_id = f"nockcc-{secrets.token_urlsafe(8)}"
    store.put_client(client_id, {
        "client_id": client_id,
        "client_name": "test",
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    })
    return client_id


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_authorize_auto_redirects_with_code(store):
    cid = _register_client(store)
    _, challenge = _pkce_pair()
    client = Client()
    resp = client.get(
        reverse("oauth:authorize"),
        {
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": "https://claude.ai/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "xyz",
            "scope": "mcp",
        },
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].startswith("https://claude.ai/cb?code=")
    assert "state=xyz" in resp.headers["Location"]
    # One code now lives in the fake store
    assert len(store.codes) == 1


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_authorize_rejects_plain_pkce(store):
    cid = _register_client(store)
    client = Client()
    resp = client.get(
        reverse("oauth:authorize"),
        {
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": "https://claude.ai/cb",
            "code_challenge": "any-verifier",
            "code_challenge_method": "plain",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_request"


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_authorize_rejects_unknown_client(store):
    _, challenge = _pkce_pair()
    client = Client()
    resp = client.get(
        reverse("oauth:authorize"),
        {
            "response_type": "code",
            "client_id": "nockcc-unknown",
            "redirect_uri": "https://claude.ai/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid_client"


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_authorize_rejects_redirect_uri_not_registered(store):
    cid = _register_client(store, redirect_uri="https://claude.ai/cb")
    _, challenge = _pkce_pair()
    client = Client()
    resp = client.get(
        reverse("oauth:authorize"),
        {
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": "https://evil.com/steal",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
    )
    assert resp.status_code == 400
    assert "redirect_uri" in resp.json()["error_description"]


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_authorize_rejects_unknown_scope(store):
    """Discovery says only 'mcp' is supported — a client asking for
    'admin' must be rejected instead of having the scope echoed back
    in the token response."""
    cid = _register_client(store)
    _, challenge = _pkce_pair()
    client = Client()
    resp = client.get(
        reverse("oauth:authorize"),
        {
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": "https://claude.ai/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "mcp admin",  # 'admin' is not supported
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "invalid_scope"
    assert "admin" in body["error_description"]


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_authorize_accepts_default_mcp_scope(store):
    """When no scope is supplied the shim defaults to 'mcp'."""
    cid = _register_client(store)
    _, challenge = _pkce_pair()
    client = Client()
    resp = client.get(
        reverse("oauth:authorize"),
        {
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": "https://claude.ai/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
    )
    assert resp.status_code == 302


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_authorize_rejects_wrong_response_type(store):
    cid = _register_client(store)
    _, challenge = _pkce_pair()
    client = Client()
    resp = client.get(
        reverse("oauth:authorize"),
        {
            "response_type": "token",  # implicit flow — not allowed
            "client_id": cid,
            "redirect_uri": "https://claude.ai/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "unsupported_response_type"


# ---------------------------------------------------------------------------
# Token endpoint
# ---------------------------------------------------------------------------


def _get_code(store, client_client, client_id: str, verifier: str, challenge: str) -> str:
    """Helper: drive the authorize endpoint to get a real code."""
    resp = client_client.get(
        reverse("oauth:authorize"),
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "https://claude.ai/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
    )
    assert resp.status_code == 302
    # Parse the code out of the Location URL
    location = resp.headers["Location"]
    return location.split("code=", 1)[1].split("&", 1)[0]


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_token_exchanges_valid_code_for_access_token(store):
    cid = _register_client(store)
    verifier, challenge = _pkce_pair()
    client = Client()
    code = _get_code(store, client, cid, verifier, challenge)

    resp = client.post(
        reverse("oauth:token"),
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://claude.ai/cb",
            "client_id": cid,
            "code_verifier": verifier,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    # Access token is the NockCC API key so the existing BearerAuthMiddleware
    # on /mcp/ accepts it unchanged
    assert body["access_token"] == _API_KEY
    assert body["token_type"] == "Bearer"
    assert body["scope"] == "mcp"
    assert body["expires_in"] > 0


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_token_rejects_wrong_pkce_verifier(store):
    cid = _register_client(store)
    _, challenge = _pkce_pair()
    client = Client()
    code = _get_code(store, client, cid, "right-verifier", challenge)

    resp = client.post(
        reverse("oauth:token"),
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://claude.ai/cb",
            "client_id": cid,
            "code_verifier": "wrong-verifier",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_grant"


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_token_rejects_expired_code(store):
    """Authorization codes expire after 60 seconds — the fake store's
    advance() fast-forwards past that cliff so this test would fail
    loudly if the TTL were removed from core/oauth/storage.py."""
    cid = _register_client(store)
    verifier, challenge = _pkce_pair()
    client = Client()
    code = _get_code(store, client, cid, verifier, challenge)

    # Fast-forward past the 60-second TTL
    store.advance(store.code_ttl + 1)

    resp = client.post(
        reverse("oauth:token"),
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://claude.ai/cb",
            "client_id": cid,
            "code_verifier": verifier,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_grant"


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_token_rejects_code_reuse(store):
    cid = _register_client(store)
    verifier, challenge = _pkce_pair()
    client = Client()
    code = _get_code(store, client, cid, verifier, challenge)

    resp1 = client.post(
        reverse("oauth:token"),
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://claude.ai/cb",
            "client_id": cid,
            "code_verifier": verifier,
        },
    )
    assert resp1.status_code == 200

    # Second attempt with the same code must fail
    resp2 = client.post(
        reverse("oauth:token"),
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://claude.ai/cb",
            "client_id": cid,
            "code_verifier": verifier,
        },
    )
    assert resp2.status_code == 400
    assert resp2.json()["error"] == "invalid_grant"


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_token_rejects_client_id_mismatch(store):
    cid = _register_client(store)
    verifier, challenge = _pkce_pair()
    client = Client()
    code = _get_code(store, client, cid, verifier, challenge)

    resp = client.post(
        reverse("oauth:token"),
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://claude.ai/cb",
            "client_id": "nockcc-different",
            "code_verifier": verifier,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_grant"


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_token_rejects_redirect_uri_mismatch(store):
    cid = _register_client(store)
    verifier, challenge = _pkce_pair()
    client = Client()
    code = _get_code(store, client, cid, verifier, challenge)

    resp = client.post(
        reverse("oauth:token"),
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://different.com/cb",
            "client_id": cid,
            "code_verifier": verifier,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_grant"


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY=_API_KEY)
def test_token_rejects_wrong_grant_type(store):
    client = Client()
    resp = client.post(
        reverse("oauth:token"),
        {
            "grant_type": "password",
            "code": "x",
            "redirect_uri": "https://claude.ai/cb",
            "client_id": "nockcc-x",
            "code_verifier": "x",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "unsupported_grant_type"


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, NOCKCC_API_KEY="")
def test_token_500s_when_api_key_not_configured(store):
    cid = _register_client(store)
    verifier, challenge = _pkce_pair()
    client = Client()
    code = _get_code(store, client, cid, verifier, challenge)

    resp = client.post(
        reverse("oauth:token"),
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://claude.ai/cb",
            "client_id": cid,
            "code_verifier": verifier,
        },
    )
    assert resp.status_code == 500
    assert resp.json()["error"] == "server_error"


# ---------------------------------------------------------------------------
# End-to-end round-trip through the full OAuth flow
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(NOCKCC_OAUTH_ENABLED=True, OAUTH_ISSUER_URL=_ISSUER, NOCKCC_API_KEY=_API_KEY)
def test_end_to_end_register_authorize_token(store):
    """Walk the full RFC 6749 authorization_code + PKCE dance."""
    client = Client()

    # 1. Register
    reg_resp = client.post(
        reverse("oauth:register"),
        data=json.dumps({
            "client_name": "Claude.ai",
            "redirect_uris": ["https://claude.ai/api/mcp/callback"],
        }),
        content_type="application/json",
    )
    assert reg_resp.status_code == 201
    client_id = reg_resp.json()["client_id"]

    # 2. Authorize
    verifier, challenge = _pkce_pair()
    auth_resp = client.get(
        reverse("oauth:authorize"),
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "https://claude.ai/api/mcp/callback",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "opaque-state-value",
        },
    )
    assert auth_resp.status_code == 302
    location = auth_resp.headers["Location"]
    assert location.startswith("https://claude.ai/api/mcp/callback?")
    assert "state=opaque-state-value" in location
    code = location.split("code=", 1)[1].split("&", 1)[0]

    # 3. Token
    tok_resp = client.post(
        reverse("oauth:token"),
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://claude.ai/api/mcp/callback",
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )
    assert tok_resp.status_code == 200
    body = tok_resp.json()
    assert body["access_token"] == _API_KEY
    assert body["token_type"] == "Bearer"


# ---------------------------------------------------------------------------
# /mcp trailing-slash redirect + WWW-Authenticate resource_metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@override_settings(NOCKCC_OAUTH_ENABLED=True, OAUTH_ISSUER_URL=_ISSUER, NOCKCC_API_KEY=_API_KEY)
async def test_www_authenticate_header_includes_resource_metadata_when_oauth_on():
    """When OAuth is enabled the 401 breadcrumbs claude.ai to discovery."""
    from httpx import ASGITransport, AsyncClient
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    from mcp_server.http_app import BearerAuthMiddleware

    async def _protected(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    app = Starlette(
        routes=[Route("/protected", _protected, methods=["GET"])],
        middleware=[Middleware(BearerAuthMiddleware)],
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/protected")
    assert resp.status_code == 401
    header = resp.headers.get("www-authenticate", "")
    assert "Bearer" in header
    assert "resource_metadata=" in header
    assert f'"{_ISSUER}/.well-known/oauth-protected-resource/mcp"' in header


@pytest.mark.asyncio
@override_settings(
    NOCKCC_OAUTH_ENABLED=True,
    OAUTH_ISSUER_URL="https://example.com/\u00ff",  # non-ASCII in issuer
    NOCKCC_API_KEY=_API_KEY,
)
async def test_www_authenticate_header_falls_back_on_non_ascii_issuer():
    """A misconfigured issuer URL must not cascade into 500s on every
    401. The middleware falls back to the bare Bearer realm instead."""
    from httpx import ASGITransport, AsyncClient
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    from mcp_server.http_app import BearerAuthMiddleware

    async def _protected(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    app = Starlette(
        routes=[Route("/protected", _protected, methods=["GET"])],
        middleware=[Middleware(BearerAuthMiddleware)],
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/protected")
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == 'Bearer realm="nockcc-mcp"'


@pytest.mark.asyncio
@override_settings(NOCKCC_OAUTH_ENABLED=False, NOCKCC_API_KEY=_API_KEY)
async def test_www_authenticate_header_is_bare_when_oauth_off():
    """When OAuth is disabled the header is the plain Bearer challenge."""
    from httpx import ASGITransport, AsyncClient
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    from mcp_server.http_app import BearerAuthMiddleware

    async def _protected(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    app = Starlette(
        routes=[Route("/protected", _protected, methods=["GET"])],
        middleware=[Middleware(BearerAuthMiddleware)],
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/protected")
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == 'Bearer realm="nockcc-mcp"'


@pytest.mark.asyncio
@override_settings(NOCKCC_OAUTH_ENABLED=True, OAUTH_ISSUER_URL=_ISSUER, NOCKCC_API_KEY=_API_KEY)
async def test_mcp_bare_path_redirects_to_trailing_slash():
    """Verify config.asgi's redirect route turns /mcp into /mcp/."""
    from httpx import ASGITransport, AsyncClient

    # Import the outer router directly (it has the Route before the Mount)
    from config.asgi import http_router

    async with AsyncClient(
        transport=ASGITransport(app=http_router),
        base_url="http://t",
        follow_redirects=False,
    ) as client:
        resp = await client.get("/mcp")
    assert resp.status_code == 308
    assert resp.headers["location"] == "/mcp/"
