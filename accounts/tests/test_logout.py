"""Tests for the allauth logout flow."""
from django.test import TestCase
from django.urls import reverse


class LogoutTests(TestCase):
    def setUp(self):
        self.url = reverse("account_logout")
        from django.contrib.auth.models import User
        from allauth.account.models import EmailAddress
        self.user = User.objects.create_user(
            username="logouttest", email="logout@example.com", password="LogoutPass123!"
        )
        EmailAddress.objects.create(
            user=self.user, email=self.user.email, primary=True, verified=True
        )

    def test_logout_clears_session(self):
        self.client.force_login(self.user)
        self.assertIn("_auth_user_id", self.client.session)
        # allauth logout is a POST for CSRF safety
        self.client.post(self.url)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_redirects_to_login(self):
        self.client.force_login(self.user)
        resp = self.client.post(self.url)
        self.assertIn(resp.status_code, [302])
        self.assertIn("/accounts/login", resp.url)
