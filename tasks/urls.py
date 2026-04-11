from django.urls import path

from . import views

app_name = "tasks"

urlpatterns = [
    path("tasks/", views.task_feed, name="feed"),
    path("handoffs/", views.handoffs, name="handoffs"),
]
