from datetime import timedelta
from typing import Any

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods
from django_ratelimit.decorators import ratelimit

from core.auth import require_brain_access
from core.utils import parse_json_body

from .models import ConsolidationLog, MemoryEntry

VALID_CATEGORIES = {c[0] for c in MemoryEntry.CATEGORY_CHOICES}
VALID_CONFIDENCES = {c[0] for c in MemoryEntry.CONFIDENCE_CHOICES}


def _entry_to_dict(entry: MemoryEntry) -> dict[str, Any]:
    return {
        "id": entry.pk,
        "key": entry.key,
        "value": entry.value,
        "category": entry.category,
        "confidence": entry.confidence,
        "source": entry.source,
        "tags": entry.tags,
        "is_stale": entry.is_stale,
        "preview": entry.preview,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
    }


def _validate_tags(tags: Any) -> list[str] | None:
    """Validate tags field. Returns cleaned list or None if invalid."""
    if not isinstance(tags, list):
        return None
    if len(tags) > 20:
        return None
    cleaned = []
    for tag in tags:
        if not isinstance(tag, str):
            return None
        tag = tag[:50]
        cleaned.append(tag)
    return cleaned


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@ratelimit(key="ip", rate="10/m", method="POST", block=False)
@require_http_methods(["GET", "POST"])
@require_brain_access
def entries_list_create(request: HttpRequest) -> JsonResponse:
    """List entries (GET) or create a new entry (POST)."""
    if request.method == "POST":
        if len(request.body) > 256 * 1024:
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

        key = str(body.get("key", ""))[:200]
        value = str(body.get("value", ""))
        category = str(body.get("category", ""))
        confidence = str(body.get("confidence", "observed"))
        source = str(body.get("source", "manual"))[:100]
        tags = body.get("tags", [])

        if not key or not value:
            return JsonResponse(
                {"success": False, "message": "key and value are required", "data": None},
                status=400,
            )

        if category not in VALID_CATEGORIES:
            return JsonResponse(
                {"success": False, "message": f"Invalid category. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}", "data": None},
                status=400,
            )

        if confidence not in VALID_CONFIDENCES:
            return JsonResponse(
                {"success": False, "message": f"Invalid confidence. Must be one of: {', '.join(sorted(VALID_CONFIDENCES))}", "data": None},
                status=400,
            )

        cleaned_tags = _validate_tags(tags)
        if cleaned_tags is None:
            return JsonResponse(
                {"success": False, "message": "tags must be a list of strings (max 20 tags, each max 50 chars)", "data": None},
                status=400,
            )

        entry = MemoryEntry.objects.create(
            key=key,
            value=value,
            category=category,
            confidence=confidence,
            source=source,
            tags=cleaned_tags,
        )
        return JsonResponse(
            {"success": True, "message": "Entry created", "data": _entry_to_dict(entry)},
            status=201,
        )

    # GET — list with filters
    qs = MemoryEntry.objects.all().order_by("category", "key")

    category = request.GET.get("category")
    if category:
        qs = qs.filter(category=category)

    tag = request.GET.get("tag")
    if tag:
        qs = qs.filter(tags__contains=[tag])

    search = request.GET.get("search")
    if search:
        qs = qs.filter(
            Q(key__icontains=search)
            | Q(value__icontains=search)
        )

    stale = request.GET.get("stale")
    if stale == "true":
        cutoff = timezone.now() - timedelta(days=30)
        qs = qs.filter(updated_at__lt=cutoff)

    entries = [_entry_to_dict(e) for e in qs]
    return JsonResponse(
        {"success": True, "message": "ok", "data": {"total": len(entries), "entries": entries}},
    )


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@ratelimit(key="ip", rate="10/m", method=["PUT", "DELETE"], block=False)
@require_http_methods(["GET", "PUT", "DELETE"])
@require_brain_access
def entry_detail(request: HttpRequest, entry_id: int) -> JsonResponse:
    """Get, update, or delete a single entry."""
    try:
        entry = MemoryEntry.objects.get(pk=entry_id)
    except MemoryEntry.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Entry not found", "data": None},
            status=404,
        )

    if request.method == "GET":
        return JsonResponse(
            {"success": True, "message": "ok", "data": _entry_to_dict(entry)},
        )

    if request.method == "DELETE":
        entry.delete()
        return JsonResponse(
            {"success": True, "message": "Entry deleted", "data": None},
        )

    # PUT — update
    if len(request.body) > 256 * 1024:
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

    if "key" in body:
        entry.key = str(body["key"])[:200]
    if "value" in body:
        entry.value = str(body["value"])
    if "category" in body:
        cat = str(body["category"])
        if cat not in VALID_CATEGORIES:
            return JsonResponse(
                {"success": False, "message": f"Invalid category. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}", "data": None},
                status=400,
            )
        entry.category = cat
    if "confidence" in body:
        conf = str(body["confidence"])
        if conf not in VALID_CONFIDENCES:
            return JsonResponse(
                {"success": False, "message": f"Invalid confidence. Must be one of: {', '.join(sorted(VALID_CONFIDENCES))}", "data": None},
                status=400,
            )
        entry.confidence = conf
    if "source" in body:
        entry.source = str(body["source"])[:100]
    if "tags" in body:
        cleaned_tags = _validate_tags(body["tags"])
        if cleaned_tags is None:
            return JsonResponse(
                {"success": False, "message": "tags must be a list of strings (max 20 tags, each max 50 chars)", "data": None},
                status=400,
            )
        entry.tags = cleaned_tags

    entry.save()
    return JsonResponse(
        {"success": True, "message": "Entry updated", "data": _entry_to_dict(entry)},
    )


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@require_GET
@require_brain_access
def categories_list(request: HttpRequest) -> JsonResponse:
    """Return category list with entry counts."""
    counts = {}
    for code, label in MemoryEntry.CATEGORY_CHOICES:
        count = MemoryEntry.objects.filter(category=code).count()
        counts[code] = {"label": label, "count": count}

    return JsonResponse(
        {"success": True, "message": "ok", "data": counts},
    )


@ratelimit(key="ip", rate="5/m", method="POST", block=False)
@require_http_methods(["POST"])
@require_brain_access
def generate_brief(request: HttpRequest) -> JsonResponse:
    """Generate a context brief from memory entries."""
    if len(request.body) > 256 * 1024:
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

    scope = body.get("scope", "general")
    project_name = body.get("project")

    # Continuity scope: narrative "State of Mind"
    if scope == "continuity":
        cont_entries = MemoryEntry.objects.filter(
            category="continuity",
        ).order_by("-updated_at")

        paragraphs = [e.value for e in cont_entries]
        narrative = "Here's where I am right now.\n\n"
        narrative += "\n\n".join(paragraphs)
        if paragraphs:
            narrative += "\n\nThese are the patterns I'm carrying forward."

        return JsonResponse({
            "success": True,
            "message": "Brief generated",
            "data": {
                "brief": f"# State of Mind\n\n{narrative}",
                "entry_count": len(paragraphs),
                "generated_at": timezone.now().isoformat(),
            },
        })

    if scope == "domain":
        categories = ["domain", "decision", "lesson"]
    elif scope == "project":
        categories = ["project"]
    elif scope == "personal":
        categories = ["identity", "relationship", "personal"]
    else:
        categories = [c[0] for c in MemoryEntry.CATEGORY_CHOICES]

    qs = MemoryEntry.objects.filter(category__in=categories).order_by("category", "key")

    if scope == "project" and project_name:
        qs = qs.filter(tags__contains=[project_name])

    sections: dict[str, list[str]] = {}
    for entry in qs:
        label = entry.get_category_display()
        if label not in sections:
            sections[label] = []
        sections[label].append(f"- **{entry.key}**: {entry.value}")

    brief_parts = ["# Context Brief", ""]
    for section_name, items in sections.items():
        brief_parts.append(f"## {section_name}")
        brief_parts.extend(items)
        brief_parts.append("")

    # Add State of Mind subsection for general scope
    if scope == "general":
        cont_recent = MemoryEntry.objects.filter(
            category="continuity",
        ).order_by("-updated_at")[:3]
        if cont_recent.exists():
            brief_parts.append("## State of Mind")
            for entry in cont_recent:
                sentences = entry.value.split(".")
                preview = ". ".join(s.strip() for s in sentences[:2] if s.strip())
                if preview and not preview.endswith("."):
                    preview += "."
                brief_parts.append(f"- **{entry.key}**: {preview}")
            brief_parts.append("")

    brief = "\n".join(brief_parts)
    entry_count = qs.count()

    return JsonResponse({
        "success": True,
        "message": "Brief generated",
        "data": {
            "brief": brief,
            "entry_count": entry_count,
            "generated_at": timezone.now().isoformat(),
        },
    })


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@require_GET
@require_brain_access
def stats(request: HttpRequest) -> JsonResponse:
    """Stats for Nerve Center panel."""
    now = timezone.now()
    cutoff = now - timedelta(days=30)

    total = MemoryEntry.objects.count()
    stale_count = MemoryEntry.objects.filter(updated_at__lt=cutoff).count()

    category_counts = {}
    for code, _label in MemoryEntry.CATEGORY_CHOICES:
        count = MemoryEntry.objects.filter(category=code).count()
        if count > 0:
            category_counts[code] = count

    last_entry = MemoryEntry.objects.order_by("-updated_at").first()

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "entry_count": total,
            "stale_count": stale_count,
            "category_counts": category_counts,
            "last_updated": last_entry.updated_at.isoformat() if last_entry else None,
        },
    })


# --- Consolidation API ---

@ratelimit(key="ip", rate="5/m", method="POST", block=False)
@require_http_methods(["POST"])
@require_brain_access
def consolidate(request: HttpRequest) -> JsonResponse:
    """Run brain consolidation. Pass ?force=true to skip gate checks."""
    force = request.GET.get("force", "").lower() == "true"

    from .services import BrainConsolidator

    consolidator = BrainConsolidator()
    result = consolidator.run(force=force)

    return JsonResponse({
        "success": True,
        "message": "Consolidation complete" if not result.get("skipped") else "Consolidation skipped",
        "data": result,
    })


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@require_GET
@require_brain_access
def consolidation_history(request: HttpRequest) -> JsonResponse:
    """Return recent consolidation logs."""
    logs = ConsolidationLog.objects.order_by("-started_at")[:20]
    data = []
    for log in logs:
        data.append({
            "id": log.pk,
            "started_at": log.started_at.isoformat(),
            "completed_at": log.completed_at.isoformat() if log.completed_at else None,
            "entries_reviewed": log.entries_reviewed,
            "entries_promoted": log.entries_promoted,
            "entries_archived": log.entries_archived,
            "entries_pruned": log.entries_pruned,
            "contradictions_resolved": log.contradictions_resolved,
            "notes": log.notes,
        })

    # Gate status — use last completed log to match _check_gates() logic
    now = timezone.now()
    last_log = (
        ConsolidationLog.objects.filter(completed_at__isnull=False)
        .order_by("-started_at")
        .first()
    )
    hours_since = (
        round((now - last_log.started_at).total_seconds() / 3600, 1)
        if last_log else None
    )
    since = last_log.started_at if last_log else now - timedelta(days=365)
    entries_since = MemoryEntry.objects.filter(updated_at__gte=since).count()
    lock_held = ConsolidationLog.objects.filter(completed_at__isnull=True).exists()

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "logs": data,
            "gate_status": {
                "hours_since_last": hours_since,
                "entries_since_last": entries_since,
                "lock_held": lock_held,
            },
        },
    })


@ratelimit(key="ip", rate="5/m", method="POST", block=False)
@require_http_methods(["POST"])
@require_brain_access
def send_test_morning_note(request: HttpRequest) -> JsonResponse:
    """Generate and send a test morning note immediately."""
    from core.telegram import TelegramNotifier

    from .services import MorningNoteGenerator

    generator = MorningNoteGenerator()
    note = generator.generate()

    if not note:
        return JsonResponse({
            "success": False,
            "message": "Failed to generate morning note",
            "data": None,
        }, status=500)

    result = TelegramNotifier.send(note, parse_mode="Markdown")
    sent = result is not None and result.get("ok", False)

    return JsonResponse({
        "success": True,
        "message": "Test morning note sent" if sent else "Note generated but Telegram send failed",
        "data": {"note": note, "telegram_sent": sent},
    })


# --- Web views ---

@login_required
def brain_index(request: HttpRequest) -> HttpResponse:
    """Brain deep dive page — full memory browser."""
    categories = []
    for code, label in MemoryEntry.CATEGORY_CHOICES:
        count = MemoryEntry.objects.filter(category=code).count()
        categories.append({"code": code, "label": label, "count": count})

    last_consolidation = ConsolidationLog.objects.order_by("-started_at").first()

    return render(request, "brain/index.html", {
        "categories": categories,
        "total_entries": MemoryEntry.objects.count(),
        "last_consolidation": last_consolidation,
    })


@login_required
def handoffs_browser(request: HttpRequest) -> HttpResponse:
    """Browser page for session handoffs — one card per context."""
    from .models import HandoffEntry  # noqa: PLC0415

    contexts = [{"code": c[0], "label": c[1]} for c in HandoffEntry.Context.choices]
    return render(request, "brain/handoffs.html", {
        "contexts": contexts,
    })


@login_required
def research_browser(request: HttpRequest) -> HttpResponse:
    """Semantic search frontend for the Research Library corpus.

    Renders a search-and-results UI that queries
    /api/brain/research/search/ via Alpine.js. Initial payload carries
    the corpus stats and the distinct topic list so the page has
    everything it needs to populate the filter dropdown and the "N
    documents indexed" banner without an extra round-trip.
    """
    from .models import ResearchDocument  # noqa: PLC0415 — avoid circular at import time

    topics = list(
        ResearchDocument.objects
        .values_list("topic", flat=True)
        .distinct()
        .order_by("topic")
    )
    total_documents = ResearchDocument.objects.count()
    indexed_documents = ResearchDocument.objects.filter(is_indexed=True).count()

    return render(request, "brain/research.html", {
        "topics": topics,
        "total_documents": total_documents,
        "indexed_documents": indexed_documents,
    })
