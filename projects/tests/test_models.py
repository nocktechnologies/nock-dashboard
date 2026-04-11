from datetime import timedelta

from django.apps import apps
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone


class ProjectModelTests(TestCase):
    def test_project_slug_is_generated_from_name(self) -> None:
        project = apps.get_model("projects", "Project").objects.create(name="NockCC Development Roadmap")

        self.assertEqual(project.slug, "nockcc-development-roadmap")

    def test_project_archive_flags_can_hide_project(self) -> None:
        project = apps.get_model("projects", "Project").objects.create(name="Archive Me")
        project.is_archived = True
        project.is_active = False
        project.save()

        project.refresh_from_db()

        self.assertTrue(project.is_archived)
        self.assertFalse(project.is_active)


class SectionModelTests(TestCase):
    def test_section_name_is_unique_within_project(self) -> None:
        Project = apps.get_model("projects", "Project")
        Section = apps.get_model("projects", "Section")
        project = Project.objects.create(name="Platform")
        Section.objects.create(project=project, name="Backlog", order=1)

        with self.assertRaises(IntegrityError):
            Section.objects.create(project=project, name="Backlog", order=2)

    def test_section_ordering_uses_project_then_order(self) -> None:
        Project = apps.get_model("projects", "Project")
        Section = apps.get_model("projects", "Section")
        alpha = Project.objects.create(name="Alpha")
        beta = Project.objects.create(name="Beta")
        alpha_done = Section.objects.create(project=alpha, name="Done", order=2)
        alpha_backlog = Section.objects.create(project=alpha, name="Backlog", order=1)
        beta_backlog = Section.objects.create(project=beta, name="Backlog", order=1)

        sections = list(Section.objects.all())

        self.assertEqual(sections, [alpha_backlog, alpha_done, beta_backlog])


class TaskModelTests(TestCase):
    def test_task_marked_done_sets_completion_fields(self) -> None:
        Project = apps.get_model("projects", "Project")
        Task = apps.get_model("projects", "Task")
        project = Project.objects.create(name="Ops")
        task = Task.objects.create(project=project, name="Ship build", status="done")

        self.assertTrue(task.completed)
        self.assertIsNotNone(task.completed_at)

    def test_task_leaving_done_clears_completion_fields(self) -> None:
        Project = apps.get_model("projects", "Project")
        Task = apps.get_model("projects", "Task")
        project = Project.objects.create(name="Ops")
        task = Task.objects.create(project=project, name="Ship build", status="done")

        task.status = "todo"
        task.save()
        task.refresh_from_db()

        self.assertFalse(task.completed)
        self.assertIsNone(task.completed_at)

    def test_completed_flag_updates_when_task_is_reopened(self) -> None:
        Project = apps.get_model("projects", "Project")
        Task = apps.get_model("projects", "Task")
        project = Project.objects.create(name="Ops")
        task = Task.objects.create(project=project, name="Fix bug", completed=True, status="todo")

        task.refresh_from_db()

        self.assertFalse(task.completed)
        self.assertIsNone(task.completed_at)

    def test_task_without_due_date_is_not_overdue(self) -> None:
        Project = apps.get_model("projects", "Project")
        Task = apps.get_model("projects", "Task")
        project = Project.objects.create(name="Ops")
        task = Task.objects.create(project=project, name="Someday task")

        self.assertFalse(task.is_overdue)

    def test_task_past_due_and_incomplete_is_overdue(self) -> None:
        Project = apps.get_model("projects", "Project")
        Task = apps.get_model("projects", "Task")
        project = Project.objects.create(name="Ops")
        task = Task.objects.create(
            project=project,
            name="Past due task",
            due_date=timezone.localdate() - timedelta(days=1),
        )

        self.assertTrue(task.is_overdue)


class TaskCommentModelTests(TestCase):
    def test_comment_ordering_is_newest_first(self) -> None:
        Project = apps.get_model("projects", "Project")
        Task = apps.get_model("projects", "Task")
        TaskComment = apps.get_model("projects", "TaskComment")
        project = Project.objects.create(name="Ops")
        task = Task.objects.create(project=project, name="Review copy")
        older_comment = TaskComment.objects.create(task=task, text="First", author="mara")
        newer_comment = TaskComment.objects.create(task=task, text="Second", author="kevin")

        comments = list(TaskComment.objects.all())

        self.assertEqual(comments, [newer_comment, older_comment])
