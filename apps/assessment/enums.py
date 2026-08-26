"""شمارش‌های ماژول بانک سؤال و آزمون."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class QuestionType(models.TextChoices):
    """انواع سؤال (بخش ۴.۴)."""

    SINGLE_CHOICE = "SINGLE_CHOICE", _("چندگزینه‌ای تک‌پاسخ")
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE", _("چندگزینه‌ای چندپاسخی")
    TRUE_FALSE = "TRUE_FALSE", _("درست/نادرست")
    SHORT_ANSWER = "SHORT_ANSWER", _("کوتاه‌پاسخ")
    ESSAY = "ESSAY", _("تشریحی")
    NUMERIC = "NUMERIC", _("عددی")
    MATCHING = "MATCHING", _("تطبیقی")
    ORDERING = "ORDERING", _("ترتیبی")
    FILE_UPLOAD = "FILE_UPLOAD", _("بارگذاری فایل")
    AUDIO = "AUDIO", _("پاسخ صوتی")


#: سؤالاتی که تصحیح خودکار دارند
AUTO_GRADED_TYPES = {
    QuestionType.SINGLE_CHOICE,
    QuestionType.MULTIPLE_CHOICE,
    QuestionType.TRUE_FALSE,
    QuestionType.NUMERIC,
    QuestionType.MATCHING,
    QuestionType.ORDERING,
}


class BankVisibility(models.TextChoices):
    PRIVATE = "PRIVATE", _("شخصی")
    DEPARTMENT = "DEPARTMENT", _("گروه درسی")
    SCHOOL = "SCHOOL", _("مدرسه")
    SHARED = "SHARED", _("مشترک")


class QuestionLifecycle(models.TextChoices):
    """چرخه سؤال: پیش‌نویس، تأیید، انتشار، بازنشستگی (بخش ۴.۴)."""

    DRAFT = "DRAFT", _("پیش‌نویس")
    UNDER_REVIEW = "UNDER_REVIEW", _("در حال بازبینی")
    APPROVED = "APPROVED", _("تأییدشده")
    PUBLISHED = "PUBLISHED", _("منتشرشده")
    RETIRED = "RETIRED", _("بازنشسته")


class ReviewStatus(models.TextChoices):
    PENDING = "PENDING", _("در انتظار بازبینی")
    APPROVED = "APPROVED", _("تأییدشده")
    CHANGES_REQUESTED = "CHANGES_REQUESTED", _("نیازمند اصلاح")
    REJECTED = "REJECTED", _("ردشده")


class DifficultyLevel(models.TextChoices):
    VERY_EASY = "VERY_EASY", _("خیلی آسان")
    EASY = "EASY", _("آسان")
    MEDIUM = "MEDIUM", _("متوسط")
    HARD = "HARD", _("دشوار")
    VERY_HARD = "VERY_HARD", _("خیلی دشوار")


class ExamMode(models.TextChoices):
    ONLINE = "ONLINE", _("آنلاین")
    IN_PERSON = "IN_PERSON", _("حضوری")
    HYBRID = "HYBRID", _("ترکیبی")
    PAPER_ENTRY = "PAPER_ENTRY", _("کاغذی با ورود نمره")
    TAKE_HOME = "TAKE_HOME", _("تکلیف زمان‌دار")


class ExamPurpose(models.TextChoices):
    FORMATIVE = "FORMATIVE", _("مستمر")
    MIDTERM = "MIDTERM", _("میان‌ترم")
    FINAL = "FINAL", _("پایانی")
    PRACTICE = "PRACTICE", _("تمرینی")
    MAKEUP = "MAKEUP", _("جبرانی")
    PLACEMENT = "PLACEMENT", _("تعیین سطح")


class ExamStatus(models.TextChoices):
    """ماشین حالت آزمون — بخش ۱۰.۳ سند تحلیل."""

    DRAFT = "DRAFT", _("پیش‌نویس")
    UNDER_REVIEW = "UNDER_REVIEW", _("در حال بازبینی")
    APPROVED = "APPROVED", _("تأییدشده")
    SCHEDULED = "SCHEDULED", _("زمان‌بندی‌شده")
    PUBLISHED = "PUBLISHED", _("منتشرشده")
    IN_PROGRESS = "IN_PROGRESS", _("در حال اجرا")
    SUBMISSION_CLOSED = "SUBMISSION_CLOSED", _("پایان مهلت تحویل")
    GRADING = "GRADING", _("در حال تصحیح")
    MODERATION = "MODERATION", _("بازبینی نمرات")
    RESULTS_READY = "RESULTS_READY", _("نتایج آماده")
    PUBLISHED_RESULTS = "PUBLISHED_RESULTS", _("نتایج منتشرشده")
    ARCHIVED = "ARCHIVED", _("بایگانی")
    CANCELLED = "CANCELLED", _("لغوشده")


class ExamSessionStatus(models.TextChoices):
    PLANNED = "PLANNED", _("برنامه‌ریزی‌شده")
    OPEN = "OPEN", _("باز")
    CLOSED = "CLOSED", _("بسته")
    CANCELLED = "CANCELLED", _("لغوشده")


class RegistrationStatus(models.TextChoices):
    REGISTERED = "REGISTERED", _("ثبت‌نام‌شده")
    ABSENT = "ABSENT", _("غایب")
    EXCUSED = "EXCUSED", _("غیبت موجه")
    DISQUALIFIED = "DISQUALIFIED", _("محروم")


class AttemptStatus(models.TextChoices):
    """ماشین حالت تلاش آزمون آنلاین — بخش ۱۰.۴ سند تحلیل."""

    CREATED = "CREATED", _("ایجادشده")
    IN_PROGRESS = "IN_PROGRESS", _("در حال پاسخ‌دهی")
    INTERRUPTED = "INTERRUPTED", _("قطع اتصال")
    SUBMITTED = "SUBMITTED", _("تحویل‌شده")
    AUTO_SUBMITTED = "AUTO_SUBMITTED", _("تحویل خودکار (پایان زمان)")
    EXPIRED = "EXPIRED", _("منقضی (شروع نشد)")
    GRADING = "GRADING", _("در حال تصحیح")
    GRADED = "GRADED", _("تصحیح‌شده")
    UNDER_APPEAL = "UNDER_APPEAL", _("در حال رسیدگی به اعتراض")
    REGRADED = "REGRADED", _("بازتصحیح‌شده")
    FINALIZED = "FINALIZED", _("نهایی‌شده")


class GradingStatus(models.TextChoices):
    PENDING = "PENDING", _("در انتظار تصحیح")
    AUTO_GRADED = "AUTO_GRADED", _("تصحیح خودکار")
    MANUAL_GRADED = "MANUAL_GRADED", _("تصحیح دستی")
    NEEDS_REVIEW = "NEEDS_REVIEW", _("نیازمند بازبینی")


class ProctorEventType(models.TextChoices):
    """
    رخداد مراقبت.

    بخش ۷.۶: «رخداد مراقبت فقط شاهد است. تصمیم تخلف با انسان انجام می‌شود.»
    """

    TAB_SWITCH = "TAB_SWITCH", _("خروج از پنجره آزمون")
    FOCUS_LOST = "FOCUS_LOST", _("از دست رفتن تمرکز صفحه")
    COPY_PASTE = "COPY_PASTE", _("کپی/چسباندن")
    MULTIPLE_SESSION = "MULTIPLE_SESSION", _("ورود هم‌زمان")
    DISCONNECT = "DISCONNECT", _("قطع اتصال")
    RECONNECT = "RECONNECT", _("اتصال مجدد")
    IP_CHANGE = "IP_CHANGE", _("تغییر نشانی شبکه")
    MANUAL_FLAG = "MANUAL_FLAG", _("ثبت دستی مراقب")


class EventSeverity(models.TextChoices):
    INFO = "INFO", _("اطلاعاتی")
    WARNING = "WARNING", _("هشدار")
    CRITICAL = "CRITICAL", _("بحرانی")


class ReviewType(models.TextChoices):
    FIRST_PASS = "FIRST_PASS", _("تصحیح اول")
    SECOND_PASS = "SECOND_PASS", _("بازبینی دوم")
    APPEAL = "APPEAL", _("بازتصحیح پس از اعتراض")
    MODERATION = "MODERATION", _("تعدیل")


class AppealStatus(models.TextChoices):
    SUBMITTED = "SUBMITTED", _("ثبت‌شده")
    UNDER_REVIEW = "UNDER_REVIEW", _("در حال بررسی")
    ACCEPTED = "ACCEPTED", _("پذیرفته‌شده")
    REJECTED = "REJECTED", _("ردشده")
    WITHDRAWN = "WITHDRAWN", _("پس‌گرفته‌شده")
