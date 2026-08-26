"""شمارش‌های ماژول هویت و دسترسی."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class PersonStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("فعال")
    INACTIVE = "INACTIVE", _("غیرفعال")
    MERGED = "MERGED", _("ادغام‌شده در پرونده دیگر")
    DECEASED = "DECEASED", _("متوفی")


class UserStatus(models.TextChoices):
    """چرخه حساب کاربری (بخش ۷.۲ و ۱۵.۱)."""

    INVITED = "INVITED", _("دعوت‌شده")
    ACTIVE = "ACTIVE", _("فعال")
    LOCKED = "LOCKED", _("قفل‌شده")
    SUSPENDED = "SUSPENDED", _("تعلیق‌شده")
    DISABLED = "DISABLED", _("غیرفعال")


class RoleAssignmentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("فعال")
    EXPIRED = "EXPIRED", _("منقضی")
    REVOKED = "REVOKED", _("لغوشده")


class AccessReviewStatus(models.TextChoices):
    OPEN = "OPEN", _("باز")
    IN_PROGRESS = "IN_PROGRESS", _("در حال بررسی")
    CLOSED = "CLOSED", _("بسته")


class AccessReviewDecision(models.TextChoices):
    PENDING = "PENDING", _("در انتظار")
    KEEP = "KEEP", _("ابقا")
    REVOKE = "REVOKE", _("لغو دسترسی")
    MODIFY = "MODIFY", _("اصلاح دامنه")


class AuditAction(models.TextChoices):
    """عملیات قابل ممیزی (بخش ۱۶.۱)."""

    CREATE = "CREATE", _("ایجاد")
    UPDATE = "UPDATE", _("ویرایش")
    DELETE = "DELETE", _("حذف")
    READ_SENSITIVE = "READ_SENSITIVE", _("مشاهده داده حساس")
    LOGIN = "LOGIN", _("ورود")
    LOGIN_FAILED = "LOGIN_FAILED", _("ورود ناموفق")
    LOGOUT = "LOGOUT", _("خروج")
    PERMISSION_CHANGE = "PERMISSION_CHANGE", _("تغییر مجوز")
    STATE_TRANSITION = "STATE_TRANSITION", _("تغییر وضعیت")
    EXPORT = "EXPORT", _("خروجی‌گیری")
    BREAK_GLASS = "BREAK_GLASS", _("دسترسی اضطراری")


class MfaMethod(models.TextChoices):
    NONE = "NONE", _("بدون احراز دومرحله‌ای")
    TOTP = "TOTP", _("اپلیکیشن رمز یک‌بارمصرف")
    SMS = "SMS", _("پیامک")
    EMAIL = "EMAIL", _("ایمیل")
