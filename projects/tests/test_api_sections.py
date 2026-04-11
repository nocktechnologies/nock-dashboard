from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from projects.tests.helpers import (
    authenticated_client,
    make_project,
    make_section,
    make_task,
    task_model,
)


@override_settings(ROOT_URLCONF="projects.urls")
class SectionAPITests(TestCase):
    def setUp(self) -> None:
        self.user, self.client = authenticated_client()

    def test_section_endpoints_require_authentication(self) -> None:
        project = make_project("Roadmap")
        section = make_section(project)

        self.assertEqual(
            APIClient().get(f"/api/projects/{project.slug}/sections/").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            APIClient().put(f"/api/sections/{section.id}/", {"name": "New", "order": 1}, format="json").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            APIClient().post(f"/api/sections/{section.id}/reorder/", {"order": 1}, format="json").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_list_sections_for_project(self) -> None:
        project = make_project("Roadmap")
        backlog = make_section(project, name="Backlog", order=0)
        progress = make_section(project, name="In Progress", order=1)
        make_task(project, name="Task A", section=backlog)
        make_task(project, name="Task B", section=progress)

        response = self.client.get(f"/api/projects/{project.slug}/sections/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sections = response.json()
        self.assertEqual([section["name"] for section in sections], ["Backlog", "In Progress"])
        self.assertEqual([section["task_count"] for section in sections], [1, 1])

    def test_create_section_for_project(self) -> None:
        project = make_project("Roadmap")

        response = self.client.post(
            f"/api/projects/{project.slug}/sections/",
            {"name": "QA", "order": 2},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["name"], "QA")
        self.assertEqual(response.json()["project"], project.slug)

    def test_update_section(self) -> None:
        project = make_project("Roadmap")
        section = make_section(project, name="QA", order=2)

        response = self.client.put(
            f"/api/sections/{section.id}/",
            {"name": "Ready for QA", "order": 3},
            format="json",
        )

        section.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(section.name, "Ready for QA")
        self.assertEqual(section.order, 3)

    def test_reorder_section(self) -> None:
        project = make_project("Roadmap")
        section = make_section(project, name="QA", order=2)

        response = self.client.post(
            f"/api/sections/{section.id}/reorder/",
            {"order": 5},
            format="json",
        )

        section.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(section.order, 5)

    def test_delete_section_moves_tasks_to_null_section(self) -> None:
        Task = task_model()
        project = make_project("Roadmap")
        section = make_section(project, name="QA", order=2)
        task = make_task(project, name="Task", section=section)

        response = self.client.delete(f"/api/sections/{section.id}/")

        task.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Task.objects.filter(section=section).exists())
        self.assertIsNone(task.section)
