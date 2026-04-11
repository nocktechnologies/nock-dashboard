import os

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

_TEST_FERNET_KEYS = [os.environ.get("TEST_FERNET_KEY", "")]


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class ControlPageTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="kevin", password="testpass")

    def test_authenticated_access(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/remote/")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "remote/control.html")
        self.assertContains(resp, "remoteControl")

    def test_unauthenticated_redirect(self) -> None:
        resp = self.client.get("/remote/")
        self.assertEqual(resp.status_code, 302)

    def test_contains_new_session_button(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/remote/")
        self.assertContains(resp, "New Session")

    def test_contains_kill_all_button(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/remote/")
        self.assertContains(resp, "Kill All")

    def test_contains_agent_status_banner(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/remote/")
        self.assertContains(resp, "agentOnline")


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class SessionDetailPageTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="kevin", password="testpass")

    def test_authenticated_access(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/remote/session/sess-test-123/")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "remote/session_detail.html")
        self.assertContains(resp, "sess-test-123")

    def test_unauthenticated_redirect(self) -> None:
        resp = self.client.get("/remote/session/sess-test-123/")
        self.assertEqual(resp.status_code, 302)

    def test_contains_output_container(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/remote/session/sess-test-123/")
        self.assertContains(resp, "outputContainer")

    def test_contains_send_button(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/remote/session/sess-test-123/")
        self.assertContains(resp, "Send")

    def test_contains_stop_button(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/remote/session/sess-test-123/")
        self.assertContains(resp, "Stop")


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class ChatPageTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="kevin", password="testpass")

    def test_authenticated_access(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/remote/chat/")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "remote/chat.html")
        self.assertContains(resp, "chatView")

    def test_unauthenticated_redirect(self) -> None:
        resp = self.client.get("/remote/chat/")
        self.assertEqual(resp.status_code, 302)

    def test_contains_chat_input(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/remote/chat/")
        self.assertContains(resp, "Message Claude Code")

    def test_contains_repo_selector(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/remote/chat/")
        self.assertContains(resp, "selectedRepo")

    def test_contains_marked_js(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/remote/chat/")
        self.assertContains(resp, "marked")

    def test_initial_conversation_id(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/remote/chat/?c=42")
        self.assertContains(resp, "42")


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS)
class BaseTemplateTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="kevin", password="testpass")

    def test_mobile_bottom_nav_present(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/remote/")
        # Asserts on `ncc-bottom-tabs` (the custom class on the mobile nav
        # element in templates/base.html). The original assertion looked for
        # Tailwind's `fixed bottom-0`, which pre-dated a template refactor to
        # use the ncc-bottom-tabs custom class. This fix is nock-dashboard-
        # specific (the product fork is permanently divergent from nock-cc
        # per docs/ARCHITECTURE; nock-cc has the same stale assertion and
        # can update it independently if they wish).
        self.assertContains(resp, "ncc-bottom-tabs")
        self.assertContains(resp, "/remote/")

    def test_pwa_manifest_link(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/remote/")
        self.assertContains(resp, "manifest.json")

    def test_service_worker_registration(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get("/remote/")
        self.assertContains(resp, "serviceWorker")
