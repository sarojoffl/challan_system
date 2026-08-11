import datetime

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


VOID_WINDOW_DAYS = 3
PENDING_REMINDER_DAYS = 7  # "after 3-day due date, then after 1 week" reminder cycle


class Client(models.Model):
    """A billing client. Kept as its own model so the same client can be
    picked from a dropdown across the Initiation Form, Billing Context and
    Hand Challan forms, and so challan <-> client matching can be validated
    in the Billing Context flow."""

    name = models.CharField(max_length=255, unique=True)
    phone_no = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Challan(models.Model):
    """Covers both the quotation-based Initiation Form challan and the
    auto-generated Hand Challan. `challan_type` distinguishes the two;
    most fields are shared, per the notes ("Same as initiation form for
    goods detail")."""

    class ChallanType(models.TextChoices):
        QUOTATION = "quotation", "Quotation-based (Initiation Form)"
        HAND = "hand", "Hand Challan"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        VOID = "void", "Void"

    challan_type = models.CharField(max_length=20, choices=ChallanType.choices)
    challan_no = models.CharField(max_length=50, unique=True, blank=True)

    billed_company = models.CharField(
        "Billed Company (or Firm)", max_length=255, blank=True
    )
    client = models.ForeignKey(
        Client, on_delete=models.PROTECT, related_name="challans"
    )
    contact_name = models.CharField("Name", max_length=255, blank=True)

    is_quotation_based = models.BooleanField(default=False)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    void_reason = models.TextField(blank=True)
    challan_no_change_reason = models.TextField(
        "Challan No. change reason", blank=True
    )

    # Adjustment / replacement material workflow
    adjust_requested = models.BooleanField("Adjust", default=False)
    admin_approval_required = models.BooleanField(default=False)
    admin_approved = models.BooleanField(default=False)

    # Delivery / receipt info
    delivered_by = models.CharField(max_length=255, blank=True)
    received_by_name = models.CharField(max_length=255, blank=True)
    received_by_phone = models.CharField(max_length=30, blank=True)

    # Billing state
    is_billed_out = models.BooleanField(default=False)
    billed_out_at = models.DateTimeField(null=True, blank=True)

    # Lock/void window & pending reminder tracking
    locked = models.BooleanField(default=False)
    unlocked_by_admin = models.BooleanField(default=False)
    last_reminder_sent_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="challans_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.challan_no} ({self.get_status_display()})"

    # ------------------------------------------------------------------
    # Numbering
    # ------------------------------------------------------------------
    def save(self, *args, **kwargs):
        if not self.challan_no and self.challan_type == self.ChallanType.HAND:
            self.challan_no = self._generate_hand_challan_no()
        self.admin_approval_required = self.adjust_requested
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_hand_challan_no():
        today = timezone.localdate()
        prefix = f"HC-{today.strftime('%Y%m%d')}"
        last = (
            Challan.objects.filter(challan_no__startswith=prefix)
            .order_by("-challan_no")
            .first()
        )
        seq = 1
        if last:
            try:
                seq = int(last.challan_no.rsplit("-", 1)[-1]) + 1
            except ValueError:
                seq = 1
        return f"{prefix}-{seq:03d}"

    # ------------------------------------------------------------------
    # Void / lock window logic — "Time duration for user to void: 3 days.
    # Replacement adjust/material unlock; void greyed out (locked) after
    # 3 days unless admin unlocks."
    # ------------------------------------------------------------------
    @property
    def void_deadline(self):
        return self.created_at + datetime.timedelta(days=VOID_WINDOW_DAYS)

    @property
    def can_void(self):
        if self.status != self.Status.PENDING:
            return False
        if self.unlocked_by_admin:
            return True
        return timezone.now() <= self.void_deadline

    @property
    def is_overdue_for_reminder(self):
        """Pending Challan time limit 3-days -> after due date, remind
        again every 1 week until the user updates (extend / change
        challan no. / void)."""
        if self.status != self.Status.PENDING:
            return False
        return timezone.now() > self.void_deadline

    def get_absolute_url(self):
        return reverse("challan:challan_detail", args=[self.pk])


class ChallanItem(models.Model):
    challan = models.ForeignKey(
        Challan, on_delete=models.CASCADE, related_name="items"
    )
    serial_number = models.PositiveIntegerField("S.N.")
    product_name = models.CharField("Item / Goods detail", max_length=255)
    quantity = models.PositiveIntegerField("Qty")

    class Meta:
        ordering = ["serial_number"]

    def __str__(self):
        return f"{self.serial_number}. {self.product_name} x{self.quantity}"


class Billing(models.Model):
    """Billing Context: selecting a company + client, picking pending
    challans belonging to that client, and marking them billed out."""

    company_name = models.CharField(max_length=255)
    client = models.ForeignKey(
        Client, on_delete=models.PROTECT, related_name="billings"
    )
    challans = models.ManyToManyField(Challan, related_name="billing_entries")
    adjust_requested = models.BooleanField("Adjust", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Billings"

    def __str__(self):
        return f"Billing #{self.pk} — {self.client}"


class StockItem(models.Model):
    """Inventory catalog item, added via Stock Intake."""

    name = models.CharField(max_length=255)
    brand = models.CharField(max_length=255, blank=True)
    model = models.CharField(max_length=255, blank=True)
    serial_number = models.CharField(max_length=255, blank=True)
    is_disposable = models.BooleanField(default=False)
    quantity_available = models.IntegerField(default=0)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        bits = [self.name]
        if self.brand:
            bits.append(self.brand)
        return " - ".join(bits)


class StockIntake(models.Model):
    """A stock-in event ("Stock: Intake"). Increases the linked
    StockItem's quantity_available on save."""

    stock_item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="intakes"
    )
    for_client = models.ForeignKey(
        Client,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_intakes",
    )
    quantity = models.PositiveIntegerField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            StockItem.objects.filter(pk=self.stock_item_id).update(
                quantity_available=models.F("quantity_available") + self.quantity
            )

    def __str__(self):
        return f"Intake: {self.stock_item} +{self.quantity}"


class EmployeeStockChallan(models.Model):
    """Hand Challan issuing stock to an individual employee. Deducts
    stock and is merged into the main Challan Dashboard via its
    `challan` link."""

    employee_name = models.CharField(max_length=255)
    challan = models.OneToOneField(
        Challan,
        on_delete=models.CASCADE,
        related_name="employee_stock_challan",
    )
    delivered_by = models.CharField(max_length=255, blank=True)
    adjust_requested = models.BooleanField("Adjust", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Stock hand challan for {self.employee_name} ({self.challan.challan_no})"


class EmployeeStockChallanItem(models.Model):
    employee_stock_challan = models.ForeignKey(
        EmployeeStockChallan, on_delete=models.CASCADE, related_name="items"
    )
    stock_item = models.ForeignKey(StockItem, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            StockItem.objects.filter(pk=self.stock_item_id).update(
                quantity_available=models.F("quantity_available") - self.quantity
            )

    def __str__(self):
        return f"{self.stock_item} x{self.quantity}"
