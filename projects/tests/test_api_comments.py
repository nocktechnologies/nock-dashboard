from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from projects.tests.helpers import (
    authenticated_client,
    make_comment,
    make_project,
    make_task,
    task_comment_model,
)


@override_settings(ROOT_URLCONF="projects.urls")
class TaskCommentAPITests(TestCase):
    def setUp(self) -> None:
        self.user, self.client = authenticated_client()

    def test_comment_endpoints_require_authentication(self) -> None:
        project = make_project("Roadmap")
        task = make_task(project, name="Task")
        comment = make_comment(task, text="Comment")

        self.assertEqual(
            APIClient().get(f"/api/tasks/{task.id}/comments/").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            APIClient().delete(f"/api/comments/{comment.id}/").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_list_comments_for_task(self) -> None:
        project = make_project("Roadmap")
        task = make_task(project, name="Task")
        first = make_comment(task, text="First", author="mara")
        second = make_comment(task, text="Second", author="kevin")

        response = self.client.get(f"/api/tasks/{task.id}/comments/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.json()], [second.id, first.id])

    def test_create_comment(self) -> None:
        project = make_project("Roadmap")
        task = make_task(project, name="Task")

        response = self.client.post(
            f"/api/tasks/{task.id}/comments/",
            {"text": "Needs follow-up", "author": "kevin"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["author"], "kevin")

    def test_delete_comment(self) -> None:
        TaskComment = task_comment_model()
        project = make_project("Roadmap")
        task = make_task(project, name="Task")
        comment = make_comment(task, text="Needs follow-up", author="kevin")

        response = self.client.delete(f"/api/comments/{comment.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(TaskComment.objects.filter(id=comment.id).exists())
