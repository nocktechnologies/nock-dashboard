from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("healthz/", views.healthz, name="healthz"),
    path("", views.index, name="index"),
    path("api/pipeline/status/", views.pipeline_status_api, name="pipeline-status-api"),
    path("api/dashboard/sessions/", views.active_sessions_api, name="active-sessions-api"),
    path("api/dashboard/summary/", views.dashboard_summary_api, name="dashboard-summary-api"),
    path("api/dashboard/executive/", views.executive_dashboard_api, name="executive-dashboard-api"),
    # PM plugin dashboard (frontend for the projects/ app)
    path("pm/", views.pm_dashboard, name="pm"),
    path("pm/tasks/", views.pm_tasks_all, name="pm-tasks-all"),
    path("pm/<slug:slug>/", views.pm_project_detail, name="pm-project-detail"),
]
