from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from core.auth import require_api_key
from core.utils import parse_json_body

from .forms import DocumentForm
from .models import Document, SessionReport


@require_GET
@login_required
def document_list(request: HttpRequest) -> HttpResponse:
    qs = Document.objects.all()
    category = request.GET.get("category", "")
    search = request.GET.get("q", "")

    if category:
        qs = qs.filter(category=category)
    if search:
        qs = qs.filter(title__icontains=search) | qs.filter(tags__icontains=search)

    return render(request, "vault/list.html", {
        "documents": qs,
        "categories": Document.CATEGORIES,
        "selected_category": category,
        "search": search,
    })


@require_http_methods(["GET", "POST"])
@login_required
def document_upload(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Document uploaded.")
            return redirect("vault:list")
    else:
        form = DocumentForm()
    return render(request, "vault/upload.html", {"form": form})


@require_GET
@login_required
def document_detail(request: HttpRequest, pk: int) -> HttpResponse:
    doc = get_object_or_404(Document, pk=pk)
    return render(request, "vault/detail.html", {"document": doc})


# ---------------------------------------------------------------------------
# Terminal Bridge — Session Reports API
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_api_key
def session_reports_api(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return _list_reports(request)
    return _create_report(request)


def _list_reports(request: HttpRequest) -> JsonResponse:
    qs = SessionReport.objects.all()

    project = request.GET.get("project", "")
    if project:
        qs = qs.filter(project_name__icontains=project)

    try:
        limit = int(request.GET.get("limit", 20))
    except ValueError:
        limit = 20
    limit = max(1, min(limit, 100))

    total = qs.count()
    reports = list(qs[:limit])

    data = [
        {
            "id": r.pk,
            "project_name": r.project_name,
            "title": r.title,
            "content_preview": r.content_preview,
            "branch": r.branch,
            "captured_at": r.captured_at.isoformat(),
            "received_at": r.received_at.isoformat(),
            "machine": r.machine,
        }
        for r in reports
    ]

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {"total": total, "reports": data},
    })


def _create_report(request: HttpRequest) -> JsonResponse:
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

    project_name = body.get("project_name", "")
    content = body.get("content", "")

    if not project_name:
        return JsonResponse(
            {"success": False, "message": "project_name is required", "data": None},
            status=400,
        )
    if not content:
        return JsonResponse(
            {"success": False, "message": "content is required", "data": None},
            status=400,
        )

    # Truncate content at 50KB to prevent abuse
    if len(content) > 50_000:
        content = content[:50_000] + "\n\n[Truncated at 50KB]"

    captured_at_str = body.get("captured_at", "")
    captured_at = None
    if captured_at_str:
        captured_at = parse_datetime(captured_at_str)
    if not captured_at:
        captured_at = timezone.now()

    report = SessionReport.objects.create(
        project_name=project_name[:200],
        title=body.get("title", "")[:300],
        content=content,
        branch=body.get("branch", "")[:255],
        captured_at=captured_at,
        machine=body.get("machine", "mac")[:50],
    )

    return JsonResponse(
        {
            "success": True,
            "message": "Report saved",
            "data": {
                "id": report.pk,
                "project_name": report.project_name,
                "captured_at": report.captured_at.isoformat(),
            },
        },
        status=201,
    )


@csrf_exempt
@require_GET
@require_api_key
def session_report_detail_api(request: HttpRequest, pk: int) -> JsonResponse:
    try:
        report = SessionReport.objects.get(pk=pk)
    except SessionReport.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Report not found", "data": None},
            status=404,
        )

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "id": report.pk,
            "project_name": report.project_name,
            "title": report.title,
            "content": report.content,
            "branch": report.branch,
            "captured_at": report.captured_at.isoformat(),
            "received_at": report.received_at.isoformat(),
            "machine": report.machine,
        },
    })
