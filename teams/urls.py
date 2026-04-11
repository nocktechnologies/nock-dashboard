from django.urls import path

from . import views

app_name = "teams"

urlpatterns = [
    path("teams/", views.teams_page, name="teams-page"),
    path("prompts/", views.prompts_page, name="prompts-page"),
]
