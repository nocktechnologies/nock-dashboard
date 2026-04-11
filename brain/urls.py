from django.urls import path

from . import diary_views, views

app_name = "brain"

urlpatterns = [
    path("", views.brain_index, name="index"),
    path("diary/", diary_views.diary_browser, name="diary"),
    path("handoffs/", views.handoffs_browser, name="handoffs"),
    path("research/", views.research_browser, name="research"),
]
