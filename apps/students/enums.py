"""شمارش‌های ماژول امور دانش‌آموزان."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class AdmissionStatus(models.TextChoices):
    """ماشین حالت درخواست پذیرش — بخش ۱۰.۱ سند تحلیل."""

    DRAFT = "DRAFT", _("پیش‌نویس")
    SUBMITTED = "SUBMITTED", _("ارسال‌شده")
    INCOMPLETE = "INCOMPLETE", _("نقص مدارک")
    UNDER_REVIEW = "UNDER_REVIEW", _("در حال بررسی")
    WAITLISTED = "WAITLISTED", _("فهرست انتظار")
    CONDITIONALLY_ACCEPTED = "CONDITIONALLY_ACCEPTED", _("پذیرش مشروط")
    ACCEPTED = "ACCEPTED", _("پذیرفته‌شده")
    REJECTED = "REJECTED", _("ردشده")
    CONVERTED = "CONVERTED", _("تبدیل به ثبت‌نام")
    WITHDRAWN = "WITHDRAWN", _("انصراف")


class EnrollmentStatus(models.TextChoices):
    """ماشین حالت ثبت‌نام تحصیلی — بخش ۱۰.۲ سند تحلیل."""

    PENDING_DOCUMENTS = "PENDING_DOCUMENTS", _("در انتظار مدارک")
    PENDING_FINANCE = "PENDING_FINANCE", _("در انتظار تسویه مالی")
    PENDING_PLACEMENT = "PENDING_PLACEMENT", _("در انتظار تخصیص کلاس")
    ACTIVE = "ACTIVE", _("فعال")
    SUSPENDED = "SUSPENDED", _("تعلیق")
    TRANSFERRED = "TRANSFERRED", _("انتقالی")
    WITHDRAWN = "WITHDRAWN", _("ترک تحصیل")
    COMPLETED = "COMPLETED", _("پایان سال")
    GRADUATED = "GRADUATED", _("فارغ‌التحصیل")
    CANCELLED = "CANCELLED", _("لغوشده")


class StudentStatus(models.TextChoices):
    PROSPECTIVE = "PROSPECTIVE", _("متقاضی")
    ACTIVE = "ACTIVE", _("در حال تحصیل")
    SUSPENDED = "SUSPENDED", _("تعلیق")
    TRANSFERRED_OUT = "TRANSFERRED_OUT", _("انتقال به مدرسه دیگر")
    WITHDRAWN = "WITHDRAWN", _("ترک تحصیل")
    GRADUATED = "GRADUATED", _("فارغ‌التحصیل")


class ClassMembershipStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("فعال")
    TRANSFERRED = "TRANSFERRED", _("منتقل‌شده")
    ENDED = "ENDED", _("پایان‌یافته")


class RelationshipType(models.TextChoices):
    FATHER = "FATHER", _("پدر")
    MOTHER = "MOTHER", _("مادر")
    STEP_PARENT = "STEP_PARENT", _("ناپدری/نامادری")
    GRANDPARENT = "GRANDPARENT", _("پدربزرگ/مادربزرگ")
    SIBLING = "SIBLING", _("خواهر/برادر")
    LEGAL_GUARDIAN = "LEGAL_GUARDIAN", _("قیم قانونی")
    OTHER = "OTHER", _("سایر")


class ConsentType(models.TextChoices):
    """انواع رضایت‌نامه (بخش ۴.۲)."""

    PHOTO = "PHOTO", _("انتشار تصویر")
    FIELD_TRIP = "FIELD_TRIP", _("سفر و اردو")
    EMERGENCY_MEDICAL = "EMERGENCY_MEDICAL", _("درمان اضطراری")
    CONTENT_PUBLISH = "CONTENT_PUBLISH", _("انتشار محتوا")
    TRANSPORT = "TRANSPORT", _("استفاده از سرویس")
    DATA_PROCESSING = "DATA_PROCESSING", _("پردازش داده")


class ConsentStatus(models.TextChoices):
    GRANTED = "GRANTED", _("اعطاشده")
    REVOKED = "REVOKED", _("لغوشده")
    EXPIRED = "EXPIRED", _("منقضی")


class TransferType(models.TextChoices):
    INTERNAL_CLASS = "INTERNAL_CLASS", _("انتقال بین کلاس")
    INTERNAL_CAMPUS = "INTERNAL_CAMPUS", _("انتقال بین شعبه")
    EXTERNAL_OUT = "EXTERNAL_OUT", _("انتقال به مدرسه دیگر")
    EXTERNAL_IN = "EXTERNAL_IN", _("انتقال از مدرسه دیگر")


class PromotionDecision(models.TextChoices):
    """نتیجه ارتقای پایه (بخش ۱۱.۲)."""

    PROMOTED = "PROMOTED", _("ارتقا")
    REPEATED = "REPEATED", _("تکرار پایه")
    CONDITIONAL = "CONDITIONAL", _("مشروط")
    COUNCIL_REVIEW = "COUNCIL_REVIEW", _("نیازمند تصمیم شورا")
    TRANSFERRED = "TRANSFERRED", _("انتقال")
    GRADUATED = "GRADUATED", _("فارغ‌التحصیل")
