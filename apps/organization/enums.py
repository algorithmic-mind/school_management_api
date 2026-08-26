"""شمارش‌های ماژول ساختار سازمانی و آموزشی."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class SchoolType(models.TextChoices):
    PRESCHOOL = "PRESCHOOL", _("پیش‌دبستان")
    PRIMARY = "PRIMARY", _("دبستان")
    LOWER_SECONDARY = "LOWER_SECONDARY", _("متوسطه اول")
    UPPER_SECONDARY = "UPPER_SECONDARY", _("متوسطه دوم")
    COMBINED = "COMBINED", _("مجتمع چندمقطعی")


class AcademicYearStatus(models.TextChoices):
    """چرخه سال تحصیلی (بخش ۱۱.۱)."""

    PLANNING = "PLANNING", _("در حال برنامه‌ریزی")
    ACTIVE = "ACTIVE", _("فعال")
    CLOSING = "CLOSING", _("در حال بستن")
    CLOSED = "CLOSED", _("بسته")
    ARCHIVED = "ARCHIVED", _("بایگانی")


class TermStatus(models.TextChoices):
    PLANNED = "PLANNED", _("برنامه‌ریزی‌شده")
    ACTIVE = "ACTIVE", _("جاری")
    CLOSED = "CLOSED", _("بسته")


class AssessmentScheme(models.TextChoices):
    """طرح ارزشیابی درس (بخش ۲.۱)."""

    NUMERIC = "NUMERIC", _("عددی")
    DESCRIPTIVE = "DESCRIPTIVE", _("توصیفی")
    LETTER = "LETTER", _("حرفی")
    COMPETENCY = "COMPETENCY", _("شایستگی‌محور")
    MIXED = "MIXED", _("ترکیبی")


class RoomType(models.TextChoices):
    CLASSROOM = "CLASSROOM", _("کلاس درس")
    LAB = "LAB", _("آزمایشگاه")
    WORKSHOP = "WORKSHOP", _("کارگاه")
    GYM = "GYM", _("سالن ورزش")
    LIBRARY = "LIBRARY", _("کتابخانه")
    EXAM_HALL = "EXAM_HALL", _("حوزه آزمون")
    OFFICE = "OFFICE", _("اداری")
    OTHER = "OTHER", _("سایر")


class ClassGroupStatus(models.TextChoices):
    DRAFT = "DRAFT", _("پیش‌نویس")
    ACTIVE = "ACTIVE", _("فعال")
    FULL = "FULL", _("تکمیل ظرفیت")
    CLOSED = "CLOSED", _("بسته")


class CourseOfferingStatus(models.TextChoices):
    PLANNED = "PLANNED", _("برنامه‌ریزی‌شده")
    ACTIVE = "ACTIVE", _("جاری")
    COMPLETED = "COMPLETED", _("پایان‌یافته")
    CANCELLED = "CANCELLED", _("لغوشده")


class ScheduleStatus(models.TextChoices):
    DRAFT = "DRAFT", _("پیش‌نویس")
    PUBLISHED = "PUBLISHED", _("منتشرشده")
    SUPERSEDED = "SUPERSEDED", _("جایگزین‌شده")


class CalendarEventType(models.TextChoices):
    HOLIDAY = "HOLIDAY", _("تعطیلی")
    EXAM_PERIOD = "EXAM_PERIOD", _("بازه امتحانات")
    PARENT_MEETING = "PARENT_MEETING", _("جلسه اولیا")
    CEREMONY = "CEREMONY", _("مراسم")
    FIELD_TRIP = "FIELD_TRIP", _("اردو")
    OTHER = "OTHER", _("سایر")
