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
            "is_quotation_based": "Quotation Based",
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
        instance.challan_type = Challan.ChallanType.QUOTATION
        if commit:
            instance.save()
        return instance


ChallanItemFormSet = inlineformset_factory(
    Challan,
    ChallanItem,
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
    company_name = forms.CharField(label="Specific Company Name")
    client = forms.ModelChoiceField(
        queryset=Client.objects.all(), label="Client's Name"
    )
    challans = forms.ModelMultipleChoiceField(
        queryset=Challan.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Pending Challans",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        client_id = None
        if self.data.get("client"):
            client_id = self.data.get("client")
        elif self.initial.get("client"):
            client_id = self.initial.get("client")
        qs = Challan.objects.filter(status=Challan.Status.APPROVED, is_billed_out=False)
        if client_id:
            qs = qs.filter(client_id=client_id)
        self.fields["challans"].queryset = qs

    def clean(self):
        cleaned = super().clean()
        client = cleaned.get("client")
        challans = cleaned.get("challans")
        if client and challans:
            mismatched = [c for c in challans if c.client_id != client.id]
            if mismatched:
                raise forms.ValidationError(
                    "The billing out client's name doesn't match the client's "
                    "name on the selected challan(s) — invalid."
                )
            already_billed = [c for c in challans if c.is_billed_out]
            if already_billed:
                raise forms.ValidationError(
                    "This challan has already been billed out."
                )
        return cleaned


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
