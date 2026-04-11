from django.urls import path

from . import views

urlpatterns = [
    path("api/projects/", views.ProjectListCreateView.as_view(), name="projects-list"),
    path("api/projects/<slug:slug>/", views.ProjectDetailView.as_view(), name="projects-detail"),
    path(
        "api/projects/<slug:slug>/sections/",
        views.ProjectSectionListCreateView.as_view(),
        name="projects-sections",
    ),
    path("api/sections/<int:pk>/", views.SectionDetailView.as_view(), name="sections-detail"),
    path("api/sections/<int:pk>/reorder/", views.SectionReorderView.as_view(), name="sections-reorder"),
    path("api/tasks/dashboard/", views.TaskDashboardView.as_view(), name="tasks-dashboard"),
    path("api/tasks/overdue/", views.TaskOverdueView.as_view(), name="tasks-overdue"),
    path("api/tasks/today/", views.TaskTodayView.as_view(), name="tasks-today"),
    path("api/tasks/upcoming/", views.TaskUpcomingView.as_view(), name="tasks-upcoming"),
    path("api/tasks/", views.TaskListCreateView.as_view(), name="tasks-list"),
    path("api/tasks/<int:pk>/", views.TaskDetailView.as_view(), name="tasks-detail"),
    path("api/tasks/<int:pk>/complete/", views.TaskCompleteView.as_view(), name="tasks-complete"),
    path("api/tasks/<int:pk>/reopen/", views.TaskReopenView.as_view(), name="tasks-reopen"),
    path("api/tasks/<int:pk>/move/", views.TaskMoveView.as_view(), name="tasks-move"),
    path("api/tasks/<int:pk>/comments/", views.TaskCommentListCreateView.as_view(), name="tasks-comments"),
    path("api/comments/<int:pk>/", views.CommentDetailView.as_view(), name="comments-detail"),
]
