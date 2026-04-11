import csv
import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Case, F, Sum, Value, When
from django.db.models.functions import TruncMonth
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from core.auth import require_api_key
from pipeline.models import PullRequest

from .forms import ExpenseForm, RevenueForm
from .models import Expense, Revenue, SpendBudget, SubscriptionTracker, UsagePeriod


def _get_month_bounds() -> tuple:
    """Return (first_of_month, now) as dates."""
    now = timezone.now().date()
    first = now.replace(day=1)
    return first, now


def _mtd_spend() -> Decimal:
    first, _ = _get_month_bounds()
    return (
        UsagePeriod.objects.filter(date__gte=first)
        .aggregate(total=Sum("cost_usd"))["total"]
    ) or Decimal("0")


def _today_spend() -> Decimal:
    today = timezone.now().date()
    return (
        UsagePeriod.objects.filter(date=today)
        .aggregate(total=Sum("cost_usd"))["total"]
    ) or Decimal("0")


def _projected_month_end() -> Decimal:
    """Linear extrapolation of month-to-date spend."""
    first, today = _get_month_bounds()
    days_elapsed = (today - first).days + 1
    if days_elapsed <= 0:
        return Decimal("0")
    # Days in month
    if first.month == 12:
        next_month = first.replace(year=first.year + 1, month=1)
    else:
        next_month = first.replace(month=first.month + 1)
    days_in_month = (next_month - first).days
    mtd = _mtd_spend()
    return (mtd / days_elapsed) * days_in_month


def _cost_per_pr() -> Decimal | None:
    """Month spend / PRs merged this month."""
    first, _ = _get_month_bounds()
    merged_count = PullRequest.objects.filter(
        state=PullRequest.State.MERGED,
        merged_at__date__gte=first,
    ).count()
    if not merged_count:
        return None
    return _mtd_spend() / merged_count


def _expense_totals() -> dict[str, Decimal]:
    """Compute expense totals: gross, refunds, net, tax."""
    agg = Expense.objects.aggregate(
        gross=Sum(
            Case(
                When(is_refund=False, then=F("total")),
                default=Value(Decimal("0")),
            )
        ),
        refunds=Sum(
            Case(
                When(is_refund=True, then=F("total")),
                default=Value(Decimal("0")),
            )
        ),
        tax_gross=Sum(
            Case(
                When(is_refund=False, then=F("tax")),
                default=Value(Decimal("0")),
            )
        ),
        tax_refunds=Sum(
            Case(
                When(is_refund=True, then=F("tax")),
                default=Value(Decimal("0")),
            )
        ),
    )
    gross = agg["gross"] or Decimal("0")
    refunds = agg["refunds"] or Decimal("0")
    tax_gross = agg["tax_gross"] or Decimal("0")
    tax_refunds = agg["tax_refunds"] or Decimal("0")
    return {
        "gross": gross,
        "refunds": refunds,
        "net": gross - refunds,
        "tax": tax_gross - tax_refunds,
    }


def _category_breakdown() -> list[dict]:
    """Expense totals grouped by category, net of refunds."""
    rows = (
        Expense.objects.values("category")
        .annotate(
            cat_gross=Sum(
                Case(
                    When(is_refund=False, then=F("total")),
                    default=Value(Decimal("0")),
                )
            ),
            cat_refunds=Sum(
                Case(
                    When(is_refund=True, then=F("total")),
                    default=Value(Decimal("0")),
                )
            ),
        )
        .order_by("-cat_gross", "category")
    )
    result = []
    for r in rows:
        gross = r["cat_gross"] or Decimal("0")
        refunds = r["cat_refunds"] or Decimal("0")
        net = gross - refunds
        if net > 0:
            label = dict(Expense.CATEGORIES).get(r["category"], r["category"])
            result.append({"category": r["category"], "label": label, "total": net})
    return result


def _payment_method_breakdown() -> list[dict]:
    """Expense totals grouped by payment method, net of refunds."""
    rows = (
        Expense.objects.values("payment_method")
        .annotate(
            pm_gross=Sum(
                Case(
                    When(is_refund=False, then=F("total")),
                    default=Value(Decimal("0")),
                )
            ),
            pm_refunds=Sum(
                Case(
                    When(is_refund=True, then=F("total")),
                    default=Value(Decimal("0")),
                )
            ),
        )
        .order_by("-pm_gross", "payment_method")
    )
    result = []
    for r in rows:
        gross = r["pm_gross"] or Decimal("0")
        refunds = r["pm_refunds"] or Decimal("0")
        net = gross - refunds
        if net > 0:
            label = dict(Expense.PAYMENT_METHODS).get(r["payment_method"], r["payment_method"])
            result.append({"method": r["payment_method"], "label": label, "total": net})
    return result


def _monthly_expense_series() -> list[dict]:
    """Monthly expense totals for bar chart, net of refunds."""
    rows = (
        Expense.objects.annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(
            gross=Sum(
                Case(When(is_refund=False, then=F("total")), default=Value(Decimal("0")))
            ),
            refunds=Sum(
                Case(When(is_refund=True, then=F("total")), default=Value(Decimal("0")))
            ),
        )
        .order_by("month")
    )
    result = []
    for r in rows:
        m = r["month"]
        month_str = str(m.date()) if hasattr(m, "date") else str(m)
        net = (r["gross"] or Decimal("0")) - (r["refunds"] or Decimal("0"))
        result.append({"month": month_str, "total": net})
    return result


@require_GET
@login_required
def spend_dashboard(request: HttpRequest) -> HttpResponse:
    """Full spend dashboard with charts and tables."""
    first_of_month, today = _get_month_bounds()
    thirty_days_ago = today - timedelta(days=29)

    # Summary stats
    mtd = _mtd_spend()
    today_cost = _today_spend()
    projected = _projected_month_end()
    cost_pr = _cost_per_pr()

    # Budget
    budget = SpendBudget.objects.filter(month=first_of_month).first()
    budget_pct = 0
    if budget and budget.budget_usd > 0:
        budget_pct = int((mtd / budget.budget_usd) * 100)

    # Subscriptions
    subs = SubscriptionTracker.objects.filter(is_active=True).order_by("name")
    subs_total = subs.aggregate(total=Sum("monthly_cost"))["total"] or Decimal("0")

    # Expense totals
    exp_totals = _expense_totals()

    # Category & payment method breakdowns
    cat_breakdown = _category_breakdown()
    pm_breakdown = _payment_method_breakdown()
    monthly_series = _monthly_expense_series()

    # Expense log with filters
    expenses_qs = Expense.objects.all().order_by("-date", "vendor")
    expense_category = request.GET.get("expense_category", "")
    expense_payment = request.GET.get("expense_payment", "")
    has_expense_filters = bool(expense_category or expense_payment)
    if expense_category:
        expenses_qs = expenses_qs.filter(category=expense_category)
    if expense_payment:
        expenses_qs = expenses_qs.filter(payment_method=expense_payment)

    # Filtered totals for table footer (differs from overall when filters active)
    filtered_agg = expenses_qs.aggregate(
        f_gross=Sum(
            Case(When(is_refund=False, then=F("total")), default=Value(Decimal("0")))
        ),
        f_refunds=Sum(
            Case(When(is_refund=True, then=F("total")), default=Value(Decimal("0")))
        ),
        f_tax=Sum(
            Case(When(is_refund=False, then=F("tax")), default=Value(Decimal("0")))
        ),
    )
    filtered_totals = {
        "net": (filtered_agg["f_gross"] or Decimal("0")) - (filtered_agg["f_refunds"] or Decimal("0")),
        "tax": filtered_agg["f_tax"] or Decimal("0"),
    }

    # Daily data for charts (last 30 days)
    daily_qs = (
        UsagePeriod.objects.filter(date__gte=thirty_days_ago)
        .values("date", "model")
        .annotate(
            total_cost=Sum("cost_usd"),
            total_input=Sum("input_tokens"),
            total_output=Sum("output_tokens"),
            total_requests=Sum("request_count"),
        )
        .order_by("date", "model")
    )

    # Model breakdown for current month
    model_breakdown = (
        UsagePeriod.objects.filter(date__gte=first_of_month)
        .values("model")
        .annotate(total_cost=Sum("cost_usd"))
        .order_by("-total_cost")
    )

    # Most expensive model
    most_expensive = model_breakdown.first()

    # Daily table data
    daily_table = (
        UsagePeriod.objects.filter(date__gte=thirty_days_ago)
        .select_related()
        .order_by("-date", "model")
    )

    # Filter params
    model_filter = request.GET.get("model", "")
    if model_filter:
        daily_table = daily_table.filter(model__icontains=model_filter)

    # Average daily spend
    days_with_data = (
        UsagePeriod.objects.filter(date__gte=thirty_days_ago)
        .values("date").distinct().count()
    )
    avg_daily = Decimal("0")
    if days_with_data:
        total_30d = (
            UsagePeriod.objects.filter(date__gte=thirty_days_ago)
            .aggregate(total=Sum("cost_usd"))["total"]
        ) or Decimal("0")
        avg_daily = total_30d / days_with_data

    # Prepare chart data as JSON
    daily_chart_data = [
        {
            "date": str(r["date"]),
            "model": r["model"],
            "cost": str(r["total_cost"] or 0),
            "input_tokens": r["total_input"] or 0,
            "output_tokens": r["total_output"] or 0,
        }
        for r in daily_qs
    ]

    model_chart_data = [
        {"model": r["model"], "cost": str(r["total_cost"] or 0)}
        for r in model_breakdown
    ]

    category_chart_data = [
        {"label": c["label"], "total": str(c["total"])}
        for c in cat_breakdown
    ]

    payment_chart_data = [
        {"label": p["label"], "total": str(p["total"])}
        for p in pm_breakdown
    ]

    monthly_chart_data = [
        {"month": m["month"], "total": str(m["total"])}
        for m in monthly_series
    ]

    # Get distinct models for filter
    models_list = (
        UsagePeriod.objects.values_list("model", flat=True)
        .distinct()
        .order_by("model")
    )

    return render(request, "spend/dashboard.html", {
        "mtd_spend": mtd,
        "today_spend": today_cost,
        "projected": projected,
        "cost_per_pr": cost_pr,
        "budget": budget,
        "budget_pct": budget_pct,
        "subs": subs,
        "subs_total": subs_total,
        "subs_annual": subs_total * 12,
        "daily_table": daily_table[:100],
        "most_expensive": most_expensive,
        "avg_daily": avg_daily,
        "daily_chart_json": json.dumps(daily_chart_data),
        "model_chart_json": json.dumps(model_chart_data),
        "category_chart_json": json.dumps(category_chart_data),
        "payment_chart_json": json.dumps(payment_chart_data),
        "monthly_chart_json": json.dumps(monthly_chart_data),
        "models_list": models_list,
        "model_filter": model_filter,
        # Expense data
        "expenses": expenses_qs,
        "expense_totals": exp_totals,
        "expense_category": expense_category,
        "expense_payment": expense_payment,
        "expense_categories": Expense.CATEGORIES,
        "expense_payment_methods": Expense.PAYMENT_METHODS,
        "filtered_totals": filtered_totals,
        "has_expense_filters": has_expense_filters,
    })


@require_http_methods(["GET", "POST"])
@login_required
def add_expense(request: HttpRequest) -> HttpResponse:
    """Mobile-friendly expense entry form."""
    vendors = list(
        Expense.objects.values_list("vendor", flat=True).distinct().order_by("vendor")
    )
    if request.method == "POST":
        form = ExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                form.save()
            messages.success(request, "Expense added.")
            return redirect("spend:dashboard")
    else:
        form = ExpenseForm(initial={"date": timezone.now().date(), "tax": Decimal("0")})
    return render(request, "spend/add_expense.html", {
        "form": form,
        "vendors_json": vendors,
    })


@require_http_methods(["GET", "POST"])
@login_required
def add_revenue(request: HttpRequest) -> HttpResponse:
    """Mobile-friendly revenue entry form."""
    if request.method == "POST":
        form = RevenueForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                form.save()
            messages.success(request, "Revenue recorded.")
            return redirect("spend:pnl")
    else:
        form = RevenueForm(initial={"date": timezone.now().date()})
    return render(request, "spend/add_revenue.html", {"form": form})


@require_GET
@login_required
def pnl_view(request: HttpRequest) -> HttpResponse:
    """Profit & Loss dashboard."""
    # Revenue
    total_revenue = Revenue.objects.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    revenue_by_source = (
        Revenue.objects.values("source")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )
    monthly_revenue = (
        Revenue.objects.annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total=Sum("amount"))
        .order_by("month")
    )

    # Expenses (net of refunds)
    exp_totals = _expense_totals()
    monthly_expenses = _monthly_expense_series()

    # Net position
    net_position = total_revenue - exp_totals["net"]

    # Monthly P&L chart data
    # Merge revenue and expense series by month
    rev_map: dict[str, Decimal] = {}
    for r in monthly_revenue:
        m = r["month"]
        key = str(m.date()) if hasattr(m, "date") else str(m)
        rev_map[key] = r["total"] or Decimal("0")

    exp_map: dict[str, Decimal] = {}
    for e in monthly_expenses:
        exp_map[e["month"]] = e["total"]

    all_months = sorted(set(list(rev_map.keys()) + list(exp_map.keys())))
    pnl_chart_data = [
        {
            "month": m[:7],
            "revenue": str(rev_map.get(m, Decimal("0"))),
            "expenses": str(exp_map.get(m, Decimal("0"))),
        }
        for m in all_months
    ]

    # Subscriptions for burn rate
    subs_total = (
        SubscriptionTracker.objects.filter(is_active=True)
        .aggregate(total=Sum("monthly_cost"))["total"]
    ) or Decimal("0")

    revenue_sources_data = [
        {"source": dict(Revenue.SOURCES).get(r["source"], r["source"]), "total": str(r["total"])}
        for r in revenue_by_source
    ]

    return render(request, "spend/pnl.html", {
        "total_revenue": total_revenue,
        "total_expenses": exp_totals["net"],
        "net_position": net_position,
        "subs_total": subs_total,
        "revenue_by_source": revenue_by_source,
        "revenue_sources": Revenue.SOURCES,
        "pnl_chart_json": json.dumps(pnl_chart_data),
        "revenue_sources_json": json.dumps(revenue_sources_data),
    })


@require_GET
@login_required
def tax_view(request: HttpRequest) -> HttpResponse:
    """Tax preparation view — expenses grouped by IRS deductibility."""
    TAX_CATEGORIES = [
        {
            "key": "section_179",
            "title": "Section 179 / Depreciable Assets",
            "description": "Hardware purchases — fully deductible in year of purchase under Section 179.",
            "db_categories": ["hardware"],
        },
        {
            "key": "ordinary",
            "title": "Ordinary Business Expenses",
            "description": "Software subscriptions, SaaS tools, and recurring services.",
            "db_categories": ["software", "infrastructure"],
        },
        {
            "key": "startup",
            "title": "Startup / Organizational Costs",
            "description": "Business formation, LLC filing, DBA registration. Up to $5K deductible first year, remainder amortized over 15 years.",
            "db_categories": ["formation"],
        },
        {
            "key": "legal",
            "title": "Legal & Professional Fees",
            "description": "Trademark filing, attorney fees, accounting services.",
            "db_categories": ["legal"],
        },
        {
            "key": "branding",
            "title": "Domain & Branding",
            "description": "Domain registrations, branding assets.",
            "db_categories": ["domains"],
        },
    ]

    try:
        rate_val = Decimal(request.GET.get("rate", "24"))
        if not rate_val.is_finite() or rate_val < 0 or rate_val > 100:
            rate_val = Decimal("24")
        marginal_rate = rate_val / Decimal("100")
    except (ValueError, ArithmeticError, InvalidOperation):
        marginal_rate = Decimal("24") / Decimal("100")
    grand_total = Decimal("0")
    total_tax = Decimal("0")

    for cat in TAX_CATEGORIES:
        expenses = (
            Expense.objects.filter(
                category__in=cat["db_categories"],
                is_refund=False,
            ).order_by("-date", "vendor")
        )
        cat_total = expenses.aggregate(
            total=Sum("total"), tax=Sum("tax")
        )
        cat["expenses"] = expenses
        cat["total"] = cat_total["total"] or Decimal("0")
        cat["tax"] = cat_total["tax"] or Decimal("0")
        cat["count"] = expenses.count()
        grand_total += cat["total"]
        total_tax += cat["tax"]

    # Uncategorized (other)
    other_expenses = Expense.objects.filter(
        category="other", is_refund=False
    ).order_by("-date", "vendor")
    other_total = other_expenses.aggregate(total=Sum("total"))["total"] or Decimal("0")
    other_tax = other_expenses.aggregate(tax=Sum("tax"))["tax"] or Decimal("0")
    if other_expenses.exists():
        TAX_CATEGORIES.append({
            "key": "other",
            "title": "Other Expenses",
            "description": "Expenses that don't fit standard IRS categories.",
            "expenses": other_expenses,
            "total": other_total,
            "tax": other_tax,
            "count": other_expenses.count(),
        })
        grand_total += other_total
        total_tax += other_tax

    estimated_savings = grand_total * marginal_rate

    return render(request, "spend/tax.html", {
        "tax_categories": TAX_CATEGORIES,
        "grand_total": grand_total,
        "total_tax": total_tax,
        "estimated_savings": estimated_savings,
        "marginal_rate": int(marginal_rate * 100),
    })


@require_GET
@login_required
def tax_export_csv(request: HttpRequest) -> HttpResponse:
    """Export all expenses as CSV for accountant."""
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="nockcc_expenses.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "Date", "Vendor", "Description", "Category", "Subtotal",
        "Tax", "Total", "Is Refund", "Payment Method", "Reference",
    ])
    def _sanitize_csv_cell(value: object) -> object:
        """Prefix cells that start with formula characters to prevent injection."""
        s = str(value)
        if s and s[0] in ("=", "+", "-", "@"):
            return f"'{s}"
        return value

    for e in Expense.objects.filter(is_refund=False).order_by("date", "vendor"):
        writer.writerow([
            e.date, _sanitize_csv_cell(e.vendor),
            _sanitize_csv_cell(e.description), e.get_category_display(),
            e.subtotal, e.tax, e.total, e.is_refund,
            e.get_payment_method_display(), _sanitize_csv_cell(e.reference),
        ])
    return response


@csrf_exempt
@require_GET
@require_api_key
def spend_summary_api(request: HttpRequest) -> JsonResponse:
    """JSON API for dashboard widget — spend summary."""
    first_of_month, _ = _get_month_bounds()
    mtd = _mtd_spend()
    today_cost = _today_spend()
    projected = _projected_month_end()

    budget = SpendBudget.objects.filter(month=first_of_month).first()
    budget_total = budget.budget_usd if budget else None
    budget_pct = 0
    if budget and budget.budget_usd > 0:
        budget_pct = int((mtd / budget.budget_usd) * 100)

    subs_total = (
        SubscriptionTracker.objects.filter(is_active=True)
        .aggregate(total=Sum("monthly_cost"))["total"]
    ) or Decimal("0")

    exp_totals = _expense_totals()

    # Revenue MTD
    total_revenue = (
        Revenue.objects.aggregate(total=Sum("amount"))["total"]
    ) or Decimal("0")

    # Computed fields for mobile app
    total_spend = exp_totals["net"] + mtd
    burn_rate = subs_total

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "today_spend": str(today_cost),
            "mtd_spend": str(mtd),
            "budget_total": str(budget_total) if budget_total else None,
            "budget_pct": budget_pct,
            "projected_month_end": str(projected),
            "subscriptions_total": str(subs_total),
            "expense_total": str(exp_totals["net"]),
            "expense_tax": str(exp_totals["tax"]),
            # Mobile-friendly fields
            "total_spend": str(total_spend),
            "burn_rate": str(burn_rate),
            "revenue_mtd": str(total_revenue),
        },
    })


@csrf_exempt
@require_GET
@require_api_key
def spend_daily_api(request: HttpRequest) -> JsonResponse:
    """JSON API for charts — daily spend data."""
    try:
        days = int(request.GET.get("days", 30))
    except ValueError:
        return JsonResponse(
            {"success": False, "message": "days must be an integer", "data": None},
            status=400,
        )
    days = max(1, min(days, 90))

    start_date = timezone.now().date() - timedelta(days=days - 1)
    records = (
        UsagePeriod.objects.filter(date__gte=start_date)
        .values("date", "model")
        .annotate(
            total_input=Sum("input_tokens"),
            total_output=Sum("output_tokens"),
            total_cost=Sum("cost_usd"),
            total_requests=Sum("request_count"),
        )
        .order_by("date", "model")
    )

    data = [
        {
            "date": str(r["date"]),
            "model": r["model"],
            "input_tokens": r["total_input"] or 0,
            "output_tokens": r["total_output"] or 0,
            "cost_usd": str(r["total_cost"] or 0),
            "request_count": r["total_requests"] or 0,
        }
        for r in records
    ]

    return JsonResponse({"success": True, "message": "ok", "data": data})


@csrf_exempt
@require_GET
@require_api_key
def expenses_api(request: HttpRequest) -> JsonResponse:
    """JSON API — list all expenses with optional filters."""
    qs = Expense.objects.all().order_by("-date", "vendor")

    category = request.GET.get("category", "")
    payment_method = request.GET.get("payment_method", "")
    if category:
        qs = qs.filter(category=category)
    if payment_method:
        qs = qs.filter(payment_method=payment_method)

    data = [
        {
            "id": e.id,
            "date": str(e.date),
            "vendor": e.vendor,
            "description": e.description,
            "category": e.category,
            "category_display": e.get_category_display(),
            "subtotal": str(e.subtotal),
            "tax": str(e.tax),
            "total": str(e.total),
            "is_refund": e.is_refund,
            "payment_method": e.payment_method,
            "payment_method_display": e.get_payment_method_display(),
            "reference": e.reference,
            "has_receipt": bool(e.receipt),
        }
        for e in qs
    ]

    return JsonResponse({"success": True, "message": "ok", "data": data})


@csrf_exempt
@require_GET
@require_api_key
def subscriptions_api(request: HttpRequest) -> JsonResponse:
    """JSON API — list active subscriptions."""
    subs = SubscriptionTracker.objects.filter(is_active=True).order_by("name")
    subs_total = subs.aggregate(total=Sum("monthly_cost"))["total"] or Decimal("0")

    data = [
        {
            "id": s.id,
            "name": s.name,
            "provider": s.provider,
            "provider_display": s.get_provider_display(),
            "monthly_cost": str(s.monthly_cost),
            "renewal_date": str(s.renewal_date),
            "notes": s.notes,
        }
        for s in subs
    ]

    return JsonResponse({
        "success": True,
        "message": "ok",
        "data": {
            "subscriptions": data,
            "monthly_total": str(subs_total),
            "annual_projection": str(subs_total * 12),
        },
    })
