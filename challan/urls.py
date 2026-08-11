from django.urls import path

from . import views

app_name = "challan"

urlpatterns = [
    path("", views.challan_dashboard, name="dashboard"),
    path("challan/<int:pk>/", views.challan_detail, name="challan_detail"),
    path("challan/<int:pk>/approve/", views.challan_approve, name="challan_approve"),
    path("challan/<int:pk>/void/", views.challan_void, name="challan_void"),
    path("challan/<int:pk>/unlock/", views.challan_unlock, name="challan_unlock"),
    path(
        "challan/<int:pk>/change-no/",
        views.challan_no_change,
        name="challan_no_change",
    ),
    path("initiate/", views.initiation_form, name="initiation_form"),
    path("hand-challan/", views.hand_challan_form, name="hand_challan_form"),
    path("billing/", views.billing_context, name="billing_context"),
    path("stock/intake/", views.stock_intake, name="stock_intake"),
    path("stock/employee/", views.employee_stock_form, name="employee_stock_form"),
    path(
        "stock/employee/<str:employee_name>/",
        views.employee_stock_overview,
        name="employee_stock_overview",
    ),
]
