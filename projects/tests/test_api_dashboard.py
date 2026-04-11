from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from projects.tests.helpers import authenticated_client, days_from_today, make_project, make_task


@override_settings(ROOT_URLCONF="projects.urls")
class TaskDashboardAPITests(TestCase):
    def setUp(self) -> None:
        self.user, self.client = authenticated_client()

    def test_dashboard_endpoints_require_authentication(self) -> None:
        unauthenticated = APIClient()

        self.assertEqual(unauthenticated.get("/api/tasks/dashboard/").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(unauthenticated.get("/api/tasks/overdue/").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(unauthenticated.get("/api/tasks/today/").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(unauthenticated.get("/api/tasks/upcoming/").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_dashboard_returns_cross_project_counts(self) -> None:
        alpha = make_project("Alpha")
        beta = make_project("Beta")
        make_task(alpha, name="Overdue", due_date=days_from_today(-1))
        make_task(alpha, name="Done today", status="done")
        make_task(beta, name="High", priority="high")
        make_task(beta, name="Urgent", priority="urgent")

        response = self.client.get("/api/tasks/dashboard/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["total_tasks"], 4)
        self.assertEqual(payload["incomplete_tasks"], 3)
        self.assertEqual(payload["overdue_tasks"], 1)
        self.assertEqual(payload["completed_today"], 1)
        self.assertEqual(payload["by_project"][0]["slug"], alpha.slug)
        self.assertEqual(payload["by_priority"]["urgent"], 1)
        self.assertEqual(payload["by_priority"]["high"], 1)

    def test_overdue_endpoint_returns_only_incomplete_past_due_tasks(self) -> None:
        project = make_project("Roadmap")
        visible = make_task(project, name="Visible", due_date=days_from_today(-1))
        make_task(project, name="Done", due_date=days_from_today(-1), status="done")
        make_task(project, name="Future", due_date=days_from_today(2))
        make_task(project, name="No due date")

        response = self.client.get("/api/tasks/overdue/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.json()], [visible.id])

    def test_today_endpoint_returns_tasks_due_today(self) -> None:
        project = make_project("Roadmap")
        visible = make_task(project, name="Today", due_date=days_from_today(0))
        make_task(project, name="Tomorrow", due_date=days_from_today(1))

        response = self.client.get("/api/tasks/today/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.json()], [visible.id])

    def test_upcoming_endpoint_returns_tasks_due_within_requested_days(self) -> None:
        project = make_project("Roadmap")
        visible = make_task(project, name="Soon", due_date=days_from_today(3))
        make_task(project, name="Later", due_date=days_from_today(10))

        response = self.client.get("/api/tasks/upcoming/?days=7")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.json()], [visible.id])
