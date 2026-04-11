# brain/tests/test_security.py
"""Security tests for Brain API hardening.

Originally written against the DiaryEntry API (14 tests covering HIGH-1
through MEDIUM-5 in the security audit). The diary API was removed in
PR 1 of the product fork; these tests are retargeted at the MemoryEntry
endpoint (`/api/brain/entries/`) because it shares the same
`require_brain_access` decorator and therefore the same auth / CORS /
rate-limit / CSRF behavior.

Tests 11-14 from the original suite (date-parameter validation) were
specific to the diary list view's `date_from` / `date_to` /
`session_date` filters. The memory entries endpoint does not accept
those parameters, so there is nothing equivalent to assert and those
tests are dropped. The auth/CORS/rate-limit/CSRF coverage (10 tests)
is preserved.

Covers:
 1. Non-staff authenticated user → 401
 2. Staff user → 200
 3. API key auth → 200
 4. Unauthenticated request → 401
 5. Non-allowed origin → no CORS header
 6. Allowed origin → CORS header present
 7. Rate limit exceeded → 429 + Retry-After
 8. Rate limit not exceeded → 200
 9. Session POST without CSRF token → 403
10. API key POST without CSRF token → 201 (exempt)
"""

import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase, override_settings


class BrainAccessControlTest(TestCase):
    """Tests 1-4: Broken access control fix (HIGH-1)."""

    def setUp(self) -> None:
        cache.clear()

    # Test 1: Non-staff authenticated user cannot access Brain API → 401
    def test_non_staff_user_cannot_access_brain_api(self) -> None:
        non_staff = User.objects.create_user(username="regular", password="pass", is_staff=False)
        self.client.force_login(non_staff)
        resp = self.client.get("/api/brain/entries/")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Staff access required", resp.json()["message"])

    # Test 2: Staff user can access Brain API → 200
    def test_staff_user_can_access_brain_api(self) -> None:
        staff = User.objects.create_user(username="staffuser", password="pass", is_staff=True)
        self.client.force_login(staff)
        resp = self.client.get("/api/brain/entries/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

    # Test 3: API key auth still works → 200
    @override_settings(NOCKCC_API_KEY="test-key-abc")
    def test_api_key_auth_works(self) -> None:
        # Ensure there is a staff user for the key-auth user-assignment
        User.objects.create_user(username="staffapi", password="pass", is_staff=True)
        resp = self.client.get("/api/brain/entries/", HTTP_X_API_KEY="test-key-abc")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

    # Test 4: Unauthenticated request → 401
    def test_unauthenticated_request_returns_401(self) -> None:
        resp = self.client.get("/api/brain/entries/")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Authentication required", resp.json()["message"])


class BrainCORSTest(TestCase):
    """Tests 5-6: Wildcard CORS fix (HIGH-2)."""

    def setUp(self) -> None:
        cache.clear()
        self.staff = User.objects.create_user(username="corsstaff", password="pass", is_staff=True)
        self.client.force_login(self.staff)

    # Test 5: Request from non-allowed origin gets no CORS header
    @override_settings(
        CORS_ALLOW_ALL_ORIGINS=False,
        CORS_ALLOWED_ORIGINS=["https://cc.nocktechnologies.io"],
    )
    def test_disallowed_origin_gets_no_cors_header(self) -> None:
        resp = self.client.get("/api/brain/entries/", HTTP_ORIGIN="https://evil.example.com")
        self.assertNotIn("Access-Control-Allow-Origin", resp)

    # Test 6: Request from allowed origin gets CORS header
    @override_settings(
        CORS_ALLOW_ALL_ORIGINS=False,
        CORS_ALLOWED_ORIGINS=["https://cc.nocktechnologies.io"],
    )
    def test_allowed_origin_gets_cors_header(self) -> None:
        resp = self.client.get("/api/brain/entries/", HTTP_ORIGIN="https://cc.nocktechnologies.io")
        self.assertIn("Access-Control-Allow-Origin", resp)
        self.assertEqual(resp["Access-Control-Allow-Origin"], "https://cc.nocktechnologies.io")


class BrainRateLimitTest(TestCase):
    """Tests 7-8: Rate limiting fix (HIGH-3)."""

    def setUp(self) -> None:
        cache.clear()
        self.staff = User.objects.create_user(username="rlstaff", password="pass", is_staff=True)
        self.client.force_login(self.staff)

    # Test 7: Rate limit exceeded → 429 with Retry-After
    def test_rate_limit_exceeded_returns_429_with_retry_after(self) -> None:
        with patch("django_ratelimit.decorators.is_ratelimited", return_value=True):
            resp = self.client.get("/api/brain/entries/")
        self.assertEqual(resp.status_code, 429)
        self.assertIn("Retry-After", resp)
        self.assertEqual(resp["Retry-After"], "60")
        body = resp.json()
        self.assertFalse(body["success"])
        self.assertIn("Rate limit exceeded", body["message"])

    # Test 8: Rate limit not exceeded → 200
    def test_rate_limit_not_exceeded_returns_200(self) -> None:
        resp = self.client.get("/api/brain/entries/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])


class BrainCSRFTest(TestCase):
    """Tests 9-10: CSRF enforcement fix (MEDIUM-4)."""

    def setUp(self) -> None:
        cache.clear()
        self.staff = User.objects.create_user(username="csrfstaff", password="pass", is_staff=True)

    # Test 9: Session POST without CSRF token → 403
    def test_session_post_without_csrf_token_returns_403(self) -> None:
        # Use a client that enforces CSRF checks
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)
        resp = csrf_client.post(
            "/api/brain/entries/",
            data=json.dumps({"key": "security-test", "value": "csrf-session", "category": "project"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    # Test 10: API key POST without CSRF token → 201 (exempt)
    @override_settings(NOCKCC_API_KEY="csrf-test-key")
    def test_api_key_post_without_csrf_token_returns_201(self) -> None:
        # Ensure staff user exists for key-auth user-assignment
        User.objects.create_user(username="csrfkeystaff", password="pass", is_staff=True)
        csrf_client = Client(enforce_csrf_checks=True)
        resp = csrf_client.post(
            "/api/brain/entries/",
            data=json.dumps({"key": "security-test", "value": "csrf-apikey", "category": "project"}),
            content_type="application/json",
            HTTP_X_API_KEY="csrf-test-key",
        )
        # API key auth bypasses CSRF — should succeed (201) not 403
        self.assertEqual(resp.status_code, 201)
