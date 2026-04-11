"""Tests for the allauth login flow."""
from django.test import TestCase
from django.urls import reverse

from allauth.account.models import EmailAddress
from django.contrib.auth.models import User


class LoginPageTests(TestCase):
    def setUp(self):
        self.url = reverse("account_login")
        self.user = User.objects.create_user(
            username="logintest",
            email="login@example.com",
            password="LoginPass123!",
        )
        # Mark email as verified so login isn't blocked by mandatory verification
        EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            primary=True,
            verified=True,
        )

    def test_login_page_renders(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Sign in")

    def test_valid_credentials_log_in_and_redirect(self):
        resp = self.client.post(self.url, {
            "login": "login@example.com",
            "password": "LoginPass123!",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, "/", fetch_redirect_response=False)

    def test_invalid_credentials_show_error(self):
        resp = self.client.post(self.url, {
            "login": "login@example.com",
            "password": "wrongpassword",
        })
        self.assertEqual(resp.status_code, 200)
        # Structural assertion — allauth 65.x error text varies by version
        self.assertTrue(resp.context["form"].errors)

    def test_unverified_user_cannot_log_in(self):
        """ACCOUNT_EMAIL_VERIFICATION = 'mandatory' blocks unverified logins."""
        unverified = User.objects.create_user(
            username="unverified",
            email="unverified@example.com",
            password="UnverifiedPass123!",
        )
        # EmailAddress exists but is NOT verified
        EmailAddress.objects.create(
            user=unverified,
            email=unverified.email,
            primary=True,
            verified=False,
        )
        self.client.post(self.url, {
            "login": "unverified@example.com",
            "password": "UnverifiedPass123!",
        })
        # allauth redirects to email verification sent or re-renders with error
        # rather than logging in
        self.assertNotIn("_auth_user_id", self.client.session)
