from django.test import TestCase

from projects.filters import apply_task_filters, upcoming_tasks_queryset
from projects.tests.helpers import days_from_today, make_project, make_task, task_model


class TaskFilterTests(TestCase):
    def test_overdue_filter_excludes_completed_tasks(self) -> None:
        Task = task_model()
        project = make_project("Roadmap")
        visible = make_task(project, name="Visible", due_date=days_from_today(-1))
        make_task(project, name="Done", due_date=days_from_today(-1), status=Task.STATUS_DONE)
        queryset = apply_task_filters(Task.objects.all(), {"overdue": "true"})

        self.assertEqual(list(queryset), [visible])

    def test_tag_filter_matches_json_list_values(self) -> None:
        Task = task_model()
        project = make_project("Roadmap")
        visible = make_task(project, name="Visible", tags=["api", "backend"])
        make_task(project, name="Other", tags=["frontend"])
        queryset = apply_task_filters(Task.objects.all(), {"tag": "api"})

        self.assertEqual(list(queryset), [visible])

    def test_priority_ordering_uses_business_rank(self) -> None:
        Task = task_model()
        project = make_project("Roadmap")
        urgent = make_task(project, name="Urgent", priority=Task.PRIORITY_URGENT)
        high = make_task(project, name="High", priority=Task.PRIORITY_HIGH)
        low = make_task(project, name="Low", priority=Task.PRIORITY_LOW)
        queryset = apply_task_filters(Task.objects.all(), {"ordering": "-priority"})

        self.assertEqual(list(queryset), [urgent, high, low])

    def test_upcoming_tasks_queryset_limits_to_requested_window(self) -> None:
        Task = task_model()
        project = make_project("Roadmap")
        visible = make_task(project, name="Soon", due_date=days_from_today(3))
        make_task(project, name="Later", due_date=days_from_today(10))
        queryset = upcoming_tasks_queryset(Task.objects.all(), 7)

        self.assertEqual(list(queryset), [visible])
