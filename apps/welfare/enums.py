"""شمارش‌های ماژول خدمات دانش‌آموزی."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class BloodType(models.TextChoices):
    A_POS = "A+", "A+"
    A_NEG = "A-", "A-"
    B_POS = "B+", "B+"
    B_NEG = "B-", "B-"
    AB_POS = "AB+", "AB+"
    AB_NEG = "AB-", "AB-"
    O_POS = "O+", "O+"
    O_NEG = "O-", "O-"
    UNKNOWN = "UNKNOWN", _("نامشخص")


class ConfidentialityLevel(models.TextChoices):
    """
    سطح محرمانگی پرونده.

    بخش ۷.۱۰: «یادداشت درمانی و مشاوره‌ای از پرونده عمومی دانش‌آموز جدا و با
    مجوز فیلدی محافظت می‌شود.»
    """

    STANDARD = "STANDARD", _("عادی")
    SENSITIVE = "SENSITIVE", _("حساس")
    RESTRICTED = "RESTRICTED", _("بسیار محرمانه")


class HealthAlertType(models.TextChoices):
    ALLERGY = "ALLERGY", _("حساسیت")
    CHRONIC_CONDITION = "CHRONIC_CONDITION", _("بیماری مزمن")
    MEDICATION = "MEDICATION", _("داروی مصرفی")
    DIETARY = "DIETARY", _("محدودیت غذایی")
    MOBILITY = "MOBILITY", _("محدودیت حرکتی")
    VISION_HEARING = "VISION_HEARING", _("بینایی/شنوایی")
    OTHER = "OTHER", _("سایر")


class AlertSeverity(models.TextChoices):
    LOW = "LOW", _("کم")
    MEDIUM = "MEDIUM", _("متوسط")
    HIGH = "HIGH", _("زیاد")
    LIFE_THREATENING = "LIFE_THREATENING", _("تهدیدکننده حیات")


class HealthAlertStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("فعال")
    RESOLVED = "RESOLVED", _("رفع‌شده")
    EXPIRED = "EXPIRED", _("منقضی")


class IncidentOutcome(models.TextChoices):
    RESOLVED_ON_SITE = "RESOLVED_ON_SITE", _("رفع در محل")
    SENT_HOME = "SENT_HOME", _("ارسال به منزل")
    REFERRED_CLINIC = "REFERRED_CLINIC", _("ارجاع به درمانگاه")
    EMERGENCY = "EMERGENCY", _("اورژانس")
    UNDER_OBSERVATION = "UNDER_OBSERVATION", _("تحت نظر")


class CounselingPriority(models.TextChoices):
    LOW = "LOW", _("کم")
    NORMAL = "NORMAL", _("عادی")
    HIGH = "HIGH", _("زیاد")
    URGENT = "URGENT", _("فوری")


class CounselingCaseStatus(models.TextChoices):
    OPEN = "OPEN", _("باز")
    IN_PROGRESS = "IN_PROGRESS", _("در حال پیگیری")
    ON_HOLD = "ON_HOLD", _("در انتظار")
    CLOSED = "CLOSED", _("بسته")
    REFERRED_OUT = "REFERRED_OUT", _("ارجاع به بیرون")


class ReferralSource(models.TextChoices):
    TEACHER = "TEACHER", _("معلم")
    GUARDIAN = "GUARDIAN", _("ولی")
    SELF = "SELF", _("خود دانش‌آموز")
    PRINCIPAL = "PRINCIPAL", _("مدیر")
    HEALTH = "HEALTH", _("مربی بهداشت")
    DISCIPLINE = "DISCIPLINE", _("مسئول انضباط")


class BehaviorIncidentType(models.TextChoices):
    DISRUPTION = "DISRUPTION", _("اخلال در کلاس")
    TARDINESS = "TARDINESS", _("تأخیر مکرر")
    DRESS_CODE = "DRESS_CODE", _("عدم رعایت پوشش")
    BULLYING = "BULLYING", _("آزار همکلاسی")
    PROPERTY_DAMAGE = "PROPERTY_DAMAGE", _("تخریب اموال")
    ACADEMIC_DISHONESTY = "ACADEMIC_DISHONESTY", _("تقلب")
    COMMENDATION = "COMMENDATION", _("تشویق")
    OTHER = "OTHER", _("سایر")


class BehaviorSeverity(models.TextChoices):
    MINOR = "MINOR", _("جزئی")
    MODERATE = "MODERATE", _("متوسط")
    MAJOR = "MAJOR", _("جدی")
    SEVERE = "SEVERE", _("بسیار جدی")


class BehaviorIncidentStatus(models.TextChoices):
    """
    بخش ۷.۱۰: «رخداد رفتاری اتهام قطعی محسوب نمی‌شود؛ شاهد، بررسی، تصمیم،
    اقدام و اعتراض مراحل مستقل دارند.»
    """

    REPORTED = "REPORTED", _("گزارش‌شده")
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION", _("در حال بررسی")
    SUBSTANTIATED = "SUBSTANTIATED", _("تأییدشده")
    UNSUBSTANTIATED = "UNSUBSTANTIATED", _("رد شده")
    ACTION_TAKEN = "ACTION_TAKEN", _("اقدام انجام شد")
    UNDER_APPEAL = "UNDER_APPEAL", _("در حال اعتراض")
    CLOSED = "CLOSED", _("بسته")


class BehaviorActionType(models.TextChoices):
    VERBAL_WARNING = "VERBAL_WARNING", _("تذکر شفاهی")
    WRITTEN_WARNING = "WRITTEN_WARNING", _("اخطار کتبی")
    GUARDIAN_MEETING = "GUARDIAN_MEETING", _("جلسه با ولی")
    COUNSELING_REFERRAL = "COUNSELING_REFERRAL", _("ارجاع به مشاور")
    DETENTION = "DETENTION", _("ماندن پس از ساعت درسی")
    SUSPENSION = "SUSPENSION", _("تعلیق موقت")
    COMMENDATION = "COMMENDATION", _("تشویق و امتیاز")
    RESTITUTION = "RESTITUTION", _("جبران خسارت")


class MaterialType(models.TextChoices):
    BOOK = "BOOK", _("کتاب")
    MAGAZINE = "MAGAZINE", _("مجله")
    AUDIO = "AUDIO", _("صوتی")
    VIDEO = "VIDEO", _("تصویری")
    DIGITAL = "DIGITAL", _("دیجیتال")
    EQUIPMENT = "EQUIPMENT", _("تجهیزات")


class CopyStatus(models.TextChoices):
    AVAILABLE = "AVAILABLE", _("موجود")
    ON_LOAN = "ON_LOAN", _("امانت داده‌شده")
    RESERVED = "RESERVED", _("رزروشده")
    LOST = "LOST", _("مفقود")
    DAMAGED = "DAMAGED", _("آسیب‌دیده")
    WITHDRAWN = "WITHDRAWN", _("خارج از رده")


class LoanStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("در امانت")
    RETURNED = "RETURNED", _("بازگردانده‌شده")
    OVERDUE = "OVERDUE", _("سررسید گذشته")
    LOST = "LOST", _("مفقود")
    RENEWED = "RENEWED", _("تمدیدشده")


class RouteDirection(models.TextChoices):
    MORNING = "MORNING", _("رفت (صبح)")
    AFTERNOON = "AFTERNOON", _("برگشت (بعدازظهر)")
    BOTH = "BOTH", _("رفت و برگشت")


class RouteRunStatus(models.TextChoices):
    PLANNED = "PLANNED", _("برنامه‌ریزی‌شده")
    IN_PROGRESS = "IN_PROGRESS", _("در حال اجرا")
    COMPLETED = "COMPLETED", _("پایان‌یافته")
    CANCELLED = "CANCELLED", _("لغوشده")


class RidershipEventType(models.TextChoices):
    BOARDED = "BOARDED", _("سوار شد")
    ALIGHTED = "ALIGHTED", _("پیاده شد")
    NO_SHOW = "NO_SHOW", _("حاضر نشد")


class EventSource(models.TextChoices):
    DEVICE = "DEVICE", _("دستگاه")
    DRIVER = "DRIVER", _("ثبت راننده")
    SUPERVISOR = "SUPERVISOR", _("ثبت مسئول")
    MANUAL = "MANUAL", _("دستی")
