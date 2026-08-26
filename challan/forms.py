from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from .models import (
    Billing,
    Challan,
    ChallanItem,
    Client,
    StockIntake,
    StockItem,
    Company,
)


class BaseStyledForm(forms.ModelForm):
    """Adds the shared glass-input styling class to every visible field
    automatically, so templates don't need to repeat widget attrs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                continue
            existing = widget.attrs.get("class", "")
            widget.attrs["class"] = (existing + " ").strip()


# ---------------------------------------------------------------------
# Initiation Form (quotation-based challan)
# ---------------------------------------------------------------------
class ChallanInitiationForm(BaseStyledForm):
    client_name = forms.CharField(
        label="Client's Name",
        help_text="New clients are created automatically.",
        widget=forms.TextInput(attrs={"list": "existing-clients", "autocomplete": "off"}),
    )
    is_quotation_based = forms.ChoiceField(
        label="Quotation Based",
        choices=[("", "— Select Option —"), ("True", "Yes"), ("False", "No")],
        required=True,
    )

    class Meta:
        model = Challan
        fields = [
            "billed_company",
            "challan_no",
            "contact_name",
            "is_quotation_based",
            "delivered_by",
            "received_by_name",
            "received_by_phone",
            "personal_details_name",
            "personal_details_phone",
            "adjust_requested",
            "adjust_reason",
            "is_from_stock_intake",
            "stock_employee_name",
            "created_at",
        ]
        widgets = {
            "adjust_reason": forms.Textarea(
                attrs={"rows": 2, "placeholder": "Specify what was adjusted or replaced..."}
            ),
            "created_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local", "class": "form-control"}
            ),
        }
        labels = {
            "billed_company": "Billed Company (or Firm)",
            "challan_no": "Challan No.",
            "contact_name": "Name",
            "received_by_name": "Received By — Name",
            "received_by_phone": "Phone No.",
            "personal_details_name": "Personal Details — Name",
            "personal_details_phone": "Phone No.",
            "adjust_reason": "Adjustment / Replacement Details",
            "is_from_stock_intake": "Issue from Employee Stock Intake?",
            "stock_employee_name": "Employee Name (Stock Intake)",
            "created_at": "Initiation Date",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if self.instance.is_quotation_based is not None:
                self.initial["is_quotation_based"] = str(self.instance.is_quotation_based)
            if self.instance.created_at:
                self.initial["created_at"] = timezone.localtime(self.instance.created_at).strftime("%Y-%m-%dT%H:%M")
        if not self.initial.get("created_at"):
            self.initial["created_at"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%dT%H:%M")

    def clean_is_quotation_based(self):
        val = self.cleaned_data.get("is_quotation_based")
        if val == "True":
            return True
        elif val == "False":
            return False
        return None

    def clean(self):
        cleaned = super().clean()
        adjust_requested = cleaned.get("adjust_requested")
        personal_details_name = cleaned.get("personal_details_name")
        if adjust_requested and not personal_details_name:
            rec_name = cleaned.get("received_by_name") or (self.instance and getattr(self.instance, "received_by_name", ""))
            if rec_name:
                cleaned["personal_details_name"] = rec_name
            else:
                self.add_error("personal_details_name", "Personal Details Name is required when Adjust is checked.")

        is_from_stock = cleaned.get("is_from_stock_intake")
        stock_emp = cleaned.get("stock_employee_name")
        if is_from_stock and not stock_emp:
            self.add_error("stock_employee_name", "Employee name is required when issuing from Stock Intake.")

        return cleaned

    def save(self, commit=True):
        client_name = self.cleaned_data["client_name"].strip()
        client, _ = Client.objects.get_or_create(name=client_name)
        instance = super().save(commit=False)
        instance.client = client
        instance.challan_type = Challan.ChallanType.QUOTATION
        if commit:
            instance.save()
        return instance


class BaseChallanItemFormSet(forms.BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        if instance and instance.pk and instance.items.exists():
            self.extra = 0
        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()
        has_items = False
        idx = 1
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE", False):
                continue

            product = form.cleaned_data.get("product_name")
            qty = form.cleaned_data.get("quantity")

            if product and (qty is None or qty <= 0):
                form.add_error("quantity", "Quantity is required and must be at least 1.")

            if product:
                has_items = True

            form.cleaned_data["serial_number"] = idx
            if hasattr(form, "instance") and form.instance:
                form.instance.serial_number = idx
            idx += 1

        if not has_items and not any(self.errors):
            raise forms.ValidationError("At least one item with a valid product name and quantity is required.")

    def save(self, commit=True):
        instances = super().save(commit=False)
        for idx, instance in enumerate(instances, start=1):
            instance.serial_number = idx
            if commit:
                instance.save()
        if commit:
            for obj in self.deleted_objects:
                obj.delete()
            self.save_m2m()
        return instances


ChallanItemFormSet = inlineformset_factory(
    Challan,
    ChallanItem,
    formset=BaseChallanItemFormSet,
    fields=["serial_number", "product_name", "quantity", "actual_qty", "stock_intake"],
    widgets={
        "product_name": forms.TextInput(attrs={"list": "existing-items", "autocomplete": "off"}),
    },
    extra=1,
    can_delete=True,
)


# ---------------------------------------------------------------------
# Hand Challan (auto-generated challan no.)
# ---------------------------------------------------------------------
class HandChallanForm(BaseStyledForm):
    client_name = forms.CharField(
        label="Client's Name",
        widget=forms.TextInput(attrs={"list": "existing-clients", "autocomplete": "off"}),
    )

    class Meta:
        model = Challan
        fields = [
            "contact_name",
            "delivered_by",
            "received_by_name",
            "received_by_phone",
            "personal_details_name",
            "personal_details_phone",
            "adjust_requested",
            "adjust_reason",
            "is_from_stock_intake",
            "stock_employee_name",
            "created_at",
        ]
        widgets = {
            "adjust_reason": forms.Textarea(
                attrs={"rows": 2, "placeholder": "Specify what was adjusted or replaced..."}
            ),
            "created_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local", "class": "form-control"}
            ),
        }
        labels = {
            "contact_name": "Name",
            "received_by_name": "Received By — Name",
            "received_by_phone": "Phone No.",
            "personal_details_name": "Personal Details — Name",
            "personal_details_phone": "Phone No.",
            "adjust_reason": "Adjustment / Replacement Details",
            "is_from_stock_intake": "Issue from Employee Stock Intake?",
            "stock_employee_name": "Employee Name (Stock Intake)",
            "created_at": "Hand Challan Date",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.created_at:
            self.initial["created_at"] = timezone.localtime(self.instance.created_at).strftime("%Y-%m-%dT%H:%M")
        if not self.initial.get("created_at"):
            self.initial["created_at"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%dT%H:%M")

    def clean(self):
        cleaned = super().clean()
        adjust_requested = cleaned.get("adjust_requested")
        personal_details_name = cleaned.get("personal_details_name")
        if adjust_requested and not personal_details_name:
            rec_name = cleaned.get("received_by_name") or (self.instance and getattr(self.instance, "received_by_name", ""))
            if rec_name:
                cleaned["personal_details_name"] = rec_name
            else:
                self.add_error("personal_details_name", "Personal Details Name is required when Adjust is checked.")

        is_from_stock = cleaned.get("is_from_stock_intake")
        stock_emp = cleaned.get("stock_employee_name")
        if is_from_stock and not stock_emp:
            self.add_error("stock_employee_name", "Employee name is required when issuing from Stock Intake.")

        return cleaned

    def save(self, commit=True):
        client_name = self.cleaned_data["client_name"].strip()
        client, _ = Client.objects.get_or_create(name=client_name)
        instance = super().save(commit=False)
        instance.client = client
        instance.challan_type = Challan.ChallanType.HAND
        instance.is_quotation_based = False
        if commit:
            instance.save()
        return instance


# ---------------------------------------------------------------------
# Void / adjust / approval actions on the dashboard
# ---------------------------------------------------------------------
class VoidChallanForm(forms.Form):
    void_reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))


class ChallanNoChangeForm(forms.Form):
    new_challan_no = forms.CharField(label="New Challan No.")
    reason = forms.CharField(
        label="Reason for change",
        widget=forms.Textarea(attrs={"rows": 3}),
    )


# ---------------------------------------------------------------------
# Billing Context
# ---------------------------------------------------------------------
class BillingContextForm(forms.Form):
    company_name = forms.ModelChoiceField(
        queryset=Company.objects.all(),
        label="Specific Company Name",
        required=True,
    )
    bill_no = forms.CharField(
        label="Bill No.",
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={"placeholder": "e.g. BILL-2026-001"}),
    )
    created_at = forms.DateTimeField(
        label="Billing Date",
        required=False,
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local", "class": "form-control"}
        ),
    )
    challans = forms.ModelMultipleChoiceField(
        queryset=Challan.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Challans to Bill Out",
        error_messages={"required": "Please select at least one challan to bill out."},
    )

    def __init__(self, *args, **kwargs):
        client_id = kwargs.pop("client_id", None)
        start_date = kwargs.pop("start_date", None)
        end_date = kwargs.pop("end_date", None)
        super().__init__(*args, **kwargs)
        if not self.initial.get("created_at"):
            self.initial["created_at"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%dT%H:%M")
        qs = (
            Challan.objects.filter(status=Challan.Status.APPROVED, is_billed_out=False)
            .select_related("client")
            .order_by("client__name", "-created_at")
        )
        if client_id:
            qs = qs.filter(client_id=client_id)
        if start_date:
            qs = qs.filter(created_at__date__gte=start_date)
        if end_date:
            qs = qs.filter(created_at__date__lte=end_date)
        self.fields["challans"].queryset = qs

    def clean_challans(self):
        challans = self.cleaned_data.get("challans")
        if challans:
            already_billed = [c for c in challans if c.is_billed_out]
            if already_billed:
                raise forms.ValidationError("One or more selected challans have already been billed out.")
        return challans


# ---------------------------------------------------------------------
# Stock: Intake
# ---------------------------------------------------------------------
class StockItemForm(BaseStyledForm):
    class Meta:
        model = StockItem
        fields = ["name", "brand", "model", "serial_number", "is_disposable"]


class StockIntakeForm(BaseStyledForm):
    class Meta:
        model = StockIntake
        fields = ["employee_name", "stock_item", "quantity", "created_at"]
        labels = {
            "employee_name": "Employee Name",
            "stock_item": "Stock Item",
            "quantity": "Intake Qty",
            "created_at": "Intake Date",
        }
        widgets = {
            "created_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local", "class": "form-control"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.initial.get("created_at"):
            self.initial["created_at"] = timezone.localtime(timezone.now()).strftime("%Y-%m-%dT%H:%M")


class StockDecreaseForm(forms.Form):
    decrease_quantity = forms.IntegerField(
        min_value=1,
        label="Decrease Qty",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Qty to deduct"}),
    )


# ---------------------------------------------------------------------
# Challan Extend (one-time, requires reason)
# ---------------------------------------------------------------------
class ChallanExtendForm(forms.Form):
    reason = forms.CharField(
        label="Reason for Extension",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Explain why this challan needs more time…"}),
    )


# ---------------------------------------------------------------------
# Company Management
# ---------------------------------------------------------------------
class CompanyForm(BaseStyledForm):
    class Meta:
        model = Company
        fields = ["name", "code"]
        labels = {
            "name": "Company Name",
            "code": "Company Code / Prefix",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Acme Corp"}),
            "code": forms.TextInput(attrs={"placeholder": "e.g. ACME"}),
        }
