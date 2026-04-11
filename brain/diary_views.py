# brain/diary_views.py
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods
from django_ratelimit.decorators import ratelimit

from core.auth import require_brain_access
from core.utils import parse_json_body

from .models import DiaryEntry

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

VALID_DIARY_CATEGORIES = {c[0] for c in DiaryEntry.Category.choices}
VALID_DIARY_SOURCES = {s[0] for s in DiaryEntry.Source.choices}


def _parse_date_param(value: str | None) -> date | None | str:
    """Parse a YYYY-MM-DD query param. Returns the date, None if absent, or 'invalid'.

    Strictly enforces YYYY-MM-DD format before calling fromisoformat() — Python 3.11+
    accepts compact (20260409) and week-date (2026-W15-4) formats that we do not want.
    """
    if not value:
        return None
    if not _DATE_RE.match(value):
        return "invalid"
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return "invalid"


def _diary_entry_to_dict(entry: DiaryEntry, excerpt: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": entry.pk,
        "title": entry.title,
        "category": entry.category,
        "source": entry.source,
        "entry_date": entry.entry_date.isoformat(),
        "session_date": entry.session_date.isoformat(),
        "word_count": entry.word_count,
        "tags": entry.tags,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
    }
    if excerpt:
        data["excerpt"] = entry.content[:200]
    else:
        data["content"] = entry.content
        data["session_id"] = entry.session_id
        data["asana_comment_gid"] = entry.asana_comment_gid
        data["migrated_at"] = entry.migrated_at.isoformat() if entry.migrated_at else None
    return data


def _validate_diary_tags(tags: Any) -> list[str] | None:
    if not isinstance(tags, list):
        return None
    if len(tags) > 30:
        return None
    cleaned = []
    for tag in tags:
        if not isinstance(tag, str):
            return None
        if len(tag) > 100:
            return None  # reject — error message says max 100 chars
        cleaned.append(tag)
    return cleaned


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@ratelimit(key="ip", rate="10/m", method="POST", block=False)
@require_http_methods(["GET", "POST"])
@require_brain_access
def diary_list_create(request: HttpRequest) -> JsonResponse:
    """List diary entries with filters (GET) or create a new entry (POST)."""
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

        title = str(body.get("title", ""))[:500]
        content = str(body.get("content", ""))
        category = str(body.get("category", ""))
        entry_date_raw = body.get("entry_date", "")
        session_date_raw = body.get("session_date", "")
        tags = body.get("tags", [])
        session_id = body.get("session_id")
        source = str(body.get("source", DiaryEntry.Source.NOCKCC))

        if not title or not content:
            return JsonResponse(
                {"success": False, "message": "title and content are required", "data": None},
                status=400,
            )

        if category not in VALID_DIARY_CATEGORIES:
            return JsonResponse(
                {
                    "success": False,
                    "message": f"Invalid category. Must be one of: {', '.join(sorted(VALID_DIARY_CATEGORIES))}",
                    "data": None,
                },
                status=400,
            )

        if source not in VALID_DIARY_SOURCES:
            source = DiaryEntry.Source.NOCKCC

        try:
            entry_date: datetime = datetime.fromisoformat(str(entry_date_raw).replace("Z", "+00:00"))
            if timezone.is_naive(entry_date):
                entry_date = timezone.make_aware(entry_date)
        except (ValueError, AttributeError):
            entry_date = timezone.now()

        session_date_parsed = _parse_date_param(
            None if session_date_raw in (None, "") else str(session_date_raw)
        )
        if session_date_parsed == "invalid":
            return JsonResponse(
                {"success": False, "message": "Invalid session_date format. Use YYYY-MM-DD.", "data": None},
                status=400,
            )
        session_date: date = session_date_parsed if session_date_parsed else entry_date.date()

        cleaned_tags = _validate_diary_tags(tags)
        if cleaned_tags is None:
            return JsonResponse(
                {
                    "success": False,
                    "message": "tags must be a list of strings (max 30 tags, each max 100 chars)",
                    "data": None,
                },
                status=400,
            )

        entry = DiaryEntry.objects.create(
            title=title,
            content=content,
            category=category,
            entry_date=entry_date,
            session_date=session_date,
            tags=cleaned_tags,
            source=source,
            session_id=str(session_id)[:100] if session_id else None,
        )
        return JsonResponse(
            {"success": True, "message": "Entry created", "data": _diary_entry_to_dict(entry)},
            status=201,
        )

    # GET — list with filters
    qs = DiaryEntry.objects.all().order_by("-entry_date", "pk")

    category = request.GET.get("category")
    if category:
        qs = qs.filter(category=category)

    session_date_val = _parse_date_param(request.GET.get("session_date"))
    if session_date_val == "invalid":
        return JsonResponse(
            {"success": False, "message": "Invalid session_date format. Use YYYY-MM-DD.", "data": None},
            status=400,
        )
    if session_date_val:
        qs = qs.filter(session_date=session_date_val)

    date_from_val = _parse_date_param(request.GET.get("date_from"))
    if date_from_val == "invalid":
        return JsonResponse(
            {"success": False, "message": "Invalid date_from format. Use YYYY-MM-DD.", "data": None},
            status=400,
        )
    if date_from_val:
        qs = qs.filter(entry_date__date__gte=date_from_val)

    date_to_val = _parse_date_param(request.GET.get("date_to"))
    if date_to_val == "invalid":
        return JsonResponse(
            {"success": False, "message": "Invalid date_to format. Use YYYY-MM-DD.", "data": None},
            status=400,
        )
    if date_to_val:
        qs = qs.filter(entry_date__date__lte=date_to_val)

    search = request.GET.get("search")
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(content__icontains=search))

    tags_param = request.GET.get("tags")
    if tags_param:
        for tag in tags_param.split(","):
            tag = tag.strip()
            if tag:
                qs = qs.filter(tags__contains=[tag])

    source = request.GET.get("source")
    if source:
        qs = qs.filter(source=source)

    try:
        limit = max(min(int(request.GET.get("limit", 20)), 100), 0)
        offset = max(int(request.GET.get("offset", 0)), 0)
    except (TypeError, ValueError):
        limit, offset = 20, 0

    total = qs.count()
    entries = [_diary_entry_to_dict(e, excerpt=True) for e in qs[offset : offset + limit]]

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {"total": total, "limit": limit, "offset": offset, "entries": entries},
    })


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@ratelimit(key="ip", rate="10/m", method="PATCH", block=False)
@require_http_methods(["GET", "PATCH"])
@require_brain_access
def diary_detail(request: HttpRequest, entry_id: int) -> JsonResponse:
    """Get or update a single diary entry."""
    try:
        entry = DiaryEntry.objects.get(pk=entry_id)
    except DiaryEntry.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Entry not found", "data": None},
            status=404,
        )

    if request.method == "GET":
        return JsonResponse(
            {"success": True, "message": "ok", "data": _diary_entry_to_dict(entry)},
        )

    # PATCH — partial update
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

    # Validate before acquiring the lock
    if "category" in body:
        cat = str(body["category"])
        if cat not in VALID_DIARY_CATEGORIES:
            return JsonResponse(
                {
                    "success": False,
                    "message": f"Invalid category. Must be one of: {', '.join(sorted(VALID_DIARY_CATEGORIES))}",
                    "data": None,
                },
                status=400,
            )

    if "tags" in body:
        cleaned_tags = _validate_diary_tags(body["tags"])
        if cleaned_tags is None:
            return JsonResponse(
                {
                    "success": False,
                    "message": "tags must be a list of strings (max 30 tags, each max 100 chars)",
                    "data": None,
                },
                status=400,
            )
    else:
        cleaned_tags = None

    with transaction.atomic():
        try:
            entry = DiaryEntry.objects.select_for_update().get(pk=entry_id)
        except DiaryEntry.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Entry not found", "data": None},
                status=404,
            )
        if "title" in body:
            entry.title = str(body["title"])[:500]
        if "content" in body:
            entry.content = str(body["content"])
        if "category" in body:
            entry.category = str(body["category"])
        if cleaned_tags is not None:
            entry.tags = cleaned_tags
        entry.save()

    return JsonResponse(
        {"success": True, "message": "Entry updated", "data": _diary_entry_to_dict(entry)},
    )


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@require_GET
@require_brain_access
def diary_stats(request: HttpRequest) -> JsonResponse:
    """Aggregate stats for the full diary."""
    total = DiaryEntry.objects.count()
    total_words = DiaryEntry.objects.aggregate(tw=Sum("word_count"))["tw"] or 0

    by_category = dict(
        DiaryEntry.objects.values("category")
        .annotate(cnt=Count("id"))
        .values_list("category", "cnt")
    )
    by_source = dict(
        DiaryEntry.objects.values("source")
        .annotate(cnt=Count("id"))
        .values_list("source", "cnt")
    )

    sessions_count = DiaryEntry.objects.values("session_date").distinct().count()

    first_entry = DiaryEntry.objects.order_by("entry_date").first()
    last_entry = DiaryEntry.objects.order_by("-entry_date").first()

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "total_entries": total,
            "total_words": total_words,
            "entries_by_category": by_category,
            "entries_by_source": by_source,
            "sessions_count": sessions_count,
            "date_range": {
                "first": first_entry.entry_date.date().isoformat() if first_entry else None,
                "last": last_entry.entry_date.date().isoformat() if last_entry else None,
            },
        },
    })


@ratelimit(key="ip", rate="100/m", method="GET", block=False)
@require_GET
@require_brain_access
def diary_recent(request: HttpRequest) -> JsonResponse:
    """Return entries from the last N days. Optimized for session startup."""
    try:
        days = max(min(int(request.GET.get("days", 7)), 90), 1)
    except (TypeError, ValueError):
        days = 7

    cutoff = timezone.now() - timedelta(days=days)
    qs = DiaryEntry.objects.filter(entry_date__gte=cutoff).order_by("-entry_date", "pk")

    categories_param = request.GET.get("categories")
    if categories_param:
        cats = [c.strip() for c in categories_param.split(",") if c.strip()]
        if cats:
            qs = qs.filter(category__in=cats)

    entries = [_diary_entry_to_dict(e, excerpt=True) for e in qs]

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {"total": len(entries), "days": days, "entries": entries},
    })


@ratelimit(key="ip", rate="5/m", method="GET", block=False)
@require_GET
@require_brain_access
def diary_brief(request: HttpRequest) -> JsonResponse:
    """AI-generated context brief from recent diary entries."""
    scope = request.GET.get("scope", "general")[:50]
    date_param = request.GET.get("date")

    if date_param:
        try:
            target_date = date.fromisoformat(date_param)
        except ValueError:
            return JsonResponse(
                {"success": False, "message": "date must be YYYY-MM-DD", "data": None},
                status=400,
            )
        qs = DiaryEntry.objects.filter(session_date=target_date).exclude(category=DiaryEntry.Category.PRIVATE).order_by("entry_date")
    else:
        cutoff = timezone.now() - timedelta(days=7)
        qs = DiaryEntry.objects.filter(entry_date__gte=cutoff).exclude(category=DiaryEntry.Category.PRIVATE).order_by("entry_date")

    entry_count = qs.count()

    if entry_count == 0:
        return JsonResponse({
            "success": True,
            "message": "No entries found for this period",
            "data": {
                "brief": "No diary entries found for this period.",
                "entry_count": 0,
                "scope": scope,
                "generated_at": timezone.now().isoformat(),
            },
        })

    scope_instruction = {
        "general": "Synthesize these diary entries into a comprehensive context brief covering work, emotional state, key decisions, and important relationships.",
        "session": "Summarize the work sessions, technical decisions made, and progress achieved.",
        "relationship": "Focus on relationship context — interactions with Kevin, Clair, and any other people mentioned.",
        "technical": "Focus on technical work, architecture decisions, and tooling discussed.",
    }.get(scope, "Synthesize these diary entries into a context brief.")

    entries_text = "\n\n---\n\n".join(
        f"[{e.entry_date.strftime('%b %d %H:%M')}] {e.category.upper()}: {e.title}\n\n{e.content[:2000]}"
        for e in qs[:20]
    )

    from intelligence import ai_client

    result = ai_client.chat(
        messages=[{"role": "user", "content": f"{scope_instruction}\n\nDiary entries:\n\n{entries_text}"}],
        system=(
            "You are synthesizing diary entries for Mara, an AI with persistent identity. "
            "Generate a context brief she can read at session start to feel continuous with her past self. "
            "Be warm, specific, and human. This is her memory."
        ),
        max_tokens=2048,
    )

    brief = (result.get("content") or None) if result else None
    if not brief:
        brief = "AI service unavailable. Check ANTHROPIC_API_KEY configuration."

    return JsonResponse({
        "success": True,
        "message": "Brief generated",
        "data": {
            "brief": brief,
            "entry_count": entry_count,
            "scope": scope,
            "generated_at": timezone.now().isoformat(),
        },
    })


@login_required
def diary_browser(request: HttpRequest) -> HttpResponse:
    """Diary browser page — full diary viewer and search."""
    categories = [{"code": c[0], "label": c[1]} for c in DiaryEntry.Category.choices]
    sources = [{"code": s[0], "label": s[1]} for s in DiaryEntry.Source.choices]
    total = DiaryEntry.objects.count()
    return render(request, "brain/diary.html", {
        "categories": categories,
        "sources": sources,
        "total_entries": total,
    })
