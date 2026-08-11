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
from .models import Billing, Challan, EmployeeStockChallan, StockItem, VOID_WINDOW_DAYS


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
        challan.status = Challan.Status.APPROVED
        if challan.adjust_requested:
            challan.admin_approved = True
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
    if request.method == "POST":
        form = BillingContextForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                challans = form.cleaned_data["challans"]
                is_adjustment = any(c.adjust_requested for c in challans)
                billing = Billing.objects.create(
                    company_name=form.cleaned_data["company_name"],
                    client=form.cleaned_data["client"],
                    adjust_requested=is_adjustment,
                )
                billing.challans.set(challans)
                challans.update(is_billed_out=True, billed_out_at=timezone.now())
            messages.success(
                request,
                f"{challans.count()} challan(s) billed out for "
                f"{form.cleaned_data['client']}.",
            )
            return redirect("challan:dashboard")
    else:
        initial = {}
        client_id = request.GET.get("client")
        if client_id:
            initial["client"] = client_id
        form = BillingContextForm(initial=initial)
    return render(request, "challan/billing_context.html", {"form": form})


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
