from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from core.auth import require_api_key
from pipeline.models import Repository

from .models import ContextDocument


@require_GET
@login_required
def context_list(request: HttpRequest) -> HttpResponse:
    """Context document inventory page with filters."""
    qs = ContextDocument.tenant_objects.for_request(request).filter(is_active=True).select_related("repository").order_by("repository__name", "file_path")

    # Filters
    repo_filter = request.GET.get("repo", "")
    type_filter = request.GET.get("type", "")
    stale_filter = request.GET.get("stale", "")

    if repo_filter:
        qs = qs.filter(repository__name=repo_filter)
    if type_filter:
        qs = qs.filter(doc_type=type_filter)
    if stale_filter == "yes":
        qs = qs.filter(is_stale=True)

    # Sort
    sort = request.GET.get("sort", "file_path")
    allowed_sorts = {"file_path", "-file_path", "last_modified", "-last_modified", "repository__name", "-repository__name"}
    if sort in allowed_sorts:
        qs = qs.order_by(sort)

    # Stats
    all_active = ContextDocument.tenant_objects.for_request(request).filter(is_active=True)
    total_docs = all_active.count()
    stale_count = all_active.filter(is_stale=True).count()
    healthy_count = total_docs - stale_count
    last_sync = all_active.filter(last_synced__isnull=False).order_by("-last_synced").values_list("last_synced", flat=True).first()

    return render(request, "context/list.html", {
        "documents": qs,
        "repos": Repository.tenant_objects.for_request(request).filter(is_active=True).order_by("owner", "name"),
        "doc_type_choices": ContextDocument.DOC_TYPE_CHOICES,
        "filters": {"repo": repo_filter, "type": type_filter, "stale": stale_filter},
        "stats": {
            "total": total_docs,
            "stale": stale_count,
            "healthy": healthy_count,
            "last_sync": last_sync,
        },
    })


@require_GET
@login_required
def context_detail(request: HttpRequest, doc_id: int) -> HttpResponse:
    """Document detail with snapshot timeline."""
    doc = get_object_or_404(
        ContextDocument.tenant_objects.for_request(request).select_related("repository"),
        pk=doc_id,
    )
    snapshots = doc.snapshots.order_by("-captured_at")[:50]
    branch = doc.repository.default_branch or "main"
    github_url = f"https://github.com/{doc.repository.owner}/{doc.repository.name}/blob/{branch}/{doc.file_path}"

    return render(request, "context/detail.html", {
        "doc": doc,
        "snapshots": snapshots,
        "github_url": github_url,
    })


@csrf_exempt
@require_GET
@require_api_key
def context_health_api(request: HttpRequest) -> JsonResponse:
    """JSON API for dashboard widget — context health stats."""
    all_active = ContextDocument.objects.filter(is_active=True).select_related("repository")
    total_docs = all_active.count()
    stale_docs = all_active.filter(is_stale=True).order_by("repository__name", "file_path")
    stale_count = stale_docs.count()
    healthy_count = total_docs - stale_count
    last_sync = all_active.filter(last_synced__isnull=False).order_by("-last_synced").values_list("last_synced", flat=True).first()

    stale_list = [
        {
            "title": d.title,
            "repo": d.repository.name,
            "days_since_modified": d.days_since_modified,
        }
        for d in stale_docs[:10]
    ]

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "total_docs": total_docs,
            "healthy_count": healthy_count,
            "stale_count": stale_count,
            "stale_docs": stale_list,
            "last_sync": last_sync.isoformat() if last_sync else None,
        },
    })
