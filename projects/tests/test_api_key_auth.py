"""
Tests for the NockCC-specific X-API-Key authentication path on the
projects/ plugin.

The plugin ships with DRF SessionAuthentication + TokenAuthentication by
default; NockCC additionally wires in `core.auth.NockCCApiKeyAuthentication`
so that `curl -H "X-API-Key: ..."` works uniformly across /api/brain/* and
/api/pm/*. These tests exercise that auth path end-to-end against the
plugin's endpoints.
"""
from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from projects.tests.helpers import make_project


@override_settings(ROOT_URLCONF="projects.urls", NOCKCC_API_KEY="test-api-key-123")
class ProjectsApiKeyAuthTests(TestCase):
    """X-API-Key header authentication (NockCC-specific adaptation)."""

    def setUp(self) -> None:
        # NockCCApiKeyAuthentication falls back to the lowest-pk staff
        # user as the identity for API-key requests, matching the
        # require_brain_access decorator pattern.
        self.staff_user = User.objects.create_user(
            username="staff_for_api_key", password=None, is_staff=True,
        )

    def test_api_key_header_authenticates_list_projects(self) -> None:
        make_project("Visible Project")
        response = APIClient().get(
            "/api/projects/", HTTP_X_API_KEY="test-api-key-123",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 1)

    def test_api_key_header_authenticates_dashboard(self) -> None:
        response = APIClient().get(
            "/api/tasks/dashboard/", HTTP_X_API_KEY="test-api-key-123",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_missing_api_key_still_401(self) -> None:
        response = APIClient().get("/api/projects/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_api_key_returns_401(self) -> None:
        response = APIClient().get(
            "/api/projects/", HTTP_X_API_KEY="definitely-wrong-value",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_empty_api_key_header_falls_through_to_next_backend(self) -> None:
        # An empty X-API-Key header should behave as if no header were sent:
        # DRF moves to the next authentication class in the chain
        # (TokenAuthentication, then SessionAuthentication). Since neither
        # is satisfied, the request ends up 401 — proving the backend
        # didn't intercept with its own AuthenticationFailed.
        response = APIClient().get("/api/projects/", HTTP_X_API_KEY="")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


@override_settings(ROOT_URLCONF="projects.urls")
class ProjectsApiKeyAuthMisconfiguredTests(TestCase):
    """When NOCKCC_API_KEY is unset, presenting an X-API-Key must fail
    loudly rather than silently matching an empty string."""

    def test_server_missing_api_key_returns_401_on_header_present(self) -> None:
        # No NOCKCC_API_KEY override — empty string default.
        with override_settings(NOCKCC_API_KEY=""):
            response = APIClient().get(
                "/api/projects/", HTTP_X_API_KEY="whatever",
            )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


@override_settings(ROOT_URLCONF="projects.urls")
class ProjectsDrfTokenAuthStillWorksTests(TestCase):
    """The stock DRF TokenAuthentication path must continue to work
    alongside the new X-API-Key backend — adding a new auth class must
    not regress existing auth."""

    def test_drf_token_header_authenticates(self) -> None:
        user = User.objects.create_user(
            username="token_user", password=None, is_active=True,
        )
        token = Token.objects.create(user=user)
        response = APIClient().get(
            "/api/projects/", HTTP_AUTHORIZATION=f"Token {token.key}",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
