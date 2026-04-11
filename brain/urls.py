from django.urls import path

from . import views

app_name = "brain"

urlpatterns = [
    path("", views.brain_index, name="index"),
    path("handoffs/", views.handoffs_browser, name="handoffs"),
    path("research/", views.research_browser, name="research"),
]
