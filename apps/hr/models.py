"""
مدل‌های منابع انسانی.

مرجع: بخش ۷.۴ سند تحلیل — ERD «پرسنل، قرارداد، تدریس و کارکرد».

قیدهای مهم:
- مجموع allocation_percent انتساب‌های هم‌زمان معمولاً بیش از ۱۰۰٪ نیست.
- انتساب تدریس باید با صلاحیت معلم، قرارداد فعال و عدم تداخل کنترل شود.
- فیش قطعی مستقیماً ویرایش نمی‌شود؛ اصلاح با فیش مابه‌التفاوت انجام می‌شود.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseTenantModel, EffectiveDatedModel, ImmutableLedgerModel
from apps.hr.enums import (
    AttendanceSource,
    ContractStatus,
    ContractType,
    EmployeeStatus,
    LeaveStatus,
    LeaveType,
    PayrollStatus,
    PayslipItemType,
    PositionType,
    QualificationStatus,
    TeachingResponsibility,
)
from apps.identity.models import Person
from apps.organization.models import Campus, Course, CourseOffering, GradeLevel, School


class Employee(BaseTenantModel):
    """پرونده پرسنلی."""

    person = models.OneToOneField(
        Person, on_delete=models.PROTECT, related_name="employee_profile"
    )
    employee_no = models.CharField(
        max_length=30, db_index=True, verbose_name=_("شماره پرسنلی")
    )
    hired_on = models.DateField(verbose_name=_("تاریخ استخدام"))
    terminated_on = models.DateField(
        null=True, blank=True, verbose_name=_("تاریخ پایان همکاری")
    )
    status = models.CharField(
        max_length=20, choices=EmployeeStatus.choices, default=EmployeeStatus.ONBOARDING
    )
    bank_account_masked = models.CharField(
        max_length=40, blank=True, verbose_name=_("شماره حساب (ماسک‌شده)")
    )
    emergency_contact = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = _("کارمند")
        verbose_name_plural = _("پرسنل")
        ordering = ("employee_no",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "employee_no"], name="uq_employee_tenant_no"
            )
        ]

    def __str__(self) -> str:
        return f"{self.employee_no} — {self.person.full_name}"

    @property
    def full_name(self) -> str:
        return self.person.full_name


class OrgUnit(BaseTenantModel):
    """واحد سازمانی (درختی)."""

    campus = models.ForeignKey(
        Campus, on_delete=models.CASCADE, related_name="org_units"
    )
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )
    code = models.CharField(max_length=30)
    title = models.CharField(max_length=150, verbose_name=_("عنوان واحد"))

    class Meta:
        verbose_name = _("واحد سازمانی")
        verbose_name_plural = _("واحدهای سازمانی")
        constraints = [
            models.UniqueConstraint(
                fields=["campus", "code"], name="uq_orgunit_campus_code"
            )
        ]

    def __str__(self) -> str:
        return self.title


class Position(BaseTenantModel):
    """پست سازمانی."""

    org_unit = models.ForeignKey(
        OrgUnit, on_delete=models.CASCADE, related_name="positions"
    )
    code = models.CharField(max_length=30)
    title = models.CharField(max_length=150, verbose_name=_("عنوان پست"))
    position_type = models.CharField(max_length=20, choices=PositionType.choices)
    headcount = models.PositiveSmallIntegerField(
        default=1, verbose_name=_("تعداد پست مصوب")
    )

    class Meta:
        verbose_name = _("پست سازمانی")
        verbose_name_plural = _("پست‌های سازمانی")
        constraints = [
            models.UniqueConstraint(
                fields=["org_unit", "code"], name="uq_position_unit_code"
            )
        ]

    def __str__(self) -> str:
        return self.title


class EmploymentContract(BaseTenantModel):
    """قرارداد استخدامی."""

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="contracts"
    )
    contract_no = models.CharField(max_length=40, db_index=True)
    contract_type = models.CharField(max_length=20, choices=ContractType.choices)
    starts_on = models.DateField()
    ends_on = models.DateField(null=True, blank=True)
    workload_ratio = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1,
        verbose_name=_("ضریب اشتغال"),
        help_text=_("۱ یعنی تمام‌وقت"),
    )
    base_salary_amount = models.BigIntegerField(
        default=0,
        verbose_name=_("حقوق پایه"),
        help_text=_("به کوچک‌ترین واحد پولی (ریال)"),
    )
    currency = models.CharField(max_length=3, default="IRR")
    status = models.CharField(
        max_length=20, choices=ContractStatus.choices, default=ContractStatus.DRAFT
    )
    termination_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("قرارداد")
        verbose_name_plural = _("قراردادها")
        ordering = ("-starts_on",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "contract_no"], name="uq_contract_tenant_no"
            )
        ]

    def __str__(self) -> str:
        return f"{self.contract_no} — {self.employee.full_name}"


class EmployeeAssignment(BaseTenantModel, EffectiveDatedModel):
    """
    انتساب کارمند به پست و شعبه.

    بخش ۷.۴: «مجموع allocation_percent انتساب‌های هم‌زمان یک کارمند معمولاً
    نباید بیش از ۱۰۰٪ باشد.»
    """

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="assignments"
    )
    position = models.ForeignKey(
        Position, on_delete=models.PROTECT, related_name="assignments"
    )
    campus = models.ForeignKey(
        Campus, on_delete=models.PROTECT, related_name="employee_assignments"
    )
    allocation_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=100, verbose_name=_("درصد تخصیص")
    )
    is_primary = models.BooleanField(default=True, verbose_name=_("انتساب اصلی"))
    cost_center_id = models.UUIDField(
        null=True, blank=True, verbose_name=_("مرکز هزینه")
    )

    class Meta:
        verbose_name = _("انتساب سازمانی")
        verbose_name_plural = _("انتساب‌های سازمانی")
        ordering = ("-effective_from",)
        indexes = [models.Index(fields=["employee", "effective_from"])]

    def __str__(self) -> str:
        return f"{self.employee.full_name} → {self.position.title}"


class TeacherProfile(BaseTenantModel):
    """پرونده معلم."""

    employee = models.OneToOneField(
        Employee, on_delete=models.CASCADE, related_name="teacher_profile"
    )
    required_weekly_hours = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, verbose_name=_("بار موظف هفتگی")
    )
    qualification_status = models.CharField(
        max_length=20,
        choices=QualificationStatus.choices,
        default=QualificationStatus.PENDING,
    )
    specialization = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = _("پرونده معلم")
        verbose_name_plural = _("پرونده‌های معلم")

    def __str__(self) -> str:
        return self.employee.full_name

    @property
    def assigned_weekly_minutes(self) -> int:
        """جمع دقایق هفتگی انتساب‌های تدریس فعال."""
        from apps.organization.models import ScheduleEntry

        total = 0
        entries = ScheduleEntry.objects.filter(teacher_profile_id=self.id)
        for entry in entries:
            start = entry.starts_at.hour * 60 + entry.starts_at.minute
            end = entry.ends_at.hour * 60 + entry.ends_at.minute
            total += max(end - start, 0)
        return total


class TeacherQualification(BaseTenantModel):
    """صلاحیت تدریس یک درس در یک پایه."""

    teacher_profile = models.ForeignKey(
        TeacherProfile, on_delete=models.CASCADE, related_name="qualifications"
    )
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="qualified_teachers"
    )
    grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="teacher_qualifications",
    )
    valid_until = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=QualificationStatus.choices,
        default=QualificationStatus.APPROVED,
    )

    class Meta:
        verbose_name = _("صلاحیت تدریس")
        verbose_name_plural = _("صلاحیت‌های تدریس")
        constraints = [
            models.UniqueConstraint(
                fields=["teacher_profile", "course", "grade_level"],
                name="uq_teacher_course_grade",
            )
        ]

    def __str__(self) -> str:
        return f"{self.teacher_profile} — {self.course.title}"


class TeachingAssignment(BaseTenantModel, EffectiveDatedModel):
    """انتساب معلم به ارائه درس."""

    course_offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="teaching_assignments"
    )
    teacher_profile = models.ForeignKey(
        TeacherProfile, on_delete=models.PROTECT, related_name="teaching_assignments"
    )
    responsibility = models.CharField(
        max_length=20,
        choices=TeachingResponsibility.choices,
        default=TeachingResponsibility.PRIMARY,
    )
    share_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=100, verbose_name=_("سهم تدریس")
    )

    class Meta:
        verbose_name = _("انتساب تدریس")
        verbose_name_plural = _("انتساب‌های تدریس")
        ordering = ("-effective_from",)
        indexes = [models.Index(fields=["course_offering", "teacher_profile"])]

    def __str__(self) -> str:
        return f"{self.teacher_profile} → {self.course_offering}"


class WorkShift(BaseTenantModel):
    """شیفت کاری."""

    campus = models.ForeignKey(Campus, on_delete=models.CASCADE, related_name="shifts")
    title = models.CharField(max_length=100)
    starts_at = models.TimeField()
    ends_at = models.TimeField()
    tolerance_minutes = models.PositiveSmallIntegerField(
        default=10, verbose_name=_("تلورانس تأخیر")
    )

    class Meta:
        verbose_name = _("شیفت کاری")
        verbose_name_plural = _("شیفت‌های کاری")

    def __str__(self) -> str:
        return self.title


class EmployeeAttendance(BaseTenantModel):
    """کارکرد روزانه کارمند."""

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="attendances"
    )
    shift = models.ForeignKey(
        WorkShift, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="attendances",
    )
    work_date = models.DateField(db_index=True)
    check_in_at = models.DateTimeField(null=True, blank=True)
    check_out_at = models.DateTimeField(null=True, blank=True)
    worked_minutes = models.PositiveIntegerField(default=0)
    overtime_minutes = models.PositiveIntegerField(default=0)
    late_minutes = models.PositiveIntegerField(default=0)
    source = models.CharField(
        max_length=15, choices=AttendanceSource.choices, default=AttendanceSource.MANUAL
    )
    status = models.CharField(max_length=20, default="RECORDED")
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("کارکرد کارمند")
        verbose_name_plural = _("کارکرد پرسنل")
        ordering = ("-work_date",)
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "work_date"], name="uq_employee_attendance_date"
            )
        ]

    def __str__(self) -> str:
        return f"{self.employee.full_name} @ {self.work_date}"


class LeaveRequest(BaseTenantModel):
    """درخواست مرخصی/مأموریت."""

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="leave_requests"
    )
    leave_type = models.CharField(max_length=20, choices=LeaveType.choices)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    requested_minutes = models.PositiveIntegerField(default=0)
    reason = models.CharField(max_length=400, blank=True)
    substitute_employee = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="substitute_for_leaves",
        verbose_name=_("جانشین"),
    )
    status = models.CharField(
        max_length=20, choices=LeaveStatus.choices, default=LeaveStatus.DRAFT
    )
    decided_by_id = models.UUIDField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=400, blank=True)

    class Meta:
        verbose_name = _("درخواست مرخصی")
        verbose_name_plural = _("درخواست‌های مرخصی")
        ordering = ("-starts_at",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="ck_leave_end_after_start",
            )
        ]

    def __str__(self) -> str:
        return f"{self.employee.full_name} — {self.get_leave_type_display()}"


class PayrollRun(BaseTenantModel):
    """دوره اجرای حقوق و دستمزد."""

    school = models.ForeignKey(
        School, on_delete=models.PROTECT, related_name="payroll_runs"
    )
    title = models.CharField(max_length=150)
    period_from = models.DateField()
    period_to = models.DateField()
    status = models.CharField(
        max_length=20, choices=PayrollStatus.choices, default=PayrollStatus.DRAFT
    )
    calculated_at = models.DateTimeField(null=True, blank=True)
    approved_by_id = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("اجرای حقوق")
        verbose_name_plural = _("اجراهای حقوق")
        ordering = ("-period_from",)

    def __str__(self) -> str:
        return self.title


class Payslip(ImmutableLedgerModel):
    """
    فیش حقوقی.

    بخش ۷.۴: «فیش قطعی مستقیماً ویرایش نمی‌شود؛ اصلاح با فیش مابه‌التفاوت یا
    اجرای اصلاحی انجام می‌شود.» بنابراین از پایه تغییرناپذیر ارث می‌برد.
    """

    payroll_run = models.ForeignKey(
        PayrollRun, on_delete=models.PROTECT, related_name="payslips"
    )
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="payslips"
    )
    gross_amount = models.BigIntegerField(default=0, verbose_name=_("ناخالص"))
    deduction_amount = models.BigIntegerField(default=0, verbose_name=_("کسورات"))
    net_amount = models.BigIntegerField(default=0, verbose_name=_("خالص پرداختی"))
    currency = models.CharField(max_length=3, default="IRR")
    status = models.CharField(max_length=20, default="DRAFT")
    correction_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="corrections",
        verbose_name=_("فیش مابه‌التفاوت برای"),
    )

    class Meta:
        verbose_name = _("فیش حقوقی")
        verbose_name_plural = _("فیش‌های حقوقی")
        constraints = [
            models.UniqueConstraint(
                fields=["payroll_run", "employee"],
                condition=models.Q(correction_of__isnull=True),
                name="uq_payslip_run_employee",
            )
        ]

    def __str__(self) -> str:
        return f"{self.employee.full_name} — {self.payroll_run.title}"


class PayslipItem(ImmutableLedgerModel):
    """قلم فیش حقوقی."""

    payslip = models.ForeignKey(
        Payslip, on_delete=models.CASCADE, related_name="items"
    )
    item_type = models.CharField(max_length=20, choices=PayslipItemType.choices)
    code = models.CharField(max_length=40)
    title = models.CharField(max_length=150)
    amount = models.BigIntegerField(default=0)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)

    class Meta:
        verbose_name = _("قلم فیش")
        verbose_name_plural = _("اقلام فیش")

    def __str__(self) -> str:
        return f"{self.title}: {self.amount}"
