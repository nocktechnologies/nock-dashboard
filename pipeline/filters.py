import django_filters

from .models import PullRequest, Repository


class PullRequestFilter(django_filters.FilterSet):
    repository = django_filters.ModelChoiceFilter(
        queryset=Repository.objects.filter(is_active=True).order_by("owner", "name"),
        label="Repository",
        empty_label="All repos",
    )
    state = django_filters.ChoiceFilter(
        choices=[("", "All states")] + list(PullRequest.State.choices),
        label="State",
    )
    coderabbit_status = django_filters.ChoiceFilter(
        choices=[("", "All CR status")] + list(PullRequest.CodeRabbitStatus.choices),
        label="CodeRabbit",
    )
    ci_status = django_filters.ChoiceFilter(
        choices=[("", "All CI status")] + list(PullRequest.CIStatus.choices),
        label="CI",
    )

    class Meta:
        model = PullRequest
        fields = ["repository", "state", "coderabbit_status", "ci_status"]
