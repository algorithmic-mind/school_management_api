"""
مدل‌های ساختار سازمانی و آموزشی.

مرجع: بخش ۷.۱ سند تحلیل — ERD «ساختار سازمانی و آموزشی».

قیدهای مهم پیاده‌سازی‌شده:
- بازه سال تحصیلی باید همه ترم‌هایش را پوشش دهد و ترتیب ترم تکراری نباشد.
- کد کلاس در ترکیب شعبه و سال تحصیلی یکتا است.
- برنامه زمانی برای معلم، کلاس و اتاق نباید هم‌پوشانی داشته باشد.
- ظرفیت فعال کلاس از ظرفیت اتاق یا ظرفیت مصوب بیشتر نمی‌شود.
- سال بسته فقط‌خواندنی است.
"""

from __future__ import annotations

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import Weekday
from apps.core.models import BaseTenantModel, EffectiveDatedModel, RecordStatus
from apps.organization.enums import (
    AcademicYearStatus,
    AssessmentScheme,
    CalendarEventType,
    ClassGroupStatus,
    CourseOfferingStatus,
    RoomType,
    ScheduleStatus,
    SchoolType,
    TermStatus,
)


class School(BaseTenantModel):
    """مدرسه — واحد اصلی سازمانی زیر Tenant."""

    code = models.CharField(max_length=30, db_index=True, verbose_name=_("کد مدرسه"))
    name = models.CharField(max_length=200, verbose_name=_("نام مدرسه"))
    school_type = models.CharField(
        max_length=25, choices=SchoolType.choices, verbose_name=_("نوع مدرسه")
    )
    gender_policy = models.CharField(
        max_length=15,
        blank=True,
        verbose_name=_("سیاست جنسیتی"),
        help_text=_("مثلاً MALE / FEMALE / MIXED"),
    )
    registration_no = models.CharField(
        max_length=50, blank=True, verbose_name=_("شماره ثبت / مجوز")
    )
    currency = models.CharField(max_length=3, default="IRR", verbose_name=_("واحد پول"))
    timezone = models.CharField(max_length=64, default="Asia/Tehran")
    logo = models.ImageField(upload_to="schools/", null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=RecordStatus.choices, default=RecordStatus.ACTIVE
    )

    class Meta:
        verbose_name = _("مدرسه")
        verbose_name_plural = _("مدارس")
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="uq_school_tenant_code"
            )
        ]

    def __str__(self) -> str:
        return self.name


class Campus(BaseTenantModel):
    """شعبه — محل فیزیکی زیرمجموعه مدرسه."""

    school = models.ForeignKey(
        School, on_delete=models.PROTECT, related_name="campuses", verbose_name=_("مدرسه")
    )
    code = models.CharField(max_length=30, db_index=True, verbose_name=_("کد شعبه"))
    name = models.CharField(max_length=200, verbose_name=_("نام شعبه"))
    address_line = models.CharField(max_length=400, blank=True, verbose_name=_("نشانی"))
    phone = models.CharField(max_length=30, blank=True, verbose_name=_("تلفن"))
    timezone = models.CharField(max_length=64, default="Asia/Tehran")
    status = models.CharField(
        max_length=20, choices=RecordStatus.choices, default=RecordStatus.ACTIVE
    )

    class Meta:
        verbose_name = _("شعبه")
        verbose_name_plural = _("شعب")
        ordering = ("school", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["school", "code"], name="uq_campus_school_code"
            )
        ]

    def __str__(self) -> str:
        return f"{self.school.name} — {self.name}"


class AcademicYear(BaseTenantModel):
    """
    سال تحصیلی.

    بخش ۱۱.۱: «فقط یک سال می‌تواند برای عملیات روزانه هر شعبه پیش‌فرض باشد»
    و «بستن سال پس از کنترل نمرات، کارنامه، ثبت‌نام‌ها، اسناد مالی و انبار».
    """

    school = models.ForeignKey(
        School, on_delete=models.PROTECT, related_name="academic_years"
    )
    title = models.CharField(
        max_length=60, verbose_name=_("عنوان"), help_text=_("مثلاً ۱۴۰۵–۱۴۰۶")
    )
    starts_on = models.DateField(verbose_name=_("تاریخ شروع"))
    ends_on = models.DateField(verbose_name=_("تاریخ پایان"))
    is_default = models.BooleanField(
        default=False, verbose_name=_("سال پیش‌فرض عملیات روزانه")
    )
    status = models.CharField(
        max_length=20,
        choices=AcademicYearStatus.choices,
        default=AcademicYearStatus.PLANNING,
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by_id = models.UUIDField(null=True, blank=True)
    close_note = models.CharField(max_length=400, blank=True)

    class Meta:
        verbose_name = _("سال تحصیلی")
        verbose_name_plural = _("سال‌های تحصیلی")
        ordering = ("-starts_on",)
        constraints = [
            models.UniqueConstraint(
                fields=["school", "title"], name="uq_year_school_title"
            ),
            models.CheckConstraint(
                condition=models.Q(ends_on__gt=models.F("starts_on")),
                name="ck_year_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.school.name} — {self.title}"

    @property
    def is_editable(self) -> bool:
        """سال بسته فقط‌خواندنی است (بخش ۷.۱)."""
        return self.status not in {
            AcademicYearStatus.CLOSED,
            AcademicYearStatus.ARCHIVED,
        }


class Term(BaseTenantModel):
    """ترم / نوبت تحصیلی."""

    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="terms"
    )
    title = models.CharField(max_length=60, verbose_name=_("عنوان ترم"))
    starts_on = models.DateField(verbose_name=_("شروع"))
    ends_on = models.DateField(verbose_name=_("پایان"))
    sequence_no = models.PositiveSmallIntegerField(verbose_name=_("ترتیب"))
    status = models.CharField(
        max_length=20, choices=TermStatus.choices, default=TermStatus.PLANNED
    )

    class Meta:
        verbose_name = _("ترم")
        verbose_name_plural = _("ترم‌ها")
        ordering = ("academic_year", "sequence_no")
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "sequence_no"], name="uq_term_year_sequence"
            ),
            models.CheckConstraint(
                condition=models.Q(ends_on__gt=models.F("starts_on")),
                name="ck_term_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.academic_year.title} — {self.title}"


class GradeLevel(BaseTenantModel):
    """پایه تحصیلی."""

    school = models.ForeignKey(
        School, on_delete=models.PROTECT, related_name="grade_levels"
    )
    code = models.CharField(max_length=30, verbose_name=_("کد پایه"))
    title = models.CharField(max_length=100, verbose_name=_("عنوان پایه"))
    sequence_no = models.PositiveSmallIntegerField(
        verbose_name=_("ترتیب"), help_text=_("برای منطق ارتقای پایه استفاده می‌شود")
    )
    stage = models.CharField(max_length=40, blank=True, verbose_name=_("مقطع"))
    status = models.CharField(
        max_length=20, choices=RecordStatus.choices, default=RecordStatus.ACTIVE
    )

    class Meta:
        verbose_name = _("پایه تحصیلی")
        verbose_name_plural = _("پایه‌های تحصیلی")
        ordering = ("school", "sequence_no")
        constraints = [
            models.UniqueConstraint(
                fields=["school", "code"], name="uq_grade_school_code"
            )
        ]

    def __str__(self) -> str:
        return self.title


class StudyProgram(BaseTenantModel):
    """رشته / برنامه تحصیلی."""

    school = models.ForeignKey(
        School, on_delete=models.PROTECT, related_name="study_programs"
    )
    code = models.CharField(max_length=30, verbose_name=_("کد رشته"))
    title = models.CharField(max_length=150, verbose_name=_("عنوان رشته"))
    description = models.CharField(max_length=400, blank=True)
    status = models.CharField(
        max_length=20, choices=RecordStatus.choices, default=RecordStatus.ACTIVE
    )

    class Meta:
        verbose_name = _("رشته تحصیلی")
        verbose_name_plural = _("رشته‌های تحصیلی")
        ordering = ("school", "title")
        constraints = [
            models.UniqueConstraint(
                fields=["school", "code"], name="uq_program_school_code"
            )
        ]

    def __str__(self) -> str:
        return self.title


class Course(BaseTenantModel):
    """درس — تعریف مستقل از کلاس و سال."""

    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="courses")
    code = models.CharField(max_length=30, verbose_name=_("کد درس"))
    title = models.CharField(max_length=150, verbose_name=_("عنوان درس"))
    credit = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, verbose_name=_("واحد")
    )
    assessment_scheme = models.CharField(
        max_length=20,
        choices=AssessmentScheme.choices,
        default=AssessmentScheme.NUMERIC,
        verbose_name=_("طرح ارزشیابی"),
    )
    max_score = models.DecimalField(
        max_digits=6, decimal_places=2, default=20, verbose_name=_("نمره کل")
    )
    prerequisites = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="dependents",
        verbose_name=_("پیش‌نیازها"),
    )
    status = models.CharField(
        max_length=20, choices=RecordStatus.choices, default=RecordStatus.ACTIVE
    )

    class Meta:
        verbose_name = _("درس")
        verbose_name_plural = _("دروس")
        ordering = ("school", "title")
        constraints = [
            models.UniqueConstraint(
                fields=["school", "code"], name="uq_course_school_code"
            )
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.title}"


class ProgramCourse(BaseTenantModel):
    """نگاشت درس به رشته و پایه، با ساعات مصوب هفتگی."""

    program = models.ForeignKey(
        StudyProgram, on_delete=models.CASCADE, related_name="program_courses"
    )
    grade_level = models.ForeignKey(
        GradeLevel, on_delete=models.CASCADE, related_name="program_courses"
    )
    course = models.ForeignKey(
        Course, on_delete=models.PROTECT, related_name="program_links"
    )
    weekly_minutes = models.PositiveIntegerField(
        default=0, verbose_name=_("دقیقه در هفته")
    )
    is_required = models.BooleanField(default=True, verbose_name=_("اجباری"))

    class Meta:
        verbose_name = _("درس رشته/پایه")
        verbose_name_plural = _("دروس رشته/پایه")
        constraints = [
            models.UniqueConstraint(
                fields=["program", "grade_level", "course"],
                name="uq_program_grade_course",
            )
        ]

    def __str__(self) -> str:
        return f"{self.program.title} / {self.grade_level.title} / {self.course.title}"


class Room(BaseTenantModel):
    """اتاق / فضای آموزشی."""

    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, related_name="rooms")
    code = models.CharField(max_length=30, verbose_name=_("کد اتاق"))
    title = models.CharField(max_length=100, blank=True, verbose_name=_("عنوان"))
    room_type = models.CharField(
        max_length=20, choices=RoomType.choices, default=RoomType.CLASSROOM
    )
    building = models.CharField(max_length=60, blank=True, verbose_name=_("ساختمان"))
    floor = models.CharField(max_length=20, blank=True, verbose_name=_("طبقه"))
    capacity = models.PositiveIntegerField(
        default=0, verbose_name=_("ظرفیت فیزیکی")
    )
    status = models.CharField(
        max_length=20, choices=RecordStatus.choices, default=RecordStatus.ACTIVE
    )

    class Meta:
        verbose_name = _("اتاق")
        verbose_name_plural = _("اتاق‌ها")
        ordering = ("campus", "code")
        constraints = [
            models.UniqueConstraint(fields=["campus", "code"], name="uq_room_campus_code")
        ]

    def __str__(self) -> str:
        return f"{self.code} ({self.get_room_type_display()})"


class ClassGroup(BaseTenantModel):
    """
    کلاس — گروه دانش‌آموزی یک پایه/رشته در یک سال تحصیلی و شعبه.

    بخش ۷.۱: «کد کلاس در ترکیب شعبه و سال تحصیلی یکتا است.»
    """

    campus = models.ForeignKey(
        Campus, on_delete=models.PROTECT, related_name="class_groups"
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="class_groups"
    )
    grade_level = models.ForeignKey(
        GradeLevel, on_delete=models.PROTECT, related_name="class_groups"
    )
    program = models.ForeignKey(
        StudyProgram,
        on_delete=models.PROTECT,
        related_name="class_groups",
        null=True,
        blank=True,
    )
    home_room = models.ForeignKey(
        Room,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="home_class_groups",
        verbose_name=_("اتاق اصلی"),
    )
    homeroom_teacher_id = models.UUIDField(
        null=True, blank=True, verbose_name=_("معلم راهنما")
    )
    code = models.CharField(max_length=30, verbose_name=_("کد کلاس"))
    title = models.CharField(max_length=100, blank=True, verbose_name=_("عنوان کلاس"))
    capacity = models.PositiveIntegerField(
        default=0, validators=[MinValueValidator(0)], verbose_name=_("ظرفیت مصوب")
    )
    capacity_override_reason = models.CharField(
        max_length=300,
        blank=True,
        verbose_name=_("علت افزایش ظرفیت"),
        help_text=_("افزایش ظرفیت نیازمند مجوز و علت ثبت‌شده است (بخش ۱۱.۳)"),
    )
    status = models.CharField(
        max_length=20, choices=ClassGroupStatus.choices, default=ClassGroupStatus.DRAFT
    )

    class Meta:
        verbose_name = _("کلاس")
        verbose_name_plural = _("کلاس‌ها")
        ordering = ("academic_year", "grade_level", "code")
        constraints = [
            models.UniqueConstraint(
                fields=["campus", "academic_year", "code"],
                name="uq_class_campus_year_code",
            )
        ]
        indexes = [models.Index(fields=["academic_year", "grade_level"])]

    def __str__(self) -> str:
        return f"{self.code} — {self.grade_level.title}"

    @property
    def occupied_seats(self) -> int:
        """تعداد عضویت‌های فعال کلاس (داده مشتق‌شده — بخش ۱۱.۵)."""
        from apps.students.models import ClassMembership

        return ClassMembership.objects.filter(
            class_group=self, status="ACTIVE"
        ).count()

    @property
    def available_seats(self) -> int:
        return max(self.capacity - self.occupied_seats, 0)


class CourseOffering(BaseTenantModel):
    """ارائه یک درس برای یک کلاس در یک ترم (بخش ۵ واژگان)."""

    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="course_offerings"
    )
    term = models.ForeignKey(
        Term, on_delete=models.PROTECT, related_name="course_offerings"
    )
    course = models.ForeignKey(
        Course, on_delete=models.PROTECT, related_name="offerings"
    )
    weekly_minutes = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=CourseOfferingStatus.choices,
        default=CourseOfferingStatus.PLANNED,
    )

    class Meta:
        verbose_name = _("ارائه درس")
        verbose_name_plural = _("ارائه‌های درس")
        ordering = ("term", "class_group", "course")
        constraints = [
            models.UniqueConstraint(
                fields=["class_group", "term", "course"],
                name="uq_offering_class_term_course",
            )
        ]

    def __str__(self) -> str:
        return f"{self.class_group.code} / {self.course.title}"


class ScheduleEntry(BaseTenantModel, EffectiveDatedModel):
    """
    قلم برنامه هفتگی.

    بخش ۷.۱: «برنامه زمانی برای معلم، کلاس و اتاق نباید هم‌پوشانی داشته باشد.»
    کنترل تداخل در لایه سرویس (`services.detect_schedule_conflicts`) انجام می‌شود.
    """

    course_offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="schedule_entries"
    )
    room = models.ForeignKey(
        Room, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="schedule_entries",
    )
    teacher_profile_id = models.UUIDField(
        null=True, blank=True, db_index=True, verbose_name=_("معلم")
    )
    weekday = models.PositiveSmallIntegerField(
        choices=Weekday.choices, verbose_name=_("روز هفته")
    )
    starts_at = models.TimeField(verbose_name=_("ساعت شروع"))
    ends_at = models.TimeField(verbose_name=_("ساعت پایان"))
    period_no = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name=_("زنگ")
    )
    status = models.CharField(
        max_length=20, choices=ScheduleStatus.choices, default=ScheduleStatus.DRAFT
    )

    class Meta:
        verbose_name = _("قلم برنامه هفتگی")
        verbose_name_plural = _("برنامه هفتگی")
        ordering = ("weekday", "starts_at")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="ck_schedule_end_after_start",
            )
        ]
        indexes = [
            models.Index(fields=["weekday", "starts_at"]),
            models.Index(fields=["room", "weekday"]),
            models.Index(fields=["teacher_profile_id", "weekday"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_weekday_display()} {self.starts_at}–{self.ends_at}"


class CalendarEvent(BaseTenantModel):
    """تقویم آموزشی: تعطیلات، بازه امتحان، جلسه اولیا و مناسبت‌ها."""

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="calendar_events"
    )
    campus = models.ForeignKey(
        Campus, on_delete=models.CASCADE, null=True, blank=True,
        related_name="calendar_events",
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="calendar_events"
    )
    title = models.CharField(max_length=200, verbose_name=_("عنوان رویداد"))
    event_type = models.CharField(
        max_length=20, choices=CalendarEventType.choices, default=CalendarEventType.OTHER
    )
    starts_on = models.DateField(verbose_name=_("از تاریخ"))
    ends_on = models.DateField(verbose_name=_("تا تاریخ"))
    is_working_day = models.BooleanField(
        default=False, verbose_name=_("روز کاری محسوب می‌شود")
    )
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = _("رویداد تقویم")
        verbose_name_plural = _("تقویم آموزشی")
        ordering = ("starts_on",)
        indexes = [models.Index(fields=["academic_year", "starts_on"])]

    def __str__(self) -> str:
        return self.title
