"""Tests for the allauth signup flow."""
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User


class SignupPageTests(TestCase):
    def setUp(self):
        self.url = reverse("account_signup")

    def test_signup_page_renders(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Create your account")

    def test_valid_signup_creates_user_and_sends_verification(self):
        resp = self.client.post(self.url, {
            "email": "new@example.com",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        })
        # Should redirect to verification-sent page (mandatory verification)
        self.assertIn(resp.status_code, [302])
        self.assertTrue(User.objects.filter(email="new@example.com").exists())
        # Verification email should have been sent (console backend queues to
        # django.core.mail.outbox in tests even though EMAIL_BACKEND isn't outbox)
        # — allauth sends via Django's mail API; in test mode outbox is populated.
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("new@example.com", mail.outbox[0].to)

    def test_duplicate_email_rejected(self):
        User.objects.create_user(
            username="existing", email="taken@example.com", password="pass"
        )
        resp = self.client.post(self.url, {
            "email": "taken@example.com",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        })
        # allauth 65.x uses a privacy-preserving redirect (not re-render) for
        # duplicate emails to avoid leaking which addresses are registered
        self.assertIn(resp.status_code, [200, 302])
        # Either way, no duplicate user was created
        self.assertLessEqual(User.objects.filter(email="taken@example.com").count(), 1)

    def test_weak_password_rejected(self):
        resp = self.client.post(self.url, {
            "email": "weak@example.com",
            "password1": "123",
            "password2": "123",
        })
        self.assertEqual(resp.status_code, 200)  # re-renders with error
        self.assertFalse(User.objects.filter(email="weak@example.com").exists())

    def test_mismatched_passwords_rejected(self):
        resp = self.client.post(self.url, {
            "email": "mismatch@example.com",
            "password1": "StrongPass123!",
            "password2": "DifferentPass456!",
        })
        self.assertEqual(resp.status_code, 200)  # re-renders with error
        self.assertFalse(User.objects.filter(email="mismatch@example.com").exists())
