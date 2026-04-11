from django.urls import path

from .views import (
    GitHubWebhookView,
    event_summary,
    list_events,
    log_event,
    pipeline_list,
    pipeline_prs_api,
    pr_detail,
    review_alerts_list,
    review_alerts_read,
    review_alerts_summary,
    telegram_test,
)

app_name = "pipeline"

urlpatterns = [
    path("webhooks/github/", GitHubWebhookView.as_view(), name="github-webhook"),
    path("pipeline/", pipeline_list, name="list"),
    path("pipeline/<str:repo_owner>/<str:repo_name>/<int:pr_number>/", pr_detail, name="detail"),
    path("api/pipeline/prs/", pipeline_prs_api, name="pipeline-prs-api"),
    path("api/pipeline/events/", log_event, name="log-event"),
    path("api/pipeline/events/list/", list_events, name="list-events"),
    path("api/pipeline/events/summary/", event_summary, name="event-summary"),
    path("api/alerts/reviews/", review_alerts_list, name="review-alerts-list"),
    path("api/alerts/reviews/read/", review_alerts_read, name="review-alerts-read"),
    path("api/alerts/reviews/summary/", review_alerts_summary, name="review-alerts-summary"),
    path("api/telegram/test/", telegram_test, name="telegram-test"),
]
