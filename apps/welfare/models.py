"""
مدل‌های سلامت، مشاوره، انضباط، کتابخانه و حمل‌ونقل.

مرجع: بخش ۷.۱۰ سند تحلیل.

قیدهای مهم:
- یادداشت درمانی و مشاوره‌ای از پرونده عمومی جدا و با مجوز فیلدی محافظت می‌شود.
- Alert سلامت فقط حداقل اطلاعات لازم برای اقدام ایمن را نشان می‌دهد.
- رخداد رفتاری اتهام قطعی نیست؛ بررسی، تصمیم، اقدام و اعتراض مستقل‌اند.
- امانت فقط برای نسخه قابل‌امانت و عضو فعال مجاز است.
- تعداد دانش‌آموزان فعال مسیر از ظرفیت خودرو بیشتر نمی‌شود.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseTenantModel, EffectiveDatedModel
from apps.identity.models import Person
from apps.organization.models import Campus
from apps.students.models import Student
from apps.welfare.enums import (
    AlertSeverity,
    BehaviorActionType,
    BehaviorIncidentStatus,
    BehaviorIncidentType,
    BehaviorSeverity,
    BloodType,
    ConfidentialityLevel,
    CopyStatus,
    CounselingCaseStatus,
    CounselingPriority,
    EventSource,
    HealthAlertStatus,
    HealthAlertType,
    IncidentOutcome,
    LoanStatus,
    MaterialType,
    ReferralSource,
    RidershipEventType,
    RouteDirection,
    RouteRunStatus,
)


# ===========================================================================
# سلامت
# ===========================================================================
class HealthProfile(BaseTenantModel):
    """پرونده سلامت دانش‌آموز — سطح دسترسی جدا از پرونده عمومی."""

    student = models.OneToOneField(
        Student, on_delete=models.CASCADE, related_name="health_profile"
    )
    blood_type = models.CharField(
        max_length=10, choices=BloodType.choices, default=BloodType.UNKNOWN
    )
    height_cm = models.PositiveSmallIntegerField(null=True, blank=True)
    weight_kg = models.PositiveSmallIntegerField(null=True, blank=True)
    accessibility_needs = models.TextField(
        blank=True, verbose_name=_("نیازهای دسترس‌پذیری")
    )
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True)
    family_physician = models.CharField(max_length=150, blank=True)
    insurance_no = models.CharField(max_length=60, blank=True)
    confidentiality_level = models.CharField(
        max_length=15,
        choices=ConfidentialityLevel.choices,
        default=ConfidentialityLevel.SENSITIVE,
    )

    class Meta:
        verbose_name = _("پرونده سلامت")
        verbose_name_plural = _("پرونده‌های سلامت")

    def __str__(self) -> str:
        return f"پرونده سلامت {self.student.full_name}"


class HealthAlert(BaseTenantModel):
    """
    هشدار سلامت.

    بخش ۷.۱۰: «Alert سلامت فقط حداقل اطلاعات لازم برای اقدام ایمن را به
    معلم/مسئول اردو نشان می‌دهد.» فیلد `safe_summary` همین حداقل است.
    """

    health_profile = models.ForeignKey(
        HealthProfile, on_delete=models.CASCADE, related_name="alerts"
    )
    alert_type = models.CharField(max_length=25, choices=HealthAlertType.choices)
    title = models.CharField(max_length=200)
    safe_summary = models.CharField(
        max_length=300,
        verbose_name=_("خلاصه قابل نمایش به معلم"),
        help_text=_("بدون جزئیات پزشکی غیرضروری"),
    )
    instructions = models.TextField(
        blank=True, verbose_name=_("دستورالعمل اقدام (محرمانه)")
    )
    severity = models.CharField(
        max_length=20, choices=AlertSeverity.choices, default=AlertSeverity.MEDIUM
    )
    valid_until = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=15, choices=HealthAlertStatus.choices, default=HealthAlertStatus.ACTIVE
    )

    class Meta:
        verbose_name = _("هشدار سلامت")
        verbose_name_plural = _("هشدارهای سلامت")
        ordering = ("-severity", "-created_at")
        indexes = [models.Index(fields=["health_profile", "status"])]

    def __str__(self) -> str:
        return f"{self.get_alert_type_display()}: {self.title}"


class HealthIncident(BaseTenantModel):
    """رخداد سلامت و حادثه."""

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="health_incidents"
    )
    occurred_at = models.DateTimeField()
    location = models.CharField(max_length=150, blank=True)
    description = models.TextField()
    action_taken = models.TextField(blank=True)
    outcome = models.CharField(
        max_length=25,
        choices=IncidentOutcome.choices,
        default=IncidentOutcome.RESOLVED_ON_SITE,
    )
    reported_by_id = models.UUIDField(null=True, blank=True)
    guardian_notified_at = models.DateTimeField(null=True, blank=True)
    confidentiality_level = models.CharField(
        max_length=15,
        choices=ConfidentialityLevel.choices,
        default=ConfidentialityLevel.SENSITIVE,
    )

    class Meta:
        verbose_name = _("رخداد سلامت")
        verbose_name_plural = _("رخدادهای سلامت")
        ordering = ("-occurred_at",)

    def __str__(self) -> str:
        return f"{self.student.full_name} @ {self.occurred_at:%Y-%m-%d}"


# ===========================================================================
# مشاوره
# ===========================================================================
class CounselingCase(BaseTenantModel):
    """پرونده مشاوره."""

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="counseling_cases"
    )
    counselor_employee_id = models.UUIDField(null=True, blank=True)
    referral_source = models.CharField(max_length=20, choices=ReferralSource.choices)
    subject = models.CharField(max_length=200)
    priority = models.CharField(
        max_length=15, choices=CounselingPriority.choices, default=CounselingPriority.NORMAL
    )
    status = models.CharField(
        max_length=20,
        choices=CounselingCaseStatus.choices,
        default=CounselingCaseStatus.OPEN,
    )
    opened_on = models.DateField()
    closed_on = models.DateField(null=True, blank=True)
    action_plan = models.TextField(
        blank=True, verbose_name=_("برنامه اقدام")
    )
    confidentiality_level = models.CharField(
        max_length=15,
        choices=ConfidentialityLevel.choices,
        default=ConfidentialityLevel.RESTRICTED,
    )

    class Meta:
        verbose_name = _("پرونده مشاوره")
        verbose_name_plural = _("پرونده‌های مشاوره")
        ordering = ("-opened_on",)

    def __str__(self) -> str:
        return f"{self.student.full_name} — {self.subject}"


class CounselingSession(BaseTenantModel):
    """
    جلسه مشاوره.

    `protected_note` بسیار محرمانه است و فقط با مجوز فیلدی برگردانده می‌شود
    (بخش ۷.۱۰ و ۱۵.۲).
    """

    case = models.ForeignKey(
        CounselingCase, on_delete=models.CASCADE, related_name="sessions"
    )
    held_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=45)
    summary = models.TextField(
        blank=True, verbose_name=_("خلاصه قابل مشاهده برای نقش‌های مجاز")
    )
    protected_note = models.TextField(
        blank=True, verbose_name=_("یادداشت محرمانه مشاور")
    )
    next_followup_at = models.DateTimeField(null=True, blank=True)
    attendees = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("جلسه مشاوره")
        verbose_name_plural = _("جلسات مشاوره")
        ordering = ("-held_at",)


# ===========================================================================
# انضباط و تشویق
# ===========================================================================
class BehaviorIncident(BaseTenantModel):
    """رخداد رفتاری — شامل تخلف و تشویق."""

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="behavior_incidents"
    )
    occurred_at = models.DateTimeField()
    location = models.CharField(max_length=150, blank=True)
    incident_type = models.CharField(
        max_length=25, choices=BehaviorIncidentType.choices
    )
    severity = models.CharField(
        max_length=15, choices=BehaviorSeverity.choices, default=BehaviorSeverity.MINOR
    )
    description = models.TextField()
    witnesses = models.CharField(max_length=400, blank=True, verbose_name=_("شهود"))
    student_statement = models.TextField(
        blank=True, verbose_name=_("توضیح دانش‌آموز")
    )
    reported_by_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(
        max_length=25,
        choices=BehaviorIncidentStatus.choices,
        default=BehaviorIncidentStatus.REPORTED,
    )
    investigation_note = models.TextField(blank=True)
    decided_by_id = models.UUIDField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    points = models.SmallIntegerField(
        default=0,
        verbose_name=_("امتیاز"),
        help_text=_("منفی برای تخلف، مثبت برای تشویق"),
    )
    guardian_notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("رخداد رفتاری")
        verbose_name_plural = _("رخدادهای رفتاری")
        ordering = ("-occurred_at",)
        indexes = [models.Index(fields=["student", "status"])]

    def __str__(self) -> str:
        return f"{self.get_incident_type_display()} — {self.student.full_name}"


class BehaviorAction(BaseTenantModel):
    """اقدام اصلاحی یا تشویقی مرتبط با یک رخداد."""

    incident = models.ForeignKey(
        BehaviorIncident, on_delete=models.CASCADE, related_name="actions"
    )
    action_type = models.CharField(max_length=25, choices=BehaviorActionType.choices)
    details = models.TextField(blank=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_until = models.DateField(null=True, blank=True)
    assigned_by_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=20, default="PLANNED")
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("اقدام انضباطی")
        verbose_name_plural = _("اقدامات انضباطی")
        ordering = ("-created_at",)


# ===========================================================================
# کتابخانه
# ===========================================================================
class LibraryTitle(BaseTenantModel):
    """عنوان منبع کتابخانه."""

    isbn = models.CharField(max_length=20, blank=True, db_index=True)
    title = models.CharField(max_length=300)
    author = models.CharField(max_length=250, blank=True)
    publisher = models.CharField(max_length=200, blank=True)
    publish_year = models.PositiveSmallIntegerField(null=True, blank=True)
    material_type = models.CharField(
        max_length=15, choices=MaterialType.choices, default=MaterialType.BOOK
    )
    classification = models.CharField(
        max_length=60, blank=True, verbose_name=_("رده‌بندی")
    )
    subject = models.CharField(max_length=200, blank=True)
    language = models.CharField(max_length=10, default="fa")

    class Meta:
        verbose_name = _("عنوان کتابخانه")
        verbose_name_plural = _("عناوین کتابخانه")
        ordering = ("title",)

    def __str__(self) -> str:
        return self.title


class LibraryCopy(BaseTenantModel):
    """نسخه فیزیکی یک عنوان."""

    title_ref = models.ForeignKey(
        LibraryTitle, on_delete=models.CASCADE, related_name="copies"
    )
    barcode = models.CharField(max_length=60, db_index=True)
    location = models.CharField(max_length=100, blank=True, verbose_name=_("محل قفسه"))
    is_loanable = models.BooleanField(default=True, verbose_name=_("قابل امانت"))
    acquisition_cost = models.BigIntegerField(default=0)
    status = models.CharField(
        max_length=15, choices=CopyStatus.choices, default=CopyStatus.AVAILABLE
    )

    class Meta:
        verbose_name = _("نسخه کتابخانه")
        verbose_name_plural = _("نسخه‌های کتابخانه")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "barcode"], name="uq_library_copy_barcode"
            )
        ]

    def __str__(self) -> str:
        return f"{self.barcode} — {self.title_ref.title}"


class LibraryLoan(BaseTenantModel):
    """امانت کتاب."""

    copy = models.ForeignKey(
        LibraryCopy, on_delete=models.PROTECT, related_name="loans"
    )
    borrower_person = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name="library_loans"
    )
    loaned_at = models.DateTimeField()
    due_at = models.DateTimeField(db_index=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    renewal_count = models.PositiveSmallIntegerField(default=0)
    fine_amount = models.BigIntegerField(default=0, verbose_name=_("جریمه (ریال)"))
    fine_paid = models.BooleanField(default=False)
    status = models.CharField(
        max_length=15, choices=LoanStatus.choices, default=LoanStatus.ACTIVE
    )
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("امانت کتابخانه")
        verbose_name_plural = _("امانت‌های کتابخانه")
        ordering = ("-loaned_at",)
        indexes = [models.Index(fields=["borrower_person", "status"])]

    def __str__(self) -> str:
        return f"{self.copy.barcode} → {self.borrower_person.full_name}"

    @property
    def is_overdue(self) -> bool:
        from django.utils import timezone

        return self.returned_at is None and timezone.now() > self.due_at


# ===========================================================================
# حمل‌ونقل
# ===========================================================================
class Vehicle(BaseTenantModel):
    """خودرو سرویس."""

    plate_no = models.CharField(max_length=30, db_index=True, verbose_name=_("پلاک"))
    model_name = models.CharField(max_length=120, blank=True)
    capacity = models.PositiveSmallIntegerField(verbose_name=_("ظرفیت"))
    inspection_valid_until = models.DateField(
        null=True, blank=True, verbose_name=_("اعتبار معاینه فنی")
    )
    insurance_valid_until = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, default="ACTIVE")

    class Meta:
        verbose_name = _("خودرو")
        verbose_name_plural = _("خودروها")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "plate_no"], name="uq_vehicle_plate"
            )
        ]

    def __str__(self) -> str:
        return self.plate_no


class TransportRoute(BaseTenantModel):
    """مسیر سرویس."""

    campus = models.ForeignKey(
        Campus, on_delete=models.PROTECT, related_name="transport_routes"
    )
    code = models.CharField(max_length=30, db_index=True)
    title = models.CharField(max_length=150)
    direction = models.CharField(
        max_length=15, choices=RouteDirection.choices, default=RouteDirection.BOTH
    )
    default_vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_routes",
    )
    default_driver_employee_id = models.UUIDField(null=True, blank=True)
    monthly_fee = models.BigIntegerField(default=0)
    status = models.CharField(max_length=20, default="ACTIVE")

    class Meta:
        verbose_name = _("مسیر سرویس")
        verbose_name_plural = _("مسیرهای سرویس")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="uq_transport_route_code"
            )
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.title}"

    @property
    def active_rider_count(self) -> int:
        return self.student_assignments.filter(status="ACTIVE").count()


class RouteStop(BaseTenantModel):
    """ایستگاه مسیر."""

    route = models.ForeignKey(
        TransportRoute, on_delete=models.CASCADE, related_name="stops"
    )
    title = models.CharField(max_length=200)
    address_line = models.CharField(max_length=300, blank=True)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    sequence_no = models.PositiveSmallIntegerField()
    scheduled_time = models.TimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("ایستگاه")
        verbose_name_plural = _("ایستگاه‌ها")
        ordering = ("sequence_no",)
        constraints = [
            models.UniqueConstraint(
                fields=["route", "sequence_no"], name="uq_route_stop_sequence"
            )
        ]

    def __str__(self) -> str:
        return f"{self.sequence_no}. {self.title}"


class StudentRouteAssignment(BaseTenantModel, EffectiveDatedModel):
    """انتساب دانش‌آموز به مسیر سرویس."""

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="route_assignments"
    )
    route = models.ForeignKey(
        TransportRoute, on_delete=models.PROTECT, related_name="student_assignments"
    )
    pickup_stop = models.ForeignKey(
        RouteStop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pickup_assignments",
    )
    dropoff_stop = models.ForeignKey(
        RouteStop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dropoff_assignments",
    )
    status = models.CharField(max_length=20, default="ACTIVE", db_index=True)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("انتساب سرویس")
        verbose_name_plural = _("انتساب‌های سرویس")
        ordering = ("-effective_from",)
        indexes = [models.Index(fields=["route", "status"])]

    def __str__(self) -> str:
        return f"{self.student.full_name} → {self.route.code}"


class RouteRun(BaseTenantModel):
    """اجرای روزانه یک مسیر."""

    route = models.ForeignKey(
        TransportRoute, on_delete=models.PROTECT, related_name="runs"
    )
    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.PROTECT, related_name="runs"
    )
    driver_employee_id = models.UUIDField(null=True, blank=True)
    supervisor_employee_id = models.UUIDField(null=True, blank=True)
    run_date = models.DateField(db_index=True)
    direction = models.CharField(max_length=15, choices=RouteDirection.choices)
    departed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=15, choices=RouteRunStatus.choices, default=RouteRunStatus.PLANNED
    )
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("اجرای مسیر")
        verbose_name_plural = _("اجراهای مسیر")
        ordering = ("-run_date",)
        constraints = [
            models.UniqueConstraint(
                fields=["route", "run_date", "direction"], name="uq_route_run_day"
            )
        ]

    def __str__(self) -> str:
        return f"{self.route.code} @ {self.run_date}"


class RidershipEvent(BaseTenantModel):
    """
    رخداد سوار/پیاده شدن.

    بخش ۷.۱۰: «نبود رخداد دستگاه به‌تنهایی اثبات غیبت نیست.»
    """

    route_run = models.ForeignKey(
        RouteRun, on_delete=models.CASCADE, related_name="ridership_events"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="ridership_events"
    )
    stop = models.ForeignKey(
        RouteStop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ridership_events",
    )
    event_type = models.CharField(max_length=15, choices=RidershipEventType.choices)
    occurred_at = models.DateTimeField()
    source = models.CharField(
        max_length=15, choices=EventSource.choices, default=EventSource.MANUAL
    )
    guardian_notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("رخداد سرویس")
        verbose_name_plural = _("رخدادهای سرویس")
        ordering = ("-occurred_at",)
        indexes = [models.Index(fields=["route_run", "student"])]

    def __str__(self) -> str:
        return f"{self.student.full_name}: {self.get_event_type_display()}"
