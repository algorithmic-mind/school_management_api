"""شمارش‌های ماژول تدارکات، انبار و اموال."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class VendorStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("فعال")
    SUSPENDED = "SUSPENDED", _("تعلیق")
    BLACKLISTED = "BLACKLISTED", _("لیست سیاه")
    INACTIVE = "INACTIVE", _("غیرفعال")


class StockDocumentType(models.TextChoices):
    """
    انواع سند انبار.

    علامت حرکت موجودی بر اساس نوع سند تعیین می‌شود.
    """

    RECEIPT = "RECEIPT", _("رسید")
    ISSUE = "ISSUE", _("حواله مصرف")
    TRANSFER_OUT = "TRANSFER_OUT", _("انتقال خروج")
    TRANSFER_IN = "TRANSFER_IN", _("انتقال ورود")
    RETURN_TO_VENDOR = "RETURN_TO_VENDOR", _("برگشت به فروشنده")
    RETURN_FROM_USE = "RETURN_FROM_USE", _("برگشت از مصرف")
    ADJUSTMENT_IN = "ADJUSTMENT_IN", _("تعدیل مثبت")
    ADJUSTMENT_OUT = "ADJUSTMENT_OUT", _("تعدیل منفی")
    COUNT = "COUNT", _("انبارگردانی")


#: اسنادی که موجودی را افزایش می‌دهند
INBOUND_DOCUMENT_TYPES = {
    StockDocumentType.RECEIPT,
    StockDocumentType.TRANSFER_IN,
    StockDocumentType.RETURN_FROM_USE,
    StockDocumentType.ADJUSTMENT_IN,
}


class StockDocumentStatus(models.TextChoices):
    DRAFT = "DRAFT", _("پیش‌نویس")
    CONFIRMED = "CONFIRMED", _("قطعی")
    CANCELLED = "CANCELLED", _("لغوشده")
    REVERSED = "REVERSED", _("برگشت‌خورده")


class PurchaseRequestStatus(models.TextChoices):
    """ماشین حالت درخواست خرید — بخش ۱۰.۷ سند تحلیل."""

    DRAFT = "DRAFT", _("پیش‌نویس")
    SUBMITTED = "SUBMITTED", _("ارسال‌شده")
    BUDGET_CHECK = "BUDGET_CHECK", _("کنترل بودجه")
    APPROVAL = "APPROVAL", _("در انتظار تأیید")
    APPROVED = "APPROVED", _("تأییدشده")
    REJECTED = "REJECTED", _("ردشده")
    SOURCING = "SOURCING", _("در حال استعلام")
    ORDERED = "ORDERED", _("سفارش‌شده")
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED", _("دریافت جزئی")
    RECEIVED = "RECEIVED", _("دریافت کامل")
    CLOSED = "CLOSED", _("بسته")
    CANCELLED = "CANCELLED", _("لغوشده")


class PurchaseOrderStatus(models.TextChoices):
    DRAFT = "DRAFT", _("پیش‌نویس")
    ISSUED = "ISSUED", _("صادرشده")
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED", _("دریافت جزئی")
    RECEIVED = "RECEIVED", _("دریافت کامل")
    CLOSED = "CLOSED", _("بسته")
    CANCELLED = "CANCELLED", _("لغوشده")


class QualityStatus(models.TextChoices):
    PENDING = "PENDING", _("در انتظار کنترل کیفیت")
    ACCEPTED = "ACCEPTED", _("پذیرفته‌شده")
    PARTIALLY_ACCEPTED = "PARTIALLY_ACCEPTED", _("پذیرش جزئی")
    REJECTED = "REJECTED", _("مردود")


class ReceiptStatus(models.TextChoices):
    PROVISIONAL = "PROVISIONAL", _("رسید موقت")
    FINAL = "FINAL", _("رسید قطعی")
    CANCELLED = "CANCELLED", _("لغوشده")


class AssetLifecycleStatus(models.TextChoices):
    """ماشین حالت مال سرمایه‌ای — بخش ۱۰.۸ سند تحلیل."""

    REGISTERED = "REGISTERED", _("ثبت‌شده")
    IN_STOCK = "IN_STOCK", _("موجود در انبار")
    ASSIGNED = "ASSIGNED", _("تحویل‌شده")
    UNDER_MAINTENANCE = "UNDER_MAINTENANCE", _("در تعمیر")
    DAMAGED = "DAMAGED", _("آسیب‌دیده")
    LOST = "LOST", _("مفقود")
    RECOVERED = "RECOVERED", _("بازیافت‌شده")
    RETIRED = "RETIRED", _("بازنشسته")
    DISPOSED = "DISPOSED", _("اسقاط‌شده")


class AssetCondition(models.TextChoices):
    NEW = "NEW", _("نو")
    GOOD = "GOOD", _("سالم")
    FAIR = "FAIR", _("قابل قبول")
    POOR = "POOR", _("نامناسب")
    BROKEN = "BROKEN", _("خراب")


class AssigneeType(models.TextChoices):
    EMPLOYEE = "EMPLOYEE", _("کارمند")
    ROOM = "ROOM", _("اتاق")
    ORG_UNIT = "ORG_UNIT", _("واحد سازمانی")
    CLASS_GROUP = "CLASS_GROUP", _("کلاس")


class MaintenanceType(models.TextChoices):
    PREVENTIVE = "PREVENTIVE", _("پیشگیرانه")
    CORRECTIVE = "CORRECTIVE", _("اصلاحی")
    EMERGENCY = "EMERGENCY", _("اضطراری")
    INSPECTION = "INSPECTION", _("بازرسی")


class MaintenanceStatus(models.TextChoices):
    OPEN = "OPEN", _("باز")
    IN_PROGRESS = "IN_PROGRESS", _("در حال انجام")
    COMPLETED = "COMPLETED", _("انجام‌شده")
    CANCELLED = "CANCELLED", _("لغوشده")
