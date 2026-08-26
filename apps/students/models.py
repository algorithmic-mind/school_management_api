"""
مدل‌های پذیرش و امور دانش‌آموزان.

مرجع: بخش ۷.۲ سند تحلیل — ERD «هویت، دانش‌آموز، اولیا و ثبت‌نام».

قیدهای مهم:
- رابطه ولی و دانش‌آموز منبع حقیقت دسترسی ولی است.
- مسئول مالی، دریافت‌کننده گزارش، دارنده حضانت و فرد مجاز تحویل، چهار مفهوم مستقل‌اند.
- فقط یک CLASS_MEMBERSHIP اصلی فعال در یک لحظه برای هر ثبت‌نام وجود دارد.
- رضایت لغوشده حذف نمی‌شود و نسخه متن سیاست نگهداری می‌شود.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseTenantModel, EffectiveDatedModel
from apps.identity.models import Person
from apps.organization.models import (
    AcademicYear,
    Campus,
    ClassGroup,
    GradeLevel,
    StudyProgram,
)
from apps.students.enums import (
    AdmissionStatus,
    ClassMembershipStatus,
    ConsentStatus,
    ConsentType,
    EnrollmentStatus,
    PromotionDecision,
    RelationshipType,
    StudentStatus,
    TransferType,
)


class Student(BaseTenantModel):
    """نقش تحصیلی شخص با شناسه دانش‌آموزی پایدار (بخش ۵ واژگان)."""

    person = models.OneToOneField(
        Person, on_delete=models.PROTECT, related_name="student_profile"
    )
    student_no = models.CharField(
        max_length=30, db_index=True, verbose_name=_("شماره دانش‌آموزی")
    )
    joined_on = models.DateField(verbose_name=_("تاریخ ورود به مدرسه"))
    status = models.CharField(
        max_length=25, choices=StudentStatus.choices, default=StudentStatus.PROSPECTIVE
    )
    previous_school = models.CharField(
        max_length=200, blank=True, verbose_name=_("مدرسه مبدأ")
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("دانش‌آموز")
        verbose_name_plural = _("دانش‌آموزان")
        ordering = ("student_no",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "student_no"], name="uq_student_tenant_no"
            )
        ]

    def __str__(self) -> str:
        return f"{self.student_no} — {self.person.full_name}"

    @property
    def full_name(self) -> str:
        return self.person.full_name

    @property
    def current_enrollment(self):
        return self.enrollments.filter(status=EnrollmentStatus.ACTIVE).first()


class Guardian(BaseTenantModel):
    """نقش سرپرستی/ولی (بخش ۵ واژگان)."""

    person = models.OneToOneField(
        Person, on_delete=models.PROTECT, related_name="guardian_profile"
    )
    occupation = models.CharField(max_length=120, blank=True, verbose_name=_("شغل"))
    education_level = models.CharField(
        max_length=80, blank=True, verbose_name=_("تحصیلات")
    )
    workplace = models.CharField(max_length=200, blank=True, verbose_name=_("محل کار"))
    status = models.CharField(max_length=20, default="ACTIVE")

    class Meta:
        verbose_name = _("ولی/سرپرست")
        verbose_name_plural = _("اولیا و سرپرستان")

    def __str__(self) -> str:
        return self.person.full_name


class StudentGuardian(BaseTenantModel, EffectiveDatedModel):
    """
    رابطه دانش‌آموز و ولی — منبع حقیقت دسترسی ولی.

    بخش ۷.۲: «مسئول مالی، دریافت‌کننده گزارش، دارنده حضانت و فرد مجاز برای
    تحویل دانش‌آموز چهار مفهوم مستقل‌اند.»
    """

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="guardian_links"
    )
    guardian = models.ForeignKey(
        Guardian, on_delete=models.CASCADE, related_name="student_links"
    )
    relationship_type = models.CharField(
        max_length=20, choices=RelationshipType.choices, verbose_name=_("نوع رابطه")
    )
    has_custody = models.BooleanField(default=False, verbose_name=_("دارای حضانت"))
    can_pickup = models.BooleanField(
        default=False, verbose_name=_("مجاز به تحویل گرفتن دانش‌آموز")
    )
    receives_reports = models.BooleanField(
        default=True, verbose_name=_("دریافت‌کننده گزارش و کارنامه")
    )
    financially_responsible = models.BooleanField(
        default=False, verbose_name=_("مسئول مالی")
    )
    contact_priority = models.PositiveSmallIntegerField(
        default=1, verbose_name=_("اولویت تماس")
    )
    is_emergency_contact = models.BooleanField(
        default=False, verbose_name=_("تماس اضطراری")
    )

    class Meta:
        verbose_name = _("رابطه ولی و دانش‌آموز")
        verbose_name_plural = _("روابط ولی و دانش‌آموز")
        ordering = ("contact_priority",)
        constraints = [
            models.UniqueConstraint(
                fields=["student", "guardian", "effective_from"],
                name="uq_student_guardian_period",
            )
        ]
        indexes = [models.Index(fields=["student", "financially_responsible"])]

    def __str__(self) -> str:
        return f"{self.guardian} ← {self.get_relationship_type_display()} → {self.student}"


class AdmissionApplication(BaseTenantModel):
    """درخواست پذیرش — ماشین حالت بخش ۱۰.۱."""

    person = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name="admission_applications"
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="admission_applications"
    )
    preferred_campus = models.ForeignKey(
        Campus, on_delete=models.PROTECT, related_name="admission_applications"
    )
    preferred_grade_level = models.ForeignKey(
        GradeLevel, on_delete=models.PROTECT, related_name="admission_applications"
    )
    preferred_program = models.ForeignKey(
        StudyProgram,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admission_applications",
    )
    application_no = models.CharField(
        max_length=30, db_index=True, verbose_name=_("شماره درخواست")
    )
    status = models.CharField(
        max_length=25,
        choices=AdmissionStatus.choices,
        default=AdmissionStatus.DRAFT,
        db_index=True,
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewer_id = models.UUIDField(null=True, blank=True, verbose_name=_("بررسی‌کننده"))
    interview_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("زمان مصاحبه")
    )
    entrance_score = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        verbose_name=_("نمره آزمون ورودی"),
    )
    interview_score = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        verbose_name=_("نمره مصاحبه"),
    )
    final_score = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        verbose_name=_("امتیاز نهایی"),
    )
    waitlist_rank = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("رتبه در فهرست انتظار")
    )
    conditions = models.TextField(
        blank=True, verbose_name=_("شرایط پذیرش مشروط")
    )
    decision_reason = models.CharField(max_length=400, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by_id = models.UUIDField(null=True, blank=True)

    class Meta:
        verbose_name = _("درخواست پذیرش")
        verbose_name_plural = _("درخواست‌های پذیرش")
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "application_no"], name="uq_admission_tenant_no"
            )
        ]
        indexes = [models.Index(fields=["academic_year", "status"])]

    def __str__(self) -> str:
        return f"{self.application_no} — {self.person.full_name}"


class Enrollment(BaseTenantModel):
    """
    ثبت‌نام دانش‌آموز در سال تحصیلی، پایه، رشته و شعبه.

    بخش ۲.۱: «دانش‌آموز در هر سال تحصیلی می‌تواند فقط یک ثبت‌نام فعال اصلی
    در یک مدرسه داشته باشد.»
    """

    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, related_name="enrollments"
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="enrollments"
    )
    campus = models.ForeignKey(
        Campus, on_delete=models.PROTECT, related_name="enrollments"
    )
    grade_level = models.ForeignKey(
        GradeLevel, on_delete=models.PROTECT, related_name="enrollments"
    )
    program = models.ForeignKey(
        StudyProgram,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enrollments",
    )
    admission_application = models.ForeignKey(
        AdmissionApplication,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enrollments",
    )
    enrollment_no = models.CharField(
        max_length=30, db_index=True, verbose_name=_("شماره ثبت‌نام")
    )
    enrolled_on = models.DateField(verbose_name=_("تاریخ ثبت‌نام"))
    status = models.CharField(
        max_length=25,
        choices=EnrollmentStatus.choices,
        default=EnrollmentStatus.PENDING_DOCUMENTS,
        db_index=True,
    )
    exit_date = models.DateField(null=True, blank=True, verbose_name=_("تاریخ خروج"))
    exit_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("ثبت‌نام")
        verbose_name_plural = _("ثبت‌نام‌ها")
        ordering = ("-enrolled_on",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "enrollment_no"], name="uq_enrollment_tenant_no"
            ),
            # فقط یک ثبت‌نام فعال در هر سال برای هر دانش‌آموز
            models.UniqueConstraint(
                fields=["student", "academic_year"],
                condition=models.Q(status="ACTIVE"),
                name="uq_active_enrollment_per_year",
            ),
        ]
        indexes = [
            models.Index(fields=["academic_year", "status"]),
            models.Index(fields=["campus", "grade_level"]),
        ]

    def __str__(self) -> str:
        return f"{self.enrollment_no} — {self.student.full_name}"

    @property
    def current_class_group(self):
        membership = self.class_memberships.filter(
            status=ClassMembershipStatus.ACTIVE
        ).first()
        return membership.class_group if membership else None


class ClassMembership(BaseTenantModel, EffectiveDatedModel):
    """
    عضویت زمان‌مند دانش‌آموز در کلاس.

    بخش ۷.۲: «فقط یک CLASS_MEMBERSHIP اصلی فعال در یک لحظه برای هر ثبت‌نام.»
    """

    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="class_memberships"
    )
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.PROTECT, related_name="class_memberships"
    )
    is_primary = models.BooleanField(default=True, verbose_name=_("عضویت اصلی"))
    status = models.CharField(
        max_length=20,
        choices=ClassMembershipStatus.choices,
        default=ClassMembershipStatus.ACTIVE,
        db_index=True,
    )
    exit_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("عضویت کلاس")
        verbose_name_plural = _("عضویت‌های کلاس")
        ordering = ("-effective_from",)
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment"],
                condition=models.Q(status="ACTIVE", is_primary=True),
                name="uq_active_primary_membership",
            )
        ]
        indexes = [models.Index(fields=["class_group", "status"])]

    def __str__(self) -> str:
        return f"{self.enrollment.student.full_name} @ {self.class_group.code}"


class StudentTransfer(BaseTenantModel):
    """سابقه انتقال دانش‌آموز (بخش ۹.۱۰)."""

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="transfers"
    )
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="transfers"
    )
    transfer_type = models.CharField(max_length=25, choices=TransferType.choices)
    from_class_group = models.ForeignKey(
        ClassGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfers_out",
    )
    to_class_group = models.ForeignKey(
        ClassGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfers_in",
    )
    effective_on = models.DateField(verbose_name=_("تاریخ اجرا"))
    reason = models.CharField(max_length=400, verbose_name=_("علت انتقال"))
    approved_by_id = models.UUIDField(null=True, blank=True)

    class Meta:
        verbose_name = _("انتقال دانش‌آموز")
        verbose_name_plural = _("انتقال‌های دانش‌آموز")
        ordering = ("-effective_on",)

    def __str__(self) -> str:
        return f"{self.student} — {self.get_transfer_type_display()}"


class StudentStatusHistory(BaseTenantModel):
    """تاریخچه تغییر وضعیت دانش‌آموز (بخش ۷.۲)."""

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="status_history"
    )
    from_status = models.CharField(max_length=25, blank=True)
    to_status = models.CharField(max_length=25)
    reason_code = models.CharField(max_length=60, blank=True)
    reason = models.CharField(max_length=400, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by_id = models.UUIDField(null=True, blank=True)

    class Meta:
        verbose_name = _("تاریخچه وضعیت دانش‌آموز")
        verbose_name_plural = _("تاریخچه وضعیت دانش‌آموزان")
        ordering = ("-changed_at",)


class Consent(BaseTenantModel):
    """
    رضایت‌نامه.

    بخش ۷.۲: «رضایت لغوشده حذف نمی‌شود و نسخه متن سیاست هنگام اخذ رضایت
    نگهداری می‌شود.»
    """

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="consents"
    )
    guardian = models.ForeignKey(
        Guardian,
        on_delete=models.PROTECT,
        related_name="granted_consents",
        null=True,
        blank=True,
    )
    consent_type = models.CharField(
        max_length=25, choices=ConsentType.choices, verbose_name=_("نوع رضایت")
    )
    status = models.CharField(
        max_length=15, choices=ConsentStatus.choices, default=ConsentStatus.GRANTED
    )
    granted_at = models.DateTimeField(verbose_name=_("زمان اعطا"))
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.CharField(max_length=300, blank=True)
    expires_at = models.DateField(null=True, blank=True)
    policy_version = models.CharField(
        max_length=30, verbose_name=_("نسخه متن سیاست"), default="1.0"
    )
    policy_text_snapshot = models.TextField(
        blank=True, verbose_name=_("متن سیاست در زمان اخذ رضایت")
    )

    class Meta:
        verbose_name = _("رضایت‌نامه")
        verbose_name_plural = _("رضایت‌نامه‌ها")
        ordering = ("-granted_at",)
        indexes = [models.Index(fields=["student", "consent_type", "status"])]

    def __str__(self) -> str:
        return f"{self.get_consent_type_display()} — {self.student}"


class PromotionBatch(BaseTenantModel):
    """
    اجرای گروهی ارتقای پایه (بخش ۱۱.۲).

    «ارتقا یک Batch قابل پیش‌نمایش است و نتیجه هر دانش‌آموز مستقل ثبت می‌شود.»
    """

    source_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="promotion_batches_out"
    )
    target_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="promotion_batches_in"
    )
    title = models.CharField(max_length=200)
    status = models.CharField(max_length=20, default="DRAFT")
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("دسته ارتقای پایه")
        verbose_name_plural = _("دسته‌های ارتقای پایه")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.title


class PromotionDecisionRecord(BaseTenantModel):
    """نتیجه ارتقای هر دانش‌آموز در یک Batch."""

    batch = models.ForeignKey(
        PromotionBatch, on_delete=models.CASCADE, related_name="decisions"
    )
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.PROTECT, related_name="promotion_decisions"
    )
    decision = models.CharField(max_length=20, choices=PromotionDecision.choices)
    target_grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotion_targets",
    )
    note = models.CharField(max_length=400, blank=True)
    applied = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("تصمیم ارتقا")
        verbose_name_plural = _("تصمیم‌های ارتقا")
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "enrollment"], name="uq_promotion_batch_enrollment"
            )
        ]
