"""Viewهای ماژول تدارکات، انبار و اموال."""

from __future__ import annotations

import django_filters as filters
from django.db import transaction
from django.db.models import F, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleViolation
from apps.core.serializers import (
    ErrorResponseSerializer,
    OperationResultSerializer,
    ReasonSerializer,
)
from apps.core.viewsets import BaseModelViewSet, BaseReadOnlyViewSet
from apps.inventory import services
from apps.inventory.enums import (
    AssetLifecycleStatus,
    MaintenanceStatus,
    PurchaseOrderStatus,
    PurchaseRequestStatus,
)
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
from apps.inventory.serializers import (
    AssetAssignmentSerializer,
    AssetSerializer,
    AssignAssetSerializer,
    GoodsReceiptSerializer,
    ItemCategorySerializer,
    ItemSerializer,
    KardexSerializer,
    MaintenanceOrderSerializer,
    PurchaseOrderLineSerializer,
    PurchaseOrderSerializer,
    PurchaseRequestLineSerializer,
    PurchaseRequestSerializer,
    ReceiveGoodsSerializer,
    ReturnAssetSerializer,
    StockBalanceSerializer,
    StockDocumentLineSerializer,
    StockDocumentSerializer,
    StockMovementSerializer,
    ThreeWayMatchSerializer,
    UnitOfMeasureSerializer,
    VendorSerializer,
    WarehouseSerializer,
)

ERRORS = {
    400: OpenApiResponse(ErrorResponseSerializer, description="داده ورودی معتبر نیست"),
    403: OpenApiResponse(ErrorResponseSerializer, description="بدون مجوز"),
    404: OpenApiResponse(ErrorResponseSerializer, description="یافت نشد"),
    409: OpenApiResponse(ErrorResponseSerializer, description="گذار وضعیت نامعتبر"),
    422: OpenApiResponse(ErrorResponseSerializer, description="نقض قاعده کسب‌وکار"),
}


@extend_schema_view(
    list=extend_schema(tags=["Inventory"], summary="فهرست تأمین‌کنندگان"),
    create=extend_schema(tags=["Inventory"], summary="ایجاد تأمین‌کننده"),
)
class VendorViewSet(BaseModelViewSet):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer
    filterset_fields = ("status",)
    search_fields = ("code", "legal_name", "tax_id")
    permission_resource = "vendor"


@extend_schema_view(list=extend_schema(tags=["Inventory"], summary="واحدهای سنجش"))
class UnitOfMeasureViewSet(BaseModelViewSet):
    queryset = UnitOfMeasure.objects.all()
    serializer_class = UnitOfMeasureSerializer
    search_fields = ("code", "title")
    permission_resource = "item"


@extend_schema_view(list=extend_schema(tags=["Inventory"], summary="دسته‌های کالا"))
class ItemCategoryViewSet(BaseModelViewSet):
    queryset = ItemCategory.objects.select_related("school", "parent")
    serializer_class = ItemCategorySerializer
    filterset_fields = ("school", "parent")
    search_fields = ("code", "title")
    permission_resource = "item"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "school"


class ItemFilter(filters.FilterSet):
    below_reorder = filters.BooleanFilter(
        method="filter_below_reorder", label="زیر نقطه سفارش"
    )

    class Meta:
        model = Item
        fields = (
            "category",
            "status",
            "lot_tracked",
            "serial_tracked",
            "is_capital_asset",
        )

    def filter_below_reorder(self, queryset, name, value):
        queryset = queryset.annotate(on_hand=Sum("balances__on_hand_qty"))
        if value:
            return queryset.filter(
                reorder_point__gt=0, on_hand__lt=F("reorder_point")
            )
        return queryset


@extend_schema_view(
    list=extend_schema(
        tags=["Inventory"],
        summary="فهرست کالاها",
        description="`totalOnHand` جمع موجودی همه انبارها را برمی‌گرداند.",
        parameters=[
            OpenApiParameter("below_reorder", bool, description="فقط اقلام زیر نقطه سفارش")
        ],
    ),
    create=extend_schema(tags=["Inventory"], summary="تعریف کالا"),
)
class ItemViewSet(BaseModelViewSet):
    queryset = Item.objects.select_related("category", "base_uom").prefetch_related(
        "balances"
    )
    serializer_class = ItemSerializer
    filterset_class = ItemFilter
    search_fields = ("sku", "title", "barcode")
    permission_resource = "item"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "category__school"

    @extend_schema(
        tags=["Inventory"],
        summary="کاردکس کالا",
        description=(
            "ریز حرکات ورود و خروج با موجودی تجمعی — برای صفحه «کاردکس کالا» "
            "(بخش ۱۳.۵ سند فرانت)."
        ),
        parameters=[
            OpenApiParameter("warehouse", str, description="محدود به یک انبار"),
            OpenApiParameter("date_from", str, description="از تاریخ"),
            OpenApiParameter("date_to", str, description="تا تاریخ"),
        ],
        responses={200: KardexSerializer, **ERRORS},
    )
    @action(detail=True, methods=["get"])
    def kardex(self, request, pk=None):
        item = self.get_object()
        warehouse_id = request.query_params.get("warehouse")
        warehouse = (
            get_object_or_404(Warehouse, pk=warehouse_id) if warehouse_id else None
        )
        payload = services.item_kardex(
            item,
            warehouse,
            request.query_params.get("date_from"),
            request.query_params.get("date_to"),
        )
        return Response(payload)


@extend_schema_view(list=extend_schema(tags=["Inventory"], summary="انبارها"))
class WarehouseViewSet(BaseModelViewSet):
    queryset = Warehouse.objects.select_related("campus")
    serializer_class = WarehouseSerializer
    filterset_fields = ("campus", "status")
    search_fields = ("code", "title")
    permission_resource = "stock"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "campus__school"
    campus_field = "campus"


class StockBalanceFilter(filters.FilterSet):
    below_reorder = filters.BooleanFilter(
        method="filter_below_reorder", label="زیر نقطه سفارش"
    )
    expiring_before = filters.DateFilter(
        field_name="expiry_date", lookup_expr="lte", label="منقضی پیش از"
    )

    class Meta:
        model = StockBalance
        fields = ("warehouse", "item", "lot_no")

    def filter_below_reorder(self, queryset, name, value):
        if value:
            return queryset.filter(
                item__reorder_point__gt=0, on_hand_qty__lt=F("item__reorder_point")
            )
        return queryset


@extend_schema_view(
    list=extend_schema(
        tags=["Inventory"],
        summary="موجودی انبارها",
        description=(
            "موجودی خلاصه به تفکیک انبار/کالا/بچ. این جدول از حرکات موجودی "
            "ساخته می‌شود و مستقیماً قابل ویرایش نیست (بخش ۷.۹)."
        ),
        parameters=[
            OpenApiParameter("below_reorder", bool, description="فقط زیر نقطه سفارش"),
            OpenApiParameter("expiring_before", str, description="تاریخ انقضای قبل از"),
        ],
    )
)
class StockBalanceViewSet(BaseReadOnlyViewSet):
    queryset = StockBalance.objects.select_related("item", "warehouse")
    serializer_class = StockBalanceSerializer
    filterset_class = StockBalanceFilter
    search_fields = ("item__sku", "item__title", "lot_no")
    permission_resource = "stock"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "item__category__school"
    campus_field = "warehouse__campus"


class StockDocumentFilter(filters.FilterSet):
    date_from = filters.DateTimeFilter(field_name="document_at", lookup_expr="gte")
    date_to = filters.DateTimeFilter(field_name="document_at", lookup_expr="lte")

    class Meta:
        model = StockDocument
        fields = ("warehouse", "document_type", "status", "source_type", "source_id")


@extend_schema_view(
    list=extend_schema(tags=["Inventory"], summary="اسناد انبار"),
    retrieve=extend_schema(tags=["Inventory"], summary="جزئیات سند انبار"),
    create=extend_schema(
        tags=["Inventory"],
        summary="ایجاد سند انبار (پیش‌نویس)",
        description="پس از افزودن اقلام، با `confirm` سند قطعی و موجودی به‌روز می‌شود.",
    ),
)
class StockDocumentViewSet(BaseModelViewSet):
    queryset = StockDocument.objects.select_related("warehouse").prefetch_related(
        "lines__item"
    )
    serializer_class = StockDocumentSerializer
    filterset_class = StockDocumentFilter
    search_fields = ("document_no", "description")
    permission_resource = "stock"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "warehouse__campus__school"
    campus_field = "warehouse__campus"
    permission_map = {
        "confirm": "stock.receive",
        "reverse": "stock.adjust",
    }

    def perform_create(self, serializer):
        from apps.core.context import get_current_context

        ctx = get_current_context()
        serializer.save(
            tenant_id=ctx.tenant_id if ctx else None,
            document_no=services.generate_document_no(ctx.tenant_id if ctx else None),
        )

    @extend_schema(
        tags=["Inventory"],
        summary="قطعی‌کردن سند انبار",
        description=(
            "حرکات موجودی ثبت و موجودی خلاصه به‌روز می‌شود. برای خروج، کفایت "
            "موجودی، سریال و بچ کنترل می‌گردد."
        ),
        request=None,
        responses={200: StockDocumentSerializer, **ERRORS},
        examples=[
            OpenApiExample(
                "خطای کمبود موجودی",
                value={
                    "code": "INSUFFICIENT_STOCK",
                    "message": "موجودی قابل‌دسترس «کاغذ A4» در انبار W01 برابر 12 است و کمتر از 50 درخواستی است.",
                    "correlationId": "6b2f9d4a",
                    "fieldErrors": [{"field": "quantity", "reason": "insufficient_stock"}],
                    "retryable": False,
                },
                response_only=True,
                status_codes=["422"],
            )
        ],
    )
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        document = self.get_object()
        services.confirm_stock_document(document, request.user.id)
        return Response(self.get_serializer(document).data)

    @extend_schema(
        tags=["Inventory"],
        summary="برگشت سند انبار",
        description=(
            "سند قطعی ویرایش نمی‌شود؛ سند معکوس ساخته و قطعی می‌شود "
            "(بخش ۷.۹)."
        ),
        request=ReasonSerializer,
        responses={201: StockDocumentSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        document = self.get_object()
        body = ReasonSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        reversal = services.reverse_stock_document(
            document, body.validated_data["reason"], request.user.id
        )
        return Response(StockDocumentSerializer(reversal).data, status=201)


@extend_schema_view(list=extend_schema(tags=["Inventory"], summary="اقلام سند انبار"))
class StockDocumentLineViewSet(BaseModelViewSet):
    queryset = StockDocumentLine.objects.select_related("stock_document", "item", "uom")
    serializer_class = StockDocumentLineSerializer
    filterset_fields = ("stock_document", "item")
    permission_resource = "stock"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "item__category__school"
    campus_field = "stock_document__warehouse__campus"


@extend_schema_view(
    list=extend_schema(
        tags=["Inventory"],
        summary="حرکات موجودی",
        description="تنها منبع تغییر موجودی؛ رکوردها تغییرناپذیرند (بخش ۵ و ۷.۹).",
    )
)
class StockMovementViewSet(BaseReadOnlyViewSet):
    queryset = StockMovement.objects.select_related("item", "warehouse")
    serializer_class = StockMovementSerializer
    filterset_fields = ("item", "warehouse", "lot_no", "serial_no")
    ordering_fields = ("occurred_at",)
    permission_resource = "stock"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "item__category__school"
    campus_field = "warehouse__campus"


@extend_schema_view(
    list=extend_schema(tags=["Inventory"], summary="درخواست‌های خرید"),
    create=extend_schema(tags=["Inventory"], summary="ثبت درخواست خرید"),
)
class PurchaseRequestViewSet(BaseModelViewSet):
    queryset = PurchaseRequest.objects.select_related("campus").prefetch_related(
        "lines__item"
    )
    serializer_class = PurchaseRequestSerializer
    filterset_fields = ("campus", "status", "requester_user_id")
    search_fields = ("request_no", "title")
    permission_resource = "purchase_request"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "campus__school"
    campus_field = "campus"
    permission_map = {
        "submit": "purchase_request.submit",
        "approve": "purchase_request.approve",
        "reject": "purchase_request.reject",
        "cancel": "purchase_request.create",
    }

    def perform_create(self, serializer):
        from apps.core.context import get_current_context

        ctx = get_current_context()
        serializer.save(
            tenant_id=ctx.tenant_id if ctx else None,
            request_no=services.generate_request_no(ctx.tenant_id if ctx else None),
            requester_user_id=self.request.user.id,
        )

    @extend_schema(
        tags=["Inventory"],
        summary="ارسال درخواست خرید",
        description="درخواست پس از ارسال به مرحله کنترل بودجه می‌رود (بخش ۱۰.۷).",
        request=None,
        responses={200: PurchaseRequestSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        request_obj = self.get_object()
        services.apply_request_transition(request_obj, "submit")
        services.apply_request_transition(request_obj, "route")
        return Response(self.get_serializer(request_obj).data)

    @extend_schema(
        tags=["Inventory"],
        summary="تأیید درخواست خرید",
        description=(
            "**تفکیک وظایف:** درخواست‌دهنده نمی‌تواند تأییدکننده باشد "
            "(بخش ۱۶.۲)."
        ),
        request=ReasonSerializer,
        responses={200: PurchaseRequestSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        request_obj = self.get_object()
        if request_obj.requester_user_id == request.user.id:
            raise BusinessRuleViolation(
                code="SEGREGATION_OF_DUTIES",
                message="درخواست‌دهنده نمی‌تواند تأییدکننده همان درخواست خرید باشد.",
                status_code=403,
            )
        if request_obj.status == PurchaseRequestStatus.BUDGET_CHECK:
            services.apply_request_transition(request_obj, "reserve_budget")
        services.apply_request_transition(request_obj, "approve")
        return Response(self.get_serializer(request_obj).data)

    @extend_schema(
        tags=["Inventory"],
        summary="رد درخواست خرید",
        request=ReasonSerializer,
        responses={200: PurchaseRequestSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        request_obj = self.get_object()
        body = ReasonSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.apply_request_transition(request_obj, "reject")
        request_obj.decision_note = body.validated_data["reason"]
        request_obj.save(update_fields=["decision_note"])
        return Response(self.get_serializer(request_obj).data)


@extend_schema_view(list=extend_schema(tags=["Inventory"], summary="اقلام درخواست خرید"))
class PurchaseRequestLineViewSet(BaseModelViewSet):
    queryset = PurchaseRequestLine.objects.select_related("request", "item")
    serializer_class = PurchaseRequestLineSerializer
    filterset_fields = ("request", "item")
    permission_resource = "purchase_request"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "item__category__school"
    campus_field = "request__campus"


@extend_schema_view(
    list=extend_schema(tags=["Inventory"], summary="سفارش‌های خرید"),
    create=extend_schema(tags=["Inventory"], summary="ایجاد سفارش خرید"),
)
class PurchaseOrderViewSet(BaseModelViewSet):
    queryset = PurchaseOrder.objects.select_related("vendor", "purchase_request").prefetch_related(
        "lines__item"
    )
    serializer_class = PurchaseOrderSerializer
    filterset_fields = ("vendor", "status", "purchase_request")
    search_fields = ("order_no",)
    permission_resource = "purchase_order"
    permission_map = {
        "issue": "purchase_order.issue",
        "receive": "stock.receive",
        "close": "purchase_order.close",
        "three_way_match": "purchase_order.read",
    }

    def perform_create(self, serializer):
        from apps.core.context import get_current_context

        ctx = get_current_context()
        serializer.save(
            tenant_id=ctx.tenant_id if ctx else None,
            order_no=services.generate_order_no(ctx.tenant_id if ctx else None),
        )

    @extend_schema(
        tags=["Inventory"],
        summary="صدور سفارش خرید",
        request=None,
        responses={200: PurchaseOrderSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        order = self.get_object()
        if order.status != PurchaseOrderStatus.DRAFT:
            raise BusinessRuleViolation(
                code="ORDER_ALREADY_ISSUED",
                message="فقط سفارش پیش‌نویس قابل صدور است.",
                status_code=409,
            )
        order.status = PurchaseOrderStatus.ISSUED
        order.save(update_fields=["status"])

        if order.purchase_request_id:
            services.apply_request_transition(order.purchase_request, "mark_ordered")

        return Response(self.get_serializer(order).data)

    @extend_schema(
        tags=["Inventory"],
        summary="ثبت رسید کالا",
        description=(
            "سند انبار از نوع «رسید» ساخته و قطعی می‌شود، مقدار دریافتی سفارش "
            "به‌روز می‌گردد و رویداد `GoodsReceived` منتشر می‌شود.\n\n"
            "مقدار هر قلم نمی‌تواند از باقیمانده سفارش بیشتر باشد."
        ),
        request=ReceiveGoodsSerializer,
        responses={201: GoodsReceiptSerializer, **ERRORS},
        examples=[
            OpenApiExample(
                "رسید جزئی",
                value={
                    "warehouse": "7a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
                    "vendor_invoice_no": "F-140501-882",
                    "vendor_invoice_amount": 48000000,
                    "lines": [
                        {
                            "order_line": "8b2c3d4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
                            "quantity": 100,
                            "unit_cost": 480000,
                        }
                    ],
                },
                request_only=True,
            )
        ],
    )
    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        order = self.get_object()
        body = ReceiveGoodsSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data

        warehouse = get_object_or_404(Warehouse, pk=data["warehouse"])
        receipt = services.receive_goods(
            order,
            warehouse,
            data["lines"],
            received_at=data.get("received_at"),
            vendor_invoice_no=data.get("vendor_invoice_no", ""),
            vendor_invoice_amount=data.get("vendor_invoice_amount", 0),
            actor_user_id=request.user.id,
        )
        return Response(GoodsReceiptSerializer(receipt).data, status=201)

    @extend_schema(
        tags=["Inventory"],
        summary="بستن سفارش خرید",
        request=None,
        responses={200: PurchaseOrderSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        order = self.get_object()
        order.status = PurchaseOrderStatus.CLOSED
        order.save(update_fields=["status"])
        if order.purchase_request_id:
            request_obj = order.purchase_request
            if request_obj.status == PurchaseRequestStatus.RECEIVED:
                services.apply_request_transition(request_obj, "close")
        return Response(self.get_serializer(order).data)


@extend_schema_view(list=extend_schema(tags=["Inventory"], summary="اقلام سفارش خرید"))
class PurchaseOrderLineViewSet(BaseModelViewSet):
    queryset = PurchaseOrderLine.objects.select_related("order", "item")
    serializer_class = PurchaseOrderLineSerializer
    filterset_fields = ("order", "item")
    permission_resource = "purchase_order"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "item__category__school"


@extend_schema_view(
    list=extend_schema(tags=["Inventory"], summary="رسیدهای کالا"),
)
class GoodsReceiptViewSet(BaseModelViewSet):
    queryset = GoodsReceipt.objects.select_related("order__vendor", "stock_document")
    serializer_class = GoodsReceiptSerializer
    filterset_fields = ("order", "quality_status", "status", "three_way_matched")
    search_fields = ("receipt_no", "vendor_invoice_no")
    permission_resource = "stock"
    permission_map = {"three_way_match": "purchase_order.read"}
    http_method_names = ["get", "post", "patch", "head", "options"]

    @extend_schema(
        tags=["Inventory"],
        summary="تطبیق سه‌طرفه",
        description=(
            "مقایسه مبلغ سفارش، ارزش کالای دریافتی و فاکتور تأمین‌کننده با "
            "تلورانس قابل تنظیم. پیش از پرداخت به تأمین‌کننده انجام می‌شود "
            "(بخش ۷.۹)."
        ),
        parameters=[
            OpenApiParameter(
                "tolerance_percent", float, description="درصد تلورانس (پیش‌فرض ۲)"
            )
        ],
        request=None,
        responses={200: ThreeWayMatchSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="three-way-match")
    def three_way_match(self, request, pk=None):
        receipt = self.get_object()
        tolerance = float(request.query_params.get("tolerance_percent", 2.0))
        return Response(services.perform_three_way_match(receipt, tolerance))


@extend_schema_view(
    list=extend_schema(tags=["Inventory"], summary="فهرست اموال"),
    create=extend_schema(tags=["Inventory"], summary="ثبت مال سرمایه‌ای"),
)
class AssetViewSet(BaseModelViewSet):
    queryset = Asset.objects.select_related("item", "current_room").prefetch_related(
        "assignments"
    )
    serializer_class = AssetSerializer
    filterset_fields = ("item", "lifecycle_status", "condition_status", "current_room")
    search_fields = ("asset_tag", "title", "serial_no")
    permission_resource = "asset"
    permission_map = {
        "accept": "asset.create",
        "assign": "asset.assign",
        "return_asset": "asset.assign",
        "retire": "asset.retire",
    }

    @extend_schema(
        tags=["Inventory"],
        summary="پذیرش مال و ورود به انبار",
        request=None,
        responses={200: AssetSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        asset = self.get_object()
        services.apply_asset_transition(asset, "accept")
        return Response(self.get_serializer(asset).data)

    @extend_schema(
        tags=["Inventory"],
        summary="تحویل مال",
        description=(
            "مال به کارمند، اتاق، واحد سازمانی یا کلاس تحویل می‌شود و رویداد "
            "`AssetAssigned` منتشر می‌گردد (بخش ۱۳.۱)."
        ),
        request=AssignAssetSerializer,
        responses={201: AssetAssignmentSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def assign(self, request, pk=None):
        from apps.workflow.services import publish_event

        asset = self.get_object()
        body = AssignAssetSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data

        services.apply_asset_transition(asset, "assign")

        assignment = AssetAssignment.objects.create(
            tenant_id=asset.tenant_id,
            asset=asset,
            assignee_type=data["assignee_type"],
            assignee_id=data["assignee_id"],
            location_room_id=data.get("location_room"),
            assigned_at=timezone.now(),
            condition_on_assign=data.get("condition_on_assign", ""),
            note=data.get("note", ""),
        )
        if data.get("location_room"):
            asset.current_room_id = data["location_room"]
            asset.save(update_fields=["current_room"])

        publish_event(
            aggregate_type="inventory.Asset",
            aggregate_id=asset.id,
            event_type="AssetAssigned",
            payload={
                "assetId": str(asset.id),
                "assetTag": asset.asset_tag,
                "assigneeType": data["assignee_type"],
                "assigneeId": str(data["assignee_id"]),
            },
            tenant_id=asset.tenant_id,
        )
        return Response(AssetAssignmentSerializer(assignment).data, status=201)

    @extend_schema(
        tags=["Inventory"],
        summary="بازگشت مال به انبار",
        request=ReturnAssetSerializer,
        responses={200: AssetSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="return")
    @transaction.atomic
    def return_asset(self, request, pk=None):
        asset = self.get_object()
        body = ReturnAssetSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        services.apply_asset_transition(asset, "return_asset")

        assignment = asset.assignments.filter(returned_at__isnull=True).first()
        if assignment:
            assignment.returned_at = timezone.now()
            assignment.condition_on_return = body.validated_data.get(
                "condition_on_return", ""
            )
            assignment.status = "RETURNED"
            assignment.save()

        return Response(self.get_serializer(asset).data)

    @extend_schema(
        tags=["Inventory"],
        summary="بازنشستگی مال",
        request=ReasonSerializer,
        responses={200: AssetSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def retire(self, request, pk=None):
        asset = self.get_object()
        body = ReasonSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.apply_asset_transition(asset, "retire")
        return Response(self.get_serializer(asset).data)


@extend_schema_view(list=extend_schema(tags=["Inventory"], summary="تحویل‌های اموال"))
class AssetAssignmentViewSet(BaseModelViewSet):
    queryset = AssetAssignment.objects.select_related("asset", "location_room")
    serializer_class = AssetAssignmentSerializer
    filterset_fields = ("asset", "assignee_type", "assignee_id", "status")
    permission_resource = "asset"


@extend_schema_view(
    list=extend_schema(tags=["Inventory"], summary="دستورهای تعمیر"),
    create=extend_schema(tags=["Inventory"], summary="ثبت دستور تعمیر"),
)
class MaintenanceOrderViewSet(BaseModelViewSet):
    queryset = MaintenanceOrder.objects.select_related("asset", "vendor")
    serializer_class = MaintenanceOrderSerializer
    filterset_fields = ("asset", "maintenance_type", "status", "vendor")
    permission_resource = "asset"
    permission_map = {"complete": "asset.create"}

    def perform_create(self, serializer):
        from apps.core.context import get_current_context

        ctx = get_current_context()
        instance = serializer.save(
            tenant_id=ctx.tenant_id if ctx else None,
            order_no=services.generate_maintenance_no(ctx.tenant_id if ctx else None),
        )
        asset = instance.asset
        if asset.lifecycle_status in {
            AssetLifecycleStatus.IN_STOCK,
            AssetLifecycleStatus.ASSIGNED,
        }:
            services.apply_asset_transition(asset, "send_for_repair")

    @extend_schema(
        tags=["Inventory"],
        summary="تکمیل دستور تعمیر",
        description="مال از وضعیت «در تعمیر» به «موجود در انبار» بازمی‌گردد.",
        request=None,
        responses={200: MaintenanceOrderSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def complete(self, request, pk=None):
        order = self.get_object()
        order.status = MaintenanceStatus.COMPLETED
        order.closed_at = timezone.now()
        order.save(update_fields=["status", "closed_at"])

        asset = order.asset
        if asset.lifecycle_status == AssetLifecycleStatus.UNDER_MAINTENANCE:
            services.apply_asset_transition(asset, "repaired")

        return Response(self.get_serializer(order).data)
