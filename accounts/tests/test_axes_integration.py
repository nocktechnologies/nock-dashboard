"""Tests that django-axes brute-force lockout still works through allauth."""
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User

from allauth.account.models import EmailAddress


class AxesAllauthIntegrationTests(TestCase):
    """Verify axes' brute-force lockout still fires through the allauth backend.

    Axes wraps authenticate() — allauth uses authenticate() — so axes should
    capture failures. We test 5 failed logins (the AXES_FAILURE_LIMIT) and
    verify lockout, then test that successful login resets the counter.
    """

    def setUp(self):
        cache.clear()
        self.login_url = reverse("account_login")
        self.user = User.objects.create_user(
            username="axestest", email="axes@example.com", password="AxesPass123!"
        )
        EmailAddress.objects.create(
            user=self.user, email=self.user.email, primary=True, verified=True
        )

    def tearDown(self):
        cache.clear()

    def _attempt_login(self, password: str) -> int:
        resp = self.client.post(self.login_url, {
            "login": "axes@example.com",
            "password": password,
        })
        return resp.status_code

    def test_five_failures_trigger_lockout(self):
        # The 5th failure is what triggers the lockout response via axes signal.
        # Attempts 1-4 return 200 (login page with error).
        for _ in range(4):
            status = self._attempt_login("wrongpassword")
            self.assertEqual(status, 200, "Attempts 1-4 should not yet be locked out")

        # The 5th failure triggers the lockout — axes returns 429/403 for this request.
        lockout_status = self._attempt_login("wrongpassword")
        self.assertIn(
            lockout_status, [403, 429],
            f"5th failure should trigger lockout response, got {lockout_status}",
        )

        # After lockout, correct credentials are also blocked (axes blocks authenticate()).
        correct_status = self._attempt_login("AxesPass123!")
        self.assertNotIn(
            self.client.session.get("_auth_user_id"),
            [str(self.user.pk)],
            "Locked user should not be able to log in even with correct credentials",
        )

    def test_successful_login_resets_axes_counter(self):
        """AXES_RESET_ON_SUCCESS means a correct login clears the failure count."""
        # 4 failures (one below the limit)
        for _ in range(4):
            self._attempt_login("wrongpassword")
        # Successful login clears the counter
        self._attempt_login("AxesPass123!")
        self.client.logout()
        # Subsequent failures should NOT trigger lockout immediately
        self._attempt_login("wrongpassword")
        resp = self.client.post(self.login_url, {
            "login": "axes@example.com",
            "password": "wrongpassword",
        })
        # Should still be 200 (error page) not 403 (lockout)
        self.assertEqual(resp.status_code, 200)
