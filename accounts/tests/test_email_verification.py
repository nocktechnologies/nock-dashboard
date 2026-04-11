"""Tests for the allauth email verification flow."""
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User

from allauth.account.models import EmailAddress, EmailConfirmationHMAC


class EmailVerificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="verifytest", email="verify@example.com", password="VerifyPass123!"
        )
        self.email_address = EmailAddress.objects.create(
            user=self.user, email=self.user.email, primary=True, verified=False
        )

    def test_signup_sends_verification_email(self):
        """New users get a verification email after signing up."""
        resp = self.client.post(reverse("account_signup"), {
            "email": "brand_new@example.com",
            "password1": "BrandNewPass123!",
            "password2": "BrandNewPass123!",
        })
        self.assertIn(resp.status_code, [302])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("brand_new@example.com", mail.outbox[0].to)

    def test_valid_verification_link_marks_email_verified(self):
        """Clicking the verification link sets verified=True on EmailAddress."""
        confirmation = EmailConfirmationHMAC(self.email_address)
        key = confirmation.key
        url = reverse("account_confirm_email", kwargs={"key": key})
        resp = self.client.post(url)
        self.assertIn(resp.status_code, [200, 302])
        self.email_address.refresh_from_db()
        self.assertTrue(self.email_address.verified)

    def test_invalid_verification_key_returns_error(self):
        """An invalid/expired key shows an error, not a 500."""
        url = reverse("account_confirm_email", kwargs={"key": "badkey"})
        resp = self.client.get(url)
        self.assertIn(resp.status_code, [200, 302, 404])
        # The email address should remain unverified
        self.email_address.refresh_from_db()
        self.assertFalse(self.email_address.verified)
