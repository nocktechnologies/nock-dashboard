import secrets
from functools import wraps
from typing import Any

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.middleware.csrf import CsrfViewMiddleware
from rest_framework import authentication, exceptions


def _api_key() -> str:
    return getattr(settings, "NOCKCC_API_KEY", "") or ""


# Reusable CSRF enforcer — used by require_brain_access for session-based writes.
_csrf_middleware = CsrfViewMiddleware(get_response=lambda req: None)


def require_api_key(view_func):  # type: ignore[no-untyped-def]
    """Decorator that checks X-API-Key header OR session auth.

    Allows both browser sessions (cookie-based) and API key auth so
    the same endpoints work for the web dashboard and the mobile app.
    """

    @wraps(view_func)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        # Allow authenticated browser sessions
        if request.user.is_authenticated:
            return view_func(request, *args, **kwargs)

        # Fall back to API key auth
        key = _api_key()
        if not key:
            return JsonResponse(
                {"success": False, "message": "API key not configured on server", "data": None},
                status=500,
            )
        provided = request.headers.get("X-API-Key", "")
        if not provided:
            return JsonResponse(
                {"success": False, "message": "Authentication required", "data": None},
                status=401,
            )
        if not secrets.compare_digest(provided, key):
            return JsonResponse(
                {"success": False, "message": "Invalid API key", "data": None},
                status=401,
            )

        # Assign a default staff user so views using request.user work
        from django.contrib.auth import get_user_model

        User = get_user_model()
        default_user = User.objects.filter(is_staff=True).order_by("pk").first()
        if default_user:
            request.user = default_user

        return view_func(request, *args, **kwargs)

    return wrapper


def require_brain_access(view_func):  # type: ignore[no-untyped-def]
    """Auth + rate-limit gate for all Brain API endpoints.

    Allows:
    - Valid X-API-Key header (programmatic access — CSRF skipped)
    - Valid Authorization: Token header (DRF TokenAuthentication — CSRF skipped)
    - Authenticated staff session (CSRF enforced for write methods)

    Non-staff authenticated users are rejected (401).
    Checks request.limited set by @ratelimit(block=False) and returns 429.

    Sets wrapper.csrf_exempt = True so CsrfViewMiddleware skips this view;
    CSRF is enforced manually for session auth via _csrf_middleware.process_view().
    """

    @wraps(view_func)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        # Rate limit check — set by @ratelimit(block=False) decorators on the view
        if getattr(request, "limited", False):
            resp = JsonResponse(
                {"success": False, "message": "Rate limit exceeded. Try again later.", "data": None},
                status=429,
            )
            resp["Retry-After"] = "60"
            return resp

        # API key auth — CSRF not required for programmatic access
        provided = request.headers.get("X-API-Key", "")
        if provided:
            key = _api_key()
            if not key:
                return JsonResponse(
                    {"success": False, "message": "API key not configured on server", "data": None},
                    status=500,
                )
            if secrets.compare_digest(provided, key):
                from django.contrib.auth import get_user_model

                User = get_user_model()
                default_user = User.objects.filter(is_staff=True).order_by("pk").first()
                if default_user:
                    request.user = default_user
                return view_func(request, *args, **kwargs)
            return JsonResponse(
                {"success": False, "message": "Invalid API key", "data": None},
                status=401,
            )

        # DRF Token auth — CSRF not required for programmatic access
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Token "):
            token_key = auth_header[6:].strip()
            if token_key:
                try:
                    from rest_framework.authtoken.models import Token

                    token = Token.objects.select_related("user").get(key=token_key)
                    if token.user.is_active:
                        request.user = token.user
                        return view_func(request, *args, **kwargs)
                except Token.DoesNotExist:
                    pass
                return JsonResponse(
                    {"success": False, "message": "Invalid token", "data": None},
                    status=401,
                )

        # Session auth — staff only; enforce CSRF for write methods
        if request.user.is_authenticated:
            if not request.user.is_staff:
                return JsonResponse(
                    {"success": False, "message": "Staff access required", "data": None},
                    status=401,
                )
            csrf_failure = _csrf_middleware.process_view(request, view_func, args, kwargs)
            if csrf_failure is not None:
                return JsonResponse(
                    {"success": False, "message": "CSRF verification failed", "data": None},
                    status=403,
                )
            return view_func(request, *args, **kwargs)

        return JsonResponse(
            {"success": False, "message": "Authentication required", "data": None},
            status=401,
        )

    # Tell CsrfViewMiddleware to skip this view — CSRF is enforced manually
    # inside the wrapper for session-based requests only.
    wrapper.csrf_exempt = True  # type: ignore[attr-defined]
    return wrapper


class NockCCApiKeyAuthentication(authentication.BaseAuthentication):
    """DRF authentication backend that accepts NockCC's `X-API-Key` header.

    Mirrors the X-API-Key branch of `require_brain_access` so DRF-backed
    views (e.g. the `projects/` plugin mounted at `/api/pm/`) can accept
    the same API key as the rest of NockCC's brain endpoints without
    requiring clients to also fetch a DRF Token.

    Authentication succeeds when:
      * The request has a non-empty `X-API-Key` header, and
      * The value matches `settings.NOCKCC_API_KEY` in constant time.

    On success it returns (staff_user, None) where staff_user is the
    lowest-pk staff user in the database — same fallback identity used
    by the decorator path. On header absence it returns None (DRF then
    falls through to the next authentication class in the chain). On
    header presence with a wrong value it raises AuthenticationFailed
    so DRF returns 401 with a clear message.

    The class is intentionally keyword-free: no NOCKCC_API_KEY default,
    no env var lookup here — all config lives in `settings.NOCKCC_API_KEY`.
    """

    header_name = "HTTP_X_API_KEY"  # Django WSGI-normalized form of X-API-Key

    def authenticate(self, request):  # type: ignore[no-untyped-def]
        provided = request.META.get(self.header_name, "")
        if not provided:
            # No X-API-Key header — let the next authentication class handle it
            # (e.g. SessionAuthentication or TokenAuthentication).
            return None

        configured = getattr(settings, "NOCKCC_API_KEY", "") or ""
        if not configured:
            raise exceptions.AuthenticationFailed(
                "API key authentication is not configured on the server",
            )
        if not secrets.compare_digest(provided, configured):
            raise exceptions.AuthenticationFailed("Invalid API key")

        from django.contrib.auth import get_user_model  # noqa: PLC0415 — lazy

        User = get_user_model()
        default_user = User.objects.filter(is_staff=True).order_by("pk").first()
        if default_user is None:
            raise exceptions.AuthenticationFailed(
                "No staff user configured to accept API key requests",
            )
        return (default_user, None)

    def authenticate_header(self, request):  # type: ignore[no-untyped-def]
        # DRF uses this to populate the WWW-Authenticate header on 401 responses.
        return 'ApiKey realm="nockcc"'
