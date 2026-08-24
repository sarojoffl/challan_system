from django.contrib import admin

from .models import (
    Billing,
    Challan,
    ChallanItem,
    Client,
    StockIntake,
    StockItem,
    Company,
)


class ChallanItemInline(admin.TabularInline):
    model = ChallanItem
    extra = 1


@admin.register(Challan)
class ChallanAdmin(admin.ModelAdmin):
    list_display = (
        "challan_no",
        "challan_type",
        "client",
        "status",
        "is_quotation_based",
        "adjust_requested",
        "admin_approval_required",
        "is_billed_out",
        "locked",
        "created_at",
    )
    list_filter = ("status", "challan_type", "is_quotation_based", "is_billed_out")
    search_fields = ("challan_no", "billed_company", "client__name", "contact_name")
    inlines = [ChallanItemInline]
    readonly_fields = ("challan_no", "created_at", "updated_at")


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "phone_no")
    search_fields = ("name",)


@admin.register(Billing)
class BillingAdmin(admin.ModelAdmin):
    list_display = ("id", "bill_no", "company_name", "client", "adjust_requested", "created_at")
    search_fields = ("bill_no", "client__name", "company_name__name")
    filter_horizontal = ("challans",)


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "model", "is_disposable", "quantity_available")
    list_filter = ("is_disposable",)
    search_fields = ("name", "brand", "model", "serial_number")


@admin.register(StockIntake)
class StockIntakeAdmin(admin.ModelAdmin):
    list_display = ("employee_name", "stock_item", "quantity", "created_at")
    search_fields = ("employee_name", "stock_item__name")


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")
