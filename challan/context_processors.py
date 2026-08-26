from .models import Challan

def admin_counts(request):
    if not request.user.is_authenticated or not (request.user.is_staff or request.user.is_superuser):
        return {}
    pending_adjust = Challan.objects.filter(adjust_requested=True, admin_approved=False).count()
    pending_void = Challan.objects.filter(void_requested=True).exclude(status=Challan.Status.VOID).count()
    locked_count = Challan.objects.filter(locked=True).count()
    return {
        'admin_pending_adjust_count': pending_adjust,
        'admin_pending_void_count': pending_void,
        'admin_locked_count': locked_count,
        'admin_total_pending_count': pending_adjust + pending_void + locked_count,
    }


def common_form_data(request):
    if not request.user.is_authenticated:
        return {}
    from .models import Client, ChallanItem, StockItem
    clients = list(Client.objects.values_list("name", flat=True).order_by("name"))
    items_challan = set(ChallanItem.objects.values_list("product_name", flat=True))
    items_stock = set(StockItem.objects.values_list("name", flat=True))
    all_items = sorted([i for i in (items_challan | items_stock) if i])
    return {
        "existing_clients": clients,
        "existing_items": all_items,
    }
