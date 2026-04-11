"""Tests for Terminal Bridge — session reports API."""
import json
import os

from django.test import TestCase, override_settings
from django.utils import timezone

from vault.models import SessionReport

_TEST_FERNET_KEYS = [os.environ.get("TEST_FERNET_KEY", "")]
_TEST_API_KEY = "test-nockcc-api-key-12345"

REPORTS_URL = "/api/terminal/reports/"


def _auth_headers() -> dict[str, str]:
    return {"HTTP_X_API_KEY": _TEST_API_KEY}


def _valid_report(**overrides: object) -> dict:
    data: dict = {
        "project_name": "nock-command-center",
        "title": "Session Summary",
        "content": "## Summary\n\nCompleted Phase 8 terminal bridge.",
        "branch": "feature/terminal-bridge",
        "captured_at": timezone.now().isoformat(),
        "machine": "mac",
    }
    data.update(overrides)
    return data


def _make_report(**kwargs: object) -> SessionReport:
    defaults: dict = {
        "project_name": "nock-command-center",
        "title": "Session Summary",
        "content": "## Summary\n\nTest report content.",
        "branch": "main",
        "captured_at": timezone.now(),
        "machine": "mac",
    }
    defaults.update(kwargs)
    return SessionReport.objects.create(**defaults)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY=_TEST_API_KEY)
class ReportCreateTests(TestCase):
    def test_report_create(self) -> None:
        resp = self.client.post(
            REPORTS_URL,
            data=json.dumps(_valid_report()),
            content_type="application/json",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["project_name"], "nock-command-center")
        self.assertEqual(SessionReport.objects.count(), 1)

    def test_report_create_requires_project_name(self) -> None:
        resp = self.client.post(
            REPORTS_URL,
            data=json.dumps(_valid_report(project_name="")),
            content_type="application/json",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("project_name", resp.json()["message"])

    def test_report_create_truncates_large_content(self) -> None:
        large_content = "x" * 60_000
        resp = self.client.post(
            REPORTS_URL,
            data=json.dumps(_valid_report(content=large_content)),
            content_type="application/json",
            **_auth_headers(),
        )
        self.assertEqual(resp.status_code, 201)
        report = SessionReport.objects.first()
        self.assertLessEqual(len(report.content), 50_030)  # 50K + truncation notice
        self.assertIn("[Truncated at 50KB]", report.content)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY=_TEST_API_KEY)
class ReportListTests(TestCase):
    def test_report_list(self) -> None:
        for i in range(3):
            _make_report(title=f"Report {i}")
        resp = self.client.get(REPORTS_URL, **_auth_headers())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["data"]["total"], 3)
        self.assertEqual(len(body["data"]["reports"]), 3)

    def test_report_filter_by_project(self) -> None:
        _make_report(project_name="project-alpha")
        _make_report(project_name="project-alpha")
        _make_report(project_name="project-beta")
        resp = self.client.get(
            REPORTS_URL + "?project=alpha", **_auth_headers()
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["total"], 2)


@override_settings(FERNET_KEYS=_TEST_FERNET_KEYS, NOCKCC_API_KEY=_TEST_API_KEY)
class ReportDetailTests(TestCase):
    def test_report_detail(self) -> None:
        report = _make_report(content="Full markdown content here.")
        resp = self.client.get(
            f"{REPORTS_URL}{report.pk}/", **_auth_headers()
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["data"]["content"], "Full markdown content here.")
        self.assertEqual(body["data"]["project_name"], "nock-command-center")

    def test_report_detail_404(self) -> None:
        resp = self.client.get(
            f"{REPORTS_URL}9999/", **_auth_headers()
        )
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(resp.json()["success"])
