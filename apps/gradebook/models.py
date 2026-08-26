"""
مدل‌های دفتر نمره و کارنامه.

مرجع: بخش ۷.۷ سند تحلیل — ERD «دفتر نمره و کارنامه».

قیدهای مهم:
- مجموع وزن دسته‌های فعال هر درس باید ۱۰۰٪ باشد.
- «غیبت»، «معاف»، «ثبت‌نشده» و «صفر» یکسان نیستند.
- نمره خام نگهداری و نمره نرمال‌شده محاسبه می‌شود.
- کارنامه نسخه‌ای Snapshot است؛ انتشار مجدد نسخه جدید می‌سازد.
- قفل نمره در پایان بازه ثبت؛ بازگشایی نیازمند علت و تأیید.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseTenantModel
from apps.gradebook.enums import (
    CourseResultStatus,
    DropPolicy,
    GradeItemSourceType,
    GradeItemStatus,
    QualitativeLevel,
    ReportCardStatus,
    ScoreChangeApproval,
    ScoreStatus,
)
from apps.organization.models import CourseOffering, Term
from apps.students.models import Enrollment


class AssessmentCategory(BaseTenantModel):
    """
    دسته ارزشیابی یک ارائه درس با وزن درصدی.

    بخش ۷.۷: «مجموع وزن دسته‌های فعال هر درس باید ۱۰۰٪ باشد.»
    """

    course_offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="assessment_categories"
    )
    title = models.CharField(max_length=150, verbose_name=_("عنوان دسته"))
    weight_percent = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name=_("وزن درصدی")
    )
    drop_policy = models.CharField(
        max_length=20, choices=DropPolicy.choices, default=DropPolicy.NONE
    )
    display_order = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("دسته ارزشیابی")
        verbose_name_plural = _("دسته‌های ارزشیابی")
        ordering = ("display_order",)
        constraints = [
            models.UniqueConstraint(
                fields=["course_offering", "title"], name="uq_category_offering_title"
            )
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.weight_percent}٪)"


class GradeItem(BaseTenantModel):
    """قلم نمره — می‌تواند از آزمون، تکلیف یا ثبت دستی بیاید."""

    category = models.ForeignKey(
        AssessmentCategory, on_delete=models.CASCADE, related_name="grade_items"
    )
    source_type = models.CharField(
        max_length=20, choices=GradeItemSourceType.choices, default=GradeItemSourceType.MANUAL
    )
    source_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("شناسه منبع"),
        help_text=_("شناسه آزمون یا تکلیف مرتبط"),
    )
    title = models.CharField(max_length=200)
    max_score = models.DecimalField(
        max_digits=6, decimal_places=2, default=20, verbose_name=_("بارم")
    )
    weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=1, verbose_name=_("ضریب داخل دسته")
    )
    due_on = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=GradeItemStatus.choices, default=GradeItemStatus.DRAFT
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by_id = models.UUIDField(null=True, blank=True)

    class Meta:
        verbose_name = _("قلم نمره")
        verbose_name_plural = _("اقلام نمره")
        ordering = ("due_on", "title")
        indexes = [models.Index(fields=["category", "status"])]

    def __str__(self) -> str:
        return self.title


class StudentScore(BaseTenantModel):
    """نمره یک دانش‌آموز در یک قلم نمره."""

    grade_item = models.ForeignKey(
        GradeItem, on_delete=models.CASCADE, related_name="scores"
    )
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="scores"
    )
    raw_score = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("نمره خام"),
    )
    normalized_score = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("نمره نرمال‌شده"),
        help_text=_("نمره خام تقسیم بر بارم، ضرب در ۱۰۰"),
    )
    letter_grade = models.CharField(max_length=5, blank=True)
    qualitative_level = models.CharField(
        max_length=25, choices=QualitativeLevel.choices, blank=True
    )
    status = models.CharField(
        max_length=20, choices=ScoreStatus.choices, default=ScoreStatus.NOT_RECORDED
    )
    comment = models.CharField(max_length=400, blank=True)
    recorded_by_id = models.UUIDField(null=True, blank=True)
    recorded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("نمره دانش‌آموز")
        verbose_name_plural = _("نمرات دانش‌آموزان")
        constraints = [
            models.UniqueConstraint(
                fields=["grade_item", "enrollment"], name="uq_score_item_enrollment"
            )
        ]
        indexes = [models.Index(fields=["enrollment", "status"])]

    def __str__(self) -> str:
        return f"{self.enrollment.student.full_name} — {self.grade_item.title}: {self.raw_score}"


class ScoreChange(BaseTenantModel):
    """
    تاریخچه تغییر نمره.

    بخش ۷.۷: تغییر نمره پس از قفل نیازمند علت و تأیید معاون آموزشی است.
    """

    student_score = models.ForeignKey(
        StudentScore, on_delete=models.CASCADE, related_name="changes"
    )
    old_score = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    new_score = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, blank=True)
    reason = models.CharField(max_length=400)
    changed_by_id = models.UUIDField(null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    approval_status = models.CharField(
        max_length=20,
        choices=ScoreChangeApproval.choices,
        default=ScoreChangeApproval.NOT_REQUIRED,
    )
    approved_by_id = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("تغییر نمره")
        verbose_name_plural = _("تغییرات نمره")
        ordering = ("-changed_at",)


class CourseResult(BaseTenantModel):
    """نتیجه نهایی یک درس برای یک دانش‌آموز."""

    course_offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="results"
    )
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="course_results"
    )
    continuous_score = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        verbose_name=_("نمره مستمر"),
    )
    final_exam_score = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        verbose_name=_("نمره پایانی"),
    )
    final_score = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        verbose_name=_("نمره نهایی"),
    )
    letter_grade = models.CharField(max_length=5, blank=True)
    qualitative_level = models.CharField(
        max_length=25, choices=QualitativeLevel.choices, blank=True
    )
    result_status = models.CharField(
        max_length=20,
        choices=CourseResultStatus.choices,
        default=CourseResultStatus.IN_PROGRESS,
    )
    calculation_version = models.PositiveSmallIntegerField(default=1)
    calculated_at = models.DateTimeField(null=True, blank=True)
    calculation_inputs = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Snapshot ورودی‌های محاسبه"),
        help_text=_("بخش ۱۱.۵: هر محاسبه مهم Snapshot ورودی‌های ضروری دارد."),
    )
    teacher_comment = models.TextField(blank=True)

    class Meta:
        verbose_name = _("نتیجه درس")
        verbose_name_plural = _("نتایج دروس")
        constraints = [
            models.UniqueConstraint(
                fields=["course_offering", "enrollment"],
                name="uq_result_offering_enrollment",
            )
        ]
        indexes = [models.Index(fields=["enrollment", "result_status"])]

    def __str__(self) -> str:
        return f"{self.enrollment.student.full_name} — {self.course_offering.course.title}"


class ReportCard(BaseTenantModel):
    """
    کارنامه.

    بخش ۷.۷: «کارنامه نسخه‌ای Snapshot است. انتشار مجدد، نسخه جدید می‌سازد و
    نسخه قبلی قابل ممیزی باقی می‌ماند.»
    """

    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="report_cards"
    )
    term = models.ForeignKey(
        Term, on_delete=models.PROTECT, related_name="report_cards"
    )
    version_no = models.PositiveSmallIntegerField(default=1)
    generated_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=ReportCardStatus.choices, default=ReportCardStatus.DRAFT
    )
    average_score = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, verbose_name=_("معدل")
    )
    rank_in_class = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name=_("رتبه در کلاس"),
        help_text=_("فقط در صورت مجاز بودن سیاست رتبه‌بندی نمایش داده می‌شود"),
    )
    attendance_summary = models.JSONField(default=dict, blank=True)
    principal_comment = models.TextField(blank=True)
    verification_code = models.CharField(
        max_length=40, blank=True, verbose_name=_("کد اعتبارسنجی")
    )

    class Meta:
        verbose_name = _("کارنامه")
        verbose_name_plural = _("کارنامه‌ها")
        ordering = ("-version_no",)
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment", "term", "version_no"],
                name="uq_report_card_version",
            )
        ]

    def __str__(self) -> str:
        return f"کارنامه {self.enrollment.student.full_name} — {self.term.title} (v{self.version_no})"


class ReportCardItem(BaseTenantModel):
    """قلم کارنامه — Snapshot نتیجه درس در لحظه تولید کارنامه."""

    report_card = models.ForeignKey(
        ReportCard, on_delete=models.CASCADE, related_name="items"
    )
    course_result = models.ForeignKey(
        CourseResult, on_delete=models.PROTECT, related_name="report_card_items"
    )
    course_title = models.CharField(
        max_length=200, verbose_name=_("عنوان درس (Snapshot)")
    )
    displayed_score = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    displayed_level = models.CharField(max_length=25, blank=True)
    credit = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    teacher_comment = models.TextField(blank=True)
    display_order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        verbose_name = _("قلم کارنامه")
        verbose_name_plural = _("اقلام کارنامه")
        ordering = ("display_order",)
        constraints = [
            models.UniqueConstraint(
                fields=["report_card", "course_result"], name="uq_report_card_item"
            )
        ]
