"""
Smoke tests for the PM plugin frontend views (dashboard/views.py::
pm_dashboard and pm_project_detail).

These tests verify URL routing, template rendering, login enforcement,
and the 404 path — they don't exercise the full DOM.
"""
from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from projects.models import Project, Section, Task


class PMDashboardSmokeTests(TestCase):
    """The /pm/ project list page."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="pmdash", password=None, is_staff=True,
        )
        self.client.force_login(self.user)

    def test_pm_dashboard_renders_empty_state(self) -> None:
        response = self.client.get(reverse("dashboard:pm"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No projects yet")

    def test_pm_dashboard_lists_active_projects_with_counts(self) -> None:
        project = Project.objects.create(name="Engineering", color="emerald")
        section = Section.objects.create(project=project, name="Backlog", order=0)
        Task.objects.create(project=project, section=section, name="Task A")
        Task.objects.create(
            project=project, section=section, name="Task B", completed=True,
        )

        response = self.client.get(reverse("dashboard:pm"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Engineering")
        # task_count=2, incomplete_count=1 aggregations surface in the card.
        self.assertContains(response, 'href="/pm/engineering/"')

    def test_pm_dashboard_hides_archived_and_inactive_projects(self) -> None:
        Project.objects.create(name="Archived", is_archived=True)
        Project.objects.create(name="Inactive", is_active=False)
        Project.objects.create(name="Visible")

        response = self.client.get(reverse("dashboard:pm"))
        self.assertContains(response, "Visible")
        self.assertNotContains(response, "href=\"/pm/archived/\"")
        self.assertNotContains(response, "href=\"/pm/inactive/\"")

    def test_pm_dashboard_requires_login(self) -> None:
        self.client.logout()
        response = self.client.get(reverse("dashboard:pm"))
        # @login_required redirects to the login URL.
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)


class PMProjectDetailSmokeTests(TestCase):
    """The /pm/<slug>/ project detail page."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="pmdetail", password=None, is_staff=True,
        )
        self.client.force_login(self.user)
        self.project = Project.objects.create(name="Ops Rollout")

    def test_project_detail_renders(self) -> None:
        response = self.client.get(
            reverse("dashboard:pm-project-detail", kwargs={"slug": self.project.slug}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ops Rollout")
        # The detail page boots an Alpine component — confirm the init call is wired.
        self.assertContains(response, "pmProjectDetail(")

    def test_project_detail_404_on_missing_slug(self) -> None:
        response = self.client.get(
            reverse("dashboard:pm-project-detail", kwargs={"slug": "nope"}),
        )
        self.assertEqual(response.status_code, 404)

    def test_project_detail_404_on_archived_project(self) -> None:
        archived = Project.objects.create(name="Ghost", is_archived=True)
        response = self.client.get(
            reverse("dashboard:pm-project-detail", kwargs={"slug": archived.slug}),
        )
        self.assertEqual(response.status_code, 404)

    def test_project_detail_requires_login(self) -> None:
        self.client.logout()
        response = self.client.get(
            reverse("dashboard:pm-project-detail", kwargs={"slug": self.project.slug}),
        )
        self.assertEqual(response.status_code, 302)

    def test_project_detail_with_tasks_but_no_sections_renders(self) -> None:
        """Regression guard: the template used to call an undefined
        `renderTask()` helper when sections.length === 0 && tasks.length > 0.
        The fix drops that branch and lets the Unassigned bucket handle it;
        this test makes sure the page template never re-introduces the
        undefined reference."""
        Task.objects.create(project=self.project, name="Lonely task")
        response = self.client.get(
            reverse("dashboard:pm-project-detail", kwargs={"slug": self.project.slug}),
        )
        self.assertEqual(response.status_code, 200)
        # The broken helper must NOT appear in the rendered template.
        self.assertNotContains(response, "renderTask")


