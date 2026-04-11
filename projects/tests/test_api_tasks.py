from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from projects.tests.helpers import (
    authenticated_client,
    days_from_today,
    make_project,
    make_section,
    make_task,
    task_model,
)


@override_settings(ROOT_URLCONF="projects.urls", PROJECTS_MAX_TASKS_PER_PROJECT=0)
class TaskAPITests(TestCase):
    def setUp(self) -> None:
        self.user, self.client = authenticated_client()

    def test_task_endpoints_require_authentication(self) -> None:
        project = make_project("Roadmap")
        task = make_task(project, name="Task")

        self.assertEqual(APIClient().get("/api/tasks/").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(APIClient().get(f"/api/tasks/{task.id}/").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            APIClient().post(f"/api/tasks/{task.id}/complete/", {}, format="json").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            APIClient().post(f"/api/tasks/{task.id}/reopen/", {}, format="json").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            APIClient().post(f"/api/tasks/{task.id}/move/", {"project_slug": project.slug}, format="json").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_create_task_without_section(self) -> None:
        project = make_project("Roadmap")

        response = self.client.post(
            "/api/tasks/",
            {
                "project_slug": project.slug,
                "name": "Write tests",
                "description": "API coverage",
                "priority": "high",
                "status": "todo",
                "assignee": "mara",
                "tags": ["api", "backend"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["name"], "Write tests")
        self.assertIsNone(response.json()["section"])

    def test_task_detail_includes_comments(self) -> None:
        project = make_project("Roadmap")
        task = make_task(project, name="Write tests")
        task.comments.create(text="First note", author="kevin")

        response = self.client.get(f"/api/tasks/{task.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["comments"][0]["author"], "kevin")

    def test_update_task(self) -> None:
        project = make_project("Roadmap")
        section = make_section(project, name="Backlog")
        task = make_task(project, name="Write tests")

        response = self.client.put(
            f"/api/tasks/{task.id}/",
            {
                "project_slug": project.slug,
                "section_id": section.id,
                "name": "Write more tests",
                "description": "Expanded",
                "priority": "urgent",
                "status": "in_progress",
                "due_date": str(days_from_today(2)),
                "assignee": "kevin",
                "order": 4,
                "tags": ["api"],
            },
            format="json",
        )

        task.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(task.name, "Write more tests")
        self.assertEqual(task.section_id, section.id)
        self.assertEqual(task.priority, "urgent")
        self.assertEqual(task.status, "in_progress")
        self.assertEqual(task.assignee, "kevin")

    def test_delete_task_hard_deletes(self) -> None:
        Task = task_model()
        project = make_project("Roadmap")
        task = make_task(project, name="Delete me")

        response = self.client.delete(f"/api/tasks/{task.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Task.objects.filter(id=task.id).exists())

    def test_complete_task_is_idempotent(self) -> None:
        project = make_project("Roadmap")
        task = make_task(project, name="Complete me")

        first = self.client.post(f"/api/tasks/{task.id}/complete/", {}, format="json")
        completed_at = first.json()["completed_at"]
        second = self.client.post(f"/api/tasks/{task.id}/complete/", {}, format="json")

        task.refresh_from_db()

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertTrue(task.completed)
        self.assertEqual(task.status, "done")
        self.assertEqual(second.json()["completed_at"], completed_at)

    def test_reopen_task_is_idempotent(self) -> None:
        project = make_project("Roadmap")
        task = make_task(project, name="Reopen me", status="done")

        first = self.client.post(f"/api/tasks/{task.id}/reopen/", {}, format="json")
        second = self.client.post(f"/api/tasks/{task.id}/reopen/", {}, format="json")

        task.refresh_from_db()

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertFalse(task.completed)
        self.assertEqual(task.status, "todo")

    def test_complete_missing_task_returns_404(self) -> None:
        response = self.client.post("/api/tasks/9999999/complete/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_reopen_missing_task_returns_404(self) -> None:
        response = self.client.post("/api/tasks/9999999/reopen/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_move_missing_task_returns_404(self) -> None:
        response = self.client.post(
            "/api/tasks/9999999/move/", {"section_id": 1}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_move_task_to_different_section_in_same_project(self) -> None:
        project = make_project("Roadmap")
        backlog = make_section(project, name="Backlog")
        progress = make_section(project, name="In Progress", order=1)
        task = make_task(project, name="Move me", section=backlog)

        response = self.client.post(
            f"/api/tasks/{task.id}/move/",
            {"section_id": progress.id},
            format="json",
        )

        task.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(task.project_id, project.id)
        self.assertEqual(task.section_id, progress.id)

    def test_move_task_to_different_project_clears_old_section(self) -> None:
        source_project = make_project("Source")
        target_project = make_project("Target")
        backlog = make_section(source_project, name="Backlog")
        task = make_task(source_project, name="Move me", section=backlog)

        response = self.client.post(
            f"/api/tasks/{task.id}/move/",
            {"project_slug": target_project.slug},
            format="json",
        )

        task.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(task.project_id, target_project.id)
        self.assertIsNone(task.section)

    def test_move_task_to_different_project_accepts_matching_section(self) -> None:
        source_project = make_project("Source")
        target_project = make_project("Target")
        old_section = make_section(source_project, name="Backlog")
        new_section = make_section(target_project, name="Ready")
        task = make_task(source_project, name="Move me", section=old_section)

        response = self.client.post(
            f"/api/tasks/{task.id}/move/",
            {"project_slug": target_project.slug, "section_id": new_section.id},
            format="json",
        )

        task.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(task.project_id, target_project.id)
        self.assertEqual(task.section_id, new_section.id)

    def test_filter_tasks_by_project(self) -> None:
        visible = make_project("Visible")
        hidden = make_project("Hidden")
        visible_task = make_task(visible, name="Visible task")
        make_task(hidden, name="Hidden task")

        response = self.client.get(f"/api/tasks/?project={visible.slug}")

        self.assertEqual([item["id"] for item in response.json()], [visible_task.id])

    def test_filter_tasks_by_section(self) -> None:
        project = make_project("Roadmap")
        visible_section = make_section(project, name="Visible")
        hidden_section = make_section(project, name="Hidden", order=1)
        visible_task = make_task(project, name="Visible task", section=visible_section)
        make_task(project, name="Hidden task", section=hidden_section)

        response = self.client.get(f"/api/tasks/?section={visible_section.id}")

        self.assertEqual([item["id"] for item in response.json()], [visible_task.id])

    def test_filter_tasks_by_status(self) -> None:
        project = make_project("Roadmap")
        visible_task = make_task(project, name="Visible task", status="blocked")
        make_task(project, name="Hidden task", status="todo")

        response = self.client.get("/api/tasks/?status=blocked")

        self.assertEqual([item["id"] for item in response.json()], [visible_task.id])

    def test_filter_tasks_by_priority(self) -> None:
        project = make_project("Roadmap")
        visible_task = make_task(project, name="Visible task", priority="urgent")
        make_task(project, name="Hidden task", priority="low")

        response = self.client.get("/api/tasks/?priority=urgent")

        self.assertEqual([item["id"] for item in response.json()], [visible_task.id])

    def test_filter_tasks_by_assignee(self) -> None:
        project = make_project("Roadmap")
        visible_task = make_task(project, name="Visible task", assignee="mara")
        make_task(project, name="Hidden task", assignee="kevin")

        response = self.client.get("/api/tasks/?assignee=mara")

        self.assertEqual([item["id"] for item in response.json()], [visible_task.id])

    def test_filter_tasks_by_completed_flag(self) -> None:
        project = make_project("Roadmap")
        visible_task = make_task(project, name="Visible task", status="done")
        make_task(project, name="Hidden task", status="todo")

        response = self.client.get("/api/tasks/?completed=true")

        self.assertEqual([item["id"] for item in response.json()], [visible_task.id])

    def test_filter_tasks_by_due_before(self) -> None:
        project = make_project("Roadmap")
        visible_task = make_task(project, name="Visible task", due_date=days_from_today(1))
        make_task(project, name="Hidden task", due_date=days_from_today(5))

        response = self.client.get(f"/api/tasks/?due_before={days_from_today(2)}")

        self.assertEqual([item["id"] for item in response.json()], [visible_task.id])

    def test_filter_tasks_by_due_after(self) -> None:
        project = make_project("Roadmap")
        visible_task = make_task(project, name="Visible task", due_date=days_from_today(5))
        make_task(project, name="Hidden task", due_date=days_from_today(1))

        response = self.client.get(f"/api/tasks/?due_after={days_from_today(2)}")

        self.assertEqual([item["id"] for item in response.json()], [visible_task.id])

    def test_filter_tasks_by_overdue(self) -> None:
        project = make_project("Roadmap")
        visible_task = make_task(project, name="Visible task", due_date=days_from_today(-1))
        make_task(project, name="Done task", due_date=days_from_today(-1), status="done")
        make_task(project, name="Future task", due_date=days_from_today(1))

        response = self.client.get("/api/tasks/?overdue=true")

        self.assertEqual([item["id"] for item in response.json()], [visible_task.id])

    def test_filter_tasks_by_tag(self) -> None:
        project = make_project("Roadmap")
        visible_task = make_task(project, name="Visible task", tags=["backend", "api"])
        make_task(project, name="Hidden task", tags=["frontend"])

        response = self.client.get("/api/tasks/?tag=api")

        self.assertEqual([item["id"] for item in response.json()], [visible_task.id])

    def test_filter_tasks_by_search(self) -> None:
        project = make_project("Roadmap")
        visible_task = make_task(project, name="Write docs", description="REST API outline")
        make_task(project, name="Build UI", description="Dashboard cards")

        response = self.client.get("/api/tasks/?search=rest")

        self.assertEqual([item["id"] for item in response.json()], [visible_task.id])

    def test_order_tasks_by_priority(self) -> None:
        project = make_project("Roadmap")
        urgent = make_task(project, name="Urgent task", priority="urgent")
        high = make_task(project, name="High task", priority="high")
        medium = make_task(project, name="Medium task", priority="medium")

        response = self.client.get("/api/tasks/?ordering=priority")

        self.assertEqual([item["id"] for item in response.json()], [medium.id, high.id, urgent.id])

    def test_order_tasks_by_priority_descending(self) -> None:
        project = make_project("Roadmap")
        urgent = make_task(project, name="Urgent task", priority="urgent")
        high = make_task(project, name="High task", priority="high")
        medium = make_task(project, name="Medium task", priority="medium")

        response = self.client.get("/api/tasks/?ordering=-priority")

        self.assertEqual([item["id"] for item in response.json()], [urgent.id, high.id, medium.id])

    def test_order_tasks_by_due_date(self) -> None:
        project = make_project("Roadmap")
        first = make_task(project, name="First", due_date=days_from_today(1))
        second = make_task(project, name="Second", due_date=days_from_today(2))

        response = self.client.get("/api/tasks/?ordering=due_date")

        self.assertEqual([item["id"] for item in response.json()], [first.id, second.id])

    def test_order_tasks_by_created_at_descending(self) -> None:
        project = make_project("Roadmap")
        first = make_task(project, name="First")
        second = make_task(project, name="Second")

        response = self.client.get("/api/tasks/?ordering=-created_at")

        self.assertEqual([item["id"] for item in response.json()], [second.id, first.id])

    @override_settings(PROJECTS_MAX_TASKS_PER_PROJECT=1)
    def test_task_create_respects_project_task_limit(self) -> None:
        project = make_project("Roadmap")
        make_task(project, name="Existing task")

        response = self.client.post(
            "/api/tasks/",
            {"project_slug": project.slug, "name": "Blocked task"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("project_slug", response.json())
