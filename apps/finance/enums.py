"""شمارش‌های ماژول مالی و حسابداری."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class FiscalYearStatus(models.TextChoices):
    OPEN = "OPEN", _("باز")
    CLOSING = "CLOSING", _("در حال بستن")
    CLOSED = "CLOSED", _("بسته")


class AccountType(models.TextChoices):
    """گروه‌های اصلی کدینگ حساب."""

    ASSET = "ASSET", _("دارایی")
    LIABILITY = "LIABILITY", _("بدهی")
    EQUITY = "EQUITY", _("حقوق صاحبان سرمایه")
    REVENUE = "REVENUE", _("درآمد")
    EXPENSE = "EXPENSE", _("هزینه")


class FeeType(models.TextChoices):
    REGISTRATION = "REGISTRATION", _("ثبت‌نام")
    TUITION = "TUITION", _("شهریه آموزشی")
    TRANSPORT = "TRANSPORT", _("سرویس")
    MEAL = "MEAL", _("غذا")
    BOOK = "BOOK", _("کتاب و لوازم")
    FIELD_TRIP = "FIELD_TRIP", _("اردو")
    EXAM = "EXAM", _("آزمون")
    OPTIONAL_SERVICE = "OPTIONAL_SERVICE", _("خدمات اختیاری")
    LATE_FEE = "LATE_FEE", _("جریمه دیرکرد")
    OTHER = "OTHER", _("سایر")


class Recurrence(models.TextChoices):
    ONE_TIME = "ONE_TIME", _("یک‌بار")
    MONTHLY = "MONTHLY", _("ماهانه")
    TERM = "TERM", _("هر ترم")
    ANNUAL = "ANNUAL", _("سالانه")


class DiscountType(models.TextChoices):
    SIBLING = "SIBLING", _("تخفیف خواهر/برادر")
    SCHOLARSHIP = "SCHOLARSHIP", _("بورسیه")
    STAFF_CHILD = "STAFF_CHILD", _("فرزند کارکنان")
    FINANCIAL_AID = "FINANCIAL_AID", _("کمک‌هزینه")
    EARLY_PAYMENT = "EARLY_PAYMENT", _("تخفیف پرداخت زودهنگام")
    SPECIAL = "SPECIAL", _("تخفیف موردی")


class ApprovalState(models.TextChoices):
    PENDING = "PENDING", _("در انتظار تأیید")
    APPROVED = "APPROVED", _("تأییدشده")
    REJECTED = "REJECTED", _("ردشده")


class AgreementStatus(models.TextChoices):
    DRAFT = "DRAFT", _("پیش‌نویس")
    ACTIVE = "ACTIVE", _("جاری")
    SETTLED = "SETTLED", _("تسویه‌شده")
    CANCELLED = "CANCELLED", _("لغوشده")


class InvoiceStatus(models.TextChoices):
    """ماشین حالت صورتحساب — بخش ۱۰.۵ سند تحلیل."""

    DRAFT = "DRAFT", _("پیش‌نویس")
    ISSUED = "ISSUED", _("صادرشده")
    PARTIALLY_PAID = "PARTIALLY_PAID", _("پرداخت جزئی")
    PAID = "PAID", _("تسویه‌شده")
    OVERDUE = "OVERDUE", _("سررسید گذشته")
    DISPUTED = "DISPUTED", _("مورد اعتراض")
    CREDITED = "CREDITED", _("یادداشت بستانکار صادر شد")
    REFUNDED = "REFUNDED", _("مسترد شده")
    CANCELLED = "CANCELLED", _("لغوشده")


class PaymentMethod(models.TextChoices):
    CASH = "CASH", _("نقدی")
    POS = "POS", _("کارت‌خوان")
    TRANSFER = "TRANSFER", _("انتقال بانکی")
    CHEQUE = "CHEQUE", _("چک")
    ONLINE_GATEWAY = "ONLINE_GATEWAY", _("درگاه آنلاین")
    WALLET = "WALLET", _("کیف پول")
    MIXED = "MIXED", _("ترکیبی")


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", _("در انتظار")
    SUCCEEDED = "SUCCEEDED", _("موفق")
    FAILED = "FAILED", _("ناموفق")
    VOIDED = "VOIDED", _("ابطال‌شده")
    REFUNDED = "REFUNDED", _("مسترد شده")
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED", _("استرداد جزئی")


class RefundStatus(models.TextChoices):
    REQUESTED = "REQUESTED", _("درخواست‌شده")
    APPROVED = "APPROVED", _("تأییدشده")
    PROCESSING = "PROCESSING", _("در حال پردازش")
    COMPLETED = "COMPLETED", _("انجام‌شده")
    REJECTED = "REJECTED", _("ردشده")
    FAILED = "FAILED", _("ناموفق")


class JournalStatus(models.TextChoices):
    """ماشین حالت سند حسابداری — بخش ۱۰.۶ سند تحلیل."""

    DRAFT = "DRAFT", _("پیش‌نویس")
    VALIDATED = "VALIDATED", _("کنترل‌شده")
    POSTED = "POSTED", _("قطعی")
    REVERSED = "REVERSED", _("برگشت‌خورده")
    CANCELLED = "CANCELLED", _("لغوشده")


class JournalSourceType(models.TextChoices):
    MANUAL = "MANUAL", _("دستی")
    INVOICE = "INVOICE", _("صورتحساب")
    PAYMENT = "PAYMENT", _("دریافت")
    REFUND = "REFUND", _("استرداد")
    PAYROLL = "PAYROLL", _("حقوق")
    PURCHASE = "PURCHASE", _("خرید")
    STOCK = "STOCK", _("انبار")
    DEPRECIATION = "DEPRECIATION", _("استهلاک")


class ReconciliationStatus(models.TextChoices):
    OPEN = "OPEN", _("باز")
    MATCHED = "MATCHED", _("تطبیق‌شده")
    DISCREPANCY = "DISCREPANCY", _("دارای مغایرت")
    CLOSED = "CLOSED", _("بسته")
