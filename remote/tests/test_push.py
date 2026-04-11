import json
import os
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from remote.models import PushSubscription

_TEST_FERNET_KEYS = [os.environ.get("TEST_FERNET_KEY", "")]


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class PushSubscriptionModelTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="kevin", password="testpass")

    def test_create_subscription(self) -> None:
        sub = PushSubscription.objects.create(
            user=self.user,
            endpoint="https://push.example.com/abc",
            p256dh="test-p256dh-key",
            auth="test-auth-key",
        )
        self.assertEqual(str(sub), "Push subscription for kevin")
        self.assertIsNotNone(sub.created_at)

    def test_unique_user_endpoint(self) -> None:
        PushSubscription.objects.create(
            user=self.user,
            endpoint="https://push.example.com/abc",
            p256dh="key1",
            auth="auth1",
        )
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            PushSubscription.objects.create(
                user=self.user,
                endpoint="https://push.example.com/abc",
                p256dh="key2",
                auth="auth2",
            )


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class PushSubscribeViewTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="kevin", password="testpass")
        self.client.force_login(self.user)

    def test_subscribe(self) -> None:
        resp = self.client.post(
            "/remote/api/remote/push/subscribe/",
            data=json.dumps({
                "endpoint": "https://push.example.com/abc",
                "keys": {"p256dh": "test-key", "auth": "test-auth"},
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(PushSubscription.objects.count(), 1)

    def test_subscribe_missing_fields(self) -> None:
        resp = self.client.post(
            "/remote/api/remote/push/subscribe/",
            data=json.dumps({"endpoint": "https://push.example.com/abc"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_subscribe_unauthenticated(self) -> None:
        self.client.logout()
        resp = self.client.post(
            "/remote/api/remote/push/subscribe/",
            data=json.dumps({
                "endpoint": "https://push.example.com/abc",
                "keys": {"p256dh": "k", "auth": "a"},
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_subscribe_updates_existing(self) -> None:
        PushSubscription.objects.create(
            user=self.user,
            endpoint="https://push.example.com/abc",
            p256dh="old-key",
            auth="old-auth",
        )
        resp = self.client.post(
            "/remote/api/remote/push/subscribe/",
            data=json.dumps({
                "endpoint": "https://push.example.com/abc",
                "keys": {"p256dh": "new-key", "auth": "new-auth"},
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PushSubscription.objects.count(), 1)
        sub = PushSubscription.objects.first()
        self.assertEqual(sub.p256dh, "new-key")


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class PushUnsubscribeViewTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="kevin", password="testpass")
        self.client.force_login(self.user)

    def test_unsubscribe(self) -> None:
        PushSubscription.objects.create(
            user=self.user,
            endpoint="https://push.example.com/abc",
            p256dh="k",
            auth="a",
        )
        resp = self.client.post(
            "/remote/api/remote/push/unsubscribe/",
            data=json.dumps({"endpoint": "https://push.example.com/abc"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PushSubscription.objects.count(), 0)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class NotificationsPageTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="kevin", password="testpass")

    def test_authenticated_access(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/remote/notifications/")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "remote/notifications.html")

    def test_unauthenticated_redirect(self) -> None:
        resp = self.client.get("/remote/notifications/")
        self.assertEqual(resp.status_code, 302)


@override_settings(
    FERNET_KEYS=_TEST_FERNET_KEYS,
    VAPID_PUBLIC_KEY="",
    VAPID_PRIVATE_KEY="",
    SLACK_WEBHOOK_URL="",
)
class PushHelperTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="kevin", password="testpass")

    def test_no_subscriptions_returns_zero(self) -> None:
        from remote.push import send_push_notification

        result = send_push_notification(self.user, "Test", "Body")
        self.assertEqual(result, 0)

    @patch("remote.push._fallback_slack")
    def test_no_vapid_keys_falls_back(self, mock_slack) -> None:
        from remote.push import send_push_notification

        PushSubscription.objects.create(
            user=self.user,
            endpoint="https://push.example.com/abc",
            p256dh="k",
            auth="a",
        )
        result = send_push_notification(self.user, "Test", "Body")
        self.assertEqual(result, 0)
        mock_slack.assert_called_once()
