"""
مدل‌های بانک سؤال، آزمون و نتیجه.

مرجع: بخش ۷.۶ سند تحلیل — ERD «بانک سؤال، آزمون و نتیجه».

قیدهای مهم:
- آزمون منتشرشده به نسخه ثابت سؤال اشاره می‌کند؛ ویرایش سؤال، آزمون گذشته را
  تغییر نمی‌دهد.
- max_score باید با مجموع بارم سؤال‌ها سازگار باشد.
- شروع تلاش با Token کوتاه‌عمر و ثبت Idempotent انجام می‌شود.
- رخداد مراقبت فقط شاهد است؛ تصمیم تخلف با انسان انجام می‌شود.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.assessment.enums import (
    AppealStatus,
    AttemptStatus,
    BankVisibility,
    DifficultyLevel,
    EventSeverity,
    ExamMode,
    ExamPurpose,
    ExamSessionStatus,
    ExamStatus,
    GradingStatus,
    ProctorEventType,
    QuestionLifecycle,
    QuestionType,
    RegistrationStatus,
    ReviewStatus,
    ReviewType,
)
from apps.core.models import BaseTenantModel
from apps.organization.models import Course, CourseOffering, GradeLevel, Room, School
from apps.students.models import Enrollment


class QuestionBank(BaseTenantModel):
    """بانک سؤال با مالک و سطح دسترسی."""

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="question_banks"
    )
    owner_user_id = models.UUIDField(null=True, blank=True, verbose_name=_("مالک"))
    title = models.CharField(max_length=200)
    description = models.CharField(max_length=400, blank=True)
    course = models.ForeignKey(
        Course,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="question_banks",
    )
    visibility = models.CharField(
        max_length=20, choices=BankVisibility.choices, default=BankVisibility.PRIVATE
    )
    status = models.CharField(max_length=20, default="ACTIVE")

    class Meta:
        verbose_name = _("بانک سؤال")
        verbose_name_plural = _("بانک‌های سؤال")
        ordering = ("title",)

    def __str__(self) -> str:
        return self.title


class QuestionTag(BaseTenantModel):
    """برچسب سؤال: مبحث، هدف یادگیری، منبع."""

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="question_tags"
    )
    tag_type = models.CharField(
        max_length=40,
        verbose_name=_("نوع برچسب"),
        help_text=_("TOPIC | OBJECTIVE | SOURCE | SKILL"),
    )
    value = models.CharField(max_length=150)

    class Meta:
        verbose_name = _("برچسب سؤال")
        verbose_name_plural = _("برچسب‌های سؤال")
        constraints = [
            models.UniqueConstraint(
                fields=["school", "tag_type", "value"], name="uq_question_tag"
            )
        ]

    def __str__(self) -> str:
        return f"{self.tag_type}: {self.value}"


class Question(BaseTenantModel):
    """سؤال — پوسته نسخه‌ها."""

    bank = models.ForeignKey(
        QuestionBank, on_delete=models.CASCADE, related_name="questions"
    )
    question_type = models.CharField(max_length=25, choices=QuestionType.choices)
    lifecycle_status = models.CharField(
        max_length=20,
        choices=QuestionLifecycle.choices,
        default=QuestionLifecycle.DRAFT,
        db_index=True,
    )
    current_version = models.ForeignKey(
        "QuestionVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_of",
    )

    class Meta:
        verbose_name = _("سؤال")
        verbose_name_plural = _("سؤالات")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        if self.current_version_id:
            return self.current_version.body[:60]
        return f"سؤال {self.id}"

    @property
    def is_auto_graded(self) -> bool:
        from apps.assessment.enums import AUTO_GRADED_TYPES

        return self.question_type in AUTO_GRADED_TYPES


class QuestionVersion(BaseTenantModel):
    """
    نسخه سؤال.

    بخش ۷.۶: «آزمون منتشرشده به نسخه ثابت سؤال اشاره می‌کند؛ ویرایش سؤال اصلی
    محتوای آزمون گذشته را تغییر نمی‌دهد.»
    """

    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="versions"
    )
    version_no = models.PositiveSmallIntegerField(default=1)
    body = models.TextField(verbose_name=_("متن سؤال"))
    explanation = models.TextField(blank=True, verbose_name=_("پاسخ تشریحی"))
    grading_rubric = models.TextField(
        blank=True, verbose_name=_("راهنمای تصحیح (Rubric)")
    )
    default_score = models.DecimalField(
        max_digits=6, decimal_places=2, default=1, verbose_name=_("بارم پیش‌فرض")
    )
    difficulty = models.CharField(
        max_length=15, choices=DifficultyLevel.choices, default=DifficultyLevel.MEDIUM
    )
    locale = models.CharField(max_length=10, default="fa")
    grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="question_versions",
    )
    correct_answer = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("کلید پاسخ"),
        help_text=_("برای انواع کوتاه‌پاسخ/عددی/تطبیقی"),
    )
    review_status = models.CharField(
        max_length=25, choices=ReviewStatus.choices, default=ReviewStatus.PENDING
    )
    reviewed_by_id = models.UUIDField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    tags = models.ManyToManyField(
        QuestionTag, through="QuestionTagLink", related_name="question_versions"
    )
    media = models.FileField(upload_to="questions/", null=True, blank=True)

    class Meta:
        verbose_name = _("نسخه سؤال")
        verbose_name_plural = _("نسخه‌های سؤال")
        ordering = ("question", "-version_no")
        constraints = [
            models.UniqueConstraint(
                fields=["question", "version_no"], name="uq_question_version_no"
            )
        ]

    def __str__(self) -> str:
        return f"{self.body[:50]} (v{self.version_no})"


class QuestionOption(BaseTenantModel):
    """گزینه سؤال چندگزینه‌ای."""

    question_version = models.ForeignKey(
        QuestionVersion, on_delete=models.CASCADE, related_name="options"
    )
    option_key = models.CharField(max_length=10, verbose_name=_("کلید گزینه"))
    body = models.TextField(verbose_name=_("متن گزینه"))
    is_correct = models.BooleanField(default=False)
    credit_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name=_("درصد نمره این گزینه"),
        help_text=_("برای سؤال چندپاسخی با نمره جزئی"),
    )
    display_order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        verbose_name = _("گزینه سؤال")
        verbose_name_plural = _("گزینه‌های سؤال")
        ordering = ("display_order",)
        constraints = [
            models.UniqueConstraint(
                fields=["question_version", "option_key"], name="uq_option_key"
            )
        ]

    def __str__(self) -> str:
        return f"{self.option_key}) {self.body[:40]}"


class QuestionTagLink(BaseTenantModel):
    question_version = models.ForeignKey(
        QuestionVersion, on_delete=models.CASCADE, related_name="tag_links"
    )
    tag = models.ForeignKey(
        QuestionTag, on_delete=models.CASCADE, related_name="version_links"
    )

    class Meta:
        verbose_name = _("برچسب نسخه سؤال")
        verbose_name_plural = _("برچسب‌های نسخه سؤال")
        constraints = [
            models.UniqueConstraint(
                fields=["question_version", "tag"], name="uq_question_tag_link"
            )
        ]


class Exam(BaseTenantModel):
    """آزمون — ماشین حالت بخش ۱۰.۳."""

    course_offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="exams"
    )
    code = models.CharField(max_length=40, db_index=True)
    title = models.CharField(max_length=200)
    mode = models.CharField(max_length=20, choices=ExamMode.choices)
    purpose = models.CharField(
        max_length=20, choices=ExamPurpose.choices, default=ExamPurpose.FORMATIVE
    )
    max_score = models.DecimalField(
        max_digits=6, decimal_places=2, default=20, verbose_name=_("نمره کل")
    )
    instructions = models.TextField(blank=True)
    shuffle_questions = models.BooleanField(
        default=False, verbose_name=_("ترتیب تصادفی سؤالات")
    )
    shuffle_options = models.BooleanField(
        default=False, verbose_name=_("ترتیب تصادفی گزینه‌ها")
    )
    allow_backtrack = models.BooleanField(
        default=True, verbose_name=_("امکان بازگشت به سؤال قبلی")
    )
    show_result_immediately = models.BooleanField(default=False)
    status = models.CharField(
        max_length=25, choices=ExamStatus.choices, default=ExamStatus.DRAFT, db_index=True
    )
    published_at = models.DateTimeField(null=True, blank=True)
    results_published_at = models.DateTimeField(null=True, blank=True)
    appeal_deadline = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("آزمون")
        verbose_name_plural = _("آزمون‌ها")
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="uq_exam_tenant_code"
            )
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.title}"

    @property
    def total_question_score(self):
        """مجموع بارم سؤالات — برای کنترل سازگاری با max_score (بخش ۷.۶)."""
        from django.db.models import Sum

        return (
            ExamQuestion.objects.filter(section__exam=self).aggregate(
                total=Sum("score")
            )["total"]
            or 0
        )


class ExamSection(BaseTenantModel):
    """بخش آزمون."""

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="sections")
    title = models.CharField(max_length=150)
    instructions = models.TextField(blank=True)
    display_order = models.PositiveSmallIntegerField(default=1)
    time_limit_minutes = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = _("بخش آزمون")
        verbose_name_plural = _("بخش‌های آزمون")
        ordering = ("display_order",)

    def __str__(self) -> str:
        return self.title


class ExamQuestion(BaseTenantModel):
    """
    سؤال یک آزمون — به نسخه ثابت سؤال ارجاع می‌دهد (Snapshot).
    """

    section = models.ForeignKey(
        ExamSection, on_delete=models.CASCADE, related_name="questions"
    )
    question_version = models.ForeignKey(
        QuestionVersion, on_delete=models.PROTECT, related_name="exam_questions"
    )
    score = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    display_order = models.PositiveSmallIntegerField(default=1)
    is_required = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("سؤال آزمون")
        verbose_name_plural = _("سؤالات آزمون")
        ordering = ("display_order",)
        constraints = [
            models.UniqueConstraint(
                fields=["section", "question_version"], name="uq_exam_section_question"
            )
        ]

    def __str__(self) -> str:
        return f"{self.section.title} — {self.question_version.body[:40]}"


class ExamSession(BaseTenantModel):
    """نوبت اجرای آزمون (حوزه/پنجره زمانی)."""

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="sessions")
    room = models.ForeignKey(
        Room, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="exam_sessions",
    )
    title = models.CharField(max_length=150, blank=True)
    opens_at = models.DateTimeField(verbose_name=_("شروع پنجره"))
    closes_at = models.DateTimeField(verbose_name=_("پایان پنجره"))
    duration_minutes = models.PositiveSmallIntegerField(verbose_name=_("مدت آزمون"))
    attempt_limit = models.PositiveSmallIntegerField(default=1)
    proctor_employee_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ExamSessionStatus.choices,
        default=ExamSessionStatus.PLANNED,
    )

    class Meta:
        verbose_name = _("جلسه آزمون")
        verbose_name_plural = _("جلسات آزمون")
        ordering = ("opens_at",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(closes_at__gt=models.F("opens_at")),
                name="ck_exam_session_window",
            )
        ]

    def __str__(self) -> str:
        return f"{self.exam.title} @ {self.opens_at:%Y-%m-%d %H:%M}"


class ExamRegistration(BaseTenantModel):
    """ثبت‌نام دانش‌آموز در جلسه آزمون، با زمان اضافه فردی."""

    exam_session = models.ForeignKey(
        ExamSession, on_delete=models.CASCADE, related_name="registrations"
    )
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="exam_registrations"
    )
    seat_no = models.CharField(max_length=20, blank=True)
    extra_time_minutes = models.PositiveSmallIntegerField(
        default=0, verbose_name=_("زمان اضافه فردی")
    )
    registration_status = models.CharField(
        max_length=20,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.REGISTERED,
    )

    class Meta:
        verbose_name = _("ثبت‌نام آزمون")
        verbose_name_plural = _("ثبت‌نام‌های آزمون")
        constraints = [
            models.UniqueConstraint(
                fields=["exam_session", "enrollment"], name="uq_exam_registration"
            )
        ]

    def __str__(self) -> str:
        return f"{self.enrollment.student.full_name} @ {self.exam_session}"


class ExamAttempt(BaseTenantModel):
    """تلاش آزمون — ماشین حالت بخش ۱۰.۴."""

    registration = models.ForeignKey(
        ExamRegistration, on_delete=models.CASCADE, related_name="attempts"
    )
    attempt_no = models.PositiveSmallIntegerField(default=1)
    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    last_saved_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("زمان پایان مجاز")
    )
    auto_score = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    manual_score = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    final_score = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    status = models.CharField(
        max_length=20,
        choices=AttemptStatus.choices,
        default=AttemptStatus.CREATED,
        db_index=True,
    )
    idempotency_key = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        verbose_name=_("کلید Idempotency شروع تلاش"),
    )
    calculation_version = models.PositiveSmallIntegerField(default=1)

    class Meta:
        verbose_name = _("تلاش آزمون")
        verbose_name_plural = _("تلاش‌های آزمون")
        ordering = ("-started_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["registration", "attempt_no"], name="uq_attempt_registration_no"
            )
        ]
        indexes = [models.Index(fields=["status", "expires_at"])]

    def __str__(self) -> str:
        return f"{self.registration} — تلاش {self.attempt_no}"


class AttemptAnswer(BaseTenantModel):
    """پاسخ یک سؤال در یک تلاش (ذخیره خودکار و نسخه‌دار)."""

    attempt = models.ForeignKey(
        ExamAttempt, on_delete=models.CASCADE, related_name="answers"
    )
    exam_question = models.ForeignKey(
        ExamQuestion, on_delete=models.PROTECT, related_name="answers"
    )
    response_payload = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("پاسخ"),
        help_text=_('مثلاً {"selectedKeys": ["B"]} یا {"text": "..."}'),
    )
    attachment = models.FileField(
        upload_to="attempt-answers/", null=True, blank=True
    )
    saved_at = models.DateTimeField(null=True, blank=True)
    save_revision = models.PositiveIntegerField(default=0)
    awarded_score = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    grading_status = models.CharField(
        max_length=20, choices=GradingStatus.choices, default=GradingStatus.PENDING
    )
    time_spent_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = _("پاسخ تلاش")
        verbose_name_plural = _("پاسخ‌های تلاش")
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "exam_question"], name="uq_attempt_answer"
            )
        ]
        indexes = [models.Index(fields=["attempt", "grading_status"])]


class ProctorEvent(BaseTenantModel):
    """
    رخداد مراقبت — فقط شاهد، نه تصمیم.

    بخش ۷.۶: «تصمیم تخلف با انسان، امکان توضیح دانش‌آموز و مسیر اعتراض
    انجام می‌شود.»
    """

    attempt = models.ForeignKey(
        ExamAttempt, on_delete=models.CASCADE, related_name="proctor_events"
    )
    event_type = models.CharField(max_length=25, choices=ProctorEventType.choices)
    severity = models.CharField(
        max_length=15, choices=EventSeverity.choices, default=EventSeverity.INFO
    )
    occurred_at = models.DateTimeField()
    evidence_ref = models.CharField(max_length=300, blank=True)
    note = models.CharField(max_length=400, blank=True)

    class Meta:
        verbose_name = _("رخداد مراقبت")
        verbose_name_plural = _("رخدادهای مراقبت")
        ordering = ("-occurred_at",)


class GradeReview(BaseTenantModel):
    """تصحیح/بازبینی یک پاسخ."""

    attempt_answer = models.ForeignKey(
        AttemptAnswer, on_delete=models.CASCADE, related_name="reviews"
    )
    reviewer_id = models.UUIDField(null=True, blank=True)
    awarded_score = models.DecimalField(max_digits=8, decimal_places=2)
    feedback = models.TextField(blank=True)
    review_type = models.CharField(
        max_length=20, choices=ReviewType.choices, default=ReviewType.FIRST_PASS
    )
    is_anonymous = models.BooleanField(
        default=False, verbose_name=_("ناشناس‌سازی مصحح")
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("بازبینی نمره")
        verbose_name_plural = _("بازبینی‌های نمره")
        ordering = ("-reviewed_at",)


class GradeAppeal(BaseTenantModel):
    """اعتراض به نمره."""

    attempt = models.ForeignKey(
        ExamAttempt, on_delete=models.CASCADE, related_name="appeals"
    )
    submitted_by_id = models.UUIDField(null=True, blank=True)
    reason = models.TextField(verbose_name=_("دلیل اعتراض"))
    status = models.CharField(
        max_length=20, choices=AppealStatus.choices, default=AppealStatus.SUBMITTED
    )
    resolution = models.TextField(blank=True)
    resolved_by_id = models.UUIDField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    score_before = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    score_after = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    class Meta:
        verbose_name = _("اعتراض به نمره")
        verbose_name_plural = _("اعتراض‌های نمره")
        ordering = ("-created_at",)
