# brain/views_research.py
"""
Research Library API — semantic search over the user's research corpus.

Endpoints (all gated by require_brain_access):
    GET  /api/brain/research/search/?q=...&limit=10&topic=...
    GET  /api/brain/research/documents/
    GET  /api/brain/research/documents/<slug>/
    GET  /api/brain/research/topics/
    GET  /api/brain/research/stats/
"""
from __future__ import annotations

from typing import Any

from django.db import connection
from django.db.models import Count, Sum
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET
from django_ratelimit.decorators import ratelimit
from pgvector.django import CosineDistance

from core.auth import require_brain_access

from . import embeddings
from .models import ResearchChunk, ResearchDocument

MAX_SEARCH_LIMIT = 50
DEFAULT_SEARCH_LIMIT = 10


def _upstream_embedding_errors() -> tuple[type[Exception], ...]:
    """Return the tuple of OpenAI SDK exception classes to treat as upstream
    failures (→ 502).

    Imported lazily so this view module can still load in environments where
    the openai package isn't installed — matching the defensive pattern in
    brain/embeddings.py. If openai is missing, we fall back to an empty tuple
    so the except clause simply never matches.
    """
    try:
        from openai import (  # noqa: PLC0415 — intentional lazy import
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            RateLimitError,
        )
    except ImportError:
        return ()
    return (APIConnectionError, APIStatusError, APITimeoutError, RateLimitError)


def _doc_to_dict(doc: ResearchDocument, include_content: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "slug": doc.slug,
        "title": doc.title,
        "source_path": doc.source_path,
        "source_type": doc.source_type,
        "topic": doc.topic,
        "word_count": doc.word_count,
        "is_indexed": doc.is_indexed,
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
    }
    if include_content:
        data["content"] = doc.content
    return data


def _chunk_to_dict(chunk: ResearchChunk) -> dict[str, Any]:
    return {
        "chunk_index": chunk.chunk_index,
        "content": chunk.content,
        "word_count": chunk.word_count,
        "metadata": chunk.metadata,
        "has_embedding": chunk.embedding is not None,
    }


def _parse_limit(raw: str | None) -> int:
    if raw is None:
        return DEFAULT_SEARCH_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_SEARCH_LIMIT
    return max(1, min(value, MAX_SEARCH_LIMIT))


@ratelimit(key="ip", rate="60/m", method="GET", block=False)
@require_GET
@require_brain_access
def research_search(request: HttpRequest) -> JsonResponse:
    """Semantic search across research chunks."""
    # CosineDistance is a pgvector operator — PostgreSQL only. If someone's
    # running against the SQLite fallback (or any other backend), fail cleanly
    # with 503 rather than letting the query blow up with a 500 on an unknown
    # operator. The migration already gates pgvector setup the same way, and
    # the test suite skips search tests on non-Postgres.
    if getattr(connection, "vendor", None) != "postgresql":
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Semantic search requires PostgreSQL with the pgvector "
                    "extension. This environment is using a non-PostgreSQL "
                    "database backend."
                ),
                "data": None,
            },
            status=503,
        )

    query = request.GET.get("q", "").strip()
    if not query:
        return JsonResponse(
            {"success": False, "message": "Query parameter 'q' is required", "data": None},
            status=400,
        )

    limit = _parse_limit(request.GET.get("limit"))
    topic_filter = request.GET.get("topic", "").strip() or None

    upstream_errors = _upstream_embedding_errors()
    try:
        query_embedding = embeddings.generate_embedding(query)
    except RuntimeError as exc:
        # Missing config (e.g. OPENAI_API_KEY) — our fault, 500.
        return JsonResponse(
            {"success": False, "message": str(exc), "data": None},
            status=500,
        )
    except ValueError as exc:
        # Empty/invalid query reached the embedding layer — treat as 400.
        return JsonResponse(
            {"success": False, "message": str(exc), "data": None},
            status=400,
        )
    except upstream_errors as exc:
        return JsonResponse(
            {"success": False, "message": f"Embedding provider failed: {exc}", "data": None},
            status=502,
        )

    qs = ResearchChunk.objects.filter(
        embedding__isnull=False,
        document__is_indexed=True,
    ).select_related("document")

    if topic_filter:
        qs = qs.filter(document__topic=topic_filter)

    results = (
        qs.annotate(distance=CosineDistance("embedding", query_embedding))
        .order_by("distance")[:limit]
    )

    payload = [
        {
            "score": round(1 - float(r.distance), 4),
            "chunk_content": r.content,
            "chunk_index": r.chunk_index,
            "document_slug": r.document.slug,
            "document_title": r.document.title,
            "topic": r.document.topic,
            "source_type": r.document.source_type,
            "heading": (r.metadata or {}).get("heading", ""),
            "word_count": r.word_count,
        }
        for r in results
    ]

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "query": query,
            "topic": topic_filter,
            "total_results": len(payload),
            "results": payload,
        },
    })


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@require_GET
@require_brain_access
def research_documents_list(request: HttpRequest) -> JsonResponse:
    """List all research documents (no content in list view)."""
    qs = ResearchDocument.objects.all().order_by("topic", "title")

    topic_filter = request.GET.get("topic", "").strip()
    if topic_filter:
        qs = qs.filter(topic=topic_filter)
    source_type_filter = request.GET.get("source_type", "").strip()
    if source_type_filter:
        qs = qs.filter(source_type=source_type_filter)

    docs = list(qs)
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "total": len(docs),
            "documents": [_doc_to_dict(d, include_content=False) for d in docs],
        },
    })


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@require_GET
@require_brain_access
def research_document_detail(request: HttpRequest, slug: str) -> JsonResponse:
    """Get a single research document with full content and its chunks.

    Object-level authorization note
    -------------------------------
    CLAUDE.md mandates object-level auth checks on every view with a slug/id
    parameter. The research corpus is intentionally a shared read-only
    resource — all brain-access holders see the same document set, there is
    no per-document ACL, no visibility flag, and no owner. `require_brain_access`
    on this view already enforces the only authorization gate that exists for
    this resource (staff session, API key, or DRF token with an active user),
    so object-level "can this user see this slug?" collapses to "does the slug
    exist?" as a matter of design, not oversight.

    If the research library ever grows per-topic ACLs, a private flag,
    or user-scoped visibility, the filter belongs here (e.g. on an
    `is_active` / `accessible_for(request.user)` queryset method).
    """
    try:
        doc = ResearchDocument.objects.get(slug=slug)
    except ResearchDocument.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Document not found", "data": None},
            status=404,
        )

    data = _doc_to_dict(doc, include_content=True)
    data["chunks"] = [
        _chunk_to_dict(c) for c in doc.chunks.all().order_by("chunk_index")
    ]
    return JsonResponse({"success": True, "message": "ok", "data": data})


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@require_GET
@require_brain_access
def research_topics(request: HttpRequest) -> JsonResponse:
    """List distinct topics with document counts."""
    topics = (
        ResearchDocument.objects.values("topic")
        .annotate(document_count=Count("id"))
        .order_by("topic")
    )
    payload = [
        {"topic": row["topic"], "document_count": row["document_count"]}
        for row in topics
    ]
    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "total": len(payload),
            "topics": payload,
        },
    })


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@require_GET
@require_brain_access
def research_stats(request: HttpRequest) -> JsonResponse:
    """Overall stats for the research corpus."""
    total_docs = ResearchDocument.objects.count()
    indexed_docs = ResearchDocument.objects.filter(is_indexed=True).count()
    total_chunks = ResearchChunk.objects.count()
    embedded_chunks = ResearchChunk.objects.filter(embedding__isnull=False).count()
    total_topics = ResearchDocument.objects.values("topic").distinct().count()
    total_words = (
        ResearchDocument.objects.aggregate(total=Sum("word_count"))["total"] or 0
    )
    indexed_pct = (
        round(100 * indexed_docs / total_docs, 1) if total_docs else 0.0
    )
    embedded_pct = (
        round(100 * embedded_chunks / total_chunks, 1) if total_chunks else 0.0
    )

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "total_documents": total_docs,
            "indexed_documents": indexed_docs,
            "indexed_percent": indexed_pct,
            "total_chunks": total_chunks,
            "embedded_chunks": embedded_chunks,
            "embedded_percent": embedded_pct,
            "total_topics": total_topics,
            "total_words": total_words,
        },
    })
