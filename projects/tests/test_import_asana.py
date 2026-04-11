from io import StringIO
from unittest.mock import patch

from django.apps import apps
from django.core.management import call_command
from django.test import TestCase, override_settings


@override_settings(ROOT_URLCONF="projects.urls")
class ImportFromAsanaCommandTests(TestCase):
    def test_import_from_asana_creates_projects_sections_and_tasks(self) -> None:
        Project = apps.get_model("projects", "Project")
        Section = apps.get_model("projects", "Section")
        Task = apps.get_model("projects", "Task")
        stdout = StringIO()
        projects = [{"gid": "proj-1", "name": "NockCC Development", "color": "purple"}]
        sections = [{"gid": "sec-1", "name": "Backlog"}, {"gid": "sec-2", "name": "In Progress"}]
        tasks = [
            {
                "gid": "task-1",
                "name": "Implement API",
                "notes": "Build the endpoints",
                "due_on": "2026-04-12",
                "completed": False,
                "completed_at": None,
                "assignee": {"name": "Mara"},
                "memberships": [{"section": {"gid": "sec-2", "name": "In Progress"}}],
            }
        ]

        with (
            patch("projects.management.commands.import_from_asana.Command.fetch_projects", return_value=projects),
            patch("projects.management.commands.import_from_asana.Command.fetch_sections", return_value=sections),
            patch("projects.management.commands.import_from_asana.Command.fetch_tasks", return_value=tasks),
        ):
            call_command(
                "import_from_asana",
                "--token",
                "token",
                "--workspace",
                "workspace",
                stdout=stdout,
            )

        project = Project.objects.get(asana_gid="proj-1")
        section = Section.objects.get(asana_gid="sec-2")
        task = Task.objects.get(asana_gid="task-1")

        self.assertEqual(project.name, "NockCC Development")
        self.assertEqual(section.project_id, project.id)
        self.assertEqual(task.project_id, project.id)
        self.assertEqual(task.section_id, section.id)
        self.assertEqual(task.description, "Build the endpoints")
        self.assertEqual(task.assignee, "Mara")
        self.assertEqual(task.due_date.isoformat(), "2026-04-12")
        self.assertIn("Imported 1 project(s), 2 section(s), 1 task(s)", stdout.getvalue())

    def test_import_from_asana_is_idempotent_and_updates_existing_records(self) -> None:
        Project = apps.get_model("projects", "Project")
        Section = apps.get_model("projects", "Section")
        Task = apps.get_model("projects", "Task")
        initial_projects = [{"gid": "proj-1", "name": "NockCC Development", "color": "purple"}]
        initial_sections = [{"gid": "sec-1", "name": "Backlog"}]
        initial_tasks = [
            {
                "gid": "task-1",
                "name": "Implement API",
                "notes": "First pass",
                "due_on": "2026-04-12",
                "completed": False,
                "completed_at": None,
                "assignee": {"name": "Mara"},
                "memberships": [{"section": {"gid": "sec-1", "name": "Backlog"}}],
            }
        ]

        updated_tasks = [
            {
                "gid": "task-1",
                "name": "Implement projects API",
                "notes": "Updated description",
                "due_on": "2026-04-15",
                "completed": True,
                "completed_at": "2026-04-10T15:30:00Z",
                "assignee": {"name": "Kevin"},
                "memberships": [{"section": {"gid": "sec-1", "name": "Backlog"}}],
            }
        ]

        with (
            patch("projects.management.commands.import_from_asana.Command.fetch_projects", return_value=initial_projects),
            patch("projects.management.commands.import_from_asana.Command.fetch_sections", return_value=initial_sections),
            patch("projects.management.commands.import_from_asana.Command.fetch_tasks", return_value=initial_tasks),
        ):
            call_command(
                "import_from_asana",
                "--token",
                "token",
                "--workspace",
                "workspace",
                stdout=StringIO(),
            )

        with (
            patch("projects.management.commands.import_from_asana.Command.fetch_projects", return_value=initial_projects),
            patch("projects.management.commands.import_from_asana.Command.fetch_sections", return_value=initial_sections),
            patch("projects.management.commands.import_from_asana.Command.fetch_tasks", return_value=updated_tasks),
        ):
            call_command(
                "import_from_asana",
                "--token",
                "token",
                "--workspace",
                "workspace",
                stdout=StringIO(),
            )

        task = Task.objects.get(asana_gid="task-1")

        self.assertEqual(Project.objects.count(), 1)
        self.assertEqual(Section.objects.count(), 1)
        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(task.name, "Implement projects API")
        self.assertEqual(task.description, "Updated description")
        self.assertEqual(task.assignee, "Kevin")
        self.assertTrue(task.completed)
        self.assertEqual(task.status, "done")

    def test_import_from_asana_can_target_single_project(self) -> None:
        with patch(
            "projects.management.commands.import_from_asana.Command.fetch_projects",
            return_value=[{"gid": "proj-99", "name": "Specific Project", "color": "blue"}],
        ) as fetch_projects, patch(
            "projects.management.commands.import_from_asana.Command.fetch_sections",
            return_value=[],
        ), patch(
            "projects.management.commands.import_from_asana.Command.fetch_tasks",
            return_value=[],
        ):
            call_command(
                "import_from_asana",
                "--token",
                "token",
                "--workspace",
                "workspace",
                "--project",
                "proj-99",
                stdout=StringIO(),
            )

        fetch_projects.assert_called_once_with("token", "workspace", "proj-99")


class TaskStatsCommandTests(TestCase):
    def test_task_stats_prints_cross_project_summary(self) -> None:
        Project = apps.get_model("projects", "Project")
        Task = apps.get_model("projects", "Task")
        project = Project.objects.create(name="Roadmap")
        Task.objects.create(project=project, name="Open task", due_date="2026-04-09")
        Task.objects.create(project=project, name="Done task", status="done")
        stdout = StringIO()

        call_command("task_stats", stdout=stdout)

        output = stdout.getvalue()
        self.assertIn("Total tasks: 2", output)
        self.assertIn("Incomplete tasks: 1", output)
        self.assertIn("Overdue tasks: 1", output)
        self.assertIn("Roadmap: incomplete=1 overdue=1", output)
