from django.urls import path

from . import views

app_name = "context"

urlpatterns = [
    path("", views.context_list, name="list"),
    path("<int:doc_id>/", views.context_detail, name="detail"),
    path("api/health/", views.context_health_api, name="health-api"),
]
