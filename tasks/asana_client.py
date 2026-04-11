import logging
import os
import time
from typing import Any

import requests


class AsanaClientError(Exception):
    """Raised when the Asana API returns an error or a request fails."""


logger = logging.getLogger(__name__)

ASANA_BASE_URL = "https://app.asana.com/api/1.0"
_TASK_OPT_FIELDS = (
    "name,assignee.name,due_on,completed,completed_at,notes,"
    "memberships.section.name,memberships.section.gid,"
    "permalink_url,custom_fields,modified_at"
)


def _get_pat() -> str:
    pat = os.environ.get("ASANA_PAT", "")
    if not pat:
        raise ValueError("ASANA_PAT environment variable is not set")
    return pat


def _headers(content_type: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {_get_pat()}"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _get(url: str, params: dict | None = None, retries: int = 3) -> dict[str, Any]:
    """GET with retry on 429."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=_headers(), params=params, timeout=10)
        except requests.RequestException as exc:
            logger.warning("Asana request failed (attempt %d): %s", attempt + 1, exc)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            continue

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
            logger.warning("Asana rate limit hit, sleeping %ds", retry_after)
            time.sleep(retry_after)
            continue

        resp.raise_for_status()
        return resp.json()

    raise AsanaClientError(f"Asana GET {url} failed after {retries} attempts")


def _request_with_retry(
    method: str,
    url: str,
    *,
    json_body: dict | None = None,
    retries: int = 3,
) -> dict[str, Any] | None:
    """POST/PUT/DELETE with retry on 429 and transient errors.

    Returns the parsed JSON response, or None for DELETE (204 No Content).
    Raises AsanaClientError on non-retryable failures.
    """
    for attempt in range(retries):
        try:
            resp = requests.request(
                method,
                url,
                headers=_headers(content_type="application/json"),
                json=json_body,
                timeout=10,
            )
        except requests.RequestException as exc:
            logger.warning(
                "Asana %s %s failed (attempt %d): %s",
                method, url, attempt + 1, exc,
            )
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise AsanaClientError(
                f"Asana {method} {url} failed after {retries} attempts: {exc}"
            ) from exc

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
            logger.warning("Asana rate limit hit, sleeping %ds", retry_after)
            time.sleep(retry_after)
            continue

        if not resp.ok:
            # Surface Asana's error envelope when possible so callers can show
            # meaningful messages (e.g. "name is required").
            try:
                detail = resp.json().get("errors", [{}])[0].get("message", resp.text)
            except (ValueError, KeyError, IndexError):
                detail = resp.text
            raise AsanaClientError(
                f"Asana {method} {url} returned {resp.status_code}: {detail}"
            )

        # DELETE returns an empty body with {"data": {}} — still valid JSON
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    raise AsanaClientError(f"Asana {method} {url} failed after {retries} attempts")


def _parse_priority(custom_fields: list[dict]) -> str | None:
    for field in custom_fields:
        if field.get("name") == "Priority" and field.get("enum_value"):
            return field["enum_value"].get("name", "").lower() or None
    return None


def get_project_tasks(project_gid: str) -> list[dict[str, Any]]:
    """Fetch all incomplete tasks for a project."""
    url = f"{ASANA_BASE_URL}/projects/{project_gid}/tasks"
    params = {
        "opt_fields": _TASK_OPT_FIELDS,
        "limit": 100,
    }
    tasks: list[dict] = []
    while True:
        data = _get(url, params)
        tasks.extend(data.get("data", []))
        next_page = data.get("next_page")
        if not next_page:
            break
        params["offset"] = next_page["offset"]
    return tasks


def get_task_detail(task_gid: str) -> dict[str, Any]:
    """Fetch a single task with full fields."""
    url = f"{ASANA_BASE_URL}/tasks/{task_gid}"
    params = {"opt_fields": _TASK_OPT_FIELDS}
    data = _get(url, params)
    return data.get("data", {})


def get_task_stories(task_gid: str) -> list[dict[str, Any]]:
    """Fetch comment stories for a task (type=comment only)."""
    url = f"{ASANA_BASE_URL}/tasks/{task_gid}/stories"
    params = {"opt_fields": "type,text,created_by.name,created_at", "limit": 10}
    data = _get(url, params)
    return [s for s in data.get("data", []) if s.get("type") == "comment"]


def get_task_stories_paginated(task_gid: str) -> list[dict[str, Any]]:
    """Fetch ALL comment stories for a task, handling pagination.

    The standard get_task_stories() only returns the first page (limit=10).
    This version paginates through all pages and returns every comment story.
    """
    url = f"{ASANA_BASE_URL}/tasks/{task_gid}/stories"
    params: dict[str, Any] = {
        "opt_fields": "gid,type,text,created_by.name,created_at",
        "limit": 100,
    }
    stories: list[dict[str, Any]] = []
    while True:
        data = _get(url, params)
        batch = [s for s in data.get("data", []) if s.get("type") == "comment"]
        stories.extend(batch)
        next_page = data.get("next_page")
        if not next_page:
            break
        params["offset"] = next_page["offset"]
    return stories


def parse_task(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize raw Asana API task dict into our field schema."""
    memberships = raw.get("memberships") or []
    section_name = ""
    if memberships:
        section = memberships[0].get("section") or {}
        section_name = section.get("name", "")

    assignee = raw.get("assignee") or {}
    notes = raw.get("notes", "") or ""

    return {
        "asana_gid": raw["gid"],
        "name": raw.get("name", "")[:500],
        "section_name": section_name[:255],
        "assignee_name": (assignee.get("name") or "")[:255],
        "due_on": raw.get("due_on") or None,
        "completed": raw.get("completed", False),
        "completed_at": raw.get("completed_at") or None,
        "priority": _parse_priority(raw.get("custom_fields") or []),
        "notes_preview": notes[:200],
        "permalink_url": raw.get("permalink_url", "")[:500],
        "asana_updated_at": raw.get("modified_at") or None,
    }


# ---------------------------------------------------------------------------
# Write operations — used by the /api/tasks/* write-back endpoints.
#
# All writes follow the "Asana-first" rule: callers should only update the
# local AsanaTask cache AFTER the Asana API call returns a successful response.
# If any of these functions raise AsanaClientError, the local DB must NOT be
# touched so the cache stays in sync with Asana (the source of truth).
# ---------------------------------------------------------------------------

# Fields that Asana accepts on create/update. Any other keys in kwargs are
# silently dropped by the filter below so callers can pass priority or other
# local-only fields without them leaking into the Asana payload.
_ASANA_WRITE_FIELDS = frozenset({"name", "notes", "due_on", "completed", "assignee"})


def _task_payload(**kwargs: Any) -> dict[str, Any]:
    """Build a minimal Asana task payload from filtered kwargs."""
    return {k: v for k, v in kwargs.items() if k in _ASANA_WRITE_FIELDS and v is not None}


def create_task(
    project_gid: str,
    name: str,
    *,
    notes: str | None = None,
    due_on: str | None = None,
    assignee: str | None = None,
    section_gid: str | None = None,
) -> dict[str, Any]:
    """Create a task in Asana. Returns the created task data dict.

    If ``section_gid`` is provided, a second API call moves the task into that
    section (Asana's create endpoint can't accept a section directly).
    """
    if not name:
        raise AsanaClientError("Task name is required")
    payload: dict[str, Any] = {
        "data": {
            "name": name,
            "projects": [project_gid],
            **_task_payload(notes=notes, due_on=due_on, assignee=assignee),
        }
    }
    url = f"{ASANA_BASE_URL}/tasks?opt_fields={_TASK_OPT_FIELDS}"
    resp = _request_with_retry("POST", url, json_body=payload)
    if resp is None:
        raise AsanaClientError("Asana create_task returned empty response")
    created = resp.get("data", {})
    if not created.get("gid"):
        raise AsanaClientError("Asana create_task missing gid in response")

    if section_gid:
        add_task_to_section(created["gid"], section_gid)
        # Re-fetch so the returned task reflects its new section membership
        created = get_task_detail(created["gid"])
    return created


def update_task(task_gid: str, **kwargs: Any) -> dict[str, Any]:
    """Update a task in Asana. Only name/notes/due_on/completed/assignee honoured.

    ``due_on`` may be passed as None to clear the due date.
    """
    data: dict[str, Any] = {}
    for field in _ASANA_WRITE_FIELDS:
        if field in kwargs:
            data[field] = kwargs[field]
    if not data:
        raise AsanaClientError("update_task called with no updatable fields")

    url = f"{ASANA_BASE_URL}/tasks/{task_gid}?opt_fields={_TASK_OPT_FIELDS}"
    resp = _request_with_retry("PUT", url, json_body={"data": data})
    if resp is None:
        raise AsanaClientError("Asana update_task returned empty response")
    return resp.get("data", {})


def complete_task(task_gid: str) -> dict[str, Any]:
    """Mark a task complete in Asana."""
    return update_task(task_gid, completed=True)


def uncomplete_task(task_gid: str) -> dict[str, Any]:
    """Mark a task incomplete in Asana."""
    return update_task(task_gid, completed=False)


def delete_task(task_gid: str) -> bool:
    """Delete a task in Asana. Returns True on success.

    Raises AsanaClientError if Asana returns a non-success status.
    """
    url = f"{ASANA_BASE_URL}/tasks/{task_gid}"
    _request_with_retry("DELETE", url)
    return True


def add_task_to_section(task_gid: str, section_gid: str) -> dict[str, Any]:
    """Move a task into a section. Asana requires a dedicated endpoint for this."""
    url = f"{ASANA_BASE_URL}/sections/{section_gid}/addTask"
    resp = _request_with_retry("POST", url, json_body={"data": {"task": task_gid}})
    return resp or {}


def add_comment(task_gid: str, text: str) -> dict[str, Any]:
    """Add a comment (story) to an Asana task."""
    if not text or not text.strip():
        raise AsanaClientError("Comment text is required")
    url = f"{ASANA_BASE_URL}/tasks/{task_gid}/stories"
    resp = _request_with_retry("POST", url, json_body={"data": {"text": text}})
    if resp is None:
        raise AsanaClientError("Asana add_comment returned empty response")
    return resp.get("data", {})


def get_sections(project_gid: str) -> list[dict[str, Any]]:
    """Fetch all sections for a project."""
    url = f"{ASANA_BASE_URL}/projects/{project_gid}/sections"
    params = {"opt_fields": "name", "limit": 100}
    sections: list[dict[str, Any]] = []
    while True:
        data = _get(url, params)
        sections.extend(data.get("data", []))
        next_page = data.get("next_page")
        if not next_page:
            break
        params["offset"] = next_page["offset"]
    return sections
