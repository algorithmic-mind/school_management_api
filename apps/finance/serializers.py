"""سریالایزرهای ماژول مالی و حسابداری."""

from __future__ import annotations

from rest_framework import serializers

from apps.core.serializers import AUDIT_FIELDS
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


class FiscalYearSerializer(serializers.ModelSerializer):
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = FiscalYear
        fields = (
            "id",
            "school",
            "title",
            "starts_on",
            "ends_on",
            "status",
            "is_open",
            "closed_at",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "status",
            "closed_at",
            "created_at",
            "updated_at",
            "version",
        )


class AccountSerializer(serializers.ModelSerializer):
    account_type_display = serializers.CharField(
        source="get_account_type_display", read_only=True
    )
    parent_code = serializers.CharField(source="parent.code", read_only=True)

    class Meta:
        model = Account
        fields = (
            "id",
            "school",
            "parent",
            "parent_code",
            "code",
            "title",
            "account_type",
            "account_type_display",
            "allows_posting",
            "is_active",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class CostCenterSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostCenter
        fields = ("id", "school", "code", "title", "is_active", *AUDIT_FIELDS[1:])
        read_only_fields = ("id", "created_at", "updated_at", "version")


class FeePlanItemSerializer(serializers.ModelSerializer):
    fee_type_display = serializers.CharField(
        source="get_fee_type_display", read_only=True
    )

    class Meta:
        model = FeePlanItem
        fields = (
            "id",
            "fee_plan",
            "fee_type",
            "fee_type_display",
            "title",
            "amount",
            "recurrence",
            "is_mandatory",
            "revenue_account",
        )
        read_only_fields = ("id",)


class FeePlanSerializer(serializers.ModelSerializer):
    items = FeePlanItemSerializer(many=True, read_only=True)
    total_amount = serializers.IntegerField(read_only=True)

    class Meta:
        model = FeePlan
        fields = (
            "id",
            "academic_year",
            "grade_level",
            "title",
            "currency",
            "status",
            "total_amount",
            "items",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class DiscountAwardSerializer(serializers.ModelSerializer):
    discount_type_display = serializers.CharField(
        source="get_discount_type_display", read_only=True
    )

    class Meta:
        model = DiscountAward
        fields = (
            "id",
            "agreement",
            "discount_type",
            "discount_type_display",
            "percent",
            "amount",
            "reason",
            "approval_status",
            "approved_at",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "approval_status",
            "approved_at",
            "created_at",
            "updated_at",
            "version",
        )


class StudentFinancialAgreementSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="enrollment.student.person.full_name", read_only=True
    )
    student_no = serializers.CharField(
        source="enrollment.student.student_no", read_only=True
    )
    responsible_guardian_name = serializers.CharField(
        source="responsible_guardian.person.full_name", read_only=True
    )
    fee_plan_title = serializers.CharField(source="fee_plan.title", read_only=True)
    discounts = DiscountAwardSerializer(many=True, read_only=True)
    total_invoiced = serializers.IntegerField(read_only=True)
    total_paid = serializers.IntegerField(read_only=True)
    balance = serializers.IntegerField(read_only=True)

    class Meta:
        model = StudentFinancialAgreement
        fields = (
            "id",
            "enrollment",
            "student_name",
            "student_no",
            "fee_plan",
            "fee_plan_title",
            "responsible_guardian",
            "responsible_guardian_name",
            "agreed_amount",
            "currency",
            "installment_count",
            "status",
            "note",
            "discounts",
            "total_invoiced",
            "total_paid",
            "balance",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "agreed_amount",
            "created_at",
            "updated_at",
            "version",
        )


class InvoiceLineSerializer(serializers.ModelSerializer):
    fee_type_display = serializers.CharField(
        source="get_fee_type_display", read_only=True
    )

    class Meta:
        model = InvoiceLine
        fields = (
            "id",
            "invoice",
            "fee_type",
            "fee_type_display",
            "description",
            "quantity",
            "unit_amount",
            "discount_amount",
            "net_amount",
            "revenue_account",
        )
        read_only_fields = ("id", "net_amount")


class InvoiceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="agreement.enrollment.student.person.full_name", read_only=True
    )
    student_no = serializers.CharField(
        source="agreement.enrollment.student.student_no", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    balance = serializers.IntegerField(read_only=True)
    lines = InvoiceLineSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = (
            "id",
            "agreement",
            "student_name",
            "student_no",
            "invoice_no",
            "issue_date",
            "due_date",
            "installment_no",
            "total_amount",
            "discount_amount",
            "paid_amount",
            "balance",
            "currency",
            "status",
            "status_display",
            "description",
            "cancel_reason",
            "lines",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "invoice_no",
            "paid_amount",
            "status",
            "created_at",
            "updated_at",
            "version",
        )


class PaymentAllocationSerializer(serializers.ModelSerializer):
    invoice_no = serializers.CharField(source="invoice.invoice_no", read_only=True)

    class Meta:
        model = PaymentAllocation
        fields = ("id", "payment", "invoice", "invoice_no", "amount", "allocated_at")
        read_only_fields = ("id", "allocated_at")


class PaymentSerializer(serializers.ModelSerializer):
    payer_name = serializers.CharField(source="payer_person.full_name", read_only=True)
    method_display = serializers.CharField(source="get_method_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    allocations = PaymentAllocationSerializer(many=True, read_only=True)
    allocated_amount = serializers.IntegerField(read_only=True)
    unallocated_amount = serializers.IntegerField(read_only=True)

    class Meta:
        model = Payment
        fields = (
            "id",
            "payer_person",
            "payer_name",
            "school",
            "payment_no",
            "method",
            "method_display",
            "amount",
            "currency",
            "received_at",
            "bank_account",
            "gateway_reference",
            "cheque_no",
            "cheque_due_date",
            "status",
            "status_display",
            "note",
            "void_reason",
            "allocations",
            "allocated_amount",
            "unallocated_amount",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "payment_no",
            "status",
            "void_reason",
            "created_at",
            "updated_at",
            "version",
        )

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("مبلغ دریافت باید بزرگ‌تر از صفر باشد.")
        return value


class AllocationRowSerializer(serializers.Serializer):
    invoice = serializers.UUIDField()
    amount = serializers.IntegerField(min_value=1, help_text="مبلغ به ریال")


class AllocatePaymentSerializer(serializers.Serializer):
    """
    تخصیص یک پرداخت به چند صورتحساب.

    مجموع تخصیص نباید از مبلغ تخصیص‌نیافته پرداخت یا مانده هر صورتحساب بیشتر
    شود (بخش ۷.۸).
    """

    allocations = AllocationRowSerializer(many=True)


class RefundSerializer(serializers.ModelSerializer):
    payment_no = serializers.CharField(source="payment.payment_no", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Refund
        fields = (
            "id",
            "payment",
            "payment_no",
            "refund_no",
            "amount",
            "currency",
            "reason",
            "requested_by_id",
            "approval_status",
            "approved_at",
            "status",
            "status_display",
            "completed_at",
            "gateway_reference",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "refund_no",
            "approval_status",
            "approved_at",
            "status",
            "completed_at",
            "created_at",
            "updated_at",
            "version",
        )


class JournalLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source="account.code", read_only=True)
    account_title = serializers.CharField(source="account.title", read_only=True)
    cost_center_title = serializers.CharField(
        source="cost_center.title", read_only=True
    )

    class Meta:
        model = JournalLine
        fields = (
            "id",
            "journal_entry",
            "account",
            "account_code",
            "account_title",
            "cost_center",
            "cost_center_title",
            "debit_amount",
            "credit_amount",
            "description",
            "line_no",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        debit = attrs.get("debit_amount", 0)
        credit = attrs.get("credit_amount", 0)
        if bool(debit) == bool(credit):
            raise serializers.ValidationError(
                {
                    "debit_amount": (
                        "هر خط سند باید دقیقاً یکی از مبلغ بدهکار یا بستانکار "
                        "را داشته باشد."
                    )
                }
            )
        return attrs


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True, read_only=True)
    total_debit = serializers.IntegerField(read_only=True)
    total_credit = serializers.IntegerField(read_only=True)
    is_balanced = serializers.BooleanField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = JournalEntry
        fields = (
            "id",
            "fiscal_year",
            "entry_no",
            "entry_date",
            "source_type",
            "source_id",
            "description",
            "status",
            "status_display",
            "posted_at",
            "reversal_of",
            "total_debit",
            "total_credit",
            "is_balanced",
            "lines",
            "created_at",
            "version",
        )
        read_only_fields = (
            "id",
            "entry_no",
            "status",
            "posted_at",
            "reversal_of",
            "created_at",
            "version",
        )


class JournalLineInputSerializer(serializers.Serializer):
    account = serializers.UUIDField()
    cost_center = serializers.UUIDField(required=False, allow_null=True)
    debit = serializers.IntegerField(default=0, min_value=0)
    credit = serializers.IntegerField(default=0, min_value=0)
    description = serializers.CharField(
        required=False, allow_blank=True, max_length=300, default=""
    )


class CreateJournalEntrySerializer(serializers.Serializer):
    """
    ایجاد سند حسابداری دستی.

    مجموع بدهکار و بستانکار باید برابر و بزرگ‌تر از صفر باشد؛ در غیر این صورت
    قطعی‌سازی سند با خطای `JOURNAL_NOT_BALANCED` رد می‌شود.
    """

    fiscal_year = serializers.UUIDField()
    entry_date = serializers.DateField()
    description = serializers.CharField(max_length=400)
    lines = JournalLineInputSerializer(many=True)
    post_immediately = serializers.BooleanField(
        default=False, help_text="اگر true باشد، سند بلافاصله قطعی می‌شود."
    )


class ReverseJournalSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=400)


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = (
            "id",
            "school",
            "title",
            "bank_name",
            "iban_masked",
            "ledger_account",
            "currency",
            "status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class BankReconciliationSerializer(serializers.ModelSerializer):
    bank_account_title = serializers.CharField(
        source="bank_account.title", read_only=True
    )

    class Meta:
        model = BankReconciliation
        fields = (
            "id",
            "bank_account",
            "bank_account_title",
            "period_start",
            "period_end",
            "statement_balance",
            "ledger_balance",
            "difference",
            "status",
            "note",
            "reconciled_at",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "difference",
            "reconciled_at",
            "created_at",
            "updated_at",
            "version",
        )


# ---------------------------------------------------------------------------
# نماهای گزارشی
# ---------------------------------------------------------------------------
class GenerateInstallmentsSerializer(serializers.Serializer):
    first_due_date = serializers.DateField()
    interval_days = serializers.IntegerField(default=30, min_value=1)


class FamilyBalanceSerializer(serializers.Serializer):
    """
    مانده خانواده (بخش ۱۲.۲).

    همه دانش‌آموزان مرتبط با یک مسئول مالی و مانده هر کدام.
    """

    guardianId = serializers.UUIDField()
    guardianName = serializers.CharField()
    currency = serializers.CharField()
    totalInvoiced = serializers.IntegerField()
    totalPaid = serializers.IntegerField()
    totalBalance = serializers.IntegerField()
    unallocatedCredit = serializers.IntegerField(
        help_text="پیش‌دریافت تخصیص‌نیافته"
    )
    students = serializers.ListField(child=serializers.DictField())


class LedgerRowSerializer(serializers.Serializer):
    entryNo = serializers.CharField()
    entryDate = serializers.DateField()
    description = serializers.CharField()
    costCenter = serializers.CharField(allow_null=True)
    debit = serializers.IntegerField()
    credit = serializers.IntegerField()
    balance = serializers.IntegerField()


class AccountLedgerSerializer(serializers.Serializer):
    """گردش حساب (بخش ۱۲.۲)."""

    accountCode = serializers.CharField()
    accountTitle = serializers.CharField()
    openingBalance = serializers.IntegerField()
    closingBalance = serializers.IntegerField()
    rows = LedgerRowSerializer(many=True)


class ReceivablesAgingSerializer(serializers.Serializer):
    """گزارش سنی مطالبات (بخش ۱۴.۳ — داشبورد مالی)."""

    bucket = serializers.CharField(
        help_text="CURRENT | 1_30 | 31_60 | 61_90 | OVER_90"
    )
    invoiceCount = serializers.IntegerField()
    totalAmount = serializers.IntegerField()
