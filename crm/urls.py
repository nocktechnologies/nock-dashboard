from django.urls import path

from . import views

app_name = "crm"

urlpatterns = [
    path("", views.pipeline_view, name="pipeline"),
    path("deals/add/", views.deal_create, name="deal-create"),
    path("deals/<int:pk>/", views.deal_detail, name="deal-detail"),
    path("deals/<int:pk>/edit/", views.deal_edit, name="deal-edit"),
    path("contacts/", views.contact_list, name="contacts"),
    path("contacts/add/", views.contact_create, name="contact-create"),
    path("contacts/<int:pk>/edit/", views.contact_edit, name="contact-edit"),
]
