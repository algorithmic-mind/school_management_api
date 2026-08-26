"""شمارش‌های ماژول آموزش روزانه."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class SessionType(models.TextChoices):
    REGULAR = "REGULAR", _("عادی")
    MAKEUP = "MAKEUP", _("جبرانی")
    EXTRA = "EXTRA", _("فوق‌العاده")
    SUBSTITUTE = "SUBSTITUTE", _("با معلم جانشین")
    REMOTE = "REMOTE", _("مجازی")
    EXAM = "EXAM", _("جلسه آزمون")


class SessionStatus(models.TextChoices):
    PLANNED = "PLANNED", _("برنامه‌ریزی‌شده")
    IN_PROGRESS = "IN_PROGRESS", _("در حال برگزاری")
    HELD = "HELD", _("برگزارشده")
    CANCELLED = "CANCELLED", _("لغوشده")
    POSTPONED = "POSTPONED", _("به تعویق افتاده")


class SessionDuty(models.TextChoices):
    TEACHER = "TEACHER", _("مدرس")
    ASSISTANT = "ASSISTANT", _("دستیار")
    SUBSTITUTE = "SUBSTITUTE", _("جانشین")
    OBSERVER = "OBSERVER", _("ناظر")


class AttendanceStatus(models.TextChoices):
    """
    وضعیت‌های حضور — بخش ۷.۵ سند تحلیل.

    «وضعیت‌های حضور حداقل شامل PRESENT, ABSENT, LATE, EXCUSED,
    SCHOOL_ACTIVITY, REMOTE است.»
    """

    PRESENT = "PRESENT", _("حاضر")
    ABSENT = "ABSENT", _("غایب")
    LATE = "LATE", _("تأخیر")
    EXCUSED = "EXCUSED", _("غیبت موجه")
    SCHOOL_ACTIVITY = "SCHOOL_ACTIVITY", _("مأموریت مدرسه")
    REMOTE = "REMOTE", _("حضور مجازی")
    EARLY_LEAVE = "EARLY_LEAVE", _("خروج زودهنگام")


class FinalizationStatus(models.TextChoices):
    DRAFT = "DRAFT", _("پیش‌نویس")
    FINALIZED = "FINALIZED", _("نهایی‌شده")
    AMENDED = "AMENDED", _("اصلاح‌شده پس از نهایی‌سازی")


class JustificationDecision(models.TextChoices):
    PENDING = "PENDING", _("در انتظار بررسی")
    APPROVED = "APPROVED", _("پذیرفته‌شده")
    REJECTED = "REJECTED", _("ردشده")


class AssignmentStatus(models.TextChoices):
    DRAFT = "DRAFT", _("پیش‌نویس")
    PUBLISHED = "PUBLISHED", _("منتشرشده")
    CLOSED = "CLOSED", _("بسته")
    ARCHIVED = "ARCHIVED", _("بایگانی")


class SubmissionStatus(models.TextChoices):
    DRAFT = "DRAFT", _("پیش‌نویس")
    SUBMITTED = "SUBMITTED", _("ارسال‌شده")
    LATE = "LATE", _("ارسال با تأخیر")
    GRADED = "GRADED", _("تصحیح‌شده")
    RETURNED = "RETURNED", _("بازگشت برای اصلاح")
    MISSING = "MISSING", _("ارسال‌نشده")


class ResourceType(models.TextChoices):
    FILE = "FILE", _("فایل")
    LINK = "LINK", _("پیوند")
    VIDEO = "VIDEO", _("ویدئو")
    TEXT = "TEXT", _("متن")
    LIVE_SESSION = "LIVE_SESSION", _("کلاس زنده")


class ResourceVisibility(models.TextChoices):
    CLASS_ONLY = "CLASS_ONLY", _("فقط کلاس")
    GRADE = "GRADE", _("کل پایه")
    SCHOOL = "SCHOOL", _("کل مدرسه")
    PRIVATE = "PRIVATE", _("فقط معلم")


class LessonPlanStatus(models.TextChoices):
    DRAFT = "DRAFT", _("پیش‌نویس")
    APPROVED = "APPROVED", _("تأییدشده")
    DELIVERED = "DELIVERED", _("اجراشده")
