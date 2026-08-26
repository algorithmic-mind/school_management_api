"""شمارش‌های ماژول گردش کار و ارتباطات."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class ApprovalStatus(models.TextChoices):
    PENDING = "PENDING", _("در جریان")
    APPROVED = "APPROVED", _("تأییدشده")
    REJECTED = "REJECTED", _("ردشده")
    CANCELLED = "CANCELLED", _("لغوشده")
    EXPIRED = "EXPIRED", _("منقضی")


class NotificationStatus(models.TextChoices):
    QUEUED = "QUEUED", _("در صف")
    SENDING = "SENDING", _("در حال ارسال")
    SENT = "SENT", _("ارسال‌شده")
    DELIVERED = "DELIVERED", _("تحویل‌شده")
    FAILED = "FAILED", _("ناموفق")
    CANCELLED = "CANCELLED", _("لغوشده")
    READ = "READ", _("خوانده‌شده")


class NotificationPriority(models.TextChoices):
    TRANSACTIONAL = "TRANSACTIONAL", _("تراکنشی")
    OPERATIONAL = "OPERATIONAL", _("عملیاتی")
    PROMOTIONAL = "PROMOTIONAL", _("اطلاع‌رسانی عمومی")
    EMERGENCY = "EMERGENCY", _("اضطراری")


class DeliveryResult(models.TextChoices):
    SUCCESS = "SUCCESS", _("موفق")
    FAILED = "FAILED", _("ناموفق")
    RETRYING = "RETRYING", _("در حال تلاش مجدد")
    REJECTED = "REJECTED", _("رد شده توسط ارائه‌دهنده")


class ScanStatus(models.TextChoices):
    """
    وضعیت اسکن بدافزار فایل.

    بخش ۷.۱۱: «فایل تا قبل از تکمیل اسکن بدافزار در دسترس کاربر نهایی قرار
    نمی‌گیرد.»
    """

    PENDING = "PENDING", _("در انتظار اسکن")
    CLEAN = "CLEAN", _("سالم")
    INFECTED = "INFECTED", _("آلوده")
    FAILED = "FAILED", _("اسکن ناموفق")


class TicketStatus(models.TextChoices):
    OPEN = "OPEN", _("باز")
    IN_PROGRESS = "IN_PROGRESS", _("در حال بررسی")
    WAITING_REQUESTER = "WAITING_REQUESTER", _("در انتظار پاسخ درخواست‌کننده")
    RESOLVED = "RESOLVED", _("حل‌شده")
    CLOSED = "CLOSED", _("بسته")


class TicketPriority(models.TextChoices):
    LOW = "LOW", _("کم")
    NORMAL = "NORMAL", _("عادی")
    HIGH = "HIGH", _("زیاد")
    URGENT = "URGENT", _("فوری")


class IntegrationDirection(models.TextChoices):
    INBOUND = "INBOUND", _("ورودی")
    OUTBOUND = "OUTBOUND", _("خروجی")


class IntegrationStatus(models.TextChoices):
    RECEIVED = "RECEIVED", _("دریافت‌شده")
    PROCESSED = "PROCESSED", _("پردازش‌شده")
    FAILED = "FAILED", _("ناموفق")
    DEAD_LETTER = "DEAD_LETTER", _("Dead Letter")
