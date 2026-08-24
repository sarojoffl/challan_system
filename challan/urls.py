from django.urls import path

from . import views

app_name = "challan"

urlpatterns = [
    path("", views.challan_dashboard, name="dashboard"),
    path("challan/<int:pk>/", views.challan_detail, name="challan_detail"),
    path("challan/<int:pk>/edit/", views.challan_edit, name="challan_edit"),
    path("challan/<int:pk>/approve/", views.challan_approve, name="challan_approve"),
    path("challan/<int:pk>/void/", views.challan_void, name="challan_void"),
    path("challan/<int:pk>/unlock/", views.challan_unlock, name="challan_unlock"),
    path("challan/<int:pk>/extend/", views.challan_extend, name="challan_extend"),
    path(
        "challan/<int:pk>/change-no/",
        views.challan_no_change,
        name="challan_no_change",
    ),
    path("initiate/", views.initiation_form, name="initiation_form"),
    path("hand-challan/", views.hand_challan_form, name="hand_challan_form"),
    path("billing/", views.billing_context, name="billing_context"),
    path("billing/history/", views.billing_history_list, name="billing_history_list"),
    path("billing/<int:pk>/", views.billing_detail, name="billing_detail"),
    path("stock/intake/", views.stock_intake, name="stock_intake"),
    path("stock/intake/decrease/<int:pk>/", views.stock_intake_decrease, name="stock_intake_decrease"),
    path("api/employee-stock-intakes/", views.api_employee_stock_intakes, name="api_employee_stock_intakes"),
    path("api/next-challan-number/", views.next_challan_number, name="next_challan_number"),
    path("admin-panel/", views.admin_panel, name="admin_panel"),
    path("companies/", views.company_list, name="company_list"),
    path("companies/<int:pk>/edit/", views.company_edit, name="company_edit"),
    path("companies/<int:pk>/delete/", views.company_delete, name="company_delete"),
]
