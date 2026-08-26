"""
مدل‌های آموزش روزانه، حضور و تکلیف.

مرجع: بخش ۷.۵ سند تحلیل — ERD «آموزش روزانه، حضور و تکلیف».

قیدهای مهم:
- حضور فقط برای دانش‌آموز عضو فعال کلاس در زمان جلسه ثبت می‌شود.
- هر جلسه برای هر ثبت‌نام دقیقاً یک رکورد حضور جاری دارد.
- تأخیر در تحویل تکلیف با Snapshot سیاست همان تکلیف محاسبه می‌شود.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseTenantModel
from apps.hr.models import TeacherProfile
from apps.organization.models import CourseOffering, Room, ScheduleEntry
from apps.students.models import Enrollment
from apps.teaching.enums import (
    AssignmentStatus,
    AttendanceStatus,
    FinalizationStatus,
    JustificationDecision,
    LessonPlanStatus,
    ResourceType,
    ResourceVisibility,
    SessionDuty,
    SessionStatus,
    SessionType,
    SubmissionStatus,
)


class TeachingSession(BaseTenantModel):
    """جلسه درسی — نمونه اجرایی یک قلم برنامه هفتگی."""

    course_offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="sessions"
    )
    schedule_entry = models.ForeignKey(
        ScheduleEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
    )
    room = models.ForeignKey(
        Room, on_delete=models.SET_NULL, null=True, blank=True, related_name="sessions"
    )
    starts_at = models.DateTimeField(db_index=True, verbose_name=_("شروع"))
    ends_at = models.DateTimeField(verbose_name=_("پایان"))
    session_type = models.CharField(
        max_length=20, choices=SessionType.choices, default=SessionType.REGULAR
    )
    status = models.CharField(
        max_length=20, choices=SessionStatus.choices, default=SessionStatus.PLANNED
    )
    topic = models.CharField(max_length=250, blank=True, verbose_name=_("موضوع جلسه"))
    cancel_reason = models.CharField(max_length=300, blank=True)
    attendance_finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("جلسه درسی")
        verbose_name_plural = _("جلسات درسی")
        ordering = ("-starts_at",)
        indexes = [
            models.Index(fields=["course_offering", "starts_at"]),
            models.Index(fields=["status", "starts_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="ck_session_end_after_start",
            )
        ]

    def __str__(self) -> str:
        return f"{self.course_offering} @ {self.starts_at:%Y-%m-%d %H:%M}"


class SessionTeacher(BaseTenantModel):
    """معلمان حاضر در یک جلسه (شامل جانشین)."""

    session = models.ForeignKey(
        TeachingSession, on_delete=models.CASCADE, related_name="teachers"
    )
    teacher_profile = models.ForeignKey(
        TeacherProfile, on_delete=models.PROTECT, related_name="sessions"
    )
    duty = models.CharField(
        max_length=20, choices=SessionDuty.choices, default=SessionDuty.TEACHER
    )

    class Meta:
        verbose_name = _("معلم جلسه")
        verbose_name_plural = _("معلمان جلسه")
        constraints = [
            models.UniqueConstraint(
                fields=["session", "teacher_profile"], name="uq_session_teacher"
            )
        ]


class AttendanceRecord(BaseTenantModel):
    """
    رکورد حضور یک دانش‌آموز در یک جلسه.

    بخش ۷.۵: «هر جلسه برای هر ثبت‌نام دقیقاً یک رکورد حضور جاری دارد؛
    اصلاح بعد از نهایی‌شدن نیازمند علت و مجوز است.»
    """

    session = models.ForeignKey(
        TeachingSession, on_delete=models.CASCADE, related_name="attendance_records"
    )
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="attendance_records"
    )
    attendance_status = models.CharField(
        max_length=20,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.PRESENT,
        db_index=True,
    )
    late_minutes = models.PositiveSmallIntegerField(default=0)
    early_leave_minutes = models.PositiveSmallIntegerField(default=0)
    reason_code = models.CharField(max_length=60, blank=True)
    note = models.CharField(max_length=300, blank=True)
    finalization_status = models.CharField(
        max_length=20,
        choices=FinalizationStatus.choices,
        default=FinalizationStatus.DRAFT,
    )
    recorded_by_id = models.UUIDField(null=True, blank=True)
    amended_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("رکورد حضور")
        verbose_name_plural = _("رکوردهای حضور")
        constraints = [
            models.UniqueConstraint(
                fields=["session", "enrollment"], name="uq_attendance_session_enrollment"
            )
        ]
        indexes = [
            models.Index(fields=["enrollment", "attendance_status"]),
            models.Index(fields=["session", "finalization_status"]),
        ]

    def __str__(self) -> str:
        return f"{self.enrollment.student.full_name}: {self.get_attendance_status_display()}"


class AbsenceJustification(BaseTenantModel):
    """درخواست توجیه غیبت توسط ولی و تصمیم مدرسه (بخش ۴.۳)."""

    attendance = models.OneToOneField(
        AttendanceRecord, on_delete=models.CASCADE, related_name="justification"
    )
    submitted_by_guardian_id = models.UUIDField(null=True, blank=True)
    reason = models.TextField(verbose_name=_("دلیل غیبت"))
    evidence_file = models.FileField(
        upload_to="absence-evidence/", null=True, blank=True
    )
    decision = models.CharField(
        max_length=20,
        choices=JustificationDecision.choices,
        default=JustificationDecision.PENDING,
    )
    decided_by_id = models.UUIDField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("توجیه غیبت")
        verbose_name_plural = _("توجیهات غیبت")
        ordering = ("-created_at",)


class LessonPlan(BaseTenantModel):
    """طرح درس."""

    course_offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="lesson_plans"
    )
    session = models.ForeignKey(
        TeachingSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lesson_plans",
    )
    title = models.CharField(max_length=200)
    objectives = models.TextField(blank=True, verbose_name=_("اهداف یادگیری"))
    content = models.TextField(blank=True)
    planned_for = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=LessonPlanStatus.choices, default=LessonPlanStatus.DRAFT
    )

    class Meta:
        verbose_name = _("طرح درس")
        verbose_name_plural = _("طرح‌های درس")
        ordering = ("-planned_for",)

    def __str__(self) -> str:
        return self.title


class Assignment(BaseTenantModel):
    """تکلیف."""

    course_offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="assignments"
    )
    title = models.CharField(max_length=200, verbose_name=_("عنوان تکلیف"))
    description = models.TextField(blank=True)
    opens_at = models.DateTimeField(verbose_name=_("زمان بازشدن"))
    due_at = models.DateTimeField(db_index=True, verbose_name=_("مهلت تحویل"))
    close_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("پایان پذیرش با تأخیر")
    )
    max_score = models.DecimalField(
        max_digits=6, decimal_places=2, default=20, verbose_name=_("بارم")
    )
    allow_late_submission = models.BooleanField(
        default=False, verbose_name=_("پذیرش تحویل با تأخیر")
    )
    late_penalty_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, verbose_name=_("درصد جریمه تأخیر")
    )
    max_attempts = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(
        max_length=20, choices=AssignmentStatus.choices, default=AssignmentStatus.DRAFT
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("تکلیف")
        verbose_name_plural = _("تکالیف")
        ordering = ("-due_at",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(due_at__gt=models.F("opens_at")),
                name="ck_assignment_due_after_open",
            )
        ]

    def __str__(self) -> str:
        return self.title


class AssignmentSubmission(BaseTenantModel):
    """
    تحویل تکلیف.

    بخش ۷.۵: «تأخیر با Snapshot سیاست همان تکلیف محاسبه می‌شود؛ تغییر سیاست
    به ارسال‌های قبلی سرایت نمی‌کند.»
    """

    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="submissions"
    )
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="assignment_submissions"
    )
    attempt_no = models.PositiveSmallIntegerField(default=1)
    submitted_at = models.DateTimeField(null=True, blank=True)
    content = models.TextField(blank=True)
    attachment = models.FileField(
        upload_to="submissions/", null=True, blank=True
    )
    status = models.CharField(
        max_length=20, choices=SubmissionStatus.choices, default=SubmissionStatus.DRAFT
    )
    is_late = models.BooleanField(default=False)
    late_minutes = models.PositiveIntegerField(default=0)
    policy_snapshot = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Snapshot سیاست تأخیر در زمان تحویل"),
    )

    class Meta:
        verbose_name = _("تحویل تکلیف")
        verbose_name_plural = _("تحویل‌های تکلیف")
        ordering = ("-submitted_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "enrollment", "attempt_no"],
                name="uq_submission_assignment_enrollment_attempt",
            )
        ]

    def __str__(self) -> str:
        return f"{self.enrollment.student.full_name} — {self.assignment.title}"


class SubmissionFeedback(BaseTenantModel):
    """بازخورد و نمره تحویل تکلیف."""

    submission = models.ForeignKey(
        AssignmentSubmission, on_delete=models.CASCADE, related_name="feedbacks"
    )
    reviewer_id = models.UUIDField(null=True, blank=True)
    score = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    feedback = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    is_final = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("بازخورد تکلیف")
        verbose_name_plural = _("بازخوردهای تکلیف")
        ordering = ("-reviewed_at",)


class LearningResource(BaseTenantModel):
    """منابع آموزشی منتشرشده برای یک ارائه درس."""

    course_offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="resources"
    )
    resource_type = models.CharField(max_length=20, choices=ResourceType.choices)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="learning-resources/", null=True, blank=True)
    url = models.URLField(blank=True)
    visibility = models.CharField(
        max_length=20,
        choices=ResourceVisibility.choices,
        default=ResourceVisibility.CLASS_ONLY,
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("منبع آموزشی")
        verbose_name_plural = _("منابع آموزشی")
        ordering = ("-published_at",)

    def __str__(self) -> str:
        return self.title
