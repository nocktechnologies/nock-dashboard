# tasks/api_urls.py
"""URL patterns for the Asana write-back / cross-project read API.

Mounted at `/api/tasks/` from config/urls.py. The web dashboard views in
tasks/urls.py continue to be served at root for backwards compatibility.
"""
from django.urls import path

from . import views_api

app_name = "tasks_api"

urlpatterns = [
    # Cross-project read endpoints (hit local DB only — fast path for crons).
    path("all/", views_api.list_tasks_view, name="list"),
    path("overdue/", views_api.overdue_tasks_view, name="overdue"),
    path("today/", views_api.today_tasks_view, name="today"),
    path("summary/", views_api.summary_view, name="summary"),
    path("sections/<str:project_gid>/", views_api.sections_view, name="sections"),

    # Write-back endpoints (Asana-first — local DB is mirrored on success).
    path("create/", views_api.create_task_view, name="create"),
    path("<str:asana_gid>/update/", views_api.update_task_view, name="update"),
    path("<str:asana_gid>/complete/", views_api.complete_task_view, name="complete"),
    path("<str:asana_gid>/uncomplete/", views_api.uncomplete_task_view, name="uncomplete"),
    path("<str:asana_gid>/move/", views_api.move_task_view, name="move"),
    path("<str:asana_gid>/comment/", views_api.comment_task_view, name="comment"),
    path("<str:asana_gid>/delete/", views_api.delete_task_view, name="delete"),
]
