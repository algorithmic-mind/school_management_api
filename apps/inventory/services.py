"""
قواعد کسب‌وکار انبار و تدارکات.

مرجع: بخش ۷.۹ (قیدها)، ۹.۷ (خرید تا پرداخت تأمین‌کننده)، ۱۰.۷ و ۱۰.۸.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.exceptions import BusinessRuleViolation, InvalidStateTransition
from apps.inventory.enums import (
    INBOUND_DOCUMENT_TYPES,
    AssetLifecycleStatus,
    PurchaseOrderStatus,
    PurchaseRequestStatus,
    StockDocumentStatus,
    StockDocumentType,
)
from apps.inventory.models import (
    Asset,
    GoodsReceipt,
    Item,
    PurchaseOrder,
    PurchaseRequest,
    StockBalance,
    StockDocument,
    StockDocumentLine,
    StockMovement,
    Warehouse,
)

# ---------------------------------------------------------------------------
# ماشین حالت درخواست خرید — بخش ۱۰.۷
# ---------------------------------------------------------------------------
PURCHASE_REQUEST_TRANSITIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "submit": ((PurchaseRequestStatus.DRAFT,), PurchaseRequestStatus.SUBMITTED),
    "route": ((PurchaseRequestStatus.SUBMITTED,), PurchaseRequestStatus.BUDGET_CHECK),
    "reserve_budget": (
        (PurchaseRequestStatus.BUDGET_CHECK,),
        PurchaseRequestStatus.APPROVAL,
    ),
    "approve": ((PurchaseRequestStatus.APPROVAL,), PurchaseRequestStatus.APPROVED),
    "reject": (
        (PurchaseRequestStatus.BUDGET_CHECK, PurchaseRequestStatus.APPROVAL),
        PurchaseRequestStatus.REJECTED,
    ),
    "source": ((PurchaseRequestStatus.APPROVED,), PurchaseRequestStatus.SOURCING),
    "mark_ordered": (
        (PurchaseRequestStatus.SOURCING, PurchaseRequestStatus.APPROVED),
        PurchaseRequestStatus.ORDERED,
    ),
    "cancel": (
        (PurchaseRequestStatus.DRAFT, PurchaseRequestStatus.APPROVED),
        PurchaseRequestStatus.CANCELLED,
    ),
    "close": ((PurchaseRequestStatus.RECEIVED,), PurchaseRequestStatus.CLOSED),
}


def _next_no(model, tenant_id, prefix: str) -> str:
    count = model.objects.filter(tenant_id=tenant_id).count()
    return f"{prefix}-{timezone.now():%Y%m}-{count + 1:05d}"


def generate_document_no(tenant_id) -> str:
    return _next_no(StockDocument, tenant_id, "STK")


def generate_request_no(tenant_id) -> str:
    return _next_no(PurchaseRequest, tenant_id, "PR")


def generate_order_no(tenant_id) -> str:
    return _next_no(PurchaseOrder, tenant_id, "PO")


def generate_receipt_no(tenant_id) -> str:
    return _next_no(GoodsReceipt, tenant_id, "GR")


def generate_maintenance_no(tenant_id) -> str:
    from apps.inventory.models import MaintenanceOrder

    return _next_no(MaintenanceOrder, tenant_id, "MO")


def apply_request_transition(request_obj: PurchaseRequest, action_name: str):
    allowed_from, target = PURCHASE_REQUEST_TRANSITIONS[action_name]
    if request_obj.status not in allowed_from:
        raise InvalidStateTransition(
            entity="درخواست خرید", current=request_obj.status, action=action_name
        )
    request_obj.status = target
    request_obj.save(update_fields=["status", "updated_at", "version"])
    return request_obj


# ---------------------------------------------------------------------------
# حرکت موجودی
# ---------------------------------------------------------------------------
def _direction(document_type: str) -> int:
    return 1 if document_type in INBOUND_DOCUMENT_TYPES else -1


def validate_stock_line(line: StockDocumentLine, direction: int) -> None:
    """
    اعتبارسنجی یک قلم پیش از ثبت حرکت.

    بخش ۷.۹:
    - کالای سریال‌دار در هر حرکت خروجی باید سریال یکتا داشته باشد.
    - منفی‌شدن موجودی فقط برای اقلام/انبارهای مجاز.
    """
    item = line.item
    warehouse = line.stock_document.warehouse

    if item.serial_tracked and direction < 0 and not line.serial_no:
        raise BusinessRuleViolation(
            code="SERIAL_REQUIRED",
            message=f"کالای «{item.title}» سریال‌دار است؛ ثبت سریال در خروج الزامی است.",
            field_errors=[{"field": "serialNo", "reason": "required"}],
        )

    if item.lot_tracked and not line.lot_no:
        raise BusinessRuleViolation(
            code="LOT_REQUIRED",
            message=f"کالای «{item.title}» بچ‌دار است؛ ثبت شماره بچ الزامی است.",
            field_errors=[{"field": "lotNo", "reason": "required"}],
        )

    if direction < 0 and not item.allow_negative_stock:
        balance = StockBalance.objects.filter(
            warehouse=warehouse, item=item, lot_no=line.lot_no or ""
        ).first()
        available = balance.available_qty if balance else Decimal("0")
        if line.quantity > available:
            raise BusinessRuleViolation(
                code="INSUFFICIENT_STOCK",
                message=(
                    f"موجودی قابل‌دسترس «{item.title}» در انبار "
                    f"{warehouse.code} برابر {available} است و کمتر از "
                    f"{line.quantity} درخواستی است."
                ),
                field_errors=[{"field": "quantity", "reason": "insufficient_stock"}],
            )


@transaction.atomic
def confirm_stock_document(document: StockDocument, actor_user_id=None) -> StockDocument:
    """
    قطعی‌کردن سند انبار و ثبت حرکات موجودی.

    بخش ۷.۹: «موجودی فقط از STOCK_MOVEMENT قطعی تغییر می‌کند.»
    """
    if document.status == StockDocumentStatus.CONFIRMED:
        return document
    if document.status != StockDocumentStatus.DRAFT:
        raise InvalidStateTransition(
            entity="سند انبار", current=document.status, action="confirm"
        )

    lines = list(document.lines.select_related("item"))
    if not lines:
        raise BusinessRuleViolation(
            code="STOCK_DOCUMENT_EMPTY",
            message="سند انبار هیچ قلمی ندارد.",
        )

    direction = _direction(document.document_type)

    for line in lines:
        validate_stock_line(line, direction)

    for line in lines:
        signed = Decimal(str(line.quantity)) * direction
        StockMovement.objects.create(
            tenant_id=document.tenant_id,
            document_line=line,
            warehouse=document.warehouse,
            item=line.item,
            lot_no=line.lot_no,
            serial_no=line.serial_no,
            signed_quantity=signed,
            unit_cost=line.unit_cost,
            occurred_at=document.document_at,
        )
        _apply_to_balance(
            document.warehouse, line.item, line.lot_no, signed, line.unit_cost,
            line.expiry_date,
        )

    document.status = StockDocumentStatus.CONFIRMED
    document.confirmed_at = timezone.now()
    document.confirmed_by_id = actor_user_id
    document.save(update_fields=["status", "confirmed_at", "confirmed_by_id"])

    _check_reorder_point(document)
    return document


def _apply_to_balance(warehouse, item, lot_no, signed_quantity, unit_cost, expiry_date):
    """به‌روزرسانی موجودی خلاصه با میانگین موزون بهای تمام‌شده."""
    balance, _ = StockBalance.objects.select_for_update().get_or_create(
        warehouse=warehouse,
        item=item,
        lot_no=lot_no or "",
        defaults={"tenant_id": item.tenant_id, "expiry_date": expiry_date},
    )

    if signed_quantity > 0 and unit_cost:
        total_value = balance.on_hand_qty * balance.average_cost + signed_quantity * unit_cost
        new_qty = balance.on_hand_qty + signed_quantity
        balance.average_cost = int(total_value / new_qty) if new_qty else unit_cost

    balance.on_hand_qty += signed_quantity
    if expiry_date and not balance.expiry_date:
        balance.expiry_date = expiry_date
    balance.save()
    return balance


def _check_reorder_point(document: StockDocument) -> None:
    """انتشار رویداد `StockBelowReorderPoint` در صورت افت موجودی (بخش ۱۳.۱)."""
    from apps.workflow.services import publish_event

    for line in document.lines.select_related("item"):
        item = line.item
        if not item.reorder_point:
            continue
        total = (
            StockBalance.objects.filter(item=item).aggregate(
                total=Sum("on_hand_qty")
            )["total"]
            or Decimal("0")
        )
        if total < item.reorder_point:
            publish_event(
                aggregate_type="inventory.Item",
                aggregate_id=item.id,
                event_type="StockBelowReorderPoint",
                payload={
                    "itemId": str(item.id),
                    "sku": item.sku,
                    "onHand": float(total),
                    "reorderPoint": float(item.reorder_point),
                },
                tenant_id=item.tenant_id,
            )


@transaction.atomic
def reverse_stock_document(document: StockDocument, reason: str, actor_user_id=None):
    """
    برگشت سند قطعی انبار با سند معکوس.

    بخش ۷.۹: «سند قطعی انبار ویرایش نمی‌شود؛ برگشت یا سند اصلاحی حرکت معکوس
    ایجاد می‌کند.»
    """
    if document.status != StockDocumentStatus.CONFIRMED:
        raise InvalidStateTransition(
            entity="سند انبار", current=document.status, action="reverse"
        )

    reverse_type_map = {
        StockDocumentType.RECEIPT: StockDocumentType.RETURN_TO_VENDOR,
        StockDocumentType.ISSUE: StockDocumentType.RETURN_FROM_USE,
        StockDocumentType.TRANSFER_OUT: StockDocumentType.TRANSFER_IN,
        StockDocumentType.TRANSFER_IN: StockDocumentType.TRANSFER_OUT,
        StockDocumentType.ADJUSTMENT_IN: StockDocumentType.ADJUSTMENT_OUT,
        StockDocumentType.ADJUSTMENT_OUT: StockDocumentType.ADJUSTMENT_IN,
        StockDocumentType.RETURN_TO_VENDOR: StockDocumentType.RECEIPT,
        StockDocumentType.RETURN_FROM_USE: StockDocumentType.ISSUE,
    }
    reversal = StockDocument.objects.create(
        tenant_id=document.tenant_id,
        warehouse=document.warehouse,
        document_no=generate_document_no(document.tenant_id),
        document_type=reverse_type_map.get(
            document.document_type, StockDocumentType.ADJUSTMENT_OUT
        ),
        document_at=timezone.now(),
        source_type=document.source_type,
        source_id=document.source_id,
        description=f"برگشت سند {document.document_no}: {reason}",
        reversal_of=document,
    )
    for line in document.lines.all():
        StockDocumentLine.objects.create(
            tenant_id=document.tenant_id,
            stock_document=reversal,
            item=line.item,
            quantity=line.quantity,
            uom=line.uom,
            lot_no=line.lot_no,
            serial_no=line.serial_no,
            unit_cost=line.unit_cost,
            line_no=line.line_no,
        )

    confirm_stock_document(reversal, actor_user_id)

    document.status = StockDocumentStatus.REVERSED
    document.save(update_fields=["status"])
    return reversal


@transaction.atomic
def receive_goods(
    order: PurchaseOrder,
    warehouse: Warehouse,
    lines: list[dict],
    *,
    received_at=None,
    vendor_invoice_no: str = "",
    vendor_invoice_amount: int = 0,
    actor_user_id=None,
) -> GoodsReceipt:
    """
    ثبت رسید کالا: سند انبار + رسید + به‌روزرسانی مقدار دریافتی سفارش.

    هر ردیف: {"order_line": uuid, "quantity": Decimal, "lot_no": str,
              "serial_no": str, "unit_cost": int, "expiry_date": date|None}
    """
    from apps.inventory.models import PurchaseOrderLine

    if order.status not in {
        PurchaseOrderStatus.ISSUED,
        PurchaseOrderStatus.PARTIALLY_RECEIVED,
    }:
        raise InvalidStateTransition(
            entity="سفارش خرید", current=order.status, action="receive"
        )

    received_at = received_at or timezone.now()

    document = StockDocument.objects.create(
        tenant_id=order.tenant_id,
        warehouse=warehouse,
        document_no=generate_document_no(order.tenant_id),
        document_type=StockDocumentType.RECEIPT,
        document_at=received_at,
        source_type="inventory.PurchaseOrder",
        source_id=order.id,
        description=f"رسید کالای سفارش {order.order_no}",
    )

    for index, row in enumerate(lines, start=1):
        order_line = PurchaseOrderLine.objects.select_for_update().get(
            pk=row["order_line"], order=order
        )
        quantity = Decimal(str(row["quantity"]))

        if quantity > order_line.remaining_qty:
            raise BusinessRuleViolation(
                code="RECEIPT_EXCEEDS_ORDER",
                message=(
                    f"مقدار دریافتی ({quantity}) از باقیمانده سفارش برای "
                    f"«{order_line.item.title}» ({order_line.remaining_qty}) بیشتر است."
                ),
                field_errors=[{"field": f"lines[{index}].quantity", "reason": "exceeds_order"}],
            )

        StockDocumentLine.objects.create(
            tenant_id=order.tenant_id,
            stock_document=document,
            item=order_line.item,
            quantity=quantity,
            uom=order_line.item.base_uom,
            lot_no=row.get("lot_no", ""),
            serial_no=row.get("serial_no", ""),
            expiry_date=row.get("expiry_date"),
            unit_cost=row.get("unit_cost") or order_line.unit_price,
            line_no=index,
        )

        order_line.received_qty += quantity
        order_line.save(update_fields=["received_qty"])

    confirm_stock_document(document, actor_user_id)

    receipt = GoodsReceipt.objects.create(
        tenant_id=order.tenant_id,
        order=order,
        stock_document=document,
        receipt_no=generate_receipt_no(order.tenant_id),
        received_at=received_at,
        vendor_invoice_no=vendor_invoice_no,
        vendor_invoice_amount=vendor_invoice_amount,
    )

    fully_received = all(
        line.remaining_qty <= 0 for line in order.lines.all()
    )
    order.status = (
        PurchaseOrderStatus.RECEIVED
        if fully_received
        else PurchaseOrderStatus.PARTIALLY_RECEIVED
    )
    order.save(update_fields=["status"])

    if order.purchase_request_id:
        request_obj = order.purchase_request
        request_obj.status = (
            PurchaseRequestStatus.RECEIVED
            if fully_received
            else PurchaseRequestStatus.PARTIALLY_RECEIVED
        )
        request_obj.save(update_fields=["status"])

    from apps.workflow.services import publish_event

    publish_event(
        aggregate_type="inventory.GoodsReceipt",
        aggregate_id=receipt.id,
        event_type="GoodsReceived",
        payload={
            "receiptId": str(receipt.id),
            "orderId": str(order.id),
            "warehouseId": str(warehouse.id),
        },
        tenant_id=order.tenant_id,
    )
    return receipt


def perform_three_way_match(receipt: GoodsReceipt, tolerance_percent: float = 2.0) -> dict:
    """
    تطبیق سه‌طرفه سفارش، رسید و فاکتور تأمین‌کننده (بخش ۷.۹).

    تلورانس مبلغ قابل تنظیم است.
    """
    order = receipt.order
    document = receipt.stock_document

    received_value = 0
    if document:
        for line in document.lines.all():
            received_value += int(Decimal(str(line.quantity)) * line.unit_cost)

    invoice_amount = receipt.vendor_invoice_amount
    difference = abs(invoice_amount - received_value)
    tolerance = int(received_value * Decimal(str(tolerance_percent)) / 100)
    matched = invoice_amount > 0 and difference <= tolerance

    receipt.three_way_matched = matched
    receipt.save(update_fields=["three_way_matched"])

    return {
        "orderNo": order.order_no,
        "receiptNo": receipt.receipt_no,
        "orderAmount": order.total_amount,
        "receivedValue": received_value,
        "invoiceAmount": invoice_amount,
        "difference": difference,
        "tolerance": tolerance,
        "matched": matched,
    }


# ---------------------------------------------------------------------------
# اموال — ماشین حالت بخش ۱۰.۸
# ---------------------------------------------------------------------------
ASSET_TRANSITIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "accept": ((AssetLifecycleStatus.REGISTERED,), AssetLifecycleStatus.IN_STOCK),
    "assign": ((AssetLifecycleStatus.IN_STOCK,), AssetLifecycleStatus.ASSIGNED),
    "return_asset": ((AssetLifecycleStatus.ASSIGNED,), AssetLifecycleStatus.IN_STOCK),
    "send_for_repair": (
        (AssetLifecycleStatus.IN_STOCK, AssetLifecycleStatus.ASSIGNED),
        AssetLifecycleStatus.UNDER_MAINTENANCE,
    ),
    "repaired": (
        (AssetLifecycleStatus.UNDER_MAINTENANCE,),
        AssetLifecycleStatus.IN_STOCK,
    ),
    "mark_damaged": (
        (AssetLifecycleStatus.UNDER_MAINTENANCE,),
        AssetLifecycleStatus.DAMAGED,
    ),
    "report_lost": ((AssetLifecycleStatus.ASSIGNED,), AssetLifecycleStatus.LOST),
    "recover": ((AssetLifecycleStatus.LOST,), AssetLifecycleStatus.RECOVERED),
    "inspect": ((AssetLifecycleStatus.RECOVERED,), AssetLifecycleStatus.IN_STOCK),
    "retire": (
        (AssetLifecycleStatus.IN_STOCK, AssetLifecycleStatus.DAMAGED),
        AssetLifecycleStatus.RETIRED,
    ),
    "dispose": ((AssetLifecycleStatus.RETIRED,), AssetLifecycleStatus.DISPOSED),
}


def apply_asset_transition(asset: Asset, action_name: str) -> Asset:
    allowed_from, target = ASSET_TRANSITIONS[action_name]
    if asset.lifecycle_status not in allowed_from:
        raise InvalidStateTransition(
            entity="مال سرمایه‌ای", current=asset.lifecycle_status, action=action_name
        )
    asset.lifecycle_status = target
    asset.save(update_fields=["lifecycle_status", "updated_at", "version"])
    return asset


def item_kardex(item: Item, warehouse=None, date_from=None, date_to=None) -> dict:
    """کاردکس کالا: ریز حرکات با موجودی تجمعی (بخش ۱۲.۲ و ۱۳.۵ سند فرانت)."""
    movements = StockMovement.objects.filter(item=item).select_related(
        "warehouse", "document_line__stock_document"
    )
    if warehouse:
        movements = movements.filter(warehouse=warehouse)
    if date_from:
        movements = movements.filter(occurred_at__gte=date_from)
    if date_to:
        movements = movements.filter(occurred_at__lte=date_to)

    movements = movements.order_by("occurred_at")

    rows = []
    running = Decimal("0")
    for movement in movements:
        running += movement.signed_quantity
        document = movement.document_line.stock_document
        rows.append(
            {
                "occurredAt": movement.occurred_at,
                "documentNo": document.document_no,
                "documentType": document.document_type,
                "warehouse": movement.warehouse.code,
                "lotNo": movement.lot_no,
                "serialNo": movement.serial_no,
                "quantity": float(movement.signed_quantity),
                "unitCost": movement.unit_cost,
                "balance": float(running),
            }
        )

    return {
        "itemId": str(item.id),
        "sku": item.sku,
        "title": item.title,
        "closingBalance": float(running),
        "rows": rows,
    }
