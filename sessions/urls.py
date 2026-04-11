from django.urls import path

from . import views

app_name = "sessions"

urlpatterns = [
    # Page route
    path("sessions/", views.session_list_page, name="list"),
    # REST API
    path("api/sessions/active/", views.session_active, name="api-active"),
    path("api/sessions/cleanup/", views.cleanup_stale_sessions_view, name="api-cleanup"),
    path("api/sessions/<int:session_id>/end/", views.session_end, name="api-end"),
    path("api/sessions/<int:session_id>/log/", views.session_log, name="api-log"),
    path("api/sessions/<int:session_id>/", views.session_detail, name="api-detail"),
    path("api/sessions/", views.session_list_create, name="api-list-create"),
]
