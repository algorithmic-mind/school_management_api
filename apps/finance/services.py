"""
قواعد کسب‌وکار مالی و حسابداری.

مرجع: بخش ۷.۸ (قیدها)، ۹.۲ (تعهد مالی)، ۹.۶ (ثبت شهریه و پرداخت آنلاین)،
۱۰.۵ و ۱۰.۶ (ماشین حالت)، ۱۶.۲ (تفکیک وظایف).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.exceptions import (
    BusinessRuleViolation,
    InvalidStateTransition,
    PeriodClosed,
)
from apps.finance.enums import (
    ApprovalState,
    FiscalYearStatus,
    InvoiceStatus,
    JournalSourceType,
    JournalStatus,
    PaymentStatus,
    RefundStatus,
)
from apps.finance.models import (
    Account,
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

# ---------------------------------------------------------------------------
# شماره‌گذاری اسناد
# ---------------------------------------------------------------------------
def _next_sequence(model, tenant_id, field: str, prefix: str) -> str:
    """
    تولید شماره ترتیبی.

    در محیط عملیاتی باید از Sequence اتمیک پایگاه داده استفاده شود تا در بار
    همزمان شماره تکراری تولید نشود (بخش ۷.۸: شماره پس از صدور غیرقابل استفاده
    مجدد است).
    """
    count = model.objects.filter(tenant_id=tenant_id).count()
    return f"{prefix}-{timezone.now():%Y%m}-{count + 1:06d}"


def generate_invoice_no(tenant_id) -> str:
    return _next_sequence(Invoice, tenant_id, "invoice_no", "INV")


def generate_payment_no(tenant_id) -> str:
    return _next_sequence(Payment, tenant_id, "payment_no", "PAY")


def generate_refund_no(tenant_id) -> str:
    return _next_sequence(Refund, tenant_id, "refund_no", "REF")


def generate_entry_no(tenant_id) -> str:
    return _next_sequence(JournalEntry, tenant_id, "entry_no", "JV")


# ---------------------------------------------------------------------------
# قرارداد مالی و صورتحساب
# ---------------------------------------------------------------------------
def calculate_agreed_amount(agreement: StudentFinancialAgreement) -> int:
    """
    مبلغ توافق‌شده = جمع اقلام تعرفه منهای تخفیف‌های تأییدشده.

    مبالغ عدد صحیح‌اند؛ درصد تخفیف با گِرد کردن به نزدیک‌ترین ریال اعمال می‌شود.
    """
    base = agreement.fee_plan.total_amount
    total_discount = 0

    for discount in agreement.discounts.filter(
        approval_status=ApprovalState.APPROVED
    ):
        if discount.percent:
            total_discount += int(
                (Decimal(base) * Decimal(str(discount.percent)) / 100).to_integral_value()
            )
        total_discount += discount.amount

    return max(base - total_discount, 0)


@transaction.atomic
def create_agreement_for_enrollment(
    enrollment, fee_plan, responsible_guardian=None, installment_count: int = 1
) -> StudentFinancialAgreement:
    """
    ایجاد تعهد مالی هنگام ثبت‌نام (بخش ۹.۲).
    """
    if hasattr(enrollment, "financial_agreement"):
        return enrollment.financial_agreement

    agreement = StudentFinancialAgreement.objects.create(
        tenant_id=enrollment.tenant_id,
        enrollment=enrollment,
        fee_plan=fee_plan,
        responsible_guardian=responsible_guardian,
        installment_count=max(installment_count, 1),
        currency=fee_plan.currency,
        status="ACTIVE",
    )
    agreement.agreed_amount = calculate_agreed_amount(agreement)
    agreement.save(update_fields=["agreed_amount"])
    return agreement


@transaction.atomic
def generate_installments(
    agreement: StudentFinancialAgreement,
    first_due_date: date,
    interval_days: int = 30,
) -> list[Invoice]:
    """
    تولید صورتحساب اقساط بر اساس مبلغ توافق‌شده.

    باقیمانده تقسیم به قسط آخر اضافه می‌شود تا جمع اقساط دقیقاً برابر مبلغ
    توافق‌شده بماند (بدون خطای گِرد کردن).
    """
    if agreement.invoices.exists():
        raise BusinessRuleViolation(
            code="INSTALLMENTS_ALREADY_GENERATED",
            message="برای این قرارداد قبلاً صورتحساب صادر شده است.",
        )

    count = max(agreement.installment_count, 1)
    base_amount = agreement.agreed_amount // count
    remainder = agreement.agreed_amount - base_amount * count

    invoices: list[Invoice] = []
    for index in range(1, count + 1):
        amount = base_amount + (remainder if index == count else 0)
        invoice = Invoice.objects.create(
            tenant_id=agreement.tenant_id,
            agreement=agreement,
            invoice_no=generate_invoice_no(agreement.tenant_id),
            issue_date=timezone.localdate(),
            due_date=first_due_date + timedelta(days=interval_days * (index - 1)),
            installment_no=index,
            total_amount=amount,
            currency=agreement.currency,
            status=InvoiceStatus.DRAFT,
            description=f"قسط {index} از {count}",
        )
        InvoiceLine.objects.create(
            tenant_id=agreement.tenant_id,
            invoice=invoice,
            fee_type="TUITION",
            description=f"شهریه — قسط {index} از {count}",
            quantity=1,
            unit_amount=amount,
            net_amount=amount,
        )
        invoices.append(invoice)

    return invoices


def recalculate_invoice_total(invoice: Invoice) -> Invoice:
    """جمع اقلام را روی صورتحساب می‌نشاند."""
    aggregate = invoice.lines.aggregate(
        net=Sum("net_amount"), discount=Sum("discount_amount")
    )
    invoice.total_amount = aggregate["net"] or 0
    invoice.discount_amount = aggregate["discount"] or 0
    invoice.save(update_fields=["total_amount", "discount_amount"])
    return invoice


@transaction.atomic
def issue_invoice(invoice: Invoice) -> Invoice:
    """صدور صورتحساب و ثبت سند حسابداری تعهدی."""
    if invoice.status != InvoiceStatus.DRAFT:
        raise InvalidStateTransition(
            entity="صورتحساب", current=invoice.status, action="issue"
        )
    if invoice.total_amount <= 0:
        raise BusinessRuleViolation(
            code="INVOICE_AMOUNT_INVALID",
            message="مبلغ صورتحساب باید بزرگ‌تر از صفر باشد.",
            field_errors=[{"field": "totalAmount", "reason": "must_be_positive"}],
        )

    invoice.status = InvoiceStatus.ISSUED
    invoice.save(update_fields=["status"])

    post_invoice_journal(invoice)

    from apps.workflow.services import publish_event

    publish_event(
        aggregate_type="finance.Invoice",
        aggregate_id=invoice.id,
        event_type="InvoiceIssued",
        payload={
            "invoiceId": str(invoice.id),
            "invoiceNo": invoice.invoice_no,
            "amount": invoice.total_amount,
            "dueDate": invoice.due_date.isoformat(),
        },
        tenant_id=invoice.tenant_id,
    )
    return invoice


def refresh_invoice_payment_status(invoice: Invoice) -> Invoice:
    """وضعیت صورتحساب را از روی تخصیص‌های پرداخت به‌روز می‌کند."""
    allocated = (
        PaymentAllocation.objects.filter(
            invoice=invoice, payment__status=PaymentStatus.SUCCEEDED
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    invoice.paid_amount = allocated

    if invoice.status in {InvoiceStatus.CANCELLED, InvoiceStatus.CREDITED}:
        invoice.save(update_fields=["paid_amount"])
        return invoice

    if allocated >= invoice.total_amount and invoice.total_amount > 0:
        invoice.status = InvoiceStatus.PAID
    elif allocated > 0:
        invoice.status = InvoiceStatus.PARTIALLY_PAID
    elif invoice.due_date < timezone.localdate():
        invoice.status = InvoiceStatus.OVERDUE
    else:
        invoice.status = InvoiceStatus.ISSUED

    invoice.save(update_fields=["paid_amount", "status"])
    return invoice


# ---------------------------------------------------------------------------
# پرداخت و تخصیص
# ---------------------------------------------------------------------------
@transaction.atomic
def post_payment(payment: Payment) -> Payment:
    """قطعی‌کردن دریافت و ثبت سند حسابداری."""
    if payment.status == PaymentStatus.SUCCEEDED:
        return payment
    if payment.status in {PaymentStatus.VOIDED, PaymentStatus.REFUNDED}:
        raise InvalidStateTransition(
            entity="دریافت", current=payment.status, action="post"
        )

    payment.status = PaymentStatus.SUCCEEDED
    payment.save(update_fields=["status"])

    post_payment_journal(payment)

    from apps.workflow.services import publish_event

    publish_event(
        aggregate_type="finance.Payment",
        aggregate_id=payment.id,
        event_type="PaymentPosted",
        payload={
            "paymentId": str(payment.id),
            "paymentNo": payment.payment_no,
            "amount": payment.amount,
            "method": payment.method,
        },
        tenant_id=payment.tenant_id,
    )
    return payment


@transaction.atomic
def allocate_payment(payment: Payment, allocations: list[dict]) -> list[PaymentAllocation]:
    """
    تخصیص پرداخت به صورتحساب‌ها.

    بخش ۷.۸: «مجموع تخصیص‌های پرداخت از مبلغ پرداخت موفق بیشتر نمی‌شود و
    مجموع تخصیص به صورتحساب از مانده آن تجاوز نمی‌کند.»
    """
    if payment.status != PaymentStatus.SUCCEEDED:
        raise BusinessRuleViolation(
            code="PAYMENT_NOT_SUCCEEDED",
            message="فقط دریافت موفق قابل تخصیص است.",
        )

    requested_total = sum(row["amount"] for row in allocations)
    if requested_total > payment.unallocated_amount:
        raise BusinessRuleViolation(
            code="ALLOCATION_EXCEEDS_PAYMENT",
            message=(
                f"مجموع تخصیص ({requested_total:,}) از مبلغ تخصیص‌نیافته "
                f"({payment.unallocated_amount:,}) بیشتر است."
            ),
            field_errors=[{"field": "allocations", "reason": "exceeds_payment"}],
        )

    created: list[PaymentAllocation] = []
    for row in allocations:
        invoice = Invoice.objects.select_for_update().get(pk=row["invoice"])
        amount = row["amount"]

        if amount <= 0:
            raise BusinessRuleViolation(
                code="ALLOCATION_AMOUNT_INVALID",
                message="مبلغ تخصیص باید بزرگ‌تر از صفر باشد.",
            )
        if amount > invoice.balance:
            raise BusinessRuleViolation(
                code="ALLOCATION_EXCEEDS_INVOICE_BALANCE",
                message=(
                    f"مبلغ تخصیص ({amount:,}) از مانده صورتحساب "
                    f"{invoice.invoice_no} ({invoice.balance:,}) بیشتر است."
                ),
                field_errors=[{"field": "invoice", "reason": "exceeds_balance"}],
            )

        allocation, created_flag = PaymentAllocation.objects.get_or_create(
            payment=payment,
            invoice=invoice,
            defaults={"tenant_id": payment.tenant_id, "amount": amount},
        )
        if not created_flag:
            allocation.amount += amount
            allocation.save(update_fields=["amount"])

        refresh_invoice_payment_status(invoice)
        post_allocation_journal(payment, amount, invoice)
        created.append(allocation)

    return created


@transaction.atomic
def void_payment(payment: Payment, reason: str) -> Payment:
    """ابطال کنترل‌شده دریافت با سند برگشتی."""
    if payment.status != PaymentStatus.SUCCEEDED:
        raise InvalidStateTransition(
            entity="دریافت", current=payment.status, action="void"
        )

    invoices = [allocation.invoice for allocation in payment.allocations.all()]
    payment.allocations.all().delete()

    payment.status = PaymentStatus.VOIDED
    payment.void_reason = reason
    payment.save(update_fields=["status", "void_reason"])

    for invoice in invoices:
        refresh_invoice_payment_status(invoice)

    entry = JournalEntry.objects.filter(
        source_type=JournalSourceType.PAYMENT,
        source_id=payment.id,
        status=JournalStatus.POSTED,
    ).first()
    if entry:
        reverse_journal_entry(entry, reason=f"ابطال دریافت: {reason}")

    return payment


@transaction.atomic
def approve_refund(refund: Refund, approver_user_id) -> Refund:
    """
    تأیید استرداد با کنترل تفکیک وظایف.

    بخش ۳.۲: «کاربر ایجادکننده استرداد یا سند مالی نباید تأییدکننده نهایی
    همان مورد باشد.»
    """
    if refund.approval_status != ApprovalState.PENDING:
        raise InvalidStateTransition(
            entity="استرداد", current=refund.approval_status, action="approve"
        )
    if refund.requested_by_id and refund.requested_by_id == approver_user_id:
        raise BusinessRuleViolation(
            code="SEGREGATION_OF_DUTIES",
            message="درخواست‌دهنده استرداد نمی‌تواند تأییدکننده همان استرداد باشد.",
            status_code=403,
        )
    if refund.amount > refund.payment.amount:
        raise BusinessRuleViolation(
            code="REFUND_EXCEEDS_PAYMENT",
            message="مبلغ استرداد از مبلغ دریافت بیشتر است.",
            field_errors=[{"field": "amount", "reason": "exceeds_payment"}],
        )

    refund.approval_status = ApprovalState.APPROVED
    refund.approved_by_id = approver_user_id
    refund.approved_at = timezone.now()
    refund.status = RefundStatus.APPROVED
    refund.save()
    return refund


@transaction.atomic
def complete_refund(refund: Refund) -> Refund:
    """تکمیل استرداد و ثبت اثر حسابداری معکوس."""
    if refund.status != RefundStatus.APPROVED:
        raise InvalidStateTransition(
            entity="استرداد", current=refund.status, action="complete"
        )

    refund.status = RefundStatus.COMPLETED
    refund.completed_at = timezone.now()
    refund.save(update_fields=["status", "completed_at"])

    payment = refund.payment
    total_refunded = (
        payment.refunds.filter(status=RefundStatus.COMPLETED).aggregate(
            total=Sum("amount")
        )["total"]
        or 0
    )
    payment.status = (
        PaymentStatus.REFUNDED
        if total_refunded >= payment.amount
        else PaymentStatus.PARTIALLY_REFUNDED
    )
    payment.save(update_fields=["status"])

    post_refund_journal(refund)

    from apps.workflow.services import publish_event

    publish_event(
        aggregate_type="finance.Refund",
        aggregate_id=refund.id,
        event_type="RefundCompleted",
        payload={
            "refundId": str(refund.id),
            "paymentId": str(payment.id),
            "amount": refund.amount,
        },
        tenant_id=refund.tenant_id,
    )
    return refund


# ---------------------------------------------------------------------------
# حسابداری دوبل
# ---------------------------------------------------------------------------
def get_open_fiscal_year(school, on_date: date | None = None) -> FiscalYear:
    on_date = on_date or timezone.localdate()
    fiscal_year = FiscalYear.objects.filter(
        school=school, starts_on__lte=on_date, ends_on__gte=on_date
    ).first()
    if fiscal_year is None:
        raise BusinessRuleViolation(
            code="FISCAL_YEAR_NOT_FOUND",
            message=f"برای تاریخ {on_date} سال مالی تعریف نشده است.",
        )
    if not fiscal_year.is_open:
        raise PeriodClosed(fiscal_year.title)
    return fiscal_year


def _resolve_account(school, code: str) -> Account | None:
    return Account.objects.filter(
        school=school, code=code, allows_posting=True, is_active=True
    ).first()


@transaction.atomic
def create_journal_entry(
    *,
    fiscal_year: FiscalYear,
    entry_date: date,
    description: str,
    lines: list[dict],
    source_type: str = JournalSourceType.MANUAL,
    source_id=None,
    tenant_id=None,
) -> JournalEntry:
    """
    ایجاد سند حسابداری در وضعیت پیش‌نویس با اعتبارسنجی خطوط.

    هر خط: {"account": Account|uuid, "debit": int, "credit": int,
             "cost_center": uuid|None, "description": str}
    """
    if not fiscal_year.is_open:
        raise PeriodClosed(fiscal_year.title)

    entry = JournalEntry.objects.create(
        tenant_id=tenant_id or fiscal_year.tenant_id,
        fiscal_year=fiscal_year,
        entry_no=generate_entry_no(tenant_id or fiscal_year.tenant_id),
        entry_date=entry_date,
        description=description,
        source_type=source_type,
        source_id=source_id,
        status=JournalStatus.DRAFT,
    )

    for index, line in enumerate(lines, start=1):
        account = line["account"]
        if not isinstance(account, Account):
            account = Account.objects.get(pk=account)

        if not account.allows_posting:
            raise BusinessRuleViolation(
                code="ACCOUNT_NOT_POSTABLE",
                message=(
                    f"حساب «{account.code} — {account.title}» گروه است و ثبت "
                    "مستقیم روی آن مجاز نیست."
                ),
                field_errors=[{"field": f"lines[{index}].account", "reason": "group_account"}],
            )

        JournalLine.objects.create(
            tenant_id=entry.tenant_id,
            journal_entry=entry,
            account=account,
            cost_center_id=line.get("cost_center"),
            debit_amount=line.get("debit", 0),
            credit_amount=line.get("credit", 0),
            description=line.get("description", ""),
            line_no=index,
        )

    return entry


@transaction.atomic
def post_journal_entry(entry: JournalEntry, actor_user_id=None) -> JournalEntry:
    """
    قطعی‌کردن سند.

    بخش ۷.۸: «مجموع بدهکار و بستانکار هر سند قطعی برابر است و هر دو نمی‌توانند
    صفر باشند.»
    """
    if entry.status == JournalStatus.POSTED:
        return entry
    if entry.status not in {JournalStatus.DRAFT, JournalStatus.VALIDATED}:
        raise InvalidStateTransition(
            entity="سند حسابداری", current=entry.status, action="post"
        )
    if not entry.fiscal_year.is_open:
        raise PeriodClosed(entry.fiscal_year.title)

    debit = entry.total_debit
    credit = entry.total_credit
    if debit != credit or debit == 0:
        raise BusinessRuleViolation(
            code="JOURNAL_NOT_BALANCED",
            message=(
                f"سند متوازن نیست: جمع بدهکار {debit:,} و جمع بستانکار "
                f"{credit:,} است."
            ),
            field_errors=[{"field": "lines", "reason": "not_balanced"}],
        )

    entry.status = JournalStatus.POSTED
    entry.posted_at = timezone.now()
    entry.posted_by_id = actor_user_id
    entry.save(update_fields=["status", "posted_at", "posted_by_id"])
    return entry


@transaction.atomic
def reverse_journal_entry(entry: JournalEntry, reason: str, actor_user_id=None) -> JournalEntry:
    """
    ثبت سند برگشتی.

    بخش ۱۰.۶: «سند Posted ویرایش یا حذف نمی‌شود. Reversed یعنی سند جدیدی با
    خطوط معکوس و ارجاع به سند اصلی قطعی شده است.»
    """
    if entry.status != JournalStatus.POSTED:
        raise InvalidStateTransition(
            entity="سند حسابداری", current=entry.status, action="reverse"
        )

    fiscal_year = entry.fiscal_year
    if not fiscal_year.is_open:
        # اصلاح در دوره باز انجام می‌شود (بخش ۷.۸)
        fiscal_year = FiscalYear.objects.filter(
            school=fiscal_year.school, status=FiscalYearStatus.OPEN
        ).order_by("-starts_on").first()
        if fiscal_year is None:
            raise PeriodClosed(entry.fiscal_year.title)

    reversal = JournalEntry.objects.create(
        tenant_id=entry.tenant_id,
        fiscal_year=fiscal_year,
        entry_no=generate_entry_no(entry.tenant_id),
        entry_date=timezone.localdate(),
        description=f"برگشت سند {entry.entry_no}: {reason}",
        source_type=entry.source_type,
        source_id=entry.source_id,
        status=JournalStatus.DRAFT,
        reversal_of=entry,
    )
    for line in entry.lines.all():
        JournalLine.objects.create(
            tenant_id=entry.tenant_id,
            journal_entry=reversal,
            account=line.account,
            cost_center=line.cost_center,
            debit_amount=line.credit_amount,
            credit_amount=line.debit_amount,
            description=f"برگشت: {line.description}",
            line_no=line.line_no,
        )

    post_journal_entry(reversal, actor_user_id)

    entry.status = JournalStatus.REVERSED
    entry.save(update_fields=["status"])
    return reversal


# ---------------------------------------------------------------------------
# اسناد خودکار
# ---------------------------------------------------------------------------
#: کدهای پیش‌فرض حساب — قابل پیکربندی در استقرار واقعی
DEFAULT_ACCOUNTS = {
    "RECEIVABLE": "1131",   # حساب دریافتنی دانش‌آموزان
    "REVENUE": "4101",      # درآمد شهریه
    "CASH": "1101",         # صندوق
    "BANK": "1102",         # بانک
    "PREPAYMENT": "2131",   # پیش‌دریافت شهریه (بدهی)
}


def resolve_payment_school(payment: Payment):
    """
    مدرسه مرتبط با یک دریافت را پیدا می‌کند.

    ترتیب: فیلد صریح `school` → حساب بانکی → اولین صورتحساب تخصیص‌یافته.
    """
    if payment.school_id:
        return payment.school
    if payment.bank_account_id:
        return payment.bank_account.school
    allocation = payment.allocations.select_related(
        "invoice__agreement__enrollment__campus__school"
    ).first()
    if allocation:
        return allocation.invoice.agreement.enrollment.campus.school
    return None


def post_invoice_journal(invoice: Invoice) -> JournalEntry | None:
    """
    سند تعهدی صدور صورتحساب: بدهکار حساب دریافتنی / بستانکار درآمد.

    اگر کدینگ حساب پیکربندی نشده باشد، سند ثبت نمی‌شود و عملیات اصلی متوقف
    نمی‌گردد (سند بعداً از مسیر اصلاح قابل ثبت است).
    """
    school = invoice.agreement.enrollment.campus.school
    receivable = _resolve_account(school, DEFAULT_ACCOUNTS["RECEIVABLE"])
    revenue = _resolve_account(school, DEFAULT_ACCOUNTS["REVENUE"])
    if not (receivable and revenue):
        return None

    fiscal_year = get_open_fiscal_year(school, invoice.issue_date)
    entry = create_journal_entry(
        fiscal_year=fiscal_year,
        entry_date=invoice.issue_date,
        description=f"صدور صورتحساب {invoice.invoice_no}",
        source_type=JournalSourceType.INVOICE,
        source_id=invoice.id,
        tenant_id=invoice.tenant_id,
        lines=[
            {
                "account": receivable,
                "debit": invoice.total_amount,
                "credit": 0,
                "description": f"مطالبه از {invoice.agreement.enrollment.student.full_name}",
            },
            {
                "account": revenue,
                "debit": 0,
                "credit": invoice.total_amount,
                "description": "درآمد شهریه",
            },
        ],
    )
    return post_journal_entry(entry)


def post_payment_journal(payment: Payment) -> JournalEntry | None:
    """
    سند دریافت.

    وجه دریافتی تا پیش از تخصیص، «پیش‌دریافت» (بدهی) است و پس از تخصیص به
    صورتحساب، به حساب دریافتنی منتقل می‌شود (بخش ۷.۸ — پیش‌دریافت و شناسایی
    درآمد):

        بدهکار: صندوق/بانک
        بستانکار: پیش‌دریافت شهریه
    """
    school = resolve_payment_school(payment)
    if school is None:
        return None

    cash_code = (
        DEFAULT_ACCOUNTS["BANK"]
        if payment.method in {"TRANSFER", "ONLINE_GATEWAY", "POS"}
        else DEFAULT_ACCOUNTS["CASH"]
    )
    cash_account = _resolve_account(school, cash_code)
    prepayment = _resolve_account(school, DEFAULT_ACCOUNTS["PREPAYMENT"])
    if not (cash_account and prepayment):
        return None

    fiscal_year = get_open_fiscal_year(school, payment.received_at.date())
    entry = create_journal_entry(
        fiscal_year=fiscal_year,
        entry_date=payment.received_at.date(),
        description=f"دریافت {payment.payment_no}",
        source_type=JournalSourceType.PAYMENT,
        source_id=payment.id,
        tenant_id=payment.tenant_id,
        lines=[
            {
                "account": cash_account,
                "debit": payment.amount,
                "credit": 0,
                "description": f"دریافت از {payment.payer_person.full_name}",
            },
            {
                "account": prepayment,
                "debit": 0,
                "credit": payment.amount,
                "description": "پیش‌دریافت تا زمان تخصیص به صورتحساب",
            },
        ],
    )
    return post_journal_entry(entry)


def post_allocation_journal(payment: Payment, amount: int, invoice: Invoice):
    """
    سند تخصیص پیش‌دریافت به صورتحساب.

        بدهکار: پیش‌دریافت شهریه
        بستانکار: حساب دریافتنی
    """
    school = resolve_payment_school(payment)
    if school is None:
        return None

    prepayment = _resolve_account(school, DEFAULT_ACCOUNTS["PREPAYMENT"])
    receivable = _resolve_account(school, DEFAULT_ACCOUNTS["RECEIVABLE"])
    if not (prepayment and receivable):
        return None

    fiscal_year = get_open_fiscal_year(school)
    entry = create_journal_entry(
        fiscal_year=fiscal_year,
        entry_date=timezone.localdate(),
        description=(
            f"تخصیص دریافت {payment.payment_no} به صورتحساب {invoice.invoice_no}"
        ),
        source_type=JournalSourceType.PAYMENT,
        source_id=payment.id,
        tenant_id=payment.tenant_id,
        lines=[
            {"account": prepayment, "debit": amount, "credit": 0},
            {"account": receivable, "debit": 0, "credit": amount},
        ],
    )
    return post_journal_entry(entry)


def post_refund_journal(refund: Refund) -> JournalEntry | None:
    """سند استرداد: معکوس سند دریافت به میزان مبلغ مسترد."""
    entry = JournalEntry.objects.filter(
        source_type=JournalSourceType.PAYMENT,
        source_id=refund.payment_id,
        status=JournalStatus.POSTED,
    ).first()
    if entry is None:
        return None

    school = entry.fiscal_year.school
    cash_account = _resolve_account(school, DEFAULT_ACCOUNTS["CASH"])
    receivable = _resolve_account(school, DEFAULT_ACCOUNTS["RECEIVABLE"])
    if not (cash_account and receivable):
        return None


    fiscal_year = get_open_fiscal_year(school)
    reversal = create_journal_entry(
        fiscal_year=fiscal_year,
        entry_date=timezone.localdate(),
        description=f"استرداد {refund.refund_no}",
        source_type=JournalSourceType.REFUND,
        source_id=refund.id,
        tenant_id=refund.tenant_id,
        lines=[
            {"account": receivable, "debit": refund.amount, "credit": 0},
            {"account": cash_account, "debit": 0, "credit": refund.amount},
        ],
    )
    return post_journal_entry(reversal)


@transaction.atomic
def close_fiscal_year(fiscal_year: FiscalYear, actor_user_id) -> FiscalYear:
    """بستن دوره مالی پس از کنترل اسناد پیش‌نویس."""
    pending = fiscal_year.journal_entries.filter(
        status__in=[JournalStatus.DRAFT, JournalStatus.VALIDATED]
    ).count()
    if pending:
        raise BusinessRuleViolation(
            code="FISCAL_YEAR_HAS_DRAFT_ENTRIES",
            message=f"{pending} سند هنوز قطعی نشده است؛ ابتدا تعیین تکلیف کنید.",
        )

    fiscal_year.status = FiscalYearStatus.CLOSED
    fiscal_year.closed_at = timezone.now()
    fiscal_year.closed_by_id = actor_user_id
    fiscal_year.save(update_fields=["status", "closed_at", "closed_by_id"])

    from apps.workflow.services import publish_event

    publish_event(
        aggregate_type="finance.FiscalYear",
        aggregate_id=fiscal_year.id,
        event_type="PeriodClosed",
        payload={"fiscalYearId": str(fiscal_year.id), "title": fiscal_year.title},
        tenant_id=fiscal_year.tenant_id,
    )
    return fiscal_year


def account_ledger(account: Account, date_from=None, date_to=None) -> dict:
    """
    گردش حساب یک حساب در بازه (بخش ۱۲.۲ — Query «گردش حساب»).

    پیاده‌سازی به :mod:`apps.finance.reports` منتقل شده تا دفتر کل، تراز
    آزمایشی و گردش تک‌حساب از یک منطق محاسبه مشترک تغذیه شوند. این نام برای
    فراخوانی‌های موجود حفظ شده است.
    """
    from apps.finance import reports

    return reports.account_ledger(account, date_from, date_to)
