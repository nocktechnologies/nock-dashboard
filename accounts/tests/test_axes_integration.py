"""Tests that django-axes brute-force lockout still works through allauth."""
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from allauth.account.models import EmailAddress


class AxesAllauthIntegrationTests(TestCase):
    """Verify axes' brute-force lockout still fires through the allauth backend.

    Axes wraps authenticate() — allauth uses authenticate() — so axes should
    capture failures. We test AXES_FAILURE_LIMIT failed logins and verify
    lockout, then test that successful login resets the counter.
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
            "login": self.user.email,
            "password": password,
        })
        return resp.status_code

    def test_five_failures_trigger_lockout(self):
        limit = settings.AXES_FAILURE_LIMIT

        # The first (limit - 1) failures should not yet trigger lockout.
        for _ in range(limit - 1):
            status = self._attempt_login("wrongpassword")
            self.assertEqual(status, 200, f"Attempts 1-{limit - 1} should not yet be locked out")

        # The Nth failure triggers the lockout — axes returns 429/403 for this request.
        lockout_status = self._attempt_login("wrongpassword")
        self.assertIn(
            lockout_status, [403, 429],
            f"Failure #{limit} should trigger lockout response, got {lockout_status}",
        )

        # After lockout, correct credentials are also blocked (axes blocks authenticate()).
        self._attempt_login("AxesPass123!")
        self.assertNotIn(
            self.client.session.get("_auth_user_id"),
            [str(self.user.pk)],
            "Locked user should not be able to log in even with correct credentials",
        )

    def test_successful_login_resets_axes_counter(self):
        """AXES_RESET_ON_SUCCESS means a correct login clears the failure count."""
        limit = settings.AXES_FAILURE_LIMIT

        # (limit - 1) failures — one below the lockout threshold
        for _ in range(limit - 1):
            self._attempt_login("wrongpassword")

        # Successful login clears the counter; verify the user is actually logged in
        self._attempt_login("AxesPass123!")
        self.assertIn(
            "_auth_user_id", self.client.session,
            "Successful login after failures should authenticate the user",
        )
        self.client.logout()

        # One subsequent failure should NOT trigger lockout (counter was reset)
        self._attempt_login("wrongpassword")
        resp = self.client.post(self.login_url, {
            "login": self.user.email,
            "password": "wrongpassword",
        })
        # Should still be 200 (error page) not 403/429 (lockout)
        self.assertEqual(resp.status_code, 200)
