"""Viewهای ماژول مالی و حسابداری."""

from __future__ import annotations

from datetime import timedelta

import django_filters as filters
from django.core.exceptions import ValidationError
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
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.context import get_current_context
from apps.core.exceptions import BusinessRuleViolation, InvalidStateTransition
from apps.core.serializers import (
    ErrorResponseSerializer,
    OperationResultSerializer,
    ReasonSerializer,
)
from apps.core.viewsets import BaseModelViewSet, BaseReadOnlyViewSet, ensure_in_scope
from apps.finance import reports, services
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
    BalanceSheetSerializer,
    BankAccountSerializer,
    BankReconciliationSerializer,
    CostCenterReportSerializer,
    CostCenterSerializer,
    CreateJournalEntrySerializer,
    DaybookSerializer,
    DiscountAwardSerializer,
    FamilyBalanceSerializer,
    FeePlanItemSerializer,
    FeePlanSerializer,
    FiscalYearSerializer,
    GeneralLedgerSerializer,
    GenerateInstallmentsSerializer,
    IncomeStatementSerializer,
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
    TrialBalanceSerializer,
)
from apps.organization.models import School

ERRORS = {
    400: OpenApiResponse(ErrorResponseSerializer, description="داده ورودی معتبر نیست"),
    403: OpenApiResponse(ErrorResponseSerializer, description="بدون مجوز یا تفکیک وظایف"),
    404: OpenApiResponse(ErrorResponseSerializer, description="یافت نشد"),
    409: OpenApiResponse(ErrorResponseSerializer, description="دوره بسته یا تعارض وضعیت"),
    422: OpenApiResponse(ErrorResponseSerializer, description="نقض قاعده کسب‌وکار"),
}


def _resolve_optional(model, raw_id):
    """
    پارامتر اختیاریِ «شناسه یک منبع» را به شیء تبدیل می‌کند.

    خالی‌بودن پارامتر یعنی «بدون فیلتر»، نه خطا؛ ولی شناسه بدفرم یا خارج از
    Tenant باید صریح رد شود، نه اینکه بی‌صدا به «همه» تبدیل گردد.
    """
    if not raw_id:
        return None
    try:
        instance = model.objects.get(pk=raw_id)
    except (model.DoesNotExist, ValueError, ValidationError):
        raise BusinessRuleViolation(
            code="INVALID_PARAMETER",
            message=f"شناسه {model._meta.verbose_name} معتبر نیست.",
            status_code=400,
        )
    ensure_in_scope(instance)
    return instance


@extend_schema_view(
    list=extend_schema(tags=["Finance"], summary="سال‌های مالی"),
    create=extend_schema(tags=["Finance"], summary="ایجاد سال مالی"),
)
class FiscalYearViewSet(BaseModelViewSet):
    queryset = FiscalYear.objects.select_related("school")
    serializer_class = FiscalYearSerializer
    filterset_fields = ("school", "status")
    permission_resource = "journal"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "school"
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
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "school"

    @extend_schema(
        tags=["Finance"],
        summary="گردش حساب",
        description=(
            "ریز گردش یک حساب در بازه مشخص با مانده تجمعی — برای صفحه «گردش "
            "حساب» (بخش ۱۲.۲).\n\n"
            "با ارسال `date_from`، مانده پیش از آن تاریخ در `openingBalance` "
            "می‌آید و مانده تجمعی ستون `balance` از همان‌جا شروع می‌شود."
        ),
        parameters=[
            OpenApiParameter("date_from", str, description="از تاریخ (YYYY-MM-DD)"),
            OpenApiParameter("date_to", str, description="تا تاریخ (YYYY-MM-DD)"),
            OpenApiParameter("cost_center", str, description="شناسه مرکز هزینه"),
        ],
        responses={200: AccountLedgerSerializer, **ERRORS},
    )
    @action(detail=True, methods=["get"])
    def ledger(self, request, pk=None):
        account = self.get_object()
        cost_center = _resolve_optional(
            CostCenter, request.query_params.get("cost_center")
        )
        payload = reports.account_ledger(
            account,
            request.query_params.get("date_from"),
            request.query_params.get("date_to"),
            cost_center=cost_center,
        )
        return Response(payload)


@extend_schema_view(list=extend_schema(tags=["Finance"], summary="مراکز هزینه"))
class CostCenterViewSet(BaseModelViewSet):
    queryset = CostCenter.objects.select_related("school")
    serializer_class = CostCenterSerializer
    filterset_fields = ("school", "is_active")
    search_fields = ("code", "title")
    permission_resource = "journal"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "school"


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
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "academic_year__school"
    academic_year_field = "academic_year"


@extend_schema_view(list=extend_schema(tags=["Finance"], summary="اقلام الگوی شهریه"))
class FeePlanItemViewSet(BaseModelViewSet):
    queryset = FeePlanItem.objects.select_related("fee_plan", "revenue_account")
    serializer_class = FeePlanItemSerializer
    filterset_fields = ("fee_plan", "fee_type", "is_mandatory")
    permission_resource = "fee_plan"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "fee_plan__academic_year__school"
    academic_year_field = "fee_plan__academic_year"


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
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "enrollment__campus__school"
    campus_field = "enrollment__campus"
    academic_year_field = "fee_plan__academic_year"
    self_student_field = "enrollment__student"
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
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "agreement__enrollment__campus__school"
    campus_field = "agreement__enrollment__campus"
    academic_year_field = "agreement__fee_plan__academic_year"
    self_student_field = "agreement__enrollment__student"
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
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "agreement__enrollment__campus__school"
    campus_field = "agreement__enrollment__campus"
    academic_year_field = "agreement__fee_plan__academic_year"
    self_student_field = "agreement__enrollment__student"
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
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "invoice__agreement__enrollment__campus__school"
    campus_field = "invoice__agreement__enrollment__campus"
    academic_year_field = "invoice__agreement__fee_plan__academic_year"
    self_student_field = "invoice__agreement__enrollment__student"

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
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    self_person_field = "payer_person"
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
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "invoice__agreement__enrollment__campus__school"
    campus_field = "invoice__agreement__enrollment__campus"
    academic_year_field = "invoice__agreement__fee_plan__academic_year"
    self_student_field = "invoice__agreement__enrollment__student"


@extend_schema_view(
    list=extend_schema(tags=["Finance"], summary="استردادها"),
    create=extend_schema(tags=["Finance"], summary="درخواست استرداد"),
)
class RefundViewSet(BaseModelViewSet):
    queryset = Refund.objects.select_related("payment__payer_person")
    serializer_class = RefundSerializer
    filterset_fields = ("payment", "status", "approval_status")
    permission_resource = "refund"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    self_person_field = "payment__payer_person"
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
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "fiscal_year__school"
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
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "account__school"


@extend_schema_view(list=extend_schema(tags=["Finance"], summary="حساب‌های بانکی"))
class BankAccountViewSet(BaseModelViewSet):
    queryset = BankAccount.objects.select_related("school", "ledger_account")
    serializer_class = BankAccountSerializer
    filterset_fields = ("school", "status")
    permission_resource = "bank"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "school"


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
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "bank_account__school"


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


# ===========================================================================
# گزارش‌های حسابداری (بخش ۱۴.۳ سند تحلیل)
# ===========================================================================
_REPORT_PARAMETERS = [
    OpenApiParameter(
        "school",
        str,
        description="شناسه مدرسه؛ در نبودش، مدرسه Context جاری (هدر X-School-Id).",
    ),
    OpenApiParameter("fiscal_year", str, description="شناسه سال مالی"),
    OpenApiParameter("date_from", str, description="از تاریخ (YYYY-MM-DD)"),
    OpenApiParameter("date_to", str, description="تا تاریخ (YYYY-MM-DD)"),
]

_LEDGER_EXAMPLE = OpenApiExample(
    "نمونه پاسخ دفتر کل",
    value={
        "dateFrom": "2026-06-01",
        "dateTo": "2026-08-31",
        "currency": "IRR",
        "accountCount": 2,
        "totals": {
            "openingBalance": 0,
            "periodDebit": 120000000,
            "periodCredit": 120000000,
            "closingBalance": 0,
            "isBalanced": True,
        },
        "accounts": [
            {
                "accountId": "8e34ec71-cebc-4cbc-9d47-b8067dd706c0",
                "accountCode": "1101",
                "accountTitle": "صندوق",
                "accountType": "ASSET",
                "accountTypeDisplay": "دارایی",
                "openingBalance": 0,
                "openingDebit": 0,
                "openingCredit": 0,
                "periodDebit": 120000000,
                "periodCredit": 0,
                "closingBalance": 120000000,
                "closingDebit": 120000000,
                "closingCredit": 0,
                "rowCount": 1,
                "rowsTruncated": False,
                "rows": [
                    {
                        "entryId": "3f1b8c22-0d44-4f0a-9a11-6b2c7d8e9f01",
                        "lineId": "9c0d1e2f-3a4b-4c5d-8e9f-0a1b2c3d4e5f",
                        "entryNo": "JV-1405-000012",
                        "entryDate": "2026-07-05",
                        "sourceType": "PAYMENT",
                        "sourceTypeDisplay": "دریافت",
                        "description": "دریافت شهریه — قسط دوم",
                        "costCenter": "دبیرستان دوره اول",
                        "debit": 120000000,
                        "credit": 0,
                        "balance": 120000000,
                    }
                ],
            }
        ],
    },
    response_only=True,
)


class AccountingReportViewSet(viewsets.ViewSet):
    """
    گزارش‌های رسمی حسابداری روی اسناد قطعی.

    این نماها فقط‌خواندنی و تجمیعی‌اند؛ هیچ‌کدام داده‌ای نمی‌نویسند. برای دیدن
    آن‌ها یکی از مجوزهای «مشاهده سند حسابداری» یا «مشاهده گزارش» کافی است، پس
    هم حسابدار و هم ناظر/مدیر به آن دسترسی دارند.

    همه گزارش‌ها فقط سند **قطعی** را می‌شمارند: سند پیش‌نویس هنوز رسمی نیست و
    سند لغوشده اثری ندارد.
    """

    permission_resource = "journal"
    _ANY_READER = ("journal.read", "report.read")
    permission_map = {
        "list": _ANY_READER,
        "general_ledger": _ANY_READER,
        "trial_balance": _ANY_READER,
        "income_statement": _ANY_READER,
        "balance_sheet": _ANY_READER,
        "daybook": _ANY_READER,
        "cost_centers": _ANY_READER,
    }

    # -- ابزار مشترک ----------------------------------------------------
    def _tenant_id(self):
        ctx = get_current_context()
        return ctx.tenant_id if ctx else None

    def _common_filters(self, request) -> dict:
        """
        فیلترهای مشترک گزارش‌ها را از Query، Context و محدوده مجاز می‌سازد.

        این نماها از `ScopedQuerysetMixin` عبور نمی‌کنند (خروجی‌شان Queryset
        نیست)، پس محدوده مجاز باید همین‌جا صریح اعمال شود؛ وگرنه حسابدارِ یک
        مدرسه با یک درخواست ساده، دفتر کل همه مدارس سازمان را می‌گرفت.

        مدرسه اگر در Query نیامده باشد از هدر `X-School-Id` گرفته می‌شود، تا
        گزارش با همان محیط کاری‌ای اجرا شود که بقیه صفحه‌ها با آن کار می‌کنند.
        """
        ctx = get_current_context()
        school = _resolve_optional(School, request.query_params.get("school"))
        if school is None and ctx and ctx.school_id:
            school = _resolve_optional(School, ctx.school_id)

        scope = getattr(ctx, "effective_scope", None) if ctx else None
        allowed_schools = scope.dimension("schools") if scope is not None else None

        return {
            "tenant_id": self._tenant_id(),
            "school": school,
            "schools": allowed_schools,
            "fiscal_year": _resolve_optional(
                FiscalYear, request.query_params.get("fiscal_year")
            ),
            "date_from": request.query_params.get("date_from"),
            "date_to": request.query_params.get("date_to"),
        }

    @staticmethod
    def _flag(request, name: str, default: bool = False) -> bool:
        raw = request.query_params.get(name)
        if raw is None:
            return default
        return raw.lower() in {"1", "true", "yes", "on"}

    # -- کاتالوگ --------------------------------------------------------
    @extend_schema(
        tags=["Reports"],
        summary="کاتالوگ گزارش‌های حسابداری",
        description=(
            "فهرست گزارش‌های در دسترس با مسیر و پارامترهای هرکدام — برای ساخت "
            "صفحه «کاتالوگ گزارش‌ها» بدون Hardcode کردن مسیرها (بخش ۱۵.۱ سند فرانت)."
        ),
        responses={
            200: OpenApiResponse(description="فهرست گزارش‌ها"),
            **ERRORS,
        },
    )
    def list(self, request):
        base = "/api/v1/finance/reports"
        period = ["school", "fiscal_year", "date_from", "date_to"]
        catalog = [
            {
                "key": "general-ledger",
                "title": "دفتر کل",
                "description": "ریز گردش هر حساب با مانده ابتدا، گردش دوره و مانده پایان.",
                "path": f"{base}/general-ledger/",
                "parameters": period + ["account", "account_type", "cost_center", "include_empty", "max_rows"],
            },
            {
                "key": "trial-balance",
                "title": "تراز آزمایشی",
                "description": "شش‌ستونی: مانده ابتدا، گردش دوره و مانده پایان هر حساب.",
                "path": f"{base}/trial-balance/",
                "parameters": period + ["cost_center", "include_zero"],
            },
            {
                "key": "income-statement",
                "title": "صورت سود و زیان",
                "description": "درآمد، هزینه و سود خالص دوره.",
                "path": f"{base}/income-statement/",
                "parameters": period + ["cost_center"],
            },
            {
                "key": "balance-sheet",
                "title": "صورت وضعیت مالی",
                "description": "دارایی، بدهی و حقوق صاحبان سرمایه در یک تاریخ.",
                "path": f"{base}/balance-sheet/",
                "parameters": ["school", "fiscal_year", "as_of"],
            },
            {
                "key": "daybook",
                "title": "دفتر روزنامه",
                "description": "اسناد قطعی به‌ترتیب تاریخ با ریز خطوط.",
                "path": f"{base}/daybook/",
                "parameters": period,
            },
            {
                "key": "cost-centers",
                "title": "درآمد و هزینه مراکز هزینه",
                "description": "تجمیع درآمد و هزینه به تفکیک مرکز هزینه.",
                "path": f"{base}/cost-centers/",
                "parameters": period,
            },
            {
                "key": "receivables-aging",
                "title": "سن مطالبات",
                "description": "توزیع مانده مطالبات در بازه‌های سررسید.",
                "path": "/api/v1/finance/invoices/aging/",
                "parameters": ["school", "status"],
            },
        ]
        return Response(catalog)

    # -- دفتر کل --------------------------------------------------------
    @extend_schema(
        tags=["Reports"],
        summary="دفتر کل",
        description=(
            "ریز گردش حساب‌ها در یک بازه، همراه با مانده ابتدای دوره، گردش "
            "بدهکار/بستانکار و مانده پایان هر حساب (بخش ۱۴.۳).\n\n"
            "- فقط اسناد **قطعی** محاسبه می‌شوند.\n"
            "- بدون `account`، همه حساب‌های دارای گردش برمی‌گردند؛ با "
            "`include_empty=true` حساب‌های بدون گردش هم می‌آیند.\n"
            "- `max_rows` سقف ریز ردیف‌های هر حساب است؛ در صورت بریده‌شدن، "
            "`rowsTruncated` روی همان حساب `true` می‌شود.\n"
            "- `totals.isBalanced` کنترل سلامت است: در حسابداری دوبل جمع گردش "
            "بدهکار و بستانکار دوره باید برابر باشد."
        ),
        parameters=_REPORT_PARAMETERS
        + [
            OpenApiParameter("account", str, description="محدودکردن به یک حساب"),
            OpenApiParameter(
                "account_type",
                str,
                description="ASSET | LIABILITY | EQUITY | REVENUE | EXPENSE (با کاما چندتایی)",
            ),
            OpenApiParameter("cost_center", str, description="شناسه مرکز هزینه"),
            OpenApiParameter(
                "include_empty", bool, description="نمایش حساب‌های بدون گردش"
            ),
            OpenApiParameter(
                "max_rows", int, description="سقف ریز ردیف هر حساب (پیش‌فرض ۵۰۰)"
            ),
        ],
        responses={200: GeneralLedgerSerializer, **ERRORS},
        examples=[_LEDGER_EXAMPLE],
    )
    @action(detail=False, methods=["get"], url_path="general-ledger")
    def general_ledger(self, request):
        account = _resolve_optional(Account, request.query_params.get("account"))
        raw_types = request.query_params.get("account_type", "")
        account_types = [item for item in raw_types.replace(" ", "").split(",") if item]
        try:
            max_rows = int(request.query_params.get("max_rows", 500))
        except ValueError:
            raise BusinessRuleViolation(
                code="INVALID_PARAMETER",
                message="پارامتر max_rows باید عدد باشد.",
                status_code=400,
            )

        payload = reports.general_ledger(
            **self._common_filters(request),
            accounts=[account] if account else None,
            account_types=account_types or None,
            cost_center=_resolve_optional(
                CostCenter, request.query_params.get("cost_center")
            ),
            include_empty=self._flag(request, "include_empty"),
            max_rows_per_account=max(max_rows, 0) or None,
        )
        return Response(payload)

    # -- تراز آزمایشی ---------------------------------------------------
    @extend_schema(
        tags=["Reports"],
        summary="تراز آزمایشی",
        description=(
            "تراز شش‌ستونی حساب‌ها. `totals.isBalanced` باید همیشه `true` باشد؛ "
            "`false` یعنی سندی خارج از مسیر سرویس‌های مالی ثبت شده و باید بررسی شود."
        ),
        parameters=_REPORT_PARAMETERS
        + [
            OpenApiParameter("cost_center", str, description="شناسه مرکز هزینه"),
            OpenApiParameter(
                "include_zero", bool, description="نمایش حساب‌های با مانده و گردش صفر"
            ),
        ],
        responses={200: TrialBalanceSerializer, **ERRORS},
    )
    @action(detail=False, methods=["get"], url_path="trial-balance")
    def trial_balance(self, request):
        payload = reports.trial_balance(
            **self._common_filters(request),
            cost_center=_resolve_optional(
                CostCenter, request.query_params.get("cost_center")
            ),
            include_zero=self._flag(request, "include_zero"),
        )
        return Response(payload)

    # -- سود و زیان -----------------------------------------------------
    @extend_schema(
        tags=["Reports"],
        summary="صورت سود و زیان",
        description=(
            "درآمد و هزینه دوره با علامت طبیعی خودشان (هر دو مثبت) و سود خالص. "
            "`netMarginPercent` وقتی درآمد صفر باشد `null` است، نه صفر."
        ),
        parameters=_REPORT_PARAMETERS
        + [OpenApiParameter("cost_center", str, description="شناسه مرکز هزینه")],
        responses={200: IncomeStatementSerializer, **ERRORS},
    )
    @action(detail=False, methods=["get"], url_path="income-statement")
    def income_statement(self, request):
        payload = reports.income_statement(
            **self._common_filters(request),
            cost_center=_resolve_optional(
                CostCenter, request.query_params.get("cost_center")
            ),
        )
        return Response(payload)

    # -- صورت وضعیت مالی ------------------------------------------------
    @extend_schema(
        tags=["Reports"],
        summary="صورت وضعیت مالی (ترازنامه)",
        description=(
            "دارایی، بدهی و حقوق صاحبان سرمایه تا تاریخ `as_of` (پیش‌فرض: امروز).\n\n"
            "سود/زیان دوره در `equity.retainedResult` جدا آمده و در جمع حقوق "
            "صاحبان سرمایه لحاظ شده است؛ بدون آن، معادله حسابداری تا پیش از "
            "بستن حساب‌های موقت تراز نمی‌شود."
        ),
        parameters=[
            OpenApiParameter("school", str, description="شناسه مدرسه"),
            OpenApiParameter("fiscal_year", str, description="شناسه سال مالی"),
            OpenApiParameter("as_of", str, description="تا تاریخ (YYYY-MM-DD)"),
        ],
        responses={200: BalanceSheetSerializer, **ERRORS},
    )
    @action(detail=False, methods=["get"], url_path="balance-sheet")
    def balance_sheet(self, request):
        filters_ = self._common_filters(request)
        payload = reports.balance_sheet(
            tenant_id=filters_["tenant_id"],
            school=filters_["school"],
            schools=filters_["schools"],
            fiscal_year=filters_["fiscal_year"],
            as_of=request.query_params.get("as_of") or timezone.localdate(),
        )
        return Response(payload)

    # -- دفتر روزنامه ---------------------------------------------------
    @extend_schema(
        tags=["Reports"],
        summary="دفتر روزنامه",
        description="اسناد قطعی به‌ترتیب تاریخ، هر سند با ریز خطوط و جمع بدهکار/بستانکار.",
        parameters=_REPORT_PARAMETERS,
        responses={200: DaybookSerializer, **ERRORS},
    )
    @action(detail=False, methods=["get"])
    def daybook(self, request):
        return Response(reports.daybook(**self._common_filters(request)))

    # -- مراکز هزینه ----------------------------------------------------
    @extend_schema(
        tags=["Reports"],
        summary="درآمد و هزینه مراکز هزینه",
        description=(
            "تجمیع درآمد و هزینه هر مرکز هزینه. خطوط بدون مرکز هزینه زیر عنوان "
            "«بدون مرکز هزینه» می‌آیند تا جمع گزارش با صورت سود و زیان بخواند."
        ),
        parameters=_REPORT_PARAMETERS,
        responses={200: CostCenterReportSerializer, **ERRORS},
    )
    @action(detail=False, methods=["get"], url_path="cost-centers")
    def cost_centers(self, request):
        return Response(reports.cost_center_report(**self._common_filters(request)))
