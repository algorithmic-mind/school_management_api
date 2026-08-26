"""Viewهای ماژول مالی و حسابداری."""

from __future__ import annotations

from datetime import timedelta

import django_filters as filters
from django.db import transaction
from django.db.models import Count, F, Q, Sum
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

from apps.core.exceptions import BusinessRuleViolation, InvalidStateTransition
from apps.core.serializers import (
    ErrorResponseSerializer,
    OperationResultSerializer,
    ReasonSerializer,
)
from apps.core.viewsets import BaseModelViewSet, BaseReadOnlyViewSet
from apps.finance import services
from apps.finance.enums import (
    ApprovalState,
    InvoiceStatus,
    JournalStatus,
    PaymentStatus,
    RefundStatus,
)
from apps.finance.models import (
    Account,
    BankAccount,
    BankReconciliation,
    CostCenter,
    DiscountAward,
    FeePlan,
    FeePlanItem,
    FiscalYear,
    Invoice,
    InvoiceLine,
    JournalEntry,
    JournalLine,
    Payment,
    PaymentAllocation,
    Refund,
    StudentFinancialAgreement,
)
from apps.finance.serializers import (
    AccountLedgerSerializer,
    AccountSerializer,
    AllocatePaymentSerializer,
    BankAccountSerializer,
    BankReconciliationSerializer,
    CostCenterSerializer,
    CreateJournalEntrySerializer,
    DiscountAwardSerializer,
    FamilyBalanceSerializer,
    FeePlanItemSerializer,
    FeePlanSerializer,
    FiscalYearSerializer,
    GenerateInstallmentsSerializer,
    InvoiceLineSerializer,
    InvoiceSerializer,
    JournalEntrySerializer,
    JournalLineSerializer,
    PaymentAllocationSerializer,
    PaymentSerializer,
    ReceivablesAgingSerializer,
    RefundSerializer,
    ReverseJournalSerializer,
    StudentFinancialAgreementSerializer,
)

ERRORS = {
    400: OpenApiResponse(ErrorResponseSerializer, description="داده ورودی معتبر نیست"),
    403: OpenApiResponse(ErrorResponseSerializer, description="بدون مجوز یا تفکیک وظایف"),
    404: OpenApiResponse(ErrorResponseSerializer, description="یافت نشد"),
    409: OpenApiResponse(ErrorResponseSerializer, description="دوره بسته یا تعارض وضعیت"),
    422: OpenApiResponse(ErrorResponseSerializer, description="نقض قاعده کسب‌وکار"),
}


@extend_schema_view(
    list=extend_schema(tags=["Finance"], summary="سال‌های مالی"),
    create=extend_schema(tags=["Finance"], summary="ایجاد سال مالی"),
)
class FiscalYearViewSet(BaseModelViewSet):
    queryset = FiscalYear.objects.select_related("school")
    serializer_class = FiscalYearSerializer
    filterset_fields = ("school", "status")
    permission_resource = "journal"
    permission_map = {"close": "journal.close_period"}

    @extend_schema(
        tags=["Finance"],
        summary="بستن دوره مالی",
        description=(
            "پیش از بستن، وجود اسناد پیش‌نویس بررسی می‌شود. پس از بستن، ثبت یا "
            "تغییر سند در آن دوره ممنوع است و اصلاح فقط با سند برگشتی در دوره "
            "باز انجام می‌شود (بخش ۷.۸)."
        ),
        request=None,
        responses={200: FiscalYearSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        fiscal_year = self.get_object()
        services.close_fiscal_year(fiscal_year, request.user.id)
        return Response(self.get_serializer(fiscal_year).data)


@extend_schema_view(
    list=extend_schema(
        tags=["Finance"],
        summary="کدینگ حساب‌ها",
        description="حساب‌های گروه (`allowsPosting = false`) قابل ثبت سند مستقیم نیستند.",
    ),
    create=extend_schema(tags=["Finance"], summary="ایجاد حساب"),
)
class AccountViewSet(BaseModelViewSet):
    queryset = Account.objects.select_related("school", "parent")
    serializer_class = AccountSerializer
    filterset_fields = ("school", "parent", "account_type", "allows_posting", "is_active")
    search_fields = ("code", "title")
    ordering_fields = ("code",)
    permission_resource = "journal"

    @extend_schema(
        tags=["Finance"],
        summary="گردش حساب",
        description=(
            "ریز گردش یک حساب در بازه مشخص با مانده تجمعی — برای صفحه «گردش "
            "حساب» (بخش ۱۲.۲)."
        ),
        parameters=[
            OpenApiParameter("date_from", str, description="از تاریخ (YYYY-MM-DD)"),
            OpenApiParameter("date_to", str, description="تا تاریخ (YYYY-MM-DD)"),
        ],
        responses={200: AccountLedgerSerializer, **ERRORS},
    )
    @action(detail=True, methods=["get"])
    def ledger(self, request, pk=None):
        account = self.get_object()
        payload = services.account_ledger(
            account,
            request.query_params.get("date_from"),
            request.query_params.get("date_to"),
        )
        return Response(payload)


@extend_schema_view(list=extend_schema(tags=["Finance"], summary="مراکز هزینه"))
class CostCenterViewSet(BaseModelViewSet):
    queryset = CostCenter.objects.select_related("school")
    serializer_class = CostCenterSerializer
    filterset_fields = ("school", "is_active")
    search_fields = ("code", "title")
    permission_resource = "journal"


@extend_schema_view(
    list=extend_schema(tags=["Finance"], summary="الگوهای شهریه"),
    create=extend_schema(tags=["Finance"], summary="ایجاد الگوی شهریه"),
)
class FeePlanViewSet(BaseModelViewSet):
    queryset = FeePlan.objects.select_related("academic_year", "grade_level").prefetch_related(
        "items"
    )
    serializer_class = FeePlanSerializer
    filterset_fields = ("academic_year", "grade_level", "status")
    permission_resource = "fee_plan"


@extend_schema_view(list=extend_schema(tags=["Finance"], summary="اقلام الگوی شهریه"))
class FeePlanItemViewSet(BaseModelViewSet):
    queryset = FeePlanItem.objects.select_related("fee_plan", "revenue_account")
    serializer_class = FeePlanItemSerializer
    filterset_fields = ("fee_plan", "fee_type", "is_mandatory")
    permission_resource = "fee_plan"


@extend_schema_view(
    list=extend_schema(tags=["Finance"], summary="قراردادهای مالی دانش‌آموزان"),
    retrieve=extend_schema(
        tags=["Finance"],
        summary="جزئیات قرارداد مالی",
        description="شامل مبلغ توافق‌شده، تخفیف‌ها، جمع صورتحساب، پرداخت و مانده.",
    ),
    create=extend_schema(tags=["Finance"], summary="ایجاد قرارداد مالی"),
)
class StudentFinancialAgreementViewSet(BaseModelViewSet):
    queryset = StudentFinancialAgreement.objects.select_related(
        "enrollment__student__person", "fee_plan", "responsible_guardian__person"
    ).prefetch_related("discounts", "invoices")
    serializer_class = StudentFinancialAgreementSerializer
    filterset_fields = ("enrollment", "fee_plan", "responsible_guardian", "status")
    permission_resource = "invoice"
    permission_map = {
        "generate_installments": "invoice.create",
        "recalculate": "invoice.create",
    }

    def perform_create(self, serializer):
        super().perform_create(serializer)
        agreement = serializer.instance
        agreement.agreed_amount = services.calculate_agreed_amount(agreement)
        agreement.save(update_fields=["agreed_amount"])

    @extend_schema(
        tags=["Finance"],
        summary="محاسبه مجدد مبلغ توافق‌شده",
        description="پس از تأیید یا تغییر تخفیف‌ها فراخوانی می‌شود.",
        request=None,
        responses={200: StudentFinancialAgreementSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def recalculate(self, request, pk=None):
        agreement = self.get_object()
        agreement.agreed_amount = services.calculate_agreed_amount(agreement)
        agreement.save(update_fields=["agreed_amount"])
        return Response(self.get_serializer(agreement).data)

    @extend_schema(
        tags=["Finance"],
        summary="تولید صورتحساب اقساط",
        description=(
            "بر اساس `installmentCount` قرارداد، صورتحساب‌های قسطی در وضعیت "
            "پیش‌نویس ساخته می‌شوند. باقیمانده تقسیم به قسط آخر اضافه می‌شود "
            "تا جمع اقساط دقیقاً برابر مبلغ توافق‌شده بماند."
        ),
        request=GenerateInstallmentsSerializer,
        responses={201: InvoiceSerializer(many=True), **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="generate-installments")
    def generate_installments(self, request, pk=None):
        agreement = self.get_object()
        body = GenerateInstallmentsSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        invoices = services.generate_installments(
            agreement,
            body.validated_data["first_due_date"],
            body.validated_data["interval_days"],
        )
        return Response(InvoiceSerializer(invoices, many=True).data, status=201)


@extend_schema_view(
    list=extend_schema(tags=["Finance"], summary="تخفیف‌ها"),
    create=extend_schema(tags=["Finance"], summary="ثبت تخفیف"),
)
class DiscountAwardViewSet(BaseModelViewSet):
    queryset = DiscountAward.objects.select_related("agreement__enrollment__student__person")
    serializer_class = DiscountAwardSerializer
    filterset_fields = ("agreement", "discount_type", "approval_status")
    permission_resource = "invoice"
    permission_map = {"approve": "invoice.issue"}

    @extend_schema(
        tags=["Finance"],
        summary="تأیید تخفیف",
        description="پس از تأیید، مبلغ توافق‌شده قرارداد مجدداً محاسبه می‌شود.",
        request=None,
        responses={200: DiscountAwardSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def approve(self, request, pk=None):
        discount = self.get_object()
        if discount.approval_status != ApprovalState.PENDING:
            raise InvalidStateTransition(
                entity="تخفیف", current=discount.approval_status, action="approve"
            )
        discount.approval_status = ApprovalState.APPROVED
        discount.approved_by_id = request.user.id
        discount.approved_at = timezone.now()
        discount.save()

        agreement = discount.agreement
        agreement.agreed_amount = services.calculate_agreed_amount(agreement)
        agreement.save(update_fields=["agreed_amount"])
        return Response(self.get_serializer(discount).data)


class InvoiceFilter(filters.FilterSet):
    student = filters.UUIDFilter(
        field_name="agreement__enrollment__student_id", label="دانش‌آموز"
    )
    guardian = filters.UUIDFilter(
        field_name="agreement__responsible_guardian_id", label="مسئول مالی"
    )
    academic_year = filters.UUIDFilter(
        field_name="agreement__enrollment__academic_year_id", label="سال تحصیلی"
    )
    due_from = filters.DateFilter(field_name="due_date", lookup_expr="gte")
    due_to = filters.DateFilter(field_name="due_date", lookup_expr="lte")
    unpaid = filters.BooleanFilter(method="filter_unpaid", label="فقط دارای مانده")

    class Meta:
        model = Invoice
        fields = ("agreement", "status", "installment_no")

    def filter_unpaid(self, queryset, name, value):
        if value:
            return queryset.exclude(
                status__in=[InvoiceStatus.PAID, InvoiceStatus.CANCELLED]
            )
        return queryset.filter(status=InvoiceStatus.PAID)


@extend_schema_view(
    list=extend_schema(
        tags=["Finance"],
        summary="فهرست صورتحساب‌ها",
        description="برای داشبورد مطالبات و پرونده مالی دانش‌آموز (بخش ۱۲.۱ و ۱۲.۲ سند فرانت).",
        parameters=[
            OpenApiParameter("student", str, description="شناسه دانش‌آموز"),
            OpenApiParameter("unpaid", bool, description="فقط صورتحساب‌های دارای مانده"),
        ],
    ),
    retrieve=extend_schema(tags=["Finance"], summary="جزئیات صورتحساب با اقلام"),
    create=extend_schema(tags=["Finance"], summary="ایجاد صورتحساب پیش‌نویس"),
)
class InvoiceViewSet(BaseModelViewSet):
    queryset = Invoice.objects.select_related(
        "agreement__enrollment__student__person"
    ).prefetch_related("lines")
    serializer_class = InvoiceSerializer
    filterset_class = InvoiceFilter
    search_fields = ("invoice_no", "agreement__enrollment__student__student_no")
    ordering_fields = ("due_date", "issue_date", "total_amount")
    permission_resource = "invoice"
    permission_map = {
        "issue": "invoice.issue",
        "cancel": "invoice.cancel",
        "aging": "invoice.read",
    }

    def perform_create(self, serializer):
        from apps.core.context import get_current_context

        ctx = get_current_context()
        serializer.save(
            tenant_id=ctx.tenant_id if ctx else None,
            invoice_no=services.generate_invoice_no(ctx.tenant_id if ctx else None),
        )

    @extend_schema(
        tags=["Finance"],
        summary="صدور صورتحساب",
        description=(
            "صورتحساب از پیش‌نویس به «صادرشده» می‌رود و سند حسابداری تعهدی "
            "(بدهکار حساب دریافتنی / بستانکار درآمد) ثبت می‌شود. رویداد "
            "`InvoiceIssued` منتشر می‌گردد."
        ),
        request=None,
        responses={200: InvoiceSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        invoice = self.get_object()
        services.recalculate_invoice_total(invoice)
        services.issue_invoice(invoice)
        return Response(self.get_serializer(invoice).data)

    @extend_schema(
        tags=["Finance"],
        summary="لغو صورتحساب",
        description="فقط صورتحساب پیش‌نویس قابل لغو است؛ صورتحساب صادرشده با یادداشت بستانکار اصلاح می‌شود.",
        request=ReasonSerializer,
        responses={200: InvoiceSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        invoice = self.get_object()
        body = ReasonSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        if invoice.status != InvoiceStatus.DRAFT:
            raise InvalidStateTransition(
                entity="صورتحساب", current=invoice.status, action="cancel"
            )
        invoice.status = InvoiceStatus.CANCELLED
        invoice.cancel_reason = body.validated_data["reason"]
        invoice.save(update_fields=["status", "cancel_reason"])
        return Response(self.get_serializer(invoice).data)

    @extend_schema(
        tags=["Finance"],
        summary="گزارش سنی مطالبات",
        description="توزیع مانده مطالبات در بازه‌های سررسید (بخش ۱۴.۳).",
        responses={200: ReceivablesAgingSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def aging(self, request):
        today = timezone.localdate()
        queryset = self.filter_queryset(self.get_queryset()).exclude(
            status__in=[InvoiceStatus.PAID, InvoiceStatus.CANCELLED]
        )

        buckets = [
            ("CURRENT", None, 0),
            ("1_30", 1, 30),
            ("31_60", 31, 60),
            ("61_90", 61, 90),
            ("OVER_90", 91, None),
        ]

        rows = []
        for name, low, high in buckets:
            if name == "CURRENT":
                subset = queryset.filter(due_date__gte=today)
            else:
                subset = queryset.filter(due_date__lt=today)
                if low is not None:
                    subset = subset.filter(
                        due_date__lte=today - timedelta(days=low - 1)
                    )
                if high is not None:
                    subset = subset.filter(
                        due_date__gte=today - timedelta(days=high)
                    )

            aggregate = subset.aggregate(
                count=Count("id"), total=Sum("total_amount"), paid=Sum("paid_amount")
            )
            total = (aggregate["total"] or 0) - (aggregate["paid"] or 0)
            rows.append(
                {
                    "bucket": name,
                    "invoiceCount": aggregate["count"] or 0,
                    "totalAmount": total,
                }
            )
        return Response(rows)


@extend_schema_view(list=extend_schema(tags=["Finance"], summary="اقلام صورتحساب"))
class InvoiceLineViewSet(BaseModelViewSet):
    queryset = InvoiceLine.objects.select_related("invoice")
    serializer_class = InvoiceLineSerializer
    filterset_fields = ("invoice", "fee_type")
    permission_resource = "invoice"

    def perform_create(self, serializer):
        super().perform_create(serializer)
        services.recalculate_invoice_total(serializer.instance.invoice)


class PaymentFilter(filters.FilterSet):
    received_from = filters.DateTimeFilter(field_name="received_at", lookup_expr="gte")
    received_to = filters.DateTimeFilter(field_name="received_at", lookup_expr="lte")
    has_unallocated = filters.BooleanFilter(
        method="filter_unallocated", label="دارای مبلغ تخصیص‌نیافته"
    )

    class Meta:
        model = Payment
        fields = ("payer_person", "method", "status", "bank_account")

    def filter_unallocated(self, queryset, name, value):
        queryset = queryset.annotate(allocated=Sum("allocations__amount"))
        if value:
            return queryset.filter(
                Q(allocated__isnull=True) | Q(allocated__lt=F("amount"))
            )
        return queryset


@extend_schema_view(
    list=extend_schema(
        tags=["Finance"],
        summary="فهرست دریافت‌ها",
        description="برای صندوق و مغایرت‌گیری (بخش ۱۲.۳ سند فرانت).",
    ),
    retrieve=extend_schema(tags=["Finance"], summary="جزئیات دریافت با تخصیص‌ها"),
    create=extend_schema(
        tags=["Finance"],
        summary="ثبت دریافت",
        description=(
            "دریافت در وضعیت «در انتظار» ساخته می‌شود. برای قطعی‌کردن، "
            "`post` را صدا بزنید.\n\n"
            "**Idempotent:** هدر `Idempotency-Key` را برای پرداخت درگاه "
            "بفرستید تا Callback تکراری، دریافت دوم نسازد (بخش ۷.۸)."
        ),
        parameters=[
            OpenApiParameter(
                "Idempotency-Key",
                str,
                location=OpenApiParameter.HEADER,
                description="کلید یکتای عملیات",
            )
        ],
    ),
)
class PaymentViewSet(BaseModelViewSet):
    queryset = Payment.objects.select_related("payer_person", "bank_account").prefetch_related(
        "allocations__invoice"
    )
    serializer_class = PaymentSerializer
    filterset_class = PaymentFilter
    search_fields = ("payment_no", "gateway_reference")
    ordering_fields = ("received_at", "amount")
    throttle_scope = "payment"
    permission_resource = "payment"
    permission_map = {
        "post_payment": "payment.create",
        "allocate": "payment.allocate",
        "void": "payment.void",
    }

    def perform_create(self, serializer):
        from apps.core.context import get_current_context

        ctx = get_current_context()
        tenant_id = ctx.tenant_id if ctx else None
        idempotency_key = ctx.idempotency_key if ctx else ""

        if idempotency_key:
            existing = Payment.objects.filter(
                tenant_id=tenant_id, idempotency_key=idempotency_key
            ).first()
            if existing:
                serializer.instance = existing
                return

        extra = {}
        # اگر مدرسه در بدنه نیامده باشد، از Context کاری (هدر X-School-Id)
        # گرفته می‌شود تا سند حسابداری دریافت همیشه قابل ثبت باشد.
        if not serializer.validated_data.get("school") and ctx and ctx.school_id:
            extra["school_id"] = ctx.school_id

        serializer.save(
            tenant_id=tenant_id,
            payment_no=services.generate_payment_no(tenant_id),
            idempotency_key=idempotency_key,
            cashier_user_id=self.request.user.id,
            **extra,
        )

    @extend_schema(
        tags=["Finance"],
        summary="قطعی‌کردن دریافت",
        description=(
            "وضعیت را به «موفق» می‌برد و سند حسابداری دریافت را ثبت می‌کند. "
            "رویداد `PaymentPosted` منتشر می‌شود."
        ),
        request=None,
        responses={200: PaymentSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="post")
    def post_payment(self, request, pk=None):
        payment = self.get_object()
        services.post_payment(payment)
        return Response(self.get_serializer(payment).data)

    @extend_schema(
        tags=["Finance"],
        summary="تخصیص دریافت به صورتحساب‌ها",
        description=(
            "یک دریافت می‌تواند به چند صورتحساب تخصیص یابد. مجموع تخصیص از "
            "مبلغ تخصیص‌نیافته دریافت و از مانده هر صورتحساب فراتر نمی‌رود "
            "(بخش ۷.۸)."
        ),
        request=AllocatePaymentSerializer,
        responses={200: PaymentAllocationSerializer(many=True), **ERRORS},
        examples=[
            OpenApiExample(
                "تخصیص به دو قسط",
                value={
                    "allocations": [
                        {"invoice": "aaaaaaaa-1111-2222-3333-444444444444", "amount": 5000000},
                        {"invoice": "bbbbbbbb-1111-2222-3333-444444444444", "amount": 3000000},
                    ]
                },
                request_only=True,
            ),
            OpenApiExample(
                "خطای تجاوز از مانده",
                value={
                    "code": "ALLOCATION_EXCEEDS_INVOICE_BALANCE",
                    "message": "مبلغ تخصیص (5,000,000) از مانده صورتحساب INV-202608-000012 (3,000,000) بیشتر است.",
                    "correlationId": "1d4e7a2b",
                    "fieldErrors": [{"field": "invoice", "reason": "exceeds_balance"}],
                    "retryable": False,
                },
                response_only=True,
                status_codes=["422"],
            ),
        ],
    )
    @action(detail=True, methods=["post"])
    def allocate(self, request, pk=None):
        payment = self.get_object()
        body = AllocatePaymentSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        allocations = services.allocate_payment(
            payment, body.validated_data["allocations"]
        )
        return Response(PaymentAllocationSerializer(allocations, many=True).data)

    @extend_schema(
        tags=["Finance"],
        summary="ابطال دریافت",
        description=(
            "تخصیص‌ها برداشته می‌شوند، وضعیت صورتحساب‌ها به‌روز می‌شود و سند "
            "برگشتی ثبت می‌گردد. ابطال با استرداد یکی نیست (بخش ۷.۸)."
        ),
        request=ReasonSerializer,
        responses={200: PaymentSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        payment = self.get_object()
        body = ReasonSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.void_payment(payment, body.validated_data["reason"])
        return Response(self.get_serializer(payment).data)


@extend_schema_view(list=extend_schema(tags=["Finance"], summary="تخصیص‌های پرداخت"))
class PaymentAllocationViewSet(BaseReadOnlyViewSet):
    queryset = PaymentAllocation.objects.select_related("payment", "invoice")
    serializer_class = PaymentAllocationSerializer
    filterset_fields = ("payment", "invoice")
    permission_resource = "payment"


@extend_schema_view(
    list=extend_schema(tags=["Finance"], summary="استردادها"),
    create=extend_schema(tags=["Finance"], summary="درخواست استرداد"),
)
class RefundViewSet(BaseModelViewSet):
    queryset = Refund.objects.select_related("payment__payer_person")
    serializer_class = RefundSerializer
    filterset_fields = ("payment", "status", "approval_status")
    permission_resource = "refund"
    permission_map = {"approve": "refund.approve", "complete": "refund.approve"}

    def perform_create(self, serializer):
        from apps.core.context import get_current_context

        ctx = get_current_context()
        tenant_id = ctx.tenant_id if ctx else None
        serializer.save(
            tenant_id=tenant_id,
            refund_no=services.generate_refund_no(tenant_id),
            requested_by_id=self.request.user.id,
        )

    @extend_schema(
        tags=["Finance"],
        summary="تأیید استرداد",
        description=(
            "**تفکیک وظایف:** درخواست‌دهنده نمی‌تواند تأییدکننده باشد "
            "(بخش ۳.۲ و ۱۶.۲). در این حالت خطای `SEGREGATION_OF_DUTIES` با "
            "کد ۴۰۳ برمی‌گردد."
        ),
        request=None,
        responses={200: RefundSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        refund = self.get_object()
        services.approve_refund(refund, request.user.id)
        return Response(self.get_serializer(refund).data)

    @extend_schema(
        tags=["Finance"],
        summary="تکمیل استرداد",
        description="سند حسابداری معکوس ثبت و رویداد `RefundCompleted` منتشر می‌شود.",
        request=None,
        responses={200: RefundSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        refund = self.get_object()
        services.complete_refund(refund)
        return Response(self.get_serializer(refund).data)


class JournalEntryFilter(filters.FilterSet):
    date_from = filters.DateFilter(field_name="entry_date", lookup_expr="gte")
    date_to = filters.DateFilter(field_name="entry_date", lookup_expr="lte")

    class Meta:
        model = JournalEntry
        fields = ("fiscal_year", "status", "source_type", "source_id")


@extend_schema_view(
    list=extend_schema(tags=["Finance"], summary="فهرست اسناد حسابداری"),
    retrieve=extend_schema(tags=["Finance"], summary="جزئیات سند با خطوط"),
)
class JournalEntryViewSet(BaseModelViewSet):
    queryset = JournalEntry.objects.select_related("fiscal_year").prefetch_related(
        "lines__account", "lines__cost_center"
    )
    serializer_class = JournalEntrySerializer
    filterset_class = JournalEntryFilter
    search_fields = ("entry_no", "description")
    ordering_fields = ("entry_date", "entry_no")
    permission_resource = "journal"
    permission_map = {
        "create_entry": "journal.create",
        "post_entry": "journal.post",
        "reverse": "journal.reverse",
    }
    http_method_names = ["get", "post", "head", "options"]

    @extend_schema(
        tags=["Finance"],
        summary="ایجاد سند حسابداری دستی",
        description=(
            "خطوط سند باید متوازن باشند. هر خط دقیقاً یکی از «بدهکار» یا "
            "«بستانکار» را دارد. حساب گروه قابل ثبت نیست.\n\n"
            "با `postImmediately = true` سند بلافاصله قطعی می‌شود."
        ),
        request=CreateJournalEntrySerializer,
        responses={201: JournalEntrySerializer, **ERRORS},
        examples=[
            OpenApiExample(
                "سند دستی متوازن",
                value={
                    "fiscal_year": "cccccccc-1111-2222-3333-444444444444",
                    "entry_date": "2026-08-25",
                    "description": "بابت هزینه نوشت‌افزار اداری",
                    "lines": [
                        {
                            "account": "dddddddd-1111-2222-3333-444444444444",
                            "debit": 12000000,
                            "credit": 0,
                            "description": "هزینه اداری",
                        },
                        {
                            "account": "eeeeeeee-1111-2222-3333-444444444444",
                            "debit": 0,
                            "credit": 12000000,
                            "description": "پرداخت از صندوق",
                        },
                    ],
                    "post_immediately": True,
                },
                request_only=True,
            ),
            OpenApiExample(
                "خطای عدم توازن",
                value={
                    "code": "JOURNAL_NOT_BALANCED",
                    "message": "سند متوازن نیست: جمع بدهکار 12,000,000 و جمع بستانکار 10,000,000 است.",
                    "correlationId": "5e8b3c1d",
                    "fieldErrors": [{"field": "lines", "reason": "not_balanced"}],
                    "retryable": False,
                },
                response_only=True,
                status_codes=["422"],
            ),
        ],
    )
    @action(detail=False, methods=["post"], url_path="create-entry")
    def create_entry(self, request):
        from apps.core.context import get_current_context

        body = CreateJournalEntrySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        ctx = get_current_context()

        fiscal_year = get_object_or_404(FiscalYear, pk=data["fiscal_year"])
        entry = services.create_journal_entry(
            fiscal_year=fiscal_year,
            entry_date=data["entry_date"],
            description=data["description"],
            lines=data["lines"],
            tenant_id=ctx.tenant_id if ctx else None,
        )
        if data.get("post_immediately"):
            services.post_journal_entry(entry, request.user.id)

        entry.refresh_from_db()
        return Response(JournalEntrySerializer(entry).data, status=201)

    @extend_schema(
        tags=["Finance"],
        summary="قطعی‌کردن سند",
        description=(
            "پس از قطعی‌شدن، سند غیرقابل ویرایش و حذف است؛ اصلاح فقط با سند "
            "برگشتی انجام می‌شود (بخش ۱۰.۶)."
        ),
        request=None,
        responses={200: JournalEntrySerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="post")
    def post_entry(self, request, pk=None):
        entry = self.get_object()
        services.post_journal_entry(entry, request.user.id)
        return Response(self.get_serializer(entry).data)

    @extend_schema(
        tags=["Finance"],
        summary="برگشت سند",
        description=(
            "سند جدیدی با خطوط معکوس ساخته و قطعی می‌شود؛ سند اصلی به وضعیت "
            "«برگشت‌خورده» می‌رود و حذف نمی‌شود."
        ),
        request=ReverseJournalSerializer,
        responses={201: JournalEntrySerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        entry = self.get_object()
        body = ReverseJournalSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        reversal = services.reverse_journal_entry(
            entry, body.validated_data["reason"], request.user.id
        )
        return Response(JournalEntrySerializer(reversal).data, status=201)


@extend_schema_view(list=extend_schema(tags=["Finance"], summary="خطوط اسناد"))
class JournalLineViewSet(BaseReadOnlyViewSet):
    queryset = JournalLine.objects.select_related(
        "journal_entry", "account", "cost_center"
    )
    serializer_class = JournalLineSerializer
    filterset_fields = ("journal_entry", "account", "cost_center")
    permission_resource = "journal"


@extend_schema_view(list=extend_schema(tags=["Finance"], summary="حساب‌های بانکی"))
class BankAccountViewSet(BaseModelViewSet):
    queryset = BankAccount.objects.select_related("school", "ledger_account")
    serializer_class = BankAccountSerializer
    filterset_fields = ("school", "status")
    permission_resource = "bank"


@extend_schema_view(
    list=extend_schema(tags=["Finance"], summary="مغایرت‌های بانکی"),
    create=extend_schema(
        tags=["Finance"],
        summary="ثبت مغایرت‌گیری",
        description="`difference` خودکار از تفاضل مانده بانک و مانده دفتر محاسبه می‌شود.",
    ),
)
class BankReconciliationViewSet(BaseModelViewSet):
    queryset = BankReconciliation.objects.select_related("bank_account")
    serializer_class = BankReconciliationSerializer
    filterset_fields = ("bank_account", "status")
    permission_resource = "bank"


@extend_schema(
    tags=["Finance"],
    summary="مانده مالی خانواده",
    description=(
        "مانده تجمیعی همه دانش‌آموزان تحت مسئولیت مالی یک ولی، به‌همراه ریز "
        "هر دانش‌آموز و اعتبار تخصیص‌نیافته (بخش ۱۲.۲ سند تحلیل).\n\n"
        "این نما پایه صفحه «پرونده مالی خانواده» در پرتال ولی است."
    ),
    parameters=[
        OpenApiParameter("guardian", str, required=True, description="شناسه ولی")
    ],
    responses={200: FamilyBalanceSerializer, **ERRORS},
)
class FamilyBalanceViewSet(BaseReadOnlyViewSet):
    queryset = StudentFinancialAgreement.objects.none()
    serializer_class = FamilyBalanceSerializer
    permission_resource = "invoice"
    pagination_class = None

    def list(self, request, *args, **kwargs):
        from apps.students.models import Guardian

        guardian_id = request.query_params.get("guardian")
        if not guardian_id:
            raise BusinessRuleViolation(
                code="MISSING_PARAMETER",
                message="پارامتر guardian الزامی است.",
                status_code=400,
            )

        guardian = get_object_or_404(
            Guardian.objects.select_related("person"), pk=guardian_id
        )
        agreements = StudentFinancialAgreement.objects.filter(
            responsible_guardian=guardian
        ).select_related("enrollment__student__person")

        students = []
        total_invoiced = 0
        total_paid = 0
        for agreement in agreements:
            invoiced = agreement.total_invoiced
            paid = agreement.total_paid
            total_invoiced += invoiced
            total_paid += paid
            students.append(
                {
                    "studentId": str(agreement.enrollment.student_id),
                    "studentNo": agreement.enrollment.student.student_no,
                    "studentName": agreement.enrollment.student.person.full_name,
                    "agreementId": str(agreement.id),
                    "agreedAmount": agreement.agreed_amount,
                    "totalInvoiced": invoiced,
                    "totalPaid": paid,
                    "balance": invoiced - paid,
                }
            )

        unallocated = 0
        for payment in Payment.objects.filter(
            payer_person=guardian.person, status=PaymentStatus.SUCCEEDED
        ):
            unallocated += payment.unallocated_amount

        return Response(
            {
                "guardianId": guardian.id,
                "guardianName": guardian.person.full_name,
                "currency": "IRR",
                "totalInvoiced": total_invoiced,
                "totalPaid": total_paid,
                "totalBalance": total_invoiced - total_paid,
                "unallocatedCredit": unallocated,
                "students": students,
            }
        )
