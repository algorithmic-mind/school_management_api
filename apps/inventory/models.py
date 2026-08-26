"""
مدل‌های خرید، انبار و اموال.

مرجع: بخش ۷.۹ سند تحلیل — ERD «خرید، انبار و اموال».

قیدهای مهم:
- موجودی فقط از STOCK_MOVEMENT قطعی تغییر می‌کند؛ ویرایش مستقیم
  STOCK_BALANCE ممنوع است.
- موجودی قابل‌دسترس = on_hand − reserved؛ منفی‌شدن فقط با مجوز.
- کالای سریال‌دار در هر حرکت خروجی باید سریال یکتا داشته باشد.
- تطبیق سه‌طرفه سفارش، رسید و فاکتور پیش از پرداخت انجام می‌شود.
- سند قطعی انبار ویرایش نمی‌شود؛ برگشت حرکت معکوس ایجاد می‌کند.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseTenantModel, ImmutableLedgerModel
from apps.inventory.enums import (
    AssetCondition,
    AssetLifecycleStatus,
    AssigneeType,
    MaintenanceStatus,
    MaintenanceType,
    PurchaseOrderStatus,
    PurchaseRequestStatus,
    QualityStatus,
    ReceiptStatus,
    StockDocumentStatus,
    StockDocumentType,
    VendorStatus,
)
from apps.organization.models import Campus, Room, School


class Vendor(BaseTenantModel):
    """تأمین‌کننده."""

    code = models.CharField(max_length=30, db_index=True)
    legal_name = models.CharField(max_length=250, verbose_name=_("نام حقوقی"))
    tax_id = models.CharField(max_length=40, blank=True, verbose_name=_("شناسه مالیاتی"))
    contact_person = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address_line = models.CharField(max_length=400, blank=True)
    payment_terms_days = models.PositiveSmallIntegerField(
        default=0, verbose_name=_("مهلت پرداخت (روز)")
    )
    status = models.CharField(
        max_length=20, choices=VendorStatus.choices, default=VendorStatus.ACTIVE
    )

    class Meta:
        verbose_name = _("تأمین‌کننده")
        verbose_name_plural = _("تأمین‌کنندگان")
        ordering = ("legal_name",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="uq_vendor_tenant_code"
            )
        ]

    def __str__(self) -> str:
        return self.legal_name


class UnitOfMeasure(BaseTenantModel):
    """واحد سنجش."""

    code = models.CharField(max_length=20, db_index=True)
    title = models.CharField(max_length=80)
    decimal_places = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = _("واحد سنجش")
        verbose_name_plural = _("واحدهای سنجش")
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uq_uom_tenant_code")
        ]

    def __str__(self) -> str:
        return self.title


class ItemCategory(BaseTenantModel):
    """دسته کالا (درختی)."""

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="item_categories"
    )
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )
    code = models.CharField(max_length=30)
    title = models.CharField(max_length=150)

    class Meta:
        verbose_name = _("دسته کالا")
        verbose_name_plural = _("دسته‌های کالا")
        constraints = [
            models.UniqueConstraint(
                fields=["school", "code"], name="uq_item_category_school_code"
            )
        ]

    def __str__(self) -> str:
        return self.title


class Item(BaseTenantModel):
    """کالا."""

    category = models.ForeignKey(
        ItemCategory, on_delete=models.PROTECT, related_name="items"
    )
    base_uom = models.ForeignKey(
        UnitOfMeasure, on_delete=models.PROTECT, related_name="items"
    )
    sku = models.CharField(max_length=40, db_index=True, verbose_name=_("کد کالا"))
    title = models.CharField(max_length=200)
    description = models.CharField(max_length=400, blank=True)
    barcode = models.CharField(max_length=60, blank=True, db_index=True)
    lot_tracked = models.BooleanField(default=False, verbose_name=_("ردیابی بچ"))
    serial_tracked = models.BooleanField(default=False, verbose_name=_("ردیابی سریال"))
    expiry_tracked = models.BooleanField(default=False, verbose_name=_("ردیابی انقضا"))
    is_capital_asset = models.BooleanField(
        default=False, verbose_name=_("مال سرمایه‌ای (نه مصرفی)")
    )
    reorder_point = models.DecimalField(
        max_digits=12, decimal_places=3, default=0, verbose_name=_("نقطه سفارش")
    )
    min_stock = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    max_stock = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    allow_negative_stock = models.BooleanField(
        default=False,
        verbose_name=_("اجازه موجودی منفی"),
        help_text=_("بخش ۷.۹: منفی‌شدن فقط برای اقلام مجاز با تأیید"),
    )
    expense_account_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=20, default="ACTIVE")

    class Meta:
        verbose_name = _("کالا")
        verbose_name_plural = _("کالاها")
        ordering = ("title",)
        constraints = [
            models.UniqueConstraint(fields=["tenant", "sku"], name="uq_item_tenant_sku")
        ]

    def __str__(self) -> str:
        return f"{self.sku} — {self.title}"


class Warehouse(BaseTenantModel):
    """انبار."""

    campus = models.ForeignKey(
        Campus, on_delete=models.PROTECT, related_name="warehouses"
    )
    code = models.CharField(max_length=30, db_index=True)
    title = models.CharField(max_length=150)
    location = models.CharField(max_length=200, blank=True)
    keeper_employee_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=20, default="ACTIVE")

    class Meta:
        verbose_name = _("انبار")
        verbose_name_plural = _("انبارها")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="uq_warehouse_tenant_code"
            )
        ]

    def __str__(self) -> str:
        return self.title


class StockBalance(BaseTenantModel):
    """
    موجودی خلاصه.

    بخش ۷.۹: «موجودی فقط از STOCK_MOVEMENT قطعی تغییر می‌کند؛ ویرایش مستقیم
    STOCK_BALANCE ممنوع است.» این جدول قابل بازسازی از حرکات است.
    """

    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE, related_name="balances"
    )
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="balances")
    lot_no = models.CharField(max_length=60, blank=True, verbose_name=_("شماره بچ"))
    expiry_date = models.DateField(null=True, blank=True)
    on_hand_qty = models.DecimalField(
        max_digits=14, decimal_places=3, default=0, verbose_name=_("موجودی")
    )
    reserved_qty = models.DecimalField(
        max_digits=14, decimal_places=3, default=0, verbose_name=_("رزروشده")
    )
    average_cost = models.BigIntegerField(default=0, verbose_name=_("بهای تمام‌شده میانگین"))

    class Meta:
        verbose_name = _("موجودی انبار")
        verbose_name_plural = _("موجودی‌های انبار")
        constraints = [
            models.UniqueConstraint(
                fields=["warehouse", "item", "lot_no"], name="uq_stock_balance_key"
            )
        ]
        indexes = [models.Index(fields=["item", "warehouse"])]

    def __str__(self) -> str:
        return f"{self.item.sku} @ {self.warehouse.code}: {self.on_hand_qty}"

    @property
    def available_qty(self):
        """موجودی قابل‌دسترس = on_hand − reserved (بخش ۷.۹)."""
        return self.on_hand_qty - self.reserved_qty


class StockDocument(BaseTenantModel):
    """سند انبار (رسید، حواله، انتقال، تعدیل)."""

    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name="documents"
    )
    document_no = models.CharField(max_length=40, db_index=True)
    document_type = models.CharField(max_length=25, choices=StockDocumentType.choices)
    document_at = models.DateTimeField(verbose_name=_("تاریخ سند"))
    source_type = models.CharField(max_length=60, blank=True)
    source_id = models.UUIDField(null=True, blank=True)
    counterpart_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="counterpart_documents",
        verbose_name=_("انبار مقابل (در انتقال)"),
    )
    status = models.CharField(
        max_length=20,
        choices=StockDocumentStatus.choices,
        default=StockDocumentStatus.DRAFT,
    )
    description = models.CharField(max_length=400, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by_id = models.UUIDField(null=True, blank=True)
    reversal_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversals",
    )

    class Meta:
        verbose_name = _("سند انبار")
        verbose_name_plural = _("اسناد انبار")
        ordering = ("-document_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "document_no"], name="uq_stock_document_tenant_no"
            )
        ]
        indexes = [models.Index(fields=["warehouse", "document_type", "-document_at"])]

    def __str__(self) -> str:
        return f"{self.document_no} ({self.get_document_type_display()})"


class StockDocumentLine(BaseTenantModel):
    """قلم سند انبار."""

    stock_document = models.ForeignKey(
        StockDocument, on_delete=models.CASCADE, related_name="lines"
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="document_lines")
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    uom = models.ForeignKey(
        UnitOfMeasure, on_delete=models.PROTECT, related_name="document_lines"
    )
    lot_no = models.CharField(max_length=60, blank=True)
    serial_no = models.CharField(max_length=80, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    unit_cost = models.BigIntegerField(default=0, verbose_name=_("بهای واحد (ریال)"))
    line_no = models.PositiveSmallIntegerField(default=1)

    class Meta:
        verbose_name = _("قلم سند انبار")
        verbose_name_plural = _("اقلام سند انبار")
        ordering = ("line_no",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="ck_stock_line_qty_positive"
            )
        ]

    def __str__(self) -> str:
        return f"{self.item.sku} × {self.quantity}"


class StockMovement(ImmutableLedgerModel):
    """
    حرکت موجودی — تنها منبع تغییر موجودی (بخش ۵ واژگان).

    `signed_quantity` مثبت برای ورود و منفی برای خروج است.
    """

    document_line = models.ForeignKey(
        StockDocumentLine, on_delete=models.PROTECT, related_name="movements"
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name="movements"
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="movements")
    lot_no = models.CharField(max_length=60, blank=True)
    serial_no = models.CharField(max_length=80, blank=True)
    signed_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_cost = models.BigIntegerField(default=0)
    occurred_at = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = _("حرکت موجودی")
        verbose_name_plural = _("حرکات موجودی")
        ordering = ("-occurred_at",)
        indexes = [
            models.Index(fields=["item", "warehouse", "-occurred_at"]),
            models.Index(fields=["serial_no"]),
        ]

    def __str__(self) -> str:
        return f"{self.item.sku}: {self.signed_quantity:+}"


class PurchaseRequest(BaseTenantModel):
    """درخواست خرید — ماشین حالت بخش ۱۰.۷."""

    requester_user_id = models.UUIDField(null=True, blank=True)
    campus = models.ForeignKey(
        Campus, on_delete=models.PROTECT, related_name="purchase_requests"
    )
    cost_center_id = models.UUIDField(null=True, blank=True)
    request_no = models.CharField(max_length=40, db_index=True)
    title = models.CharField(max_length=200)
    needed_by = models.DateField(null=True, blank=True)
    estimated_amount = models.BigIntegerField(default=0)
    justification = models.TextField(blank=True)
    status = models.CharField(
        max_length=25,
        choices=PurchaseRequestStatus.choices,
        default=PurchaseRequestStatus.DRAFT,
        db_index=True,
    )
    budget_reserved_amount = models.BigIntegerField(default=0)
    decision_note = models.CharField(max_length=400, blank=True)

    class Meta:
        verbose_name = _("درخواست خرید")
        verbose_name_plural = _("درخواست‌های خرید")
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "request_no"], name="uq_purchase_request_tenant_no"
            )
        ]

    def __str__(self) -> str:
        return f"{self.request_no} — {self.title}"


class PurchaseRequestLine(BaseTenantModel):
    """قلم درخواست خرید."""

    request = models.ForeignKey(
        PurchaseRequest, on_delete=models.CASCADE, related_name="lines"
    )
    item = models.ForeignKey(
        Item, on_delete=models.PROTECT, related_name="request_lines"
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    estimated_unit_price = models.BigIntegerField(default=0)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("قلم درخواست خرید")
        verbose_name_plural = _("اقلام درخواست خرید")


class PurchaseOrder(BaseTenantModel):
    """سفارش خرید."""

    vendor = models.ForeignKey(
        Vendor, on_delete=models.PROTECT, related_name="purchase_orders"
    )
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    order_no = models.CharField(max_length=40, db_index=True)
    ordered_on = models.DateField()
    expected_on = models.DateField(null=True, blank=True)
    total_amount = models.BigIntegerField(default=0)
    tax_amount = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3, default="IRR")
    status = models.CharField(
        max_length=25,
        choices=PurchaseOrderStatus.choices,
        default=PurchaseOrderStatus.DRAFT,
    )
    note = models.CharField(max_length=400, blank=True)

    class Meta:
        verbose_name = _("سفارش خرید")
        verbose_name_plural = _("سفارش‌های خرید")
        ordering = ("-ordered_on",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "order_no"], name="uq_purchase_order_tenant_no"
            )
        ]

    def __str__(self) -> str:
        return f"{self.order_no} — {self.vendor.legal_name}"


class PurchaseOrderLine(BaseTenantModel):
    """قلم سفارش خرید."""

    order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="lines"
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="order_lines")
    ordered_qty = models.DecimalField(max_digits=14, decimal_places=3)
    received_qty = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    unit_price = models.BigIntegerField(default=0)
    line_no = models.PositiveSmallIntegerField(default=1)

    class Meta:
        verbose_name = _("قلم سفارش خرید")
        verbose_name_plural = _("اقلام سفارش خرید")
        ordering = ("line_no",)

    @property
    def remaining_qty(self):
        return self.ordered_qty - self.received_qty


class GoodsReceipt(BaseTenantModel):
    """رسید کالا."""

    order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="receipts"
    )
    stock_document = models.OneToOneField(
        StockDocument,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="goods_receipt",
    )
    receipt_no = models.CharField(max_length=40, db_index=True)
    received_at = models.DateTimeField()
    quality_status = models.CharField(
        max_length=25, choices=QualityStatus.choices, default=QualityStatus.PENDING
    )
    status = models.CharField(
        max_length=20, choices=ReceiptStatus.choices, default=ReceiptStatus.PROVISIONAL
    )
    vendor_invoice_no = models.CharField(max_length=60, blank=True)
    vendor_invoice_amount = models.BigIntegerField(default=0)
    three_way_matched = models.BooleanField(
        default=False,
        verbose_name=_("تطبیق سه‌طرفه انجام شد"),
        help_text=_("بخش ۷.۹: تطبیق سفارش، رسید و فاکتور پیش از پرداخت"),
    )
    note = models.CharField(max_length=400, blank=True)

    class Meta:
        verbose_name = _("رسید کالا")
        verbose_name_plural = _("رسیدهای کالا")
        ordering = ("-received_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "receipt_no"], name="uq_goods_receipt_tenant_no"
            )
        ]

    def __str__(self) -> str:
        return self.receipt_no


class Asset(BaseTenantModel):
    """مال سرمایه‌ای — ماشین حالت بخش ۱۰.۸."""

    item = models.ForeignKey(
        Item, on_delete=models.PROTECT, null=True, blank=True, related_name="assets"
    )
    asset_tag = models.CharField(max_length=40, db_index=True, verbose_name=_("پلاک اموال"))
    title = models.CharField(max_length=200)
    serial_no = models.CharField(max_length=80, blank=True, db_index=True)
    acquired_on = models.DateField()
    acquisition_cost = models.BigIntegerField(default=0)
    useful_life_months = models.PositiveSmallIntegerField(default=0)
    accumulated_depreciation = models.BigIntegerField(default=0)
    warranty_until = models.DateField(null=True, blank=True)
    insurance_policy_no = models.CharField(max_length=60, blank=True)
    condition_status = models.CharField(
        max_length=15, choices=AssetCondition.choices, default=AssetCondition.NEW
    )
    lifecycle_status = models.CharField(
        max_length=25,
        choices=AssetLifecycleStatus.choices,
        default=AssetLifecycleStatus.REGISTERED,
        db_index=True,
    )
    current_room = models.ForeignKey(
        Room, on_delete=models.SET_NULL, null=True, blank=True, related_name="assets"
    )

    class Meta:
        verbose_name = _("مال سرمایه‌ای")
        verbose_name_plural = _("اموال")
        ordering = ("asset_tag",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "asset_tag"], name="uq_asset_tenant_tag"
            )
        ]

    def __str__(self) -> str:
        return f"{self.asset_tag} — {self.title}"

    @property
    def book_value(self) -> int:
        return max(self.acquisition_cost - self.accumulated_depreciation, 0)


class AssetAssignment(BaseTenantModel):
    """تحویل مال به کارمند/اتاق/واحد."""

    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name="assignments"
    )
    assignee_type = models.CharField(max_length=20, choices=AssigneeType.choices)
    assignee_id = models.UUIDField()
    location_room = models.ForeignKey(
        Room, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="asset_assignments",
    )
    assigned_at = models.DateTimeField()
    returned_at = models.DateTimeField(null=True, blank=True)
    condition_on_assign = models.CharField(
        max_length=15, choices=AssetCondition.choices, blank=True
    )
    condition_on_return = models.CharField(
        max_length=15, choices=AssetCondition.choices, blank=True
    )
    status = models.CharField(max_length=20, default="ACTIVE")
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("تحویل اموال")
        verbose_name_plural = _("تحویل‌های اموال")
        ordering = ("-assigned_at",)
        indexes = [models.Index(fields=["assignee_type", "assignee_id"])]


class MaintenanceOrder(BaseTenantModel):
    """دستور تعمیر و نگهداری."""

    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name="maintenance_orders"
    )
    order_no = models.CharField(max_length=40, db_index=True)
    maintenance_type = models.CharField(max_length=20, choices=MaintenanceType.choices)
    description = models.TextField(blank=True)
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_orders",
    )
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    cost_amount = models.BigIntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=MaintenanceStatus.choices, default=MaintenanceStatus.OPEN
    )

    class Meta:
        verbose_name = _("دستور تعمیر")
        verbose_name_plural = _("دستورهای تعمیر")
        ordering = ("-opened_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "order_no"], name="uq_maintenance_tenant_no"
            )
        ]

    def __str__(self) -> str:
        return f"{self.order_no} — {self.asset.asset_tag}"
