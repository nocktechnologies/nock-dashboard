from datetime import timedelta
from uuid import uuid4

from django.apps import apps
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient


def authenticated_client(username: str | None = None) -> tuple[User, APIClient]:
    """Return an authenticated APIClient with a fresh test user.

    Tests use force_authenticate() to sign the user in without a password
    check, so we pass password=None (Django calls set_unusable_password()
    internally). No literal secrets in the tree and no Ruff S106 warnings.
    When username is not provided, generate a unique value per call so
    multiple helpers in the same test scope don't collide on the username
    unique constraint.
    """
    effective_username = username or f"tester_{uuid4().hex[:8]}"
    user = User.objects.create_user(username=effective_username, password=None)
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


def project_model():
    return apps.get_model("projects", "Project")


def section_model():
    return apps.get_model("projects", "Section")


def task_model():
    return apps.get_model("projects", "Task")


def task_comment_model():
    return apps.get_model("projects", "TaskComment")


def make_project(name: str = "Project", **kwargs):
    defaults = {
        "color": "blue",
    }
    defaults.update(kwargs)
    return project_model().objects.create(name=name, **defaults)


def make_section(project, name: str = "Backlog", **kwargs):
    defaults = {
        "order": 0,
    }
    defaults.update(kwargs)
    return section_model().objects.create(project=project, name=name, **defaults)


def make_task(project, name: str = "Task", **kwargs):
    task = task_model()
    defaults = {
        "priority": task.PRIORITY_MEDIUM,
        "status": task.STATUS_TODO,
        "assignee": "",
        "tags": [],
    }
    defaults.update(kwargs)
    return task.objects.create(project=project, name=name, **defaults)


def make_comment(task, text: str = "Comment", **kwargs):
    defaults = {
        "author": "system",
    }
    defaults.update(kwargs)
    return task_comment_model().objects.create(task=task, text=text, **defaults)


def today() -> timezone.datetime.date:
    return timezone.localdate()


def days_from_today(days: int):
    return today() + timedelta(days=days)
