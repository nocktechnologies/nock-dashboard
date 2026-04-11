"""Tests for the /accounts/profile/ view."""
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User


class ProfileViewTests(TestCase):
    def setUp(self):
        self.url = reverse("account-profile")
        self.user = User.objects.create_user(
            username="profiletest", email="profile@example.com", password="ProfilePass123!"
        )

    def test_unauthenticated_redirect_to_login(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login", resp.url)
        self.assertIn("next=/accounts/profile/", resp.url)

    def test_authenticated_user_sees_profile_page(self):
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "profile@example.com")
        self.assertContains(resp, "Your Profile")
