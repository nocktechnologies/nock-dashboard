from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from projects.tests.helpers import authenticated_client, make_project, make_section, make_task


@override_settings(ROOT_URLCONF="projects.urls")
class ProjectAPITests(TestCase):
    def setUp(self) -> None:
        self.user, self.client = authenticated_client()

    def test_project_list_requires_authentication(self) -> None:
        response = APIClient().get("/api/projects/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_project_list_returns_only_active_non_archived_projects(self) -> None:
        visible = make_project("Visible Project")
        hidden_archived = make_project("Archived Project", is_archived=True)
        hidden_inactive = make_project("Inactive Project", is_active=False)
        make_task(visible, name="Open task")
        make_task(visible, name="Done task", status="done")
        make_task(visible, name="Overdue task", due_date="2026-04-09")
        make_section(visible, name="Backlog")
        make_section(visible, name="In Progress", order=1)
        make_task(hidden_archived, name="Hidden archived task")
        make_task(hidden_inactive, name="Hidden inactive task")

        response = self.client.get("/api/projects/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 1)
        project = response.json()[0]
        self.assertEqual(project["slug"], visible.slug)
        self.assertEqual(project["task_count"], 3)
        self.assertEqual(project["incomplete_count"], 2)
        self.assertEqual(project["overdue_count"], 1)
        self.assertEqual(len(project["sections"]), 2)

    def test_project_list_includes_empty_project(self) -> None:
        empty = make_project("Empty Project")

        response = self.client.get("/api/projects/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()[0]["slug"], empty.slug)
        self.assertEqual(response.json()[0]["task_count"], 0)

    def test_create_project(self) -> None:
        response = self.client.post(
            "/api/projects/",
            {"name": "NockCC Development Roadmap", "description": "Roadmap", "color": "purple"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["slug"], "nockcc-development-roadmap")
        self.assertEqual(response.json()["color"], "purple")

    def test_project_detail_includes_sections_and_task_counts(self) -> None:
        project = make_project("Roadmap")
        backlog = make_section(project, name="Backlog", order=0)
        progress = make_section(project, name="In Progress", order=1)
        make_task(project, name="Task A", section=backlog)
        make_task(project, name="Task B", section=progress, status="done")

        response = self.client.get(f"/api/projects/{project.slug}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["slug"], project.slug)
        self.assertEqual(payload["task_count"], 2)
        self.assertEqual(payload["incomplete_count"], 1)
        self.assertEqual(payload["sections"][0]["task_count"], 1)
        self.assertEqual(payload["sections"][1]["task_count"], 1)

    def test_update_project(self) -> None:
        project = make_project("Roadmap")

        response = self.client.put(
            f"/api/projects/{project.slug}/",
            {
                "name": "Roadmap Updated",
                "slug": project.slug,
                "description": "Updated",
                "color": "green",
                "is_active": True,
            },
            format="json",
        )

        project.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(project.name, "Roadmap Updated")
        self.assertEqual(project.color, "green")

    def test_delete_project_archives_instead_of_hard_deleting(self) -> None:
        project = make_project("Roadmap")
        task = make_task(project, name="Keep me")

        response = self.client.delete(f"/api/projects/{project.slug}/")

        project.refresh_from_db()
        task.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(project.is_archived)
        self.assertFalse(project.is_active)
        self.assertEqual(task.project_id, project.id)
