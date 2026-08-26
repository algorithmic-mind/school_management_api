"""شمارش‌های مشترک بین ماژول‌ها."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Gender(models.TextChoices):
    MALE = "MALE", _("مرد")
    FEMALE = "FEMALE", _("زن")
    OTHER = "OTHER", _("سایر")
    UNDISCLOSED = "UNDISCLOSED", _("اعلام‌نشده")


class ContactType(models.TextChoices):
    MOBILE = "MOBILE", _("تلفن همراه")
    PHONE = "PHONE", _("تلفن ثابت")
    EMAIL = "EMAIL", _("پست الکترونیک")
    EMERGENCY = "EMERGENCY", _("تماس اضطراری")


class AddressType(models.TextChoices):
    HOME = "HOME", _("محل سکونت")
    WORK = "WORK", _("محل کار")
    BILLING = "BILLING", _("نشانی صورتحساب")
    OTHER = "OTHER", _("سایر")


class DataClassification(models.TextChoices):
    """طبقه‌بندی داده — بخش ۱۵.۲ سند تحلیل."""

    PUBLIC = "PUBLIC", _("عمومی")
    INTERNAL = "INTERNAL", _("داخلی")
    CONFIDENTIAL = "CONFIDENTIAL", _("محرمانه")
    RESTRICTED = "RESTRICTED", _("بسیار حساس")


class ApprovalDecision(models.TextChoices):
    PENDING = "PENDING", _("در انتظار")
    APPROVED = "APPROVED", _("تأیید")
    REJECTED = "REJECTED", _("رد")
    RETURNED = "RETURNED", _("بازگشت برای اصلاح")
    DELEGATED = "DELEGATED", _("ارجاع به جانشین")


class NotificationChannel(models.TextChoices):
    IN_APP = "IN_APP", _("درون‌برنامه‌ای")
    SMS = "SMS", _("پیامک")
    EMAIL = "EMAIL", _("ایمیل")
    PUSH = "PUSH", _("اعلان موبایل")


class Weekday(models.IntegerChoices):
    """روزهای هفته با شروع از شنبه (تقویم ایران)."""

    SATURDAY = 0, _("شنبه")
    SUNDAY = 1, _("یکشنبه")
    MONDAY = 2, _("دوشنبه")
    TUESDAY = 3, _("سه‌شنبه")
    WEDNESDAY = 4, _("چهارشنبه")
    THURSDAY = 5, _("پنجشنبه")
    FRIDAY = 6, _("جمعه")


class Currency(models.TextChoices):
    IRR = "IRR", _("ریال ایران")
    IRT = "IRT", _("تومان ایران")
    USD = "USD", _("دلار آمریکا")
    EUR = "EUR", _("یورو")


class VerificationStatus(models.TextChoices):
    PENDING = "PENDING", _("در انتظار بررسی")
    VERIFIED = "VERIFIED", _("تأییدشده")
    REJECTED = "REJECTED", _("ردشده")
    EXPIRED = "EXPIRED", _("منقضی")
