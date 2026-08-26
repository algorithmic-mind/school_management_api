"""شمارش‌های ماژول منابع انسانی."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class EmployeeStatus(models.TextChoices):
    ONBOARDING = "ONBOARDING", _("در حال جذب")
    ACTIVE = "ACTIVE", _("شاغل")
    ON_LEAVE = "ON_LEAVE", _("در مرخصی")
    SUSPENDED = "SUSPENDED", _("تعلیق")
    TERMINATED = "TERMINATED", _("پایان همکاری")


class ContractType(models.TextChoices):
    PERMANENT = "PERMANENT", _("رسمی/دائم")
    FIXED_TERM = "FIXED_TERM", _("مدت معین")
    HOURLY = "HOURLY", _("ساعتی/حق‌التدریس")
    CONTRACTOR = "CONTRACTOR", _("پیمانکاری")
    INTERN = "INTERN", _("کارآموز")


class ContractStatus(models.TextChoices):
    DRAFT = "DRAFT", _("پیش‌نویس")
    ACTIVE = "ACTIVE", _("جاری")
    EXPIRED = "EXPIRED", _("منقضی")
    TERMINATED = "TERMINATED", _("فسخ‌شده")


class PositionType(models.TextChoices):
    TEACHING = "TEACHING", _("آموزشی")
    ADMINISTRATIVE = "ADMINISTRATIVE", _("اداری")
    MANAGEMENT = "MANAGEMENT", _("مدیریتی")
    SUPPORT = "SUPPORT", _("پشتیبانی")
    HEALTH = "HEALTH", _("بهداشت و درمان")
    COUNSELING = "COUNSELING", _("مشاوره")


class TeachingResponsibility(models.TextChoices):
    PRIMARY = "PRIMARY", _("مدرس اصلی")
    ASSISTANT = "ASSISTANT", _("دستیار")
    SUBSTITUTE = "SUBSTITUTE", _("جانشین")
    CO_TEACHER = "CO_TEACHER", _("هم‌تدریس")


class QualificationStatus(models.TextChoices):
    PENDING = "PENDING", _("در انتظار تأیید")
    APPROVED = "APPROVED", _("تأییدشده")
    EXPIRED = "EXPIRED", _("منقضی")
    REVOKED = "REVOKED", _("لغوشده")


class AttendanceSource(models.TextChoices):
    DEVICE = "DEVICE", _("دستگاه تردد")
    MANUAL = "MANUAL", _("ثبت دستی")
    MOBILE = "MOBILE", _("اپلیکیشن موبایل")
    IMPORT = "IMPORT", _("ورود گروهی")


class LeaveType(models.TextChoices):
    ANNUAL = "ANNUAL", _("استحقاقی")
    SICK = "SICK", _("استعلاجی")
    UNPAID = "UNPAID", _("بدون حقوق")
    MISSION = "MISSION", _("مأموریت")
    HOURLY = "HOURLY", _("ساعتی")
    MATERNITY = "MATERNITY", _("زایمان")
    BEREAVEMENT = "BEREAVEMENT", _("فوت بستگان")


class LeaveStatus(models.TextChoices):
    DRAFT = "DRAFT", _("پیش‌نویس")
    SUBMITTED = "SUBMITTED", _("ارسال‌شده")
    APPROVED = "APPROVED", _("تأییدشده")
    REJECTED = "REJECTED", _("ردشده")
    CANCELLED = "CANCELLED", _("لغوشده")


class PayrollStatus(models.TextChoices):
    DRAFT = "DRAFT", _("پیش‌نویس")
    CALCULATED = "CALCULATED", _("محاسبه‌شده")
    APPROVED = "APPROVED", _("تأییدشده")
    PAID = "PAID", _("پرداخت‌شده")
    CLOSED = "CLOSED", _("بسته")


class PayslipItemType(models.TextChoices):
    EARNING = "EARNING", _("مزایا")
    DEDUCTION = "DEDUCTION", _("کسورات")
    EMPLOYER_COST = "EMPLOYER_COST", _("سهم کارفرما")
