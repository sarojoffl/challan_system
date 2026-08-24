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
    CompanyForm,
    HandChallanForm,
    StockDecreaseForm,
    StockIntakeForm,
    StockItemForm,
    VoidChallanForm,
)
from .models import Billing, Challan, StockIntake, StockItem, VOID_WINDOW_DAYS, Company


# ---------------------------------------------------------------------
# Challan Dashboard
# ---------------------------------------------------------------------
@login_required
def challan_dashboard(request):
    status_filter = request.GET.get("status", "all")
    company_filter = request.GET.get("company", "")
    client_filter = request.GET.get("client", "")
    type_filter = request.GET.get("type", "")
    query = request.GET.get("q", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    challans = Challan.objects.select_related("client", "billed_company").prefetch_related("items").all()

    if status_filter in dict(Challan.Status.choices):
        challans = challans.filter(status=status_filter)

    if company_filter:
        challans = challans.filter(billed_company_id=company_filter)

    if client_filter:
        challans = challans.filter(client_id=client_filter)

    if type_filter in dict(Challan.ChallanType.choices):
        challans = challans.filter(challan_type=type_filter)

    if date_from:
        challans = challans.filter(created_at__date__gte=date_from)

    if date_to:
        challans = challans.filter(created_at__date__lte=date_to)

    if query:
        from django.db.models import Q
        challans = challans.filter(
            Q(challan_no__icontains=query)
            | Q(client__name__icontains=query)
            | Q(contact_name__icontains=query)
            | Q(delivered_by__icontains=query)
            | Q(received_by_name__icontains=query)
            | Q(items__product_name__icontains=query)
        ).distinct()

    counts = {
        "all": Challan.objects.count(),
        "pending": Challan.objects.filter(status=Challan.Status.PENDING).count(),
        "approved": Challan.objects.filter(status=Challan.Status.APPROVED).count(),
        "void": Challan.objects.filter(status=Challan.Status.VOID).count(),
    }

    overdue_challans = Challan.objects.filter(
        status=Challan.Status.PENDING
    ).select_related("client", "billed_company")
    overdue_challans = [c for c in overdue_challans if c.is_overdue_for_reminder]

    from .models import Client, Company
    context = {
        "challans": challans,
        "status_filter": status_filter,
        "company_filter": company_filter,
        "client_filter": client_filter,
        "type_filter": type_filter,
        "query": query,
        "date_from": date_from,
        "date_to": date_to,
        "counts": counts,
        "overdue_challans": overdue_challans,
        "void_window_days": VOID_WINDOW_DAYS,
        "companies": Company.objects.all(),
        "clients": Client.objects.all(),
    }
    return render(request, "challan/dashboard.html", context)


@login_required
def challan_detail(request, pk):
    challan = get_object_or_404(
        Challan.objects.select_related("client", "billed_company"), pk=pk
    )
    if request.method == "POST" and (request.user.is_staff or request.user.is_superuser):
        action = request.POST.get("action")
        if action == "approve_adjustment":
            challan.admin_approved = True
            challan.save()
            messages.success(request, f"Material adjustment for Challan {challan.challan_no} approved.")
        elif action == "approve_void":
            challan.status = Challan.Status.VOID
            challan.void_requested = False
            challan.void_approved_by_admin = True
            challan.save()
            messages.success(request, f"Void request for Challan {challan.challan_no} approved. Status is now Void.")
        elif action == "unlock_challan":
            challan.locked = False
            challan.unlocked_by_admin = True
            challan.save()
            messages.success(request, f"Challan {challan.challan_no} unlocked by admin.")
        return redirect("challan:challan_detail", pk=pk)

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
            if challan.status == Challan.Status.APPROVED or challan.is_locked_out:
                # Require Admin approval to void an approved/locked challan
                challan.void_requested = True
                challan.void_reason = form.cleaned_data["void_reason"]
                challan.save()
                messages.success(
                    request,
                    f"Void request submitted for Challan {challan.challan_no}. "
                    f"An Admin must approve it from the Approvals & Unlocks desk."
                )
            else:
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
def process_stock_intake_deduction(challan, items):
    """Automatically deducts stock from employee StockIntake entries and StockItem quantity_available when a challan is issued from stock intake."""
    if not challan.is_from_stock_intake or not challan.stock_employee_name:
        return
    emp_name = challan.stock_employee_name.strip()
    from django.db.models import F
    for item in items:
        qty = item.quantity
        if not qty or qty <= 0:
            continue
        if item.stock_intake_id:
            intake = item.stock_intake
            deduct_qty = min(qty, intake.quantity)
            if deduct_qty > 0:
                StockIntake.objects.filter(pk=intake.pk).update(
                    quantity=F("quantity") - deduct_qty
                )
                StockItem.objects.filter(pk=intake.stock_item_id).update(
                    quantity_available=F("quantity_available") - deduct_qty
                )
        else:
            intakes = StockIntake.objects.filter(
                employee_name__iexact=emp_name,
                stock_item__name__icontains=item.product_name,
                quantity__gt=0,
            ).order_by("created_at")
            rem_qty = qty
            for intake in intakes:
                if rem_qty <= 0:
                    break
                deduct = min(rem_qty, intake.quantity)
                StockIntake.objects.filter(pk=intake.pk).update(
                    quantity=F("quantity") - deduct
                )
                StockItem.objects.filter(pk=intake.stock_item_id).update(
                    quantity_available=F("quantity_available") - deduct
                )
                rem_qty -= deduct


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
                    saved_items = formset.save(commit=False)
                    for item in saved_items:
                        item.challan = challan
                        item.save()
                    formset.save_m2m()
                    if challan.is_from_stock_intake:
                        process_stock_intake_deduction(challan, challan.items.all())
                messages.success(
                    request, f"Challan {challan.challan_no} submitted for approval."
                )
                return redirect("challan:challan_detail", pk=challan.pk)
    else:
        form = ChallanInitiationForm()
        formset = ChallanItemFormSet(prefix="items")

    stock_employees = (
        StockIntake.objects.filter(quantity__gt=0)
        .values_list("employee_name", flat=True)
        .distinct()
        .order_by("employee_name")
    )
    return render(
        request,
        "challan/initiation_form.html",
        {"form": form, "formset": formset, "stock_employees": stock_employees},
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
                    challan.status = Challan.Status.APPROVED
                    challan.save()
                    saved_items = formset.save(commit=False)
                    for item in saved_items:
                        item.challan = challan
                        item.save()
                    formset.save_m2m()
                    if challan.is_from_stock_intake:
                        process_stock_intake_deduction(challan, challan.items.all())
                messages.success(
                    request,
                    f"Hand challan {challan.challan_no} created and merged into the Challan Dashboard.",
                )
                return redirect("challan:challan_detail", pk=challan.pk)
    else:
        form = HandChallanForm()
        formset = ChallanItemFormSet(prefix="items")

    stock_employees = (
        StockIntake.objects.filter(quantity__gt=0)
        .values_list("employee_name", flat=True)
        .distinct()
        .order_by("employee_name")
    )
    return render(
        request,
        "challan/hand_challan_form.html",
        {"form": form, "formset": formset, "stock_employees": stock_employees},
    )


# ---------------------------------------------------------------------
# Billing Context
# ---------------------------------------------------------------------
@login_required
def billing_context(request):
    client_id = request.GET.get("client") or None
    start_date = request.GET.get("start_date") or None
    end_date = request.GET.get("end_date") or None

    if request.method == "POST":
        form = BillingContextForm(
            request.POST,
            client_id=client_id,
            start_date=start_date,
            end_date=end_date,
        )
        if form.is_valid():
            challans = form.cleaned_data["challans"]
            company_name_override = form.cleaned_data.get("company_name")
            bill_no = form.cleaned_data.get("bill_no")
            billing_date = form.cleaned_data.get("created_at") or timezone.now()

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
                    billing_kwargs = {
                        "company_name": company_name_override,
                        "bill_no": bill_no,
                        "client": client_obj,
                        "adjust_requested": is_adjustment,
                    }
                    if billing_date:
                        billing_kwargs["created_at"] = billing_date

                    billing = Billing.objects.create(**billing_kwargs)
                    pks = [c.pk for c in group]
                    billing.challans.set(pks)
                    Challan.objects.filter(pk__in=pks).update(
                        is_billed_out=True, billed_out_at=billing_date
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
        form = BillingContextForm(
            client_id=client_id,
            start_date=start_date,
            end_date=end_date,
        )

    # Pass all clients for the optional filter dropdown
    from .models import Client as ClientModel
    clients = ClientModel.objects.all()
    return render(request, "challan/billing_context.html", {
        "form": form,
        "clients": clients,
        "selected_client_id": int(client_id) if client_id else None,
        "start_date": start_date or "",
        "end_date": end_date or "",
    })


# ---------------------------------------------------------------------
# Stock: Intake + catalog
# ---------------------------------------------------------------------
@login_required
def stock_intake(request):
    """Register stock items, top up intake per employee, and view current stock."""
    item_form = StockItemForm(prefix="item")
    intake_form = StockIntakeForm(prefix="intake")

    if request.method == "POST" and request.POST.get("action") == "new_item":
        item_form = StockItemForm(request.POST, prefix="item")
        emp_name = request.POST.get("item-employee_name", "").strip()
        if not emp_name:
            messages.error(request, "Employee Name is compulsory for stock intake.")
        elif item_form.is_valid():
            with transaction.atomic():
                stock_item = item_form.save(commit=False)
                stock_item.quantity_available = 0
                stock_item.save()
                qty = int(request.POST.get("item-starting_quantity") or 0)
                custom_date = request.POST.get("item-created_at")

                if qty:
                    existing = StockIntake.objects.filter(
                        employee_name__iexact=emp_name,
                        stock_item=stock_item,
                    ).first()
                    if existing:
                        existing.quantity += qty
                        existing.save()
                        StockItem.objects.filter(pk=stock_item.pk).update(
                            quantity_available=models.F("quantity_available") + qty
                        )
                    else:
                        intake_kwargs = {
                            "employee_name": emp_name,
                            "stock_item": stock_item,
                            "quantity": qty,
                            "created_by": request.user,
                        }
                        if custom_date:
                            intake_kwargs["created_at"] = custom_date
                        StockIntake.objects.create(**intake_kwargs)

            messages.success(request, f"New stock item added for {emp_name}: {stock_item}.")
            return redirect("challan:stock_intake")

    elif request.method == "POST" and request.POST.get("action") == "intake":
        intake_form = StockIntakeForm(request.POST, prefix="intake")
        if intake_form.is_valid():
            emp_name = intake_form.cleaned_data["employee_name"].strip()
            stock_item = intake_form.cleaned_data["stock_item"]
            qty = intake_form.cleaned_data["quantity"]
            custom_date = intake_form.cleaned_data.get("created_at")

            with transaction.atomic():
                existing = StockIntake.objects.filter(
                    employee_name__iexact=emp_name,
                    stock_item=stock_item,
                ).first()

                if existing:
                    existing.quantity += qty
                    existing.save()
                    StockItem.objects.filter(pk=stock_item.pk).update(
                        quantity_available=models.F("quantity_available") + qty
                    )
                else:
                    intake = intake_form.save(commit=False)
                    intake.employee_name = emp_name
                    intake.created_by = request.user
                    intake.save()

            messages.success(
                request,
                f"Stock top-up recorded for {emp_name}: +{qty} {stock_item}.",
            )
            return redirect("challan:stock_intake")

    stock_intakes = StockIntake.objects.select_related("stock_item").order_by("employee_name", "-created_at")
    employees = (
        StockIntake.objects.values_list("employee_name", flat=True)
        .distinct()
        .order_by("employee_name")
    )
    stock_items = StockItem.objects.all()

    return render(
        request,
        "challan/stock_intake.html",
        {
            "item_form": item_form,
            "intake_form": intake_form,
            "stock_intakes": stock_intakes,
            "stock_items": stock_items,
            "employees": employees,
        },
    )


@login_required
def stock_intake_decrease(request, pk):
    """Manually decrease stock quantity on a StockIntake record."""
    intake = get_object_or_404(StockIntake, pk=pk)
    if request.method == "POST":
        form = StockDecreaseForm(request.POST)
        if form.is_valid():
            deduct_qty = form.cleaned_data["decrease_quantity"]
            if deduct_qty > intake.quantity:
                messages.error(
                    request,
                    f"Cannot decrease by {deduct_qty}. Maximum available for {intake.employee_name} is {intake.quantity}."
                )
            else:
                from django.db.models import F
                with transaction.atomic():
                    StockIntake.objects.filter(pk=intake.pk).update(quantity=F("quantity") - deduct_qty)
                    StockItem.objects.filter(pk=intake.stock_item_id).update(quantity_available=F("quantity_available") - deduct_qty)
                messages.success(
                    request,
                    f"Decreased {deduct_qty} units of {intake.stock_item} from {intake.employee_name}'s intake."
                )
            return redirect("challan:stock_intake")
    return redirect("challan:stock_intake")


@login_required
def api_employee_stock_intakes(request):
    """JSON API endpoint returning active stock intakes for a given employee name."""
    from django.http import JsonResponse
    emp_name = request.GET.get("employee_name", "").strip()
    if not emp_name:
        return JsonResponse({"intakes": []})
    intakes = StockIntake.objects.filter(
        employee_name__iexact=emp_name,
        quantity__gt=0,
    ).select_related("stock_item")

    data = [
        {
            "id": i.pk,
            "product_name": i.stock_item.name,
            "brand": i.stock_item.brand,
            "model": i.stock_item.model,
            "available_qty": i.quantity,
        }
        for i in intakes
    ]
    return JsonResponse({"intakes": data})


@login_required
def billing_history_list(request):
    """List all billing out transactions with filter bar."""
    company_filter = request.GET.get("company", "")
    client_filter = request.GET.get("client", "")
    query = request.GET.get("q", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    billings = Billing.objects.select_related("client", "company_name").prefetch_related("challans").all()

    if company_filter:
        billings = billings.filter(company_name_id=company_filter)

    if client_filter:
        billings = billings.filter(client_id=client_filter)

    if date_from:
        billings = billings.filter(created_at__date__gte=date_from)

    if date_to:
        billings = billings.filter(created_at__date__lte=date_to)

    if query:
        from django.db.models import Q
        billings = billings.filter(
            Q(client__name__icontains=query)
            | Q(company_name__name__icontains=query)
            | Q(company_name__code__icontains=query)
            | Q(challans__challan_no__icontains=query)
            | Q(bill_no__icontains=query)
        ).distinct()

    from .models import Client, Company
    return render(
        request,
        "challan/billing_history_list.html",
        {
            "billings": billings,
            "company_filter": company_filter,
            "client_filter": client_filter,
            "query": query,
            "date_from": date_from,
            "date_to": date_to,
            "companies": Company.objects.all(),
            "clients": Client.objects.all(),
        },
    )


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
        elif action == "approve_void":
            challan.status = Challan.Status.VOID
            challan.void_requested = False
            challan.void_approved_by_admin = True
            challan.save()
            messages.success(request, f"Void request for Challan {challan.challan_no} approved. Status is now Void.")
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

    pending_voids = (
        Challan.objects.filter(void_requested=True)
        .exclude(status=Challan.Status.VOID)
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
            "pending_voids": pending_voids,
            "locked_challans": locked_challans,
        },
    )


# ---------------------------------------------------------------------
# Company Management Views
# ---------------------------------------------------------------------
@login_required
def company_list(request):
    companies = Company.objects.all()
    if request.method == "POST":
        form = CompanyForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Company created successfully.")
            return redirect("challan:company_list")
    else:
        form = CompanyForm()

    return render(request, "challan/company_list.html", {"companies": companies, "form": form})


@login_required
def company_edit(request, pk):
    company = get_object_or_404(Company, pk=pk)
    if request.method == "POST":
        form = CompanyForm(request.POST, instance=company)
        if form.is_valid():
            form.save()
            messages.success(request, "Company details updated successfully.")
            return redirect("challan:company_list")
    else:
        form = CompanyForm(instance=company)

    return render(request, "challan/company_edit.html", {"company": company, "form": form})


@login_required
def company_delete(request, pk):
    company = get_object_or_404(Company, pk=pk)
    if request.method == "POST":
        if company.challans.exists() or company.billings.exists():
            messages.error(request, f"Cannot delete '{company.name}' because it is linked to existing challans or billing records.")
        else:
            company.delete()
            messages.success(request, "Company deleted successfully.")
        return redirect("challan:company_list")

    return render(request, "challan/company_confirm_delete.html", {"company": company})
