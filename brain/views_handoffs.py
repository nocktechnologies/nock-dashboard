# brain/views_handoffs.py
from __future__ import annotations

from typing import Any

from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods
from django_ratelimit.decorators import ratelimit

from core.auth import require_brain_access
from core.utils import parse_json_body

from .models import HandoffEntry, HandoffVersion

VALID_HANDOFF_CONTEXTS = {c[0] for c in HandoffEntry.Context.choices}
VALID_ACTION_ITEM_STATUSES = {"open", "completed", "deferred"}


def _handoff_to_dict(h: HandoffEntry, include_content: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {
        "context": h.context,
        "title": h.title,
        "version": h.version,
        "previous_items_resolved": h.previous_items_resolved,
        "updated_by": h.updated_by,
        "created_at": h.created_at.isoformat(),
        "updated_at": h.updated_at.isoformat(),
        "open_items_count": h.open_items_count,
        "completed_items_count": h.completed_items_count,
        "deferred_items_count": h.deferred_items_count,
    }
    if include_content:
        data["content"] = h.content
        data["action_items"] = h.action_items
    return data


def _version_to_dict(v: HandoffVersion) -> dict[str, Any]:
    return {
        "version": v.version,
        "title": v.title,
        "content": v.content,
        "action_items": v.action_items,
        "previous_items_resolved": v.previous_items_resolved,
        "updated_by": v.updated_by,
        "created_at": v.created_at.isoformat(),
    }


def _validate_action_items(value: Any) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Return (cleaned, None) on success or (None, error_message) on failure."""
    if not isinstance(value, list):
        return None, "action_items must be a list"
    if len(value) > 100:
        return None, "action_items: max 100 items"

    cleaned: list[dict[str, Any]] = []
    for idx, item in enumerate(value):
        if not isinstance(item, dict):
            return None, f"action_items[{idx}] must be an object"
        description = item.get("description")
        status = item.get("status", "open")
        reason = item.get("reason")

        if not isinstance(description, str) or not description.strip():
            return None, f"action_items[{idx}].description is required (string)"
        if status not in VALID_ACTION_ITEM_STATUSES:
            return (
                None,
                f"action_items[{idx}].status must be one of: "
                f"{', '.join(sorted(VALID_ACTION_ITEM_STATUSES))}",
            )
        if reason is not None and not isinstance(reason, str):
            return None, f"action_items[{idx}].reason must be a string or null"

        cleaned.append({
            "description": description.strip()[:1000],
            "status": status,
            "reason": (reason[:500] if isinstance(reason, str) else None),
        })
    return cleaned, None


def _bad_request(message: str) -> JsonResponse:
    return JsonResponse(
        {"success": False, "message": message, "data": None}, status=400,
    )


def _not_found(message: str = "Handoff not found") -> JsonResponse:
    return JsonResponse(
        {"success": False, "message": message, "data": None}, status=404,
    )


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@require_GET
@require_brain_access
def handoffs_list(request: HttpRequest) -> JsonResponse:
    """List all active handoffs (one per context). No content in list view."""
    qs = HandoffEntry.objects.all().order_by("-updated_at", "pk")
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "total": qs.count(),
            "handoffs": [_handoff_to_dict(h, include_content=False) for h in qs],
        },
    })


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@require_GET
@require_brain_access
def handoffs_latest(request: HttpRequest) -> JsonResponse:
    """Most recently updated handoff across all contexts. For Nerve Center card."""
    h = HandoffEntry.objects.order_by("-updated_at", "-pk").first()
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "handoff": _handoff_to_dict(h, include_content=False) if h else None,
        },
    })


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@ratelimit(key="ip", rate="20/m", method="PUT", block=False)
@require_http_methods(["GET", "PUT"])
@require_brain_access
def handoff_detail(request: HttpRequest, context: str) -> JsonResponse:
    """Get or PUT-overwrite the active handoff for a given context.

    PUT semantics: archives the existing handoff (if any) into HandoffVersion,
    then updates the active row in place. version auto-increments.
    """
    if context not in VALID_HANDOFF_CONTEXTS:
        return _bad_request(
            f"Invalid context. Must be one of: {', '.join(sorted(VALID_HANDOFF_CONTEXTS))}",
        )

    if request.method == "GET":
        try:
            h = HandoffEntry.objects.get(context=context)
        except HandoffEntry.DoesNotExist:
            return _not_found()
        return JsonResponse(
            {"success": True, "message": "ok", "data": _handoff_to_dict(h)},
        )

    # PUT — create-or-overwrite
    if len(request.body) > 1024 * 1024:
        return JsonResponse(
            {"success": False, "message": "Request body too large", "data": None},
            status=413,
        )

    body, err = parse_json_body(request)
    if err:
        return err
    if not isinstance(body, dict):
        return _bad_request("JSON body must be an object")

    title_raw = body.get("title")
    content_raw = body.get("content")
    if not title_raw or not isinstance(title_raw, str):
        return _bad_request("title is required")
    if not content_raw or not isinstance(content_raw, str):
        return _bad_request("content is required")

    cleaned_items, item_err = _validate_action_items(body.get("action_items", []))
    if item_err is not None:
        return _bad_request(item_err)

    title = title_raw.strip()[:500]
    content = content_raw
    previous_items_resolved = bool(body.get("previous_items_resolved", False))
    updated_by = str(body.get("updated_by", "system"))[:100]

    with transaction.atomic():
        try:
            h = HandoffEntry.objects.select_for_update().get(context=context)
            # Archive the prior state before overwriting
            HandoffVersion.objects.create(
                handoff=h,
                version=h.version,
                title=h.title,
                content=h.content,
                action_items=h.action_items,
                previous_items_resolved=h.previous_items_resolved,
                updated_by=h.updated_by,
            )
            h.title = title
            h.content = content
            h.action_items = cleaned_items or []
            h.previous_items_resolved = previous_items_resolved
            h.updated_by = updated_by
            h.version += 1
            h.save()
        except HandoffEntry.DoesNotExist:
            h = HandoffEntry.objects.create(
                context=context,
                title=title,
                content=content,
                action_items=cleaned_items or [],
                previous_items_resolved=previous_items_resolved,
                updated_by=updated_by,
            )

    return JsonResponse(
        {"success": True, "message": "Handoff saved", "data": _handoff_to_dict(h)},
    )


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@require_GET
@require_brain_access
def handoff_history(request: HttpRequest, context: str) -> JsonResponse:
    """Version history for a single context's handoff."""
    if context not in VALID_HANDOFF_CONTEXTS:
        return _bad_request(
            f"Invalid context. Must be one of: {', '.join(sorted(VALID_HANDOFF_CONTEXTS))}",
        )

    try:
        h = HandoffEntry.objects.get(context=context)
    except HandoffEntry.DoesNotExist:
        return _not_found()

    versions = h.versions.all().order_by("-version")
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "context": h.context,
            "current_version": h.version,
            "total": versions.count(),
            "versions": [_version_to_dict(v) for v in versions],
        },
    })
