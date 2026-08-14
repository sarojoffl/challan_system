from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    BillingContextForm,
    ChallanExtendForm,
    ChallanInitiationForm,
    ChallanItemFormSet,
    ChallanNoChangeForm,
    EmployeeStockChallanForm,
    EmployeeStockChallanItemFormSet,
    HandChallanForm,
    StockIntakeForm,
    StockItemForm,
    VoidChallanForm,
)
from .models import Billing, Challan, EmployeeStockChallan, StockItem, VOID_WINDOW_DAYS, Company


# ---------------------------------------------------------------------
# Challan Dashboard
# ---------------------------------------------------------------------
@login_required
def challan_dashboard(request):
    status_filter = request.GET.get("status", "all")
    challans = Challan.objects.select_related("client").all()
    if status_filter in dict(Challan.Status.choices):
        challans = challans.filter(status=status_filter)

    counts = {
        "all": Challan.objects.count(),
        "pending": Challan.objects.filter(status=Challan.Status.PENDING).count(),
        "approved": Challan.objects.filter(status=Challan.Status.APPROVED).count(),
        "void": Challan.objects.filter(status=Challan.Status.VOID).count(),
    }

    overdue_challans = Challan.objects.filter(
        status=Challan.Status.PENDING
    ).select_related("client")
    overdue_challans = [c for c in overdue_challans if c.is_overdue_for_reminder]

    context = {
        "challans": challans,
        "status_filter": status_filter,
        "counts": counts,
        "overdue_challans": overdue_challans,
        "void_window_days": VOID_WINDOW_DAYS,
    }
    return render(request, "challan/dashboard.html", context)


@login_required
def challan_detail(request, pk):
    challan = get_object_or_404(
        Challan.objects.select_related("client", "employee_stock_challan"), pk=pk
    )
    return render(request, "challan/challan_detail.html", {"challan": challan})


@login_required
def challan_approve(request, pk):
    challan = get_object_or_404(Challan, pk=pk)
    if request.method == "POST":
        if challan.adjust_requested and not challan.admin_approved:
            messages.error(
                request,
                "This challan has a requested Material Adjustment. "
                "An Admin must approve the adjustment from the Approvals & Unlocks desk first."
            )
            return redirect("challan:challan_detail", pk=pk)
        challan.status = Challan.Status.APPROVED
        challan.save()
        messages.success(request, f"Challan {challan.challan_no} approved.")
    return redirect("challan:challan_detail", pk=pk)


@login_required
def challan_void(request, pk):
    challan = get_object_or_404(Challan, pk=pk)
    if not challan.can_void:
        messages.error(
            request,
            "This challan is locked and past the 3-day void window. "
            "An admin must unlock it first.",
        )
        return redirect("challan:challan_detail", pk=pk)

    if request.method == "POST":
        form = VoidChallanForm(request.POST)
        if form.is_valid():
            challan.status = Challan.Status.VOID
            challan.void_reason = form.cleaned_data["void_reason"]
            challan.save()
            messages.success(request, f"Challan {challan.challan_no} voided.")
            return redirect("challan:challan_detail", pk=pk)
    else:
        form = VoidChallanForm()
    return render(
        request, "challan/challan_void.html", {"challan": challan, "form": form}
    )


@login_required
def challan_unlock(request, pk):
    """Admin-only unlock so a challan past its 3-day window can still be
    voided / have replacement material adjusted."""
    challan = get_object_or_404(Challan, pk=pk)
    if not request.user.is_staff:
        messages.error(request, "Only an admin can unlock a locked challan.")
        return redirect("challan:challan_detail", pk=pk)
    if request.method == "POST":
        challan.unlocked_by_admin = True
        challan.locked = False
        challan.save()
        messages.success(request, f"Challan {challan.challan_no} unlocked.")
    return redirect("challan:challan_detail", pk=pk)


@login_required
def challan_extend(request, pk):
    """One-time 3-day extension, only allowed between day 3 and day 7,
    requires a mandatory reason."""
    challan = get_object_or_404(Challan, pk=pk)

    if challan.status != Challan.Status.PENDING:
        messages.error(request, "Only pending challans can be extended.")
        return redirect("challan:challan_detail", pk=pk)

    if not challan.can_extend:
        if challan.extension_days > 0:
            messages.error(request, "This challan has already been extended once. No further extension allowed.")
        else:
            messages.error(request, "Extension is only available between day 3 and day 7 of a pending challan.")
        return redirect("challan:challan_detail", pk=pk)

    if request.method == "POST":
        form = ChallanExtendForm(request.POST)
        if form.is_valid():
            challan.extension_days = 3
            challan.extended_at = timezone.now()
            challan.extend_reason = form.cleaned_data["reason"]
            challan.save()
            messages.success(
                request,
                f"Challan {challan.challan_no} extended. "
                f"Active until day 7: {challan.extension_deadline.strftime('%d %b %Y, %H:%M')}."
            )
            return redirect("challan:challan_detail", pk=pk)
    else:
        form = ChallanExtendForm()

    return render(request, "challan/challan_extend.html", {"challan": challan, "form": form})


@login_required
def challan_no_change(request, pk):
    """After the 1-week extend cycle, allow changing the challan no. with
    a mandatory reason, per the notes."""
    challan = get_object_or_404(Challan, pk=pk)
    if request.method == "POST":
        form = ChallanNoChangeForm(request.POST)
        if form.is_valid():
            challan.challan_no = form.cleaned_data["new_challan_no"]
            challan.challan_no_change_reason = form.cleaned_data["reason"]
            challan.save()
            messages.success(request, "Challan number updated.")
            return redirect("challan:challan_detail", pk=pk)
    else:
        form = ChallanNoChangeForm()
    return render(
        request,
        "challan/challan_no_change.html",
        {"challan": challan, "form": form},
    )


@login_required
def challan_edit(request, pk):
    """Allows editing of pending, unlocked challan details and its goods items."""
    challan = get_object_or_404(Challan, pk=pk)
    if challan.status != Challan.Status.PENDING:
        messages.error(request, "Only pending challans can be edited.")
        return redirect("challan:challan_detail", pk=pk)
    if not challan.can_void:
        messages.error(request, "This challan is locked. An admin must unlock it first.")
        return redirect("challan:challan_detail", pk=pk)

    if challan.challan_type == Challan.ChallanType.QUOTATION:
        FormClass = ChallanInitiationForm
    else:
        FormClass = HandChallanForm

    if request.method == "POST":
        form = FormClass(request.POST, instance=challan)
        formset = ChallanItemFormSet(request.POST, instance=challan, prefix="items")
        if form.is_valid() and formset.is_valid():
            # Goods detail is compulsory — require at least 1 non-deleted item
            real_items = [
                f for f in formset.forms
                if f.cleaned_data and not f.cleaned_data.get("DELETE", False)
            ]
            if not real_items:
                messages.error(request, "Goods Detail is compulsory. Please keep at least one item.")
            else:
                with transaction.atomic():
                    instance = form.save(commit=False)
                    client_name = form.cleaned_data.get("client_name", "").strip()
                    if client_name:
                        from .models import Client
                        client, _ = Client.objects.get_or_create(name=client_name)
                        instance.client = client
                    if instance.adjust_requested and "adjust_requested" in form.changed_data:
                        instance.admin_approved = False
                    instance.save()
                    formset.save()
                messages.success(request, f"Challan {challan.challan_no} updated successfully.")
                return redirect("challan:challan_detail", pk=pk)
    else:
        initial = {"client_name": challan.client.name}
        form = FormClass(instance=challan, initial=initial)
        formset = ChallanItemFormSet(instance=challan, prefix="items")

    return render(
        request,
        "challan/challan_edit.html",
        {"challan": challan, "form": form, "formset": formset},
    )


# ---------------------------------------------------------------------
# Initiation Form
# ---------------------------------------------------------------------
@login_required
def initiation_form(request):
    if request.method == "POST":
        form = ChallanInitiationForm(request.POST)
        formset = ChallanItemFormSet(request.POST, prefix="items")
        if form.is_valid() and formset.is_valid():
            # Goods detail is compulsory — require at least 1 non-deleted item
            real_items = [
                f for f in formset.forms
                if f.cleaned_data and not f.cleaned_data.get("DELETE", False)
            ]
            if not real_items:
                messages.error(request, "Goods Detail is compulsory. Please add at least one item.")
            else:
                with transaction.atomic():
                    challan = form.save(commit=False)
                    challan.created_by = request.user
                    challan.save()
                    formset.instance = challan
                    formset.save()
                messages.success(
                    request, f"Challan {challan.challan_no} submitted for approval."
                )
                return redirect("challan:challan_detail", pk=challan.pk)
    else:
        form = ChallanInitiationForm()
        formset = ChallanItemFormSet(prefix="items")
    return render(
        request,
        "challan/initiation_form.html",
        {"form": form, "formset": formset},
    )


# ---------------------------------------------------------------------
# Hand Challan
# ---------------------------------------------------------------------
@login_required
def hand_challan_form(request):
    if request.method == "POST":
        form = HandChallanForm(request.POST)
        formset = ChallanItemFormSet(request.POST, prefix="items")
        if form.is_valid() and formset.is_valid():
            # Goods detail is compulsory — require at least 1 non-deleted item
            real_items = [
                f for f in formset.forms
                if f.cleaned_data and not f.cleaned_data.get("DELETE", False)
            ]
            if not real_items:
                messages.error(request, "Goods Detail is compulsory. Please add at least one item.")
            else:
                with transaction.atomic():
                    challan = form.save(commit=False)
                    challan.created_by = request.user
                    # Hand challans are considered approved on submit — they
                    # aren't quotation-based and skip the approval gate.
                    challan.status = Challan.Status.APPROVED
                    challan.save()
                    formset.instance = challan
                    formset.save()
                messages.success(
                    request,
                    f"Hand challan {challan.challan_no} created and merged "
                    f"into the Challan Dashboard.",
                )
                return redirect("challan:challan_detail", pk=challan.pk)
    else:
        form = HandChallanForm()
        formset = ChallanItemFormSet(prefix="items")
    return render(
        request,
        "challan/hand_challan_form.html",
        {"form": form, "formset": formset},
    )


# ---------------------------------------------------------------------
# Billing Context
# ---------------------------------------------------------------------
@login_required
def billing_context(request):
    client_id = request.GET.get("client") or None

    if request.method == "POST":
        form = BillingContextForm(request.POST, client_id=client_id)
        if form.is_valid():
            challans = form.cleaned_data["challans"]
            company_name_override = form.cleaned_data.get("company_name", "").strip()
            now = timezone.now()

            # Group selected challans by client, create one Billing per group
            from collections import defaultdict
            groups = defaultdict(list)
            for c in challans:
                groups[c.client_id].append(c)

            total_count = 0
            client_names = []
            with transaction.atomic():
                for cid, group in groups.items():
                    client_obj = group[0].client
                    is_adjustment = any(c.adjust_requested for c in group)
                    billing = Billing.objects.create(
                        company_name=company_name_override,
                        client=client_obj,
                        adjust_requested=is_adjustment,
                    )
                    pks = [c.pk for c in group]
                    billing.challans.set(pks)
                    Challan.objects.filter(pk__in=pks).update(
                        is_billed_out=True, billed_out_at=now
                    )
                    total_count += len(group)
                    client_names.append(client_obj.name)

            messages.success(
                request,
                f"{total_count} challan(s) billed out"
                + (f" for: {', '.join(client_names)}." if client_names else "."),
            )
            return redirect("challan:dashboard")
    else:
        form = BillingContextForm(client_id=client_id)

    # Pass all clients for the optional filter dropdown
    from .models import Client as ClientModel
    clients = ClientModel.objects.all()
    return render(request, "challan/billing_context.html", {
        "form": form,
        "clients": clients,
        "selected_client_id": int(client_id) if client_id else None,
    })


# ---------------------------------------------------------------------
# Stock: Intake + catalog
# ---------------------------------------------------------------------
@login_required
def stock_intake(request):
    """Two independent actions on one page: (1) register a brand-new
    disposable/non-disposable stock item with its starting quantity, or
    (2) top up an existing item's quantity via a fresh intake record."""
    item_form = StockItemForm(prefix="item")
    intake_form = StockIntakeForm(prefix="intake")

    if request.method == "POST" and request.POST.get("action") == "new_item":
        item_form = StockItemForm(request.POST, prefix="item")
        if item_form.is_valid():
            with transaction.atomic():
                stock_item = item_form.save(commit=False)
                stock_item.quantity_available = 0
                stock_item.save()
                qty = int(request.POST.get("item-starting_quantity") or 0)
                for_client_id = request.POST.get("item-for_client") or None
                if qty:
                    from .models import StockIntake as StockIntakeModel

                    StockIntakeModel.objects.create(
                        stock_item=stock_item,
                        for_client_id=for_client_id,
                        quantity=qty,
                        created_by=request.user,
                    )
            messages.success(request, f"New stock item added: {stock_item}.")
            return redirect("challan:stock_intake")

    elif request.method == "POST" and request.POST.get("action") == "intake":
        intake_form = StockIntakeForm(request.POST, prefix="intake")
        if intake_form.is_valid():
            intake = intake_form.save(commit=False)
            intake.created_by = request.user
            intake.save()
            messages.success(
                request,
                f"Stock intake recorded: +{intake.quantity} {intake.stock_item}.",
            )
            return redirect("challan:stock_intake")

    from .models import Client

    stock_items = StockItem.objects.all()
    return render(
        request,
        "challan/stock_intake.html",
        {
            "item_form": item_form,
            "intake_form": intake_form,
            "stock_items": stock_items,
            "clients": Client.objects.all(),
        },
    )


# ---------------------------------------------------------------------
# Stock / Hand Challan for employees
# ---------------------------------------------------------------------
@login_required
def employee_stock_form(request):
    if request.method == "POST":
        form = EmployeeStockChallanForm(request.POST)
        formset = EmployeeStockChallanItemFormSet(request.POST, prefix="items")
        client_name = request.POST.get("client_name", "").strip() or "Internal / Employee Stock"
        if form.is_valid() and formset.is_valid():
            from .models import Client

            with transaction.atomic():
                client, _ = Client.objects.get_or_create(name=client_name)
                challan = Challan.objects.create(
                    challan_type=Challan.ChallanType.HAND,
                    client=client,
                    delivered_by=form.cleaned_data["delivered_by"],
                    adjust_requested=form.cleaned_data["adjust_requested"],
                    status=Challan.Status.APPROVED,
                    created_by=request.user,
                )
                stock_challan = form.save(commit=False)
                stock_challan.challan = challan
                stock_challan.save()
                formset.instance = stock_challan
                formset.save()
            messages.success(
                request,
                f"Stock issued to {stock_challan.employee_name}, merged into "
                f"the Challan Dashboard as {challan.challan_no}.",
            )
            return redirect("challan:challan_detail", pk=challan.pk)
    else:
        form = EmployeeStockChallanForm()
        formset = EmployeeStockChallanItemFormSet(prefix="items")

    employees = (
        EmployeeStockChallan.objects.values_list("employee_name", flat=True)
        .distinct()
        .order_by("employee_name")
    )
    return render(
        request,
        "challan/employee_stock_form.html",
        {"form": form, "formset": formset, "employees": employees},
    )


@login_required
def employee_stock_overview(request, employee_name):
    """Detailed overview pop-up-equivalent page for a specific employee's
    issued stock, per: 'If clicked it should show the detailed overview
    of the specific person.'"""
    allocations = EmployeeStockChallan.objects.filter(
        employee_name=employee_name
    ).prefetch_related("items__stock_item", "challan")
    return render(
        request,
        "challan/employee_stock_overview.html",
        {"employee_name": employee_name, "allocations": allocations},
    )


@login_required
def employee_stock_summary(request):
    """Admin executive overview of warehouse stock items and employee allocations."""
    stock_items = StockItem.objects.all().order_by("name")
    
    employees_data = []
    employee_names = (
        EmployeeStockChallan.objects.values_list("employee_name", flat=True)
        .distinct()
        .order_by("employee_name")
    )
    for name in employee_names:
        ch_list = EmployeeStockChallan.objects.filter(employee_name=name).prefetch_related("items")
        total_challans = ch_list.count()
        total_items_count = sum(sum(item.quantity for item in ch.items.all()) for ch in ch_list)
        employees_data.append({
            "name": name,
            "total_challans": total_challans,
            "total_items": total_items_count,
        })

    return render(
        request,
        "challan/employee_stock_summary.html",
        {
            "stock_items": stock_items,
            "employees_data": employees_data,
        },
    )


@login_required
def billing_history_list(request):
    """List all billing out transactions."""
    billings = Billing.objects.all().select_related("client").prefetch_related("challans")
    return render(request, "challan/billing_history_list.html", {"billings": billings})


@login_required
def billing_detail(request, pk):
    """View details of a specific billing transaction, consolidating goods across all linked challans."""
    billing = get_object_or_404(Billing, pk=pk)
    
    # Consolidate items
    consolidated = {}
    for challan in billing.challans.all():
        for item in challan.items.all():
            name = item.product_name
            consolidated[name] = consolidated.get(name, 0) + item.quantity
            
    # Sort items alphabetically for clean UI presentation
    sorted_items = sorted(consolidated.items())

    return render(
        request,
        "challan/billing_detail.html",
        {
            "billing": billing,
            "consolidated_items": sorted_items,
        }
    )


from django.http import JsonResponse
import re

@login_required
def next_challan_number(request):
    company_id = request.GET.get("company_id")
    if not company_id:
        return JsonResponse({"next_number": "", "prefix": "", "seq_number": ""})
    company = get_object_or_404(Company, pk=company_id)
    prefix = f"{company.code.upper()}-"
    # Find all challans with this prefix
    challans = Challan.objects.filter(challan_no__startswith=prefix)
    max_num = 0
    for c in challans:
        match = re.match(r"^.+-(\d+)$", c.challan_no)
        if match:
            try:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    seq = max_num + 1
    return JsonResponse({
        "next_number": f"{prefix}{seq}",
        "prefix": prefix,
        "seq_number": str(seq),
    })


@login_required
def admin_panel(request):
    """Central Admin Control Panel for reviewing material replacement approvals
    and unlocking locked challans."""
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Access restricted to administrators.")
        return redirect("challan:dashboard")

    if request.method == "POST":
        action = request.POST.get("action")
        challan_id = request.POST.get("challan_id")
        challan = get_object_or_404(Challan, pk=challan_id)

        if action == "approve_adjustment":
            challan.admin_approved = True
            challan.save()
            messages.success(request, f"Material adjustment for Challan {challan.challan_no} approved.")
        elif action == "unlock_challan":
            challan.locked = False
            challan.unlocked_by_admin = True
            challan.save()
            messages.success(request, f"Challan {challan.challan_no} unlocked by admin.")

        return redirect("challan:admin_panel")

    pending_adjustments = (
        Challan.objects.filter(adjust_requested=True, admin_approved=False)
        .select_related("client", "billed_company")
        .prefetch_related("items")
    )

    locked_challans = (
        Challan.objects.filter(locked=True)
        .select_related("client", "billed_company")
        .prefetch_related("items")
    )

    return render(
        request,
        "challan/admin_panel.html",
        {
            "pending_adjustments": pending_adjustments,
            "locked_challans": locked_challans,
        },
    )
