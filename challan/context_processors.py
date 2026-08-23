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
