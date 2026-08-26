"""سریالایزرهای ماژول تدارکات، انبار و اموال."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.core.serializers import AUDIT_FIELDS
from apps.inventory.models import (
    Asset,
    AssetAssignment,
    GoodsReceipt,
    Item,
    ItemCategory,
    MaintenanceOrder,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequest,
    PurchaseRequestLine,
    StockBalance,
    StockDocument,
    StockDocumentLine,
    StockMovement,
    UnitOfMeasure,
    Vendor,
    Warehouse,
)


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = (
            "id",
            "code",
            "legal_name",
            "tax_id",
            "contact_person",
            "phone",
            "email",
            "address_line",
            "payment_terms_days",
            "status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class UnitOfMeasureSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitOfMeasure
        fields = ("id", "code", "title", "decimal_places")
        read_only_fields = ("id",)


class ItemCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemCategory
        fields = ("id", "school", "parent", "code", "title", *AUDIT_FIELDS[1:])
        read_only_fields = ("id", "created_at", "updated_at", "version")


class ItemSerializer(serializers.ModelSerializer):
    category_title = serializers.CharField(source="category.title", read_only=True)
    uom_title = serializers.CharField(source="base_uom.title", read_only=True)
    total_on_hand = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = (
            "id",
            "category",
            "category_title",
            "base_uom",
            "uom_title",
            "sku",
            "title",
            "description",
            "barcode",
            "lot_tracked",
            "serial_tracked",
            "expiry_tracked",
            "is_capital_asset",
            "reorder_point",
            "min_stock",
            "max_stock",
            "allow_negative_stock",
            "expense_account_id",
            "status",
            "total_on_hand",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")

    def get_total_on_hand(self, obj) -> float:
        from django.db.models import Sum

        total = obj.balances.aggregate(total=Sum("on_hand_qty"))["total"]
        return float(total or 0)


class WarehouseSerializer(serializers.ModelSerializer):
    campus_name = serializers.CharField(source="campus.name", read_only=True)

    class Meta:
        model = Warehouse
        fields = (
            "id",
            "campus",
            "campus_name",
            "code",
            "title",
            "location",
            "keeper_employee_id",
            "status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class StockBalanceSerializer(serializers.ModelSerializer):
    item_sku = serializers.CharField(source="item.sku", read_only=True)
    item_title = serializers.CharField(source="item.title", read_only=True)
    warehouse_code = serializers.CharField(source="warehouse.code", read_only=True)
    available_qty = serializers.DecimalField(
        max_digits=14, decimal_places=3, read_only=True
    )
    below_reorder_point = serializers.SerializerMethodField()

    class Meta:
        model = StockBalance
        fields = (
            "id",
            "warehouse",
            "warehouse_code",
            "item",
            "item_sku",
            "item_title",
            "lot_no",
            "expiry_date",
            "on_hand_qty",
            "reserved_qty",
            "available_qty",
            "average_cost",
            "below_reorder_point",
        )
        read_only_fields = fields

    def get_below_reorder_point(self, obj) -> bool:
        return bool(obj.item.reorder_point and obj.on_hand_qty < obj.item.reorder_point)


class StockDocumentLineSerializer(serializers.ModelSerializer):
    item_sku = serializers.CharField(source="item.sku", read_only=True)
    item_title = serializers.CharField(source="item.title", read_only=True)

    class Meta:
        model = StockDocumentLine
        fields = (
            "id",
            "stock_document",
            "item",
            "item_sku",
            "item_title",
            "quantity",
            "uom",
            "lot_no",
            "serial_no",
            "expiry_date",
            "unit_cost",
            "line_no",
        )
        read_only_fields = ("id",)


class StockDocumentSerializer(serializers.ModelSerializer):
    lines = StockDocumentLineSerializer(many=True, read_only=True)
    warehouse_code = serializers.CharField(source="warehouse.code", read_only=True)
    document_type_display = serializers.CharField(
        source="get_document_type_display", read_only=True
    )

    class Meta:
        model = StockDocument
        fields = (
            "id",
            "warehouse",
            "warehouse_code",
            "document_no",
            "document_type",
            "document_type_display",
            "document_at",
            "source_type",
            "source_id",
            "counterpart_warehouse",
            "status",
            "description",
            "confirmed_at",
            "reversal_of",
            "lines",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "document_no",
            "status",
            "confirmed_at",
            "reversal_of",
            "created_at",
            "updated_at",
            "version",
        )


class StockMovementSerializer(serializers.ModelSerializer):
    item_sku = serializers.CharField(source="item.sku", read_only=True)
    warehouse_code = serializers.CharField(source="warehouse.code", read_only=True)

    class Meta:
        model = StockMovement
        fields = (
            "id",
            "document_line",
            "warehouse",
            "warehouse_code",
            "item",
            "item_sku",
            "lot_no",
            "serial_no",
            "signed_quantity",
            "unit_cost",
            "occurred_at",
        )
        read_only_fields = fields


class KardexRowSerializer(serializers.Serializer):
    occurredAt = serializers.DateTimeField()
    documentNo = serializers.CharField()
    documentType = serializers.CharField()
    warehouse = serializers.CharField()
    lotNo = serializers.CharField(allow_blank=True)
    serialNo = serializers.CharField(allow_blank=True)
    quantity = serializers.FloatField()
    unitCost = serializers.IntegerField()
    balance = serializers.FloatField()


class KardexSerializer(serializers.Serializer):
    """کاردکس کالا (بخش ۱۳.۵ سند فرانت)."""

    itemId = serializers.UUIDField()
    sku = serializers.CharField()
    title = serializers.CharField()
    closingBalance = serializers.FloatField()
    rows = KardexRowSerializer(many=True)


class PurchaseRequestLineSerializer(serializers.ModelSerializer):
    item_title = serializers.CharField(source="item.title", read_only=True)
    available_stock = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseRequestLine
        fields = (
            "id",
            "request",
            "item",
            "item_title",
            "quantity",
            "estimated_unit_price",
            "note",
            "available_stock",
        )
        read_only_fields = ("id",)

    def get_available_stock(self, obj) -> float:
        """
        موجودی فعلی کالا — برای کنترل «آیا واقعاً نیاز به خرید است؟»
        (بخش ۱۳.۲ سند فرانت).
        """
        from django.db.models import Sum

        total = obj.item.balances.aggregate(total=Sum("on_hand_qty"))["total"]
        return float(total or 0)


class PurchaseRequestSerializer(serializers.ModelSerializer):
    lines = PurchaseRequestLineSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = PurchaseRequest
        fields = (
            "id",
            "requester_user_id",
            "campus",
            "cost_center_id",
            "request_no",
            "title",
            "needed_by",
            "estimated_amount",
            "justification",
            "status",
            "status_display",
            "budget_reserved_amount",
            "decision_note",
            "lines",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "request_no",
            "status",
            "requester_user_id",
            "created_at",
            "updated_at",
            "version",
        )


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    item_title = serializers.CharField(source="item.title", read_only=True)
    item_sku = serializers.CharField(source="item.sku", read_only=True)
    remaining_qty = serializers.DecimalField(
        max_digits=14, decimal_places=3, read_only=True
    )

    class Meta:
        model = PurchaseOrderLine
        fields = (
            "id",
            "order",
            "item",
            "item_sku",
            "item_title",
            "ordered_qty",
            "received_qty",
            "remaining_qty",
            "unit_price",
            "line_no",
        )
        read_only_fields = ("id", "received_qty")


class PurchaseOrderSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.legal_name", read_only=True)
    lines = PurchaseOrderLineSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = (
            "id",
            "vendor",
            "vendor_name",
            "purchase_request",
            "order_no",
            "ordered_on",
            "expected_on",
            "total_amount",
            "tax_amount",
            "currency",
            "status",
            "status_display",
            "note",
            "lines",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "order_no",
            "status",
            "created_at",
            "updated_at",
            "version",
        )


class GoodsReceiptSerializer(serializers.ModelSerializer):
    order_no = serializers.CharField(source="order.order_no", read_only=True)
    vendor_name = serializers.CharField(
        source="order.vendor.legal_name", read_only=True
    )

    class Meta:
        model = GoodsReceipt
        fields = (
            "id",
            "order",
            "order_no",
            "vendor_name",
            "stock_document",
            "receipt_no",
            "received_at",
            "quality_status",
            "status",
            "vendor_invoice_no",
            "vendor_invoice_amount",
            "three_way_matched",
            "note",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "receipt_no",
            "stock_document",
            "three_way_matched",
            "created_at",
            "updated_at",
            "version",
        )


class ReceiveGoodsLineSerializer(serializers.Serializer):
    order_line = serializers.UUIDField()
    quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal("0.001")
    )
    lot_no = serializers.CharField(required=False, allow_blank=True, default="")
    serial_no = serializers.CharField(required=False, allow_blank=True, default="")
    expiry_date = serializers.DateField(required=False, allow_null=True)
    unit_cost = serializers.IntegerField(required=False, allow_null=True)


class ReceiveGoodsSerializer(serializers.Serializer):
    """
    ثبت رسید کالا.

    مقدار دریافتی هر قلم نباید از باقیمانده سفارش بیشتر باشد. برای کالای
    سریال‌دار/بچ‌دار، فیلدهای مربوطه الزامی‌اند (بخش ۷.۹).
    """

    warehouse = serializers.UUIDField()
    received_at = serializers.DateTimeField(required=False)
    vendor_invoice_no = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    vendor_invoice_amount = serializers.IntegerField(required=False, default=0)
    lines = ReceiveGoodsLineSerializer(many=True)


class ThreeWayMatchSerializer(serializers.Serializer):
    """نتیجه تطبیق سه‌طرفه."""

    orderNo = serializers.CharField()
    receiptNo = serializers.CharField()
    orderAmount = serializers.IntegerField()
    receivedValue = serializers.IntegerField()
    invoiceAmount = serializers.IntegerField()
    difference = serializers.IntegerField()
    tolerance = serializers.IntegerField()
    matched = serializers.BooleanField()


class AssetSerializer(serializers.ModelSerializer):
    item_title = serializers.CharField(source="item.title", read_only=True)
    lifecycle_status_display = serializers.CharField(
        source="get_lifecycle_status_display", read_only=True
    )
    book_value = serializers.IntegerField(read_only=True)
    current_assignee = serializers.SerializerMethodField()

    class Meta:
        model = Asset
        fields = (
            "id",
            "item",
            "item_title",
            "asset_tag",
            "title",
            "serial_no",
            "acquired_on",
            "acquisition_cost",
            "useful_life_months",
            "accumulated_depreciation",
            "book_value",
            "warranty_until",
            "insurance_policy_no",
            "condition_status",
            "lifecycle_status",
            "lifecycle_status_display",
            "current_room",
            "current_assignee",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "lifecycle_status",
            "accumulated_depreciation",
            "created_at",
            "updated_at",
            "version",
        )

    def get_current_assignee(self, obj) -> dict | None:
        assignment = obj.assignments.filter(returned_at__isnull=True).first()
        if not assignment:
            return None
        return {
            "assignmentId": str(assignment.id),
            "assigneeType": assignment.assignee_type,
            "assigneeId": str(assignment.assignee_id),
            "assignedAt": assignment.assigned_at,
        }


class AssetAssignmentSerializer(serializers.ModelSerializer):
    asset_tag = serializers.CharField(source="asset.asset_tag", read_only=True)

    class Meta:
        model = AssetAssignment
        fields = (
            "id",
            "asset",
            "asset_tag",
            "assignee_type",
            "assignee_id",
            "location_room",
            "assigned_at",
            "returned_at",
            "condition_on_assign",
            "condition_on_return",
            "status",
            "note",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class MaintenanceOrderSerializer(serializers.ModelSerializer):
    asset_tag = serializers.CharField(source="asset.asset_tag", read_only=True)
    vendor_name = serializers.CharField(source="vendor.legal_name", read_only=True)

    class Meta:
        model = MaintenanceOrder
        fields = (
            "id",
            "asset",
            "asset_tag",
            "order_no",
            "maintenance_type",
            "description",
            "vendor",
            "vendor_name",
            "opened_at",
            "closed_at",
            "cost_amount",
            "status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "order_no", "created_at", "updated_at", "version")


class AssignAssetSerializer(serializers.Serializer):
    assignee_type = serializers.ChoiceField(
        choices=["EMPLOYEE", "ROOM", "ORG_UNIT", "CLASS_GROUP"]
    )
    assignee_id = serializers.UUIDField()
    location_room = serializers.UUIDField(required=False, allow_null=True)
    condition_on_assign = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    note = serializers.CharField(required=False, allow_blank=True, default="")


class ReturnAssetSerializer(serializers.Serializer):
    condition_on_return = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    note = serializers.CharField(required=False, allow_blank=True, default="")
