"""شمارش‌های ماژول دفتر نمره و کارنامه."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class GradeItemSourceType(models.TextChoices):
    EXAM = "EXAM", _("آزمون")
    ASSIGNMENT = "ASSIGNMENT", _("تکلیف")
    CLASS_ACTIVITY = "CLASS_ACTIVITY", _("فعالیت کلاسی")
    PROJECT = "PROJECT", _("پروژه")
    MANUAL = "MANUAL", _("ثبت دستی")


class GradeItemStatus(models.TextChoices):
    DRAFT = "DRAFT", _("پیش‌نویس")
    OPEN = "OPEN", _("باز برای ثبت نمره")
    LOCKED = "LOCKED", _("قفل‌شده")
    PUBLISHED = "PUBLISHED", _("منتشرشده")


class ScoreStatus(models.TextChoices):
    """
    وضعیت نمره.

    بخش ۷.۷: «غیبت، معاف، ثبت‌نشده و صفر یکسان نیستند و با وضعیت جدا ذخیره
    می‌شوند.»
    """

    NOT_RECORDED = "NOT_RECORDED", _("ثبت‌نشده")
    RECORDED = "RECORDED", _("ثبت‌شده")
    ABSENT = "ABSENT", _("غایب")
    EXEMPT = "EXEMPT", _("معاف")
    EXCUSED = "EXCUSED", _("غیبت موجه")
    PENDING_REVIEW = "PENDING_REVIEW", _("در انتظار بازبینی")


class DropPolicy(models.TextChoices):
    NONE = "NONE", _("بدون حذف")
    DROP_LOWEST = "DROP_LOWEST", _("حذف پایین‌ترین نمره")
    DROP_LOWEST_TWO = "DROP_LOWEST_TWO", _("حذف دو نمره پایین")


class CourseResultStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", _("در جریان")
    PASSED = "PASSED", _("قبول")
    FAILED = "FAILED", _("مردود")
    INCOMPLETE = "INCOMPLETE", _("ناتمام")
    EXEMPT = "EXEMPT", _("معاف")


class ReportCardStatus(models.TextChoices):
    """چرخه کارنامه — کارنامه نسخه‌ای Snapshot است (بخش ۷.۷)."""

    DRAFT = "DRAFT", _("پیش‌نویس")
    GENERATED = "GENERATED", _("تولیدشده")
    UNDER_REVIEW = "UNDER_REVIEW", _("در حال بازبینی")
    PUBLISHED = "PUBLISHED", _("منتشرشده")
    SUPERSEDED = "SUPERSEDED", _("جایگزین‌شده با نسخه جدید")


class ScoreChangeApproval(models.TextChoices):
    NOT_REQUIRED = "NOT_REQUIRED", _("بدون نیاز به تأیید")
    PENDING = "PENDING", _("در انتظار تأیید")
    APPROVED = "APPROVED", _("تأییدشده")
    REJECTED = "REJECTED", _("ردشده")


class QualitativeLevel(models.TextChoices):
    """ارزشیابی توصیفی."""

    EXCELLENT = "EXCELLENT", _("خیلی خوب")
    GOOD = "GOOD", _("خوب")
    ACCEPTABLE = "ACCEPTABLE", _("قابل قبول")
    NEEDS_IMPROVEMENT = "NEEDS_IMPROVEMENT", _("نیازمند تلاش بیشتر")
