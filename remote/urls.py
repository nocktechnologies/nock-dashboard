from django.urls import path

from . import views

app_name = "remote"

urlpatterns = [
    # Page views
    path("", views.control_page, name="control"),
    path(
        "session/<str:session_id>/",
        views.session_detail_page,
        name="session-detail",
    ),
    path("notifications/", views.notifications_page, name="notifications"),
    path("chat/", views.chat_page, name="chat"),
    # API endpoints
    path(
        "api/remote/commands/",
        views.command_list_create,
        name="command-list-create",
    ),
    path(
        "api/remote/commands/<int:command_id>/",
        views.command_detail,
        name="command-detail",
    ),
    path(
        "api/remote/commands/<int:command_id>/cancel/",
        views.command_cancel,
        name="command-cancel",
    ),
    path(
        "api/remote/agent/status/",
        views.agent_status,
        name="agent-status",
    ),
    path(
        "api/remote/output/<str:session_id>/",
        views.session_output,
        name="session-output",
    ),
    path(
        "api/remote/output/<str:session_id>/push/",
        views.output_push,
        name="output-push",
    ),
    path(
        "api/remote/stream/<str:session_id>/",
        views.stream_output,
        name="stream-output",
    ),
    path(
        "api/remote/kill-all/",
        views.kill_all,
        name="kill-all",
    ),
    path(
        "api/remote/push/subscribe/",
        views.push_subscribe,
        name="push-subscribe",
    ),
    path(
        "api/remote/push/unsubscribe/",
        views.push_unsubscribe,
        name="push-unsubscribe",
    ),
    # Conversation API
    path(
        "api/remote/conversations/",
        views.conversation_list_create,
        name="conversation-list-create",
    ),
    path(
        "api/remote/conversations/<int:conversation_id>/",
        views.conversation_detail,
        name="conversation-detail",
    ),
    path(
        "api/remote/conversations/<int:conversation_id>/send/",
        views.conversation_send,
        name="conversation-send",
    ),
]
