from django.urls import path

from . import views

app_name = "vault"

urlpatterns = [
    path("", views.document_list, name="list"),
    path("upload/", views.document_upload, name="upload"),
    path("<int:pk>/", views.document_detail, name="detail"),
]
