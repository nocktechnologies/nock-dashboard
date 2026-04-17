"""Smoke tests for health beacon (Task 135) — nock-dashboard port."""
from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from dashboard.views import _compute_health_status


class ComputeHealthStatusTests(TestCase):
    def test_healthy_when_no_issues(self) -> None:
        status, count = _compute_health_status([], [], [], [], [], [])
        self.assertEqual(status, "HEALTHY")
        self.assertEqual(count, 0)

    def test_critical_when_stale_sessions(self) -> None:
        status, _count = _compute_health_status(["session1"], [], [], [], [], [])
        self.assertEqual(status, "CRITICAL")

    def test_degraded_when_failed_ci(self) -> None:
        status, _count = _compute_health_status([], [], ["ci1"], [], [], [])
        self.assertEqual(status, "DEGRADED")

    def test_watch_when_idle_prs(self) -> None:
        status, _count = _compute_health_status([], [], [], ["pr1"], [], [])
        self.assertEqual(status, "WATCH")

    def test_sweep_stale_contributes_watch(self) -> None:
        status, count = _compute_health_status(
            [], [], [], [], [], [],
            sweep_status="CLEAN", sweep_stale=True,
        )
        self.assertEqual(status, "WATCH")
        self.assertEqual(count, 1)

    def test_sweep_incident_contributes_critical(self) -> None:
        status, _count = _compute_health_status(
            [], [], [], [], [], [],
            sweep_status="INCIDENT", sweep_stale=False,
        )
        self.assertEqual(status, "CRITICAL")


class HealthStreamRouteTests(TestCase):
    def setUp(self) -> None:
        self.url = reverse("dashboard:live-health-stream")
        self.user = User.objects.create_user(username="beacontest", password="x")

    def test_login_required(self) -> None:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_authenticated_returns_streaming_response(self) -> None:
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertTrue(response.streaming)
