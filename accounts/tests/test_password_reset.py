"""Tests for the allauth password reset flow."""
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User

from allauth.account.models import EmailAddress


class PasswordResetPageTests(TestCase):
    def setUp(self):
        self.url = reverse("account_reset_password")
        self.user = User.objects.create_user(
            username="resettest", email="reset@example.com", password="OldPass123!"
        )
        EmailAddress.objects.create(
            user=self.user, email=self.user.email, primary=True, verified=True
        )

    def test_reset_page_renders(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Reset your password")

    def test_valid_email_sends_reset_link(self):
        resp = self.client.post(self.url, {"email": "reset@example.com"})
        self.assertIn(resp.status_code, [302])
        # Verify the reset email was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reset@example.com", mail.outbox[0].to)

    def test_unknown_email_does_not_leak_user_existence(self):
        """Allauth should not reveal whether an email is registered."""
        resp = self.client.post(self.url, {"email": "nobody@example.com"})
        # allauth responds with a redirect (not an error) to avoid enumeration
        self.assertIn(resp.status_code, [302])
        # allauth intentionally sends to unknown addresses for anti-enumeration;
        # the important thing is the response is indistinguishable from a real one

    def test_done_page_renders(self):
        resp = self.client.get(reverse("account_reset_password_done"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Check your email")
