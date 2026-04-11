"""HTTP client for NockCC API."""

from __future__ import annotations

from typing import Any

import httpx

from .config import load_config


class NockCCClient:
    """Thin wrapper around httpx for talking to the NockCC REST API."""

    def __init__(self, api_url: str | None = None, api_key: str | None = None) -> None:
        config = load_config()
        self.api_url = (api_url or config.get("api_url", "")).rstrip("/")
        self.api_key = api_key or config.get("api_key", "")

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key, "Content-Type": "application/json"}

    def _url(self, path: str) -> str:
        return f"{self.api_url}{path}"

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = httpx.get(self._url(path), headers=self._headers(), params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    def post(self, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = httpx.post(self._url(path), headers=self._headers(), json=data or {}, timeout=15)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    # --- Session endpoints ---

    def create_session(
        self,
        agent: str,
        machine: str = "mac",
        branch: str = "",
        repo: str = "",
        task: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, str] = {"agent": agent, "machine": machine}
        if branch:
            payload["branch"] = branch
        if repo:
            payload["repository"] = repo
        if task:
            payload["task_description"] = task
        return self.post("/api/sessions/", payload)

    def end_session(
        self, session_id: str, status: str = "completed", notes: str = ""
    ) -> dict[str, Any]:
        payload: dict[str, str] = {"status": status}
        if notes:
            payload["notes"] = notes
        return self.post(f"/api/sessions/{session_id}/end/", payload)

    def add_log(self, session_id: str, level: str, message: str) -> dict[str, Any]:
        return self.post(f"/api/sessions/{session_id}/log/", {"level": level, "message": message})

    def list_sessions(
        self,
        active: bool = False,
        agent: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if active:
            params["status"] = "active"
        if agent:
            params["agent"] = agent
        return self.get("/api/sessions/", params)

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self.get(f"/api/sessions/{session_id}/")

    def push_output(
        self, session_id: str, lines: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return self.post(f"/remote/api/remote/output/{session_id}/push/", {"lines": lines})

    # --- Dashboard / Pipeline endpoints ---

    def dashboard_summary(self) -> dict[str, Any]:
        return self.get("/api/dashboard/summary/")

    def pipeline_prs(self, repo: str = "", limit: int = 20) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if repo:
            params["repo"] = repo
        return self.get("/api/pipeline/prs/", params)
