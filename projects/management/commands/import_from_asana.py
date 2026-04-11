from __future__ import annotations

import json
from typing import Any
from urllib import error, parse, request

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_date, parse_datetime

from projects.models import Project, Section, Task

ASANA_API_BASE = "https://app.asana.com/api/1.0"


def asana_get(token: str, path: str, params: dict[str, Any] | None = None) -> Any:
    query = parse.urlencode(params or {}, doseq=True)
    url = f"{ASANA_API_BASE}{path}"
    if query:
        url = f"{url}?{query}"

    asana_request = request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )

    try:
        with request.urlopen(asana_request, timeout=30) as response:
            payload = json.load(response)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise CommandError(f"Asana request failed with status {exc.code}: {body}") from exc
    except error.URLError as exc:
        raise CommandError(f"Unable to reach Asana: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise CommandError("Asana returned invalid JSON.") from exc

    if "data" not in payload:
        raise CommandError("Asana response missing top-level 'data'.")

    return payload["data"]


class Command(BaseCommand):
    help = "Import projects, sections, and tasks from Asana."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--token", required=True, help="Asana personal access token.")
        parser.add_argument("--workspace", required=True, help="Asana workspace GID.")
        parser.add_argument("--project", help="Optional Asana project GID to import.")

    def handle(self, *args, **options) -> None:
        token = options["token"]
        workspace_gid = options["workspace"]
        project_gid = options.get("project")

        projects = self.fetch_projects(token, workspace_gid, project_gid)
        imported_projects = 0
        imported_sections = 0
        imported_tasks = 0

        for raw_project in projects:
            with transaction.atomic():
                project = self.upsert_project(raw_project)
                imported_projects += 1

                sections = self.fetch_sections(token, raw_project["gid"])
                section_map: dict[str, Section] = {}
                for index, raw_section in enumerate(sections):
                    section = self.upsert_section(project, raw_section, index)
                    section_map[raw_section["gid"]] = section
                    imported_sections += 1

                tasks = self.fetch_tasks(token, raw_project["gid"])
                for index, raw_task in enumerate(tasks):
                    self.upsert_task(project, raw_task, section_map, index)
                    imported_tasks += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {imported_projects} project(s), {imported_sections} section(s), "
                f"{imported_tasks} task(s)."
            )
        )

    def fetch_projects(self, token: str, workspace_gid: str, project_gid: str | None = None) -> list[dict]:
        if project_gid:
            project = asana_get(token, f"/projects/{project_gid}", {"opt_fields": "gid,name,color"})
            return [project]
        return asana_get(
            token,
            f"/workspaces/{workspace_gid}/projects",
            {"opt_fields": "gid,name,color"},
        )

    def fetch_sections(self, token: str, project_gid: str) -> list[dict]:
        return asana_get(
            token,
            f"/projects/{project_gid}/sections",
            {"opt_fields": "gid,name"},
        )

    def fetch_tasks(self, token: str, project_gid: str) -> list[dict]:
        return asana_get(
            token,
            f"/projects/{project_gid}/tasks",
            {
                "completed_since": "1970-01-01T00:00:00.000Z",
                "opt_fields": ",".join(
                    [
                        "gid",
                        "name",
                        "notes",
                        "due_on",
                        "completed",
                        "completed_at",
                        "assignee.name",
                        "memberships.section.gid",
                        "memberships.section.name",
                    ]
                ),
            },
        )

    def upsert_project(self, raw_project: dict[str, Any]) -> Project:
        project, _created = Project.objects.get_or_create(
            asana_gid=raw_project["gid"],
            defaults={"name": raw_project.get("name", "").strip() or raw_project["gid"]},
        )
        project.name = raw_project.get("name", project.name).strip() or project.name
        project.color = raw_project.get("color") or project.color
        project.is_active = True
        project.is_archived = False
        project.save()
        return project

    def upsert_section(self, project: Project, raw_section: dict[str, Any], order: int) -> Section:
        section, _created = Section.objects.get_or_create(
            asana_gid=raw_section["gid"],
            defaults={"project": project, "name": raw_section.get("name", "").strip() or raw_section["gid"]},
        )
        section.project = project
        section.name = raw_section.get("name", section.name).strip() or section.name
        section.order = order
        section.save()
        return section

    def upsert_task(
        self,
        project: Project,
        raw_task: dict[str, Any],
        section_map: dict[str, Section],
        order: int,
    ) -> Task:
        task, _created = Task.objects.get_or_create(
            asana_gid=raw_task["gid"],
            defaults={"project": project, "name": raw_task.get("name", "").strip() or raw_task["gid"]},
        )

        memberships = raw_task.get("memberships") or []
        section = None
        for membership in memberships:
            raw_section = membership.get("section") or {}
            section_gid = raw_section.get("gid")
            if section_gid and section_gid in section_map:
                section = section_map[section_gid]
                break

        assignee = raw_task.get("assignee") or {}
        completed = bool(raw_task.get("completed"))
        completed_at = parse_datetime(raw_task["completed_at"]) if raw_task.get("completed_at") else None

        task.project = project
        task.section = section
        task.name = raw_task.get("name", task.name).strip() or task.name
        task.description = raw_task.get("notes") or ""
        task.due_date = parse_date(raw_task["due_on"]) if raw_task.get("due_on") else None
        task.assignee = assignee.get("name", "") if isinstance(assignee, dict) else ""
        task.status = Task.STATUS_DONE if completed else Task.STATUS_TODO
        task.order = order
        task.completed_at = completed_at
        task.save()
        return task
