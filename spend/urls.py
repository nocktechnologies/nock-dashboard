from django.urls import path

from . import views

app_name = "spend"

urlpatterns = [
    path("", views.spend_dashboard, name="dashboard"),
    path("add/", views.add_expense, name="add-expense"),
    path("tax/", views.tax_view, name="tax"),
    path("tax/export/", views.tax_export_csv, name="tax-export"),
    path("pnl/", views.pnl_view, name="pnl"),
    path("revenue/add/", views.add_revenue, name="add-revenue"),
    path("api/summary/", views.spend_summary_api, name="summary-api"),
    path("api/daily/", views.spend_daily_api, name="daily-api"),
    path("api/expenses/", views.expenses_api, name="expenses-api"),
    path("api/subscriptions/", views.subscriptions_api, name="subscriptions-api"),
]
