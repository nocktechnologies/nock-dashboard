from datetime import timedelta

from django.db.models import Case, F, IntegerField, Q, QuerySet, Value, When
from django.utils import timezone

from .models import Task

PRIORITY_RANK = {
    Task.PRIORITY_LOW: 1,
    Task.PRIORITY_MEDIUM: 2,
    Task.PRIORITY_HIGH: 3,
    Task.PRIORITY_URGENT: 4,
}


def with_priority_rank(queryset: QuerySet[Task]) -> QuerySet[Task]:
    return queryset.annotate(
        priority_rank=Case(
            *[When(priority=priority, then=Value(rank)) for priority, rank in PRIORITY_RANK.items()],
            default=Value(0),
            output_field=IntegerField(),
        ),
    )


def apply_task_filters(queryset: QuerySet[Task], params) -> QuerySet[Task]:
    today = timezone.localdate()

    project = params.get("project")
    if project:
        queryset = queryset.filter(project__slug=project)

    section = params.get("section")
    if section:
        queryset = queryset.filter(section_id=section)

    status = params.get("status")
    if status:
        queryset = queryset.filter(status=status)

    priority = params.get("priority")
    if priority:
        queryset = queryset.filter(priority=priority)

    assignee = params.get("assignee")
    if assignee:
        queryset = queryset.filter(assignee__iexact=assignee)

    completed = params.get("completed")
    if completed is not None:
        if completed.lower() == "true":
            queryset = queryset.filter(completed=True)
        elif completed.lower() == "false":
            queryset = queryset.filter(completed=False)

    due_before = params.get("due_before")
    if due_before:
        queryset = queryset.filter(due_date__lt=due_before)

    due_after = params.get("due_after")
    if due_after:
        queryset = queryset.filter(due_date__gt=due_after)

    if params.get("overdue", "").lower() == "true":
        queryset = queryset.filter(completed=False, due_date__lt=today, due_date__isnull=False)

    tag = params.get("tag")
    if tag:
        matching_ids = [pk for pk, tags in queryset.values_list("pk", "tags") if tag in (tags or [])]
        queryset = queryset.filter(pk__in=matching_ids)

    search = params.get("search")
    if search:
        queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))

    return apply_task_ordering(queryset, params.get("ordering"))


def apply_task_ordering(queryset: QuerySet[Task], ordering: str | None) -> QuerySet[Task]:
    if not ordering:
        return queryset.order_by("order", "created_at", "id")

    descending = ordering.startswith("-")
    field = ordering[1:] if descending else ordering

    if field == "priority":
        queryset = with_priority_rank(queryset)
        order_field = "-priority_rank" if descending else "priority_rank"
        return queryset.order_by(order_field, "order", "due_date", "created_at", "id")

    if field == "due_date":
        due_expression = F("due_date").desc(nulls_last=True) if descending else F("due_date").asc(nulls_last=True)
        return queryset.order_by(due_expression, "id")

    if field == "created_at":
        return queryset.order_by("-created_at" if descending else "created_at", "-id" if descending else "id")

    if field == "name":
        return queryset.order_by("-name" if descending else "name", "-id" if descending else "id")

    if field == "order":
        return queryset.order_by("-order" if descending else "order", "-id" if descending else "id")

    return queryset.order_by("order", "created_at", "id")


def upcoming_tasks_queryset(queryset: QuerySet[Task], days: int) -> QuerySet[Task]:
    today = timezone.localdate()
    cutoff = today + timedelta(days=days)
    return queryset.filter(completed=False, due_date__gte=today, due_date__lte=cutoff)
