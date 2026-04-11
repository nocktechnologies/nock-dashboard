import django_filters
from django.utils import timezone

from .models import AsanaProject, AsanaTask


class AsanaTaskFilter(django_filters.FilterSet):
    project = django_filters.ModelChoiceFilter(
        queryset=AsanaProject.objects.filter(is_active=True).order_by("name"),
        label="Project",
        empty_label="All projects",
    )
    priority = django_filters.ChoiceFilter(
        choices=[
            ("", "All priorities"),
            ("high", "High"),
            ("medium", "Medium"),
            ("low", "Low"),
        ],
        label="Priority",
    )
    overdue = django_filters.ChoiceFilter(
        choices=[("", "All"), ("yes", "Overdue only"), ("no", "Not overdue")],
        label="Overdue",
        method="filter_overdue",
    )

    def filter_overdue(self, queryset, name: str, value: str):
        today = timezone.localdate()
        if value == "yes":
            return queryset.filter(due_on__lt=today, completed=False)
        if value == "no":
            return queryset.exclude(due_on__lt=today).filter(completed=False)
        return queryset

    class Meta:
        model = AsanaTask
        fields = ["project", "priority", "overdue"]
