import json
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from core.auth import require_api_key

from .forms import ContactForm, DealForm, DealNoteForm
from .models import Contact, Deal


@require_GET
@login_required
def pipeline_view(request: HttpRequest) -> HttpResponse:
    """CRM pipeline — kanban or table view."""
    view_mode = request.GET.get("view", "kanban")
    deals = Deal.objects.select_related("contact").all()

    # Summary stats
    open_deals = deals.filter(~Q(stage__in=["closed_won", "closed_lost"]))
    pipeline_value = open_deals.aggregate(
        total=Sum("estimated_value")
    )["total"] or Decimal("0")

    won = deals.filter(stage="closed_won").count()
    lost = deals.filter(stage="closed_lost").count()
    win_rate = 0
    if won + lost > 0:
        win_rate = int((won / (won + lost)) * 100)

    # Deals needing action this week
    today = timezone.now().date()
    week_end = today + timezone.timedelta(days=7)
    action_needed = open_deals.filter(
        next_action_date__lte=week_end,
        next_action_date__isnull=False,
    ).count()

    # Stage counts for kanban
    stages = []
    for key, label in Deal.STAGES:
        stage_deals = deals.filter(stage=key).order_by("-updated_at")
        stages.append({
            "key": key,
            "label": label,
            "deals": stage_deals,
            "count": stage_deals.count(),
        })

    return render(request, "crm/pipeline.html", {
        "stages": stages,
        "deals": deals,
        "view_mode": view_mode,
        "total_deals": open_deals.count(),
        "pipeline_value": pipeline_value,
        "win_rate": win_rate,
        "action_needed": action_needed,
    })


@require_http_methods(["GET", "POST"])
@login_required
def deal_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = DealForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Deal created.")
            return redirect("crm:pipeline")
    else:
        form = DealForm()
    return render(request, "crm/deal_form.html", {"form": form, "editing": False})


@require_http_methods(["GET", "POST"])
@login_required
def deal_detail(request: HttpRequest, pk: int) -> HttpResponse:
    deal = get_object_or_404(Deal.objects.select_related("contact"), pk=pk)
    notes = deal.deal_notes.all()
    note_form = DealNoteForm()

    if request.method == "POST":
        if "add_note" in request.POST:
            note_form = DealNoteForm(request.POST)
            if note_form.is_valid():
                note = note_form.save(commit=False)
                note.deal = deal
                note.save()
                messages.success(request, "Note added.")
                return redirect("crm:deal-detail", pk=deal.pk)
        elif "update_stage" in request.POST:
            new_stage = request.POST.get("stage", "")
            valid = [s[0] for s in Deal.STAGES]
            if new_stage in valid:
                with transaction.atomic():
                    deal.stage = new_stage
                    if new_stage in ("closed_won", "closed_lost"):
                        deal.closed_at = timezone.now().date()
                    else:
                        deal.closed_at = None
                    deal.save()
                messages.success(request, f"Stage updated to {deal.get_stage_display()}.")
                return redirect("crm:deal-detail", pk=deal.pk)

    return render(request, "crm/deal_detail.html", {
        "deal": deal,
        "notes": notes,
        "note_form": note_form,
        "stage_choices": Deal.STAGES,
    })


@require_http_methods(["GET", "POST"])
@login_required
def deal_edit(request: HttpRequest, pk: int) -> HttpResponse:
    deal = get_object_or_404(Deal, pk=pk)
    if request.method == "POST":
        form = DealForm(request.POST, instance=deal)
        if form.is_valid():
            form.save()
            messages.success(request, "Deal updated.")
            return redirect("crm:deal-detail", pk=deal.pk)
    else:
        form = DealForm(instance=deal)
    return render(request, "crm/deal_form.html", {"form": form, "editing": True, "deal": deal})


@require_GET
@login_required
def contact_list(request: HttpRequest) -> HttpResponse:
    contacts = Contact.objects.annotate(deal_count=Count("deals")).all()
    q = request.GET.get("q", "")
    if q:
        contacts = contacts.filter(
            Q(name__icontains=q) | Q(company__icontains=q) | Q(email__icontains=q)
        )
    return render(request, "crm/contacts.html", {"contacts": contacts, "search": q})


@require_http_methods(["GET", "POST"])
@login_required
def contact_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Contact created.")
            return redirect("crm:contacts")
    else:
        form = ContactForm()
    return render(request, "crm/contact_form.html", {"form": form, "editing": False})


@require_http_methods(["GET", "POST"])
@login_required
def contact_edit(request: HttpRequest, pk: int) -> HttpResponse:
    contact = get_object_or_404(Contact, pk=pk)
    if request.method == "POST":
        form = ContactForm(request.POST, instance=contact)
        if form.is_valid():
            form.save()
            messages.success(request, "Contact updated.")
            return redirect("crm:contacts")
    else:
        form = ContactForm(instance=contact)
    return render(request, "crm/contact_form.html", {
        "form": form, "editing": True, "contact": contact,
    })


# --- JSON API endpoints for mobile app ---


@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_api_key
def deals_api(request: HttpRequest) -> JsonResponse:
    """JSON API — list deals (GET) or create a deal (POST)."""
    if request.method == "POST":
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse(
                {"success": False, "message": "Invalid JSON", "data": None}, status=400
            )
        contact = None
        contact_id = body.get("contact_id")
        if contact_id:
            contact = Contact.objects.filter(pk=contact_id).first()
        deal = Deal.objects.create(
            title=body.get("title", ""),
            contact=contact,
            stage=body.get("stage", "prospect"),
            source=body.get("source", "other"),
            estimated_value=body.get("value") or body.get("estimated_value"),
            description=body.get("description", ""),
            next_action=body.get("next_action", ""),
            next_action_date=body.get("next_action_date"),
        )
        return JsonResponse({
            "success": True,
            "message": "Deal created",
            "data": {"id": deal.pk},
        }, status=201)

    deals = Deal.objects.select_related("contact").all()
    data = [
        {
            "id": d.pk,
            "title": d.title,
            "contact_name": str(d.contact) if d.contact else "",
            "value": float(d.display_value or 0),
            "stage": d.get_stage_display(),
            "next_action": d.next_action,
            "next_action_date": str(d.next_action_date) if d.next_action_date else None,
            "notes": d.description,
            "created_at": d.created_at.isoformat(),
            "updated_at": d.updated_at.isoformat(),
        }
        for d in deals
    ]
    return JsonResponse({"success": True, "message": "ok", "data": data})


@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_api_key
def contacts_api(request: HttpRequest) -> JsonResponse:
    """JSON API — list contacts (GET) or create a contact (POST)."""
    if request.method == "POST":
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse(
                {"success": False, "message": "Invalid JSON", "data": None}, status=400
            )
        contact = Contact.objects.create(
            name=body.get("name", ""),
            company=body.get("company", ""),
            email=body.get("email", ""),
            phone=body.get("phone", ""),
            role=body.get("role", ""),
            notes=body.get("notes", ""),
        )
        return JsonResponse({
            "success": True,
            "message": "Contact created",
            "data": {"id": contact.pk},
        }, status=201)

    contacts = Contact.objects.all()
    data = [
        {
            "id": c.pk,
            "name": c.name,
            "email": c.email,
            "phone": c.phone,
            "company": c.company,
            "role": c.role,
            "notes": c.notes,
        }
        for c in contacts
    ]
    return JsonResponse({"success": True, "message": "ok", "data": data})
