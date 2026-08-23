from django import forms
from django.forms import inlineformset_factory

from .models import (
    Billing,
    Challan,
    ChallanItem,
    Client,
    EmployeeStockChallan,
    EmployeeStockChallanItem,
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
        ]
        labels = {
            "billed_company": "Billed Company (or Firm)",
            "challan_no": "Challan No.",
            "contact_name": "Name",
            "received_by_name": "Received By — Name",
            "received_by_phone": "Phone No.",
            "personal_details_name": "Personal Details — Name",
            "personal_details_phone": "Phone No.",
        }

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
            self.add_error("personal_details_name", "Personal Details Name is required when Adjust is checked.")
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


class BaseChallanItemFormSet(forms.models.BaseInlineFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)
        if "serial_number" in form.fields:
            form.fields["serial_number"].widget = forms.HiddenInput()
            form.fields["serial_number"].required = False

    def clean(self):
        super().clean()
        idx = 1
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get("DELETE", False):
                form.cleaned_data["serial_number"] = idx
                if hasattr(form, "instance") and form.instance:
                    form.instance.serial_number = idx
                idx += 1

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
    fields=["serial_number", "product_name", "quantity"],
    extra=1,
    can_delete=True,
)


# ---------------------------------------------------------------------
# Hand Challan (auto-generated challan no.)
# ---------------------------------------------------------------------
class HandChallanForm(BaseStyledForm):
    client_name = forms.CharField(label="Client's Name")

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
        ]
        labels = {
            "contact_name": "Name",
            "received_by_name": "Received By — Name",
            "received_by_phone": "Phone No.",
            "personal_details_name": "Personal Details — Name",
            "personal_details_phone": "Phone No.",
        }

    def clean(self):
        cleaned = super().clean()
        adjust_requested = cleaned.get("adjust_requested")
        personal_details_name = cleaned.get("personal_details_name")
        if adjust_requested and not personal_details_name:
            self.add_error("personal_details_name", "Personal Details Name is required when Adjust is checked.")
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
    challans = forms.ModelMultipleChoiceField(
        queryset=Challan.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Challans to Bill Out",
        error_messages={"required": "Please select at least one challan to bill out."},
    )

    def __init__(self, *args, **kwargs):
        client_id = kwargs.pop("client_id", None)
        super().__init__(*args, **kwargs)
        qs = (
            Challan.objects.filter(status=Challan.Status.APPROVED, is_billed_out=False)
            .select_related("client")
            .order_by("client__name", "-created_at")
        )
        if client_id:
            qs = qs.filter(client_id=client_id)
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
        fields = ["stock_item", "for_client", "quantity"]


# ---------------------------------------------------------------------
# Stock / Hand Challan for employees
# ---------------------------------------------------------------------
class EmployeeStockChallanForm(forms.ModelForm):
    class Meta:
        model = EmployeeStockChallan
        fields = ["employee_name", "delivered_by", "adjust_requested"]


EmployeeStockChallanItemFormSet = inlineformset_factory(
    EmployeeStockChallan,
    EmployeeStockChallanItem,
    fields=["stock_item", "quantity"],
    extra=1,
    can_delete=True,
)


# ---------------------------------------------------------------------
# Challan Extend (one-time, requires reason)
# ---------------------------------------------------------------------
class ChallanExtendForm(forms.Form):
    reason = forms.CharField(
        label="Reason for Extension",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Explain why this challan needs more time…"}),
    )
