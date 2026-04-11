# brain/views_identity.py
from __future__ import annotations

import contextlib
from typing import Any

from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods
from django_ratelimit.decorators import ratelimit

from core.auth import require_brain_access
from core.utils import parse_json_body

from .models import IdentityDocument, IdentityDocumentVersion

VALID_DOCUMENT_TYPES = {t[0] for t in IdentityDocument.DOCUMENT_TYPES}


def _doc_to_dict(doc: IdentityDocument, include_content: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {
        "slug": doc.slug,
        "title": doc.title,
        "version": doc.version,
        "document_type": doc.document_type,
        "is_active": doc.is_active,
        "load_order": doc.load_order,
        "updated_by": doc.updated_by,
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
    }
    if include_content:
        data["content"] = doc.content
    return data


def _version_to_dict(ver: IdentityDocumentVersion) -> dict[str, Any]:
    return {
        "version": ver.version,
        "title": ver.title,
        "content": ver.content,
        "document_type": ver.document_type,
        "updated_by": ver.updated_by,
        "created_at": ver.created_at.isoformat(),
    }


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@ratelimit(key="ip", rate="10/m", method="POST", block=False)
@require_http_methods(["GET", "POST"])
@require_brain_access
def identity_list_create(request: HttpRequest) -> JsonResponse:
    """List all active identity documents (GET) or create a new one (POST)."""
    if request.method == "POST":
        if len(request.body) > 1024 * 1024:
            return JsonResponse(
                {"success": False, "message": "Request body too large", "data": None},
                status=413,
            )
        body, err = parse_json_body(request)
        if err:
            return err
        if not isinstance(body, dict):
            return JsonResponse(
                {"success": False, "message": "JSON body must be an object", "data": None},
                status=400,
            )

        slug = str(body.get("slug", "")).strip()[:100]
        title = str(body.get("title", "")).strip()[:255]
        content = str(body.get("content", ""))
        document_type = str(body.get("document_type", ""))
        load_order = body.get("load_order", 0)
        updated_by = str(body.get("updated_by", "system"))[:100]

        if not slug or not title or not content:
            return JsonResponse(
                {"success": False, "message": "slug, title, and content are required", "data": None},
                status=400,
            )

        if document_type not in VALID_DOCUMENT_TYPES:
            return JsonResponse(
                {
                    "success": False,
                    "message": f"Invalid document_type. Must be one of: {', '.join(sorted(VALID_DOCUMENT_TYPES))}",
                    "data": None,
                },
                status=400,
            )

        try:
            load_order = max(int(load_order), 0)
        except (TypeError, ValueError):
            load_order = 0

        if IdentityDocument.objects.filter(slug=slug).exists():
            return JsonResponse(
                {"success": False, "message": f"Document with slug '{slug}' already exists", "data": None},
                status=409,
            )

        doc = IdentityDocument.objects.create(
            slug=slug,
            title=title,
            content=content,
            document_type=document_type,
            load_order=load_order,
            updated_by=updated_by,
        )
        return JsonResponse(
            {"success": True, "message": "Document created", "data": _doc_to_dict(doc)},
            status=201,
        )

    # GET — list active documents (no content in list view)
    docs = IdentityDocument.objects.filter(is_active=True).order_by("load_order", "created_at")
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "total": docs.count(),
            "documents": [_doc_to_dict(d, include_content=False) for d in docs],
        },
    })


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@ratelimit(key="ip", rate="10/m", method=["PUT", "DELETE"], block=False)
@require_http_methods(["GET", "PUT", "DELETE"])
@require_brain_access
def identity_detail(request: HttpRequest, slug: str) -> JsonResponse:
    """Get, update, or soft-delete a specific identity document."""
    try:
        doc = IdentityDocument.objects.get(slug=slug)
    except IdentityDocument.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Document not found", "data": None},
            status=404,
        )

    if request.method == "GET":
        return JsonResponse(
            {"success": True, "message": "ok", "data": _doc_to_dict(doc)},
        )

    if request.method == "DELETE":
        if not doc.is_active:
            return JsonResponse(
                {"success": False, "message": "Document already inactive", "data": None},
                status=400,
            )
        doc.is_active = False
        doc.save(update_fields=["is_active", "updated_at"])
        return JsonResponse(
            {"success": True, "message": "Document deactivated (soft delete)", "data": _doc_to_dict(doc)},
        )

    # PUT — update with version archiving
    if len(request.body) > 1024 * 1024:
        return JsonResponse(
            {"success": False, "message": "Request body too large", "data": None},
            status=413,
        )

    body, err = parse_json_body(request)
    if err:
        return err
    if not isinstance(body, dict):
        return JsonResponse(
            {"success": False, "message": "JSON body must be an object", "data": None},
            status=400,
        )

    new_content = body.get("content")
    new_title = body.get("title")
    new_document_type = body.get("document_type")
    updated_by = str(body.get("updated_by", "system"))[:100]

    if new_document_type is not None and new_document_type not in VALID_DOCUMENT_TYPES:
        return JsonResponse(
            {
                "success": False,
                "message": f"Invalid document_type. Must be one of: {', '.join(sorted(VALID_DOCUMENT_TYPES))}",
                "data": None,
            },
            status=400,
        )

    with transaction.atomic():
        try:
            doc = IdentityDocument.objects.select_for_update().get(slug=slug)
        except IdentityDocument.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Document not found", "data": None},
                status=404,
            )

        # Archive current version before updating
        IdentityDocumentVersion.objects.create(
            document=doc,
            version=doc.version,
            title=doc.title,
            content=doc.content,
            document_type=doc.document_type,
            updated_by=doc.updated_by,
        )

        if new_content is not None:
            doc.content = str(new_content)
        if new_title is not None:
            doc.title = str(new_title)[:255]
        if new_document_type is not None:
            doc.document_type = new_document_type
        if "load_order" in body:
            with contextlib.suppress(TypeError, ValueError):
                doc.load_order = max(int(body["load_order"]), 0)

        doc.version += 1
        doc.updated_by = updated_by
        doc.save()

    return JsonResponse(
        {"success": True, "message": "Document updated", "data": _doc_to_dict(doc)},
    )


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@require_GET
@require_brain_access
def identity_history(request: HttpRequest, slug: str) -> JsonResponse:
    """Get version history for a specific identity document."""
    try:
        doc = IdentityDocument.objects.get(slug=slug)
    except IdentityDocument.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Document not found", "data": None},
            status=404,
        )

    versions = doc.versions.all().order_by("-version")
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "slug": doc.slug,
            "current_version": doc.version,
            "total": versions.count(),
            "versions": [_version_to_dict(v) for v in versions],
        },
    })


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@require_GET
@require_brain_access
def identity_boot(request: HttpRequest) -> JsonResponse:
    """Return all active identity documents with full content, ordered by load_order.

    Single call to load complete identity on session start.
    """
    docs = IdentityDocument.objects.filter(is_active=True).order_by("load_order", "created_at")
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "total": docs.count(),
            "documents": [_doc_to_dict(d, include_content=True) for d in docs],
        },
    })
