"""
مدل‌های شهریه، صورتحساب، پرداخت و حسابداری دوبل.

مرجع: بخش ۷.۸ سند تحلیل — ERD «شهریه، صورتحساب، پرداخت و حسابداری».

قیدهای مهم:
- مجموع بدهکار و بستانکار هر سند قطعی برابر است و هر دو نمی‌توانند صفر باشند.
- حساب گروه اجازه ثبت مستقیم ندارد؛ فقط حساب معین/تفصیلی مجاز به Posting است.
- شماره سند/صورتحساب/پرداخت/استرداد یکتا و غیرقابل استفاده مجدد است.
- مجموع تخصیص‌های پرداخت از مبلغ پرداخت موفق بیشتر نمی‌شود.
- سند Posted ویرایش یا حذف نمی‌شود؛ اصلاح با سند برگشتی است.

توجه: تمام مبالغ به‌صورت عدد صحیح در کوچک‌ترین واحد پولی (ریال) نگهداری
می‌شوند — بخش ۱: «محاسبات مالی از نوع اعشاری شناور نیستند».
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import Currency
from apps.core.models import BaseTenantModel, ImmutableLedgerModel
from apps.finance.enums import (
    AccountType,
    AgreementStatus,
    ApprovalState,
    DiscountType,
    FeeType,
    FiscalYearStatus,
    InvoiceStatus,
    JournalSourceType,
    JournalStatus,
    PaymentMethod,
    PaymentStatus,
    Recurrence,
    ReconciliationStatus,
    RefundStatus,
)
from apps.identity.models import Person
from apps.organization.models import AcademicYear, GradeLevel, School
from apps.students.models import Enrollment, Guardian


class FiscalYear(BaseTenantModel):
    """سال مالی — بستن دوره، ثبت سند در آن را ممنوع می‌کند (بخش ۷.۸)."""

    school = models.ForeignKey(
        School, on_delete=models.PROTECT, related_name="fiscal_years"
    )
    title = models.CharField(max_length=60)
    starts_on = models.DateField()
    ends_on = models.DateField()
    status = models.CharField(
        max_length=15, choices=FiscalYearStatus.choices, default=FiscalYearStatus.OPEN
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by_id = models.UUIDField(null=True, blank=True)

    class Meta:
        verbose_name = _("سال مالی")
        verbose_name_plural = _("سال‌های مالی")
        ordering = ("-starts_on",)
        constraints = [
            models.UniqueConstraint(
                fields=["school", "title"], name="uq_fiscal_year_school_title"
            )
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def is_open(self) -> bool:
        return self.status == FiscalYearStatus.OPEN


class Account(BaseTenantModel):
    """
    حساب در کدینگ حساب‌ها (درختی).

    بخش ۷.۸: «حساب گروه اجازه ثبت مستقیم ندارد؛ فقط حساب معین/تفصیلی مجاز به
    Posting است.»
    """

    school = models.ForeignKey(
        School, on_delete=models.PROTECT, related_name="accounts"
    )
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    code = models.CharField(max_length=30, db_index=True, verbose_name=_("کد حساب"))
    title = models.CharField(max_length=200)
    account_type = models.CharField(max_length=15, choices=AccountType.choices)
    allows_posting = models.BooleanField(
        default=True, verbose_name=_("قابل ثبت سند مستقیم")
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("حساب")
        verbose_name_plural = _("کدینگ حساب‌ها")
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(
                fields=["school", "code"], name="uq_account_school_code"
            )
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.title}"


class CostCenter(BaseTenantModel):
    """مرکز هزینه."""

    school = models.ForeignKey(
        School, on_delete=models.PROTECT, related_name="cost_centers"
    )
    code = models.CharField(max_length=30, db_index=True)
    title = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("مرکز هزینه")
        verbose_name_plural = _("مراکز هزینه")
        constraints = [
            models.UniqueConstraint(
                fields=["school", "code"], name="uq_cost_center_school_code"
            )
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.title}"


class FeePlan(BaseTenantModel):
    """الگوی شهریه بر اساس سال تحصیلی و پایه."""

    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="fee_plans"
    )
    grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="fee_plans",
    )
    title = models.CharField(max_length=200)
    currency = models.CharField(
        max_length=3, choices=Currency.choices, default=Currency.IRR
    )
    status = models.CharField(max_length=20, default="ACTIVE")

    class Meta:
        verbose_name = _("الگوی شهریه")
        verbose_name_plural = _("الگوهای شهریه")

    def __str__(self) -> str:
        return self.title

    @property
    def total_amount(self) -> int:
        return self.items.aggregate(total=models.Sum("amount"))["total"] or 0


class FeePlanItem(BaseTenantModel):
    """قلم الگوی شهریه با حساب درآمد متناظر."""

    fee_plan = models.ForeignKey(
        FeePlan, on_delete=models.CASCADE, related_name="items"
    )
    fee_type = models.CharField(max_length=25, choices=FeeType.choices)
    title = models.CharField(max_length=200)
    amount = models.BigIntegerField(verbose_name=_("مبلغ (ریال)"))
    recurrence = models.CharField(
        max_length=15, choices=Recurrence.choices, default=Recurrence.ONE_TIME
    )
    is_mandatory = models.BooleanField(default=True)
    revenue_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="fee_plan_items",
        verbose_name=_("حساب درآمد"),
    )

    class Meta:
        verbose_name = _("قلم الگوی شهریه")
        verbose_name_plural = _("اقلام الگوی شهریه")

    def __str__(self) -> str:
        return f"{self.title}: {self.amount:,}"


class StudentFinancialAgreement(BaseTenantModel):
    """قرارداد مالی دانش‌آموز."""

    enrollment = models.OneToOneField(
        Enrollment, on_delete=models.PROTECT, related_name="financial_agreement"
    )
    fee_plan = models.ForeignKey(
        FeePlan, on_delete=models.PROTECT, related_name="agreements"
    )
    responsible_guardian = models.ForeignKey(
        Guardian,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="financial_agreements",
        verbose_name=_("مسئول مالی"),
    )
    agreed_amount = models.BigIntegerField(
        default=0, verbose_name=_("مبلغ توافق‌شده پس از تخفیف")
    )
    currency = models.CharField(max_length=3, default=Currency.IRR)
    installment_count = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(
        max_length=20, choices=AgreementStatus.choices, default=AgreementStatus.DRAFT
    )
    note = models.CharField(max_length=400, blank=True)

    class Meta:
        verbose_name = _("قرارداد مالی")
        verbose_name_plural = _("قراردادهای مالی")

    def __str__(self) -> str:
        return f"قرارداد {self.enrollment.student.full_name}"

    @property
    def total_invoiced(self) -> int:
        return self.invoices.exclude(
            status__in=[InvoiceStatus.CANCELLED, InvoiceStatus.DRAFT]
        ).aggregate(total=models.Sum("total_amount"))["total"] or 0

    @property
    def total_paid(self) -> int:
        return self.invoices.aggregate(total=models.Sum("paid_amount"))["total"] or 0

    @property
    def balance(self) -> int:
        return self.total_invoiced - self.total_paid


class DiscountAward(BaseTenantModel):
    """تخفیف اعطاشده روی یک قرارداد مالی."""

    agreement = models.ForeignKey(
        StudentFinancialAgreement, on_delete=models.CASCADE, related_name="discounts"
    )
    discount_type = models.CharField(max_length=25, choices=DiscountType.choices)
    percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, verbose_name=_("درصد تخفیف")
    )
    amount = models.BigIntegerField(default=0, verbose_name=_("مبلغ ثابت تخفیف"))
    reason = models.CharField(max_length=400, blank=True)
    approval_status = models.CharField(
        max_length=15, choices=ApprovalState.choices, default=ApprovalState.PENDING
    )
    approved_by_id = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("تخفیف")
        verbose_name_plural = _("تخفیف‌ها")

    def __str__(self) -> str:
        return f"{self.get_discount_type_display()} — {self.agreement}"


class Invoice(BaseTenantModel):
    """صورتحساب — ماشین حالت بخش ۱۰.۵."""

    agreement = models.ForeignKey(
        StudentFinancialAgreement, on_delete=models.PROTECT, related_name="invoices"
    )
    invoice_no = models.CharField(max_length=40, db_index=True)
    issue_date = models.DateField(verbose_name=_("تاریخ صدور"))
    due_date = models.DateField(db_index=True, verbose_name=_("سررسید"))
    installment_no = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name=_("شماره قسط")
    )
    total_amount = models.BigIntegerField(default=0, verbose_name=_("مبلغ کل"))
    discount_amount = models.BigIntegerField(default=0)
    paid_amount = models.BigIntegerField(default=0, verbose_name=_("مبلغ پرداخت‌شده"))
    currency = models.CharField(max_length=3, default=Currency.IRR)
    status = models.CharField(
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT,
        db_index=True,
    )
    description = models.CharField(max_length=400, blank=True)
    cancel_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("صورتحساب")
        verbose_name_plural = _("صورتحساب‌ها")
        ordering = ("-issue_date",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "invoice_no"], name="uq_invoice_tenant_no"
            )
        ]
        indexes = [
            models.Index(fields=["agreement", "status"]),
            models.Index(fields=["due_date", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.invoice_no} — {self.total_amount:,}"

    @property
    def balance(self) -> int:
        return max(self.total_amount - self.paid_amount, 0)


class InvoiceLine(BaseTenantModel):
    """قلم صورتحساب."""

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="lines"
    )
    fee_type = models.CharField(max_length=25, choices=FeeType.choices)
    description = models.CharField(max_length=300)
    quantity = models.PositiveIntegerField(default=1)
    unit_amount = models.BigIntegerField(default=0)
    discount_amount = models.BigIntegerField(default=0)
    net_amount = models.BigIntegerField(default=0)
    revenue_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoice_lines",
    )

    class Meta:
        verbose_name = _("قلم صورتحساب")
        verbose_name_plural = _("اقلام صورتحساب")

    def save(self, *args, **kwargs):
        self.net_amount = self.quantity * self.unit_amount - self.discount_amount
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.description}: {self.net_amount:,}"


class BankAccount(BaseTenantModel):
    """حساب بانکی مدرسه."""

    school = models.ForeignKey(
        School, on_delete=models.PROTECT, related_name="bank_accounts"
    )
    title = models.CharField(max_length=200)
    bank_name = models.CharField(max_length=120, blank=True)
    iban_masked = models.CharField(
        max_length=40,
        blank=True,
        verbose_name=_("شبا (ماسک‌شده)"),
        help_text=_("بخش ۱۵.۲: شماره کامل حساب در Log و پاسخ API ذخیره نمی‌شود."),
    )
    ledger_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="bank_accounts",
    )
    currency = models.CharField(max_length=3, default=Currency.IRR)
    status = models.CharField(max_length=20, default="ACTIVE")

    class Meta:
        verbose_name = _("حساب بانکی")
        verbose_name_plural = _("حساب‌های بانکی")

    def __str__(self) -> str:
        return self.title


class Payment(BaseTenantModel):
    """
    دریافت وجه.

    بخش ۷.۸: «پرداخت موفق درگاه با Callback امضاشده و Idempotency Key ثبت
    می‌شود؛ موفقیت مرورگر به‌تنهایی مدرک پرداخت نیست.»
    """

    payer_person = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name="payments"
    )
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="payments",
        null=True,
        blank=True,
        verbose_name=_("مدرسه"),
        help_text=_("برای تعیین کدینگ حساب و سال مالی هنگام ثبت سند"),
    )
    payment_no = models.CharField(max_length=40, db_index=True)
    method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    amount = models.BigIntegerField(verbose_name=_("مبلغ"))
    currency = models.CharField(max_length=3, default=Currency.IRR)
    received_at = models.DateTimeField(verbose_name=_("زمان دریافت"))
    bank_account = models.ForeignKey(
        BankAccount,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payments",
    )
    gateway_reference = models.CharField(
        max_length=200, blank=True, db_index=True, verbose_name=_("کد پیگیری درگاه")
    )
    idempotency_key = models.CharField(
        max_length=100, blank=True, db_index=True
    )
    cheque_no = models.CharField(max_length=40, blank=True)
    cheque_due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True,
    )
    cashier_user_id = models.UUIDField(null=True, blank=True)
    note = models.CharField(max_length=400, blank=True)
    void_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("دریافت")
        verbose_name_plural = _("دریافت‌ها")
        ordering = ("-received_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "payment_no"], name="uq_payment_tenant_no"
            ),
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uq_payment_idempotency",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.payment_no} — {self.amount:,}"

    @property
    def allocated_amount(self) -> int:
        return self.allocations.aggregate(total=models.Sum("amount"))["total"] or 0

    @property
    def unallocated_amount(self) -> int:
        """مبلغ تخصیص‌نیافته = پیش‌دریافت (بخش ۵ واژگان)."""
        return self.amount - self.allocated_amount


class PaymentAllocation(BaseTenantModel):
    """
    تخصیص یک پرداخت به یک صورتحساب.

    بخش ۷.۸: یک پرداخت به چند صورتحساب و یک صورتحساب به چند پرداخت.
    """

    payment = models.ForeignKey(
        Payment, on_delete=models.CASCADE, related_name="allocations"
    )
    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="allocations"
    )
    amount = models.BigIntegerField()
    allocated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("تخصیص پرداخت")
        verbose_name_plural = _("تخصیص‌های پرداخت")
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "invoice"], name="uq_payment_invoice_allocation"
            )
        ]

    def __str__(self) -> str:
        return f"{self.payment.payment_no} → {self.invoice.invoice_no}: {self.amount:,}"


class Refund(BaseTenantModel):
    """
    استرداد.

    بخش ۷.۸: «استرداد مستقل از ابطال دریافت است و باید اثر حسابداری معکوس،
    وضعیت درگاه و مانده تخصیص را هماهنگ کند.»
    """

    payment = models.ForeignKey(
        Payment, on_delete=models.PROTECT, related_name="refunds"
    )
    refund_no = models.CharField(max_length=40, db_index=True)
    amount = models.BigIntegerField()
    currency = models.CharField(max_length=3, default=Currency.IRR)
    reason = models.CharField(max_length=400)
    requested_by_id = models.UUIDField(null=True, blank=True)
    approval_status = models.CharField(
        max_length=15, choices=ApprovalState.choices, default=ApprovalState.PENDING
    )
    approved_by_id = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=15, choices=RefundStatus.choices, default=RefundStatus.REQUESTED
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    gateway_reference = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = _("استرداد")
        verbose_name_plural = _("استردادها")
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "refund_no"], name="uq_refund_tenant_no"
            )
        ]

    def __str__(self) -> str:
        return f"{self.refund_no} — {self.amount:,}"


class JournalEntry(ImmutableLedgerModel):
    """
    سند حسابداری — ماشین حالت بخش ۱۰.۶.

    «سند Posted ویرایش یا حذف نمی‌شود. Reversed یعنی سند جدیدی با خطوط معکوس
    و ارجاع به سند اصلی قطعی شده است.»
    """

    fiscal_year = models.ForeignKey(
        FiscalYear, on_delete=models.PROTECT, related_name="journal_entries"
    )
    entry_no = models.CharField(max_length=40, db_index=True)
    entry_date = models.DateField(db_index=True)
    source_type = models.CharField(
        max_length=20, choices=JournalSourceType.choices, default=JournalSourceType.MANUAL
    )
    source_id = models.UUIDField(null=True, blank=True, db_index=True)
    description = models.CharField(max_length=400)
    status = models.CharField(
        max_length=15, choices=JournalStatus.choices, default=JournalStatus.DRAFT
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by_id = models.UUIDField(null=True, blank=True)
    reversal_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversals",
        verbose_name=_("سند برگشتی برای"),
    )

    class Meta:
        verbose_name = _("سند حسابداری")
        verbose_name_plural = _("اسناد حسابداری")
        ordering = ("-entry_date", "-entry_no")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "entry_no"], name="uq_journal_tenant_no"
            )
        ]
        indexes = [models.Index(fields=["source_type", "source_id"])]

    def __str__(self) -> str:
        return f"سند {self.entry_no} — {self.description[:40]}"

    @property
    def total_debit(self) -> int:
        return self.lines.aggregate(total=models.Sum("debit_amount"))["total"] or 0

    @property
    def total_credit(self) -> int:
        return self.lines.aggregate(total=models.Sum("credit_amount"))["total"] or 0

    @property
    def is_balanced(self) -> bool:
        debit = self.total_debit
        credit = self.total_credit
        return debit == credit and debit > 0


class JournalLine(ImmutableLedgerModel):
    """خط سند حسابداری."""

    journal_entry = models.ForeignKey(
        JournalEntry, on_delete=models.CASCADE, related_name="lines"
    )
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="journal_lines"
    )
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="journal_lines",
    )
    debit_amount = models.BigIntegerField(default=0, verbose_name=_("بدهکار"))
    credit_amount = models.BigIntegerField(default=0, verbose_name=_("بستانکار"))
    description = models.CharField(max_length=300, blank=True)
    line_no = models.PositiveSmallIntegerField(default=1)

    class Meta:
        verbose_name = _("خط سند")
        verbose_name_plural = _("خطوط سند")
        ordering = ("line_no",)
        constraints = [
            # یک خط یا بدهکار است یا بستانکار، نه هر دو و نه هیچ‌کدام
            models.CheckConstraint(
                condition=(
                    models.Q(debit_amount__gt=0, credit_amount=0)
                    | models.Q(credit_amount__gt=0, debit_amount=0)
                ),
                name="ck_journal_line_debit_xor_credit",
            )
        ]
        indexes = [models.Index(fields=["account", "journal_entry"])]

    def __str__(self) -> str:
        side = "بد" if self.debit_amount else "بس"
        return f"{self.account.code} {side} {self.debit_amount or self.credit_amount:,}"


class BankReconciliation(BaseTenantModel):
    """مغایرت‌گیری بانکی."""

    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name="reconciliations"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    statement_balance = models.BigIntegerField(verbose_name=_("مانده صورتحساب بانک"))
    ledger_balance = models.BigIntegerField(verbose_name=_("مانده دفتر"))
    difference = models.BigIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=ReconciliationStatus.choices,
        default=ReconciliationStatus.OPEN,
    )
    note = models.TextField(blank=True)
    reconciled_by_id = models.UUIDField(null=True, blank=True)
    reconciled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("مغایرت بانکی")
        verbose_name_plural = _("مغایرت‌های بانکی")
        ordering = ("-period_end",)

    def save(self, *args, **kwargs):
        self.difference = self.statement_balance - self.ledger_balance
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.bank_account.title} — {self.period_end}"
