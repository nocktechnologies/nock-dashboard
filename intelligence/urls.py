from django.urls import path

from . import views

app_name = "intelligence"

urlpatterns = [
    # Pages
    path("executive/", views.executive_dashboard, name="executive"),
    path("advisor/", views.advisor_page, name="advisor"),
    path("alerts/", views.alerts_page, name="alerts"),
    path("alerts/<int:pk>/resolve/", views.resolve_alert, name="resolve-alert"),

    # APIs
    path("api/alerts/", views.alerts_api, name="alerts-api"),
    path("api/executive/", views.executive_api, name="executive-api"),
    path("api/advisor/chat/", views.advisor_chat_api, name="advisor-chat-api"),
    path("api/advisor/conversations/", views.conversations_list_api, name="conversations-list-api"),
    path(
        "api/advisor/conversations/<int:pk>/",
        views.conversation_detail_api,
        name="conversation-detail-api",
    ),
    path("api/snapshot/latest/", views.snapshot_latest_api, name="snapshot-latest-api"),
    path("api/snapshot/generate/", views.snapshot_generate_api, name="snapshot-generate-api"),
    path("api/memo/generate/", views.memo_generate_api, name="memo-generate-api"),

    # Smart Watch
    path("api/smart-watch/rules/", views.smart_watch_rules_list, name="smart-watch-rules"),
    path("api/smart-watch/rules/create/", views.smart_watch_rules_create, name="smart-watch-rules-create"),
    path("api/smart-watch/rules/<int:pk>/", views.smart_watch_rules_update, name="smart-watch-rules-update"),
    path("api/smart-watch/events/", views.smart_watch_events_list, name="smart-watch-events"),
    path("api/smart-watch/tick/", views.smart_watch_force_tick, name="smart-watch-tick"),
    path("api/smart-watch/status/", views.smart_watch_status, name="smart-watch-status"),
]
