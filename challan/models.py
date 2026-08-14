import datetime

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


VOID_WINDOW_DAYS = 3       # initial active window (days)
OVERDUE_LOCK_DAYS = 7      # if not extended by day 7, challan locks


class Company(models.Model):
    """The internal or billed business divisions (e.g. Office, Store, Maintenance)"""
    name = models.CharField(max_length=255, unique=True)
    code = models.CharField(max_length=10, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Companies"

    def __str__(self):
        return self.name



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

    billed_company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="challans",
        null=True,
        blank=True,
        verbose_name="Billed Company (or Firm)"
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
    personal_details_name = models.CharField(max_length=255, blank=True)
    personal_details_phone = models.CharField(max_length=30, blank=True)

    # Billing state
    is_billed_out = models.BooleanField(default=False)
    billed_out_at = models.DateTimeField(null=True, blank=True)

    # Lock/void window & pending reminder tracking
    locked = models.BooleanField(default=False)
    unlocked_by_admin = models.BooleanField(default=False)
    # Extension: one-time 3-day extension after the initial 3-day window
    extension_days = models.PositiveIntegerField(default=0)  # 0 = not extended, 3 = extended
    extended_at = models.DateTimeField(null=True, blank=True)  # when the extension was granted
    extend_reason = models.TextField(blank=True)              # required reason for extension
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
    # Void / lock window logic
    # Timeline:
    #   Day 0–3  : active (void/edit freely)
    #   Day 3–7  : overdue — one-time extend available WITH reason
    #   Day 7+   : locked (admin unlock only)
    #   If extended: 3 more days from extended_at, then locked
    # ------------------------------------------------------------------

    @property
    def initial_deadline(self):
        """The original 3-day active window."""
        return self.created_at + datetime.timedelta(days=VOID_WINDOW_DAYS)

    @property
    def overdue_lock_deadline(self):
        """Day 7 — if not extended by then, challan locks."""
        return self.created_at + datetime.timedelta(days=OVERDUE_LOCK_DAYS)

    @property
    def extension_deadline(self):
        """When the one-time extension expires.
        Always the full 7-day mark from creation, so extending gives
        the challan until day 7 regardless of when the extension was taken."""
        if self.extension_days > 0 and self.extended_at:
            return self.overdue_lock_deadline
        return None

    @property
    def void_deadline(self):
        """The effective latest active deadline (used in templates)."""
        if self.extension_deadline:
            return self.extension_deadline
        return self.initial_deadline

    @property
    def can_void(self):
        """True if the challan can still be acted on (voided / edited)."""
        if self.status != self.Status.PENDING:
            return False
        if self.unlocked_by_admin:
            return True
        now = timezone.now()
        if now <= self.initial_deadline:
            return True
        # Extended window
        if self.extension_deadline and now <= self.extension_deadline:
            return True
        return False

    @property
    def can_extend(self):
        """True only when:
        - still pending
        - past the initial 3-day window (overdue)
        - within the 7-day lock deadline
        - not yet extended (one-time only)
        - not admin-unlocked
        """
        if self.status != self.Status.PENDING:
            return False
        if self.extension_days > 0:   # already extended once
            return False
        if self.unlocked_by_admin:
            return False
        now = timezone.now()
        return self.initial_deadline < now <= self.overdue_lock_deadline

    @property
    def is_overdue_for_reminder(self):
        """Pending challan past its initial 3-day window — show the overdue banner."""
        if self.status != self.Status.PENDING:
            return False
        return timezone.now() > self.initial_deadline

    @property
    def is_locked_out(self):
        """Truly locked: past day 7 without extension, or extension expired,
        and not admin-unlocked."""
        if self.status != self.Status.PENDING:
            return False
        if self.unlocked_by_admin:
            return False
        if self.can_void or self.can_extend:
            return False
        return True

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

    company_name = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="billings",
        null=True,
        blank=True,
        verbose_name="Specific Company Name"
    )

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
