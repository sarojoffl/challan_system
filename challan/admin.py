from django.contrib import admin

from .models import (
    Billing,
    Challan,
    ChallanItem,
    Client,
    EmployeeStockChallan,
    EmployeeStockChallanItem,
    StockIntake,
    StockItem,
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
    list_display = ("id", "company_name", "client", "adjust_requested", "created_at")
    filter_horizontal = ("challans",)


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "model", "is_disposable", "quantity_available")
    list_filter = ("is_disposable",)
    search_fields = ("name", "brand", "model", "serial_number")


@admin.register(StockIntake)
class StockIntakeAdmin(admin.ModelAdmin):
    list_display = ("stock_item", "quantity", "for_client", "created_at")


class EmployeeStockChallanItemInline(admin.TabularInline):
    model = EmployeeStockChallanItem
    extra = 1


@admin.register(EmployeeStockChallan)
class EmployeeStockChallanAdmin(admin.ModelAdmin):
    list_display = ("employee_name", "challan", "delivered_by", "created_at")
    inlines = [EmployeeStockChallanItemInline]
