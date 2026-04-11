from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from projects.models import Project, Task


class Command(BaseCommand):
    help = "Print a cross-project task summary."

    def handle(self, *args, **options) -> None:
        today = timezone.localdate()
        total = Task.objects.count()
        incomplete = Task.objects.filter(completed=False).count()
        overdue = Task.objects.filter(completed=False, due_date__lt=today, due_date__isnull=False).count()
        projects = (
            Project.objects.filter(is_archived=False)
            .annotate(
                incomplete=Count("tasks", filter=Q(tasks__completed=False), distinct=True),
                overdue=Count(
                    "tasks",
                    filter=Q(tasks__completed=False, tasks__due_date__lt=today, tasks__due_date__isnull=False),
                    distinct=True,
                ),
            )
            .order_by("name", "id")
        )

        self.stdout.write(f"Total tasks: {total}")
        self.stdout.write(f"Incomplete tasks: {incomplete}")
        self.stdout.write(f"Overdue tasks: {overdue}")
        self.stdout.write("")
        self.stdout.write("Projects:")
        for project in projects:
            self.stdout.write(
                f"{project.name}: incomplete={project.incomplete} overdue={project.overdue}"
            )
