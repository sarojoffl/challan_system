from .models import Challan

def admin_counts(request):
    if not request.user.is_authenticated or not (request.user.is_staff or request.user.is_superuser):
        return {}
    pending_adjust = Challan.objects.filter(adjust_requested=True, admin_approved=False).count()
    locked_count = Challan.objects.filter(locked=True).count()
    return {
        'admin_pending_adjust_count': pending_adjust,
        'admin_locked_count': locked_count,
        'admin_total_pending_count': pending_adjust + locked_count,
    }
