# brain/tests/test_security.py
"""Security tests for Brain API hardening (fixes HIGH-1 through MEDIUM-5).

Covers all 14 test cases from the security audit:
 1. Non-staff authenticated user → 401
 2. Staff user → 200
 3. API key auth → 200
 4. Unauthenticated request → 401
 5. Non-allowed origin → no CORS header
 6. Allowed origin → CORS header present
 7. Rate limit exceeded → 429 + Retry-After
 8. Rate limit not exceeded → 200
 9. Session POST without CSRF token → 403
10. API key POST without CSRF token → 200 (exempt)
11. Invalid date_from → 400
12. Invalid date_to → 400
13. Invalid session_date → 400
14. Valid dates → 200
"""

import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from brain.models import DiaryEntry


class BrainAccessControlTest(TestCase):
    """Tests 1-4: Broken access control fix (HIGH-1)."""

    def setUp(self) -> None:
        cache.clear()

    def _make_entry(self) -> DiaryEntry:
        return DiaryEntry.objects.create(
            title="Test",
            content="Content",
            category=DiaryEntry.Category.WORK,
            source=DiaryEntry.Source.NOCKCC,
            entry_date=timezone.now(),
            session_date=timezone.now().date(),
        )

    # Test 1: Non-staff authenticated user cannot access Brain API → 401
    def test_non_staff_user_cannot_access_brain_api(self) -> None:
        non_staff = User.objects.create_user(username="regular", password="pass", is_staff=False)
        self.client.force_login(non_staff)
        resp = self.client.get("/api/brain/diary/")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Staff access required", resp.json()["message"])

    # Test 2: Staff user can access Brain API → 200
    def test_staff_user_can_access_brain_api(self) -> None:
        staff = User.objects.create_user(username="staffuser", password="pass", is_staff=True)
        self.client.force_login(staff)
        resp = self.client.get("/api/brain/diary/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

    # Test 3: API key auth still works → 200
    @override_settings(NOCKCC_API_KEY="test-key-abc")
    def test_api_key_auth_works(self) -> None:
        # Ensure there is a staff user for the key-auth user-assignment
        User.objects.create_user(username="staffapi", password="pass", is_staff=True)
        resp = self.client.get("/api/brain/diary/", HTTP_X_API_KEY="test-key-abc")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

    # Test 4: Unauthenticated request → 401
    def test_unauthenticated_request_returns_401(self) -> None:
        resp = self.client.get("/api/brain/diary/")
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
        resp = self.client.get("/api/brain/diary/", HTTP_ORIGIN="https://evil.example.com")
        self.assertNotIn("Access-Control-Allow-Origin", resp)

    # Test 6: Request from allowed origin gets CORS header
    @override_settings(
        CORS_ALLOW_ALL_ORIGINS=False,
        CORS_ALLOWED_ORIGINS=["https://cc.nocktechnologies.io"],
    )
    def test_allowed_origin_gets_cors_header(self) -> None:
        resp = self.client.get("/api/brain/diary/", HTTP_ORIGIN="https://cc.nocktechnologies.io")
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
            resp = self.client.get("/api/brain/diary/")
        self.assertEqual(resp.status_code, 429)
        self.assertIn("Retry-After", resp)
        self.assertEqual(resp["Retry-After"], "60")
        body = resp.json()
        self.assertFalse(body["success"])
        self.assertIn("Rate limit exceeded", body["message"])

    # Test 8: Rate limit not exceeded → 200
    def test_rate_limit_not_exceeded_returns_200(self) -> None:
        resp = self.client.get("/api/brain/diary/")
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
            "/api/brain/diary/",
            data=json.dumps({"title": "t", "content": "c", "category": "work"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    # Test 10: API key POST without CSRF token → 200 (exempt)
    @override_settings(NOCKCC_API_KEY="csrf-test-key")
    def test_api_key_post_without_csrf_token_returns_200(self) -> None:
        # Ensure staff user exists for key-auth user-assignment
        User.objects.create_user(username="csrfkeystaff", password="pass", is_staff=True)
        csrf_client = Client(enforce_csrf_checks=True)
        resp = csrf_client.post(
            "/api/brain/diary/",
            data=json.dumps({"title": "t", "content": "c", "category": "work"}),
            content_type="application/json",
            HTTP_X_API_KEY="csrf-test-key",
        )
        # API key auth bypasses CSRF — should succeed (201) not 403
        self.assertEqual(resp.status_code, 201)


class BrainDateValidationTest(TestCase):
    """Tests 11-14: Date parameter validation fix (MEDIUM-5)."""

    def setUp(self) -> None:
        cache.clear()
        self.staff = User.objects.create_user(username="datestaff", password="pass", is_staff=True)
        self.client.force_login(self.staff)

    def _make_entry(self) -> DiaryEntry:
        return DiaryEntry.objects.create(
            title="Test",
            content="Content",
            category=DiaryEntry.Category.WORK,
            source=DiaryEntry.Source.NOCKCC,
            entry_date=timezone.now(),
            session_date=timezone.now().date(),
        )

    # Test 11: Invalid date_from → 400 with error message
    def test_invalid_date_from_returns_400(self) -> None:
        resp = self.client.get("/api/brain/diary/?date_from=not-a-date")
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertFalse(body["success"])
        self.assertIn("date_from", body["message"])
        self.assertIn("YYYY-MM-DD", body["message"])

    # Test 12: Invalid date_to → 400
    def test_invalid_date_to_returns_400(self) -> None:
        resp = self.client.get("/api/brain/diary/?date_to=2026/04/08")
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertFalse(body["success"])
        self.assertIn("date_to", body["message"])

    # Test 13: Invalid session_date → 400
    def test_invalid_session_date_returns_400(self) -> None:
        resp = self.client.get("/api/brain/diary/?session_date=April-8-2026")
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertFalse(body["success"])
        self.assertIn("session_date", body["message"])

    # Test 14: Valid dates still work → 200
    def test_valid_dates_return_200(self) -> None:
        self._make_entry()
        resp = self.client.get(
            "/api/brain/diary/?date_from=2026-01-01&date_to=2026-12-31&session_date=2026-04-08"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
