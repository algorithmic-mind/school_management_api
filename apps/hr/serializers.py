"""سریالایزرهای ماژول منابع انسانی."""

from __future__ import annotations

from django.db.models import Sum
from rest_framework import serializers

from apps.core.serializers import AUDIT_FIELDS
from apps.hr.models import (
    Employee,
    EmployeeAssignment,
    EmployeeAttendance,
    EmploymentContract,
    LeaveRequest,
    OrgUnit,
    PayrollRun,
    Payslip,
    PayslipItem,
    Position,
    TeacherProfile,
    TeacherQualification,
    TeachingAssignment,
    WorkShift,
)
from apps.identity.serializers import PersonListSerializer


class OrgUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrgUnit
        fields = ("id", "campus", "parent", "code", "title", *AUDIT_FIELDS[1:])
        read_only_fields = ("id", "created_at", "updated_at", "version")


class PositionSerializer(serializers.ModelSerializer):
    org_unit_title = serializers.CharField(source="org_unit.title", read_only=True)
    position_type_display = serializers.CharField(
        source="get_position_type_display", read_only=True
    )

    class Meta:
        model = Position
        fields = (
            "id",
            "org_unit",
            "org_unit_title",
            "code",
            "title",
            "position_type",
            "position_type_display",
            "headcount",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class EmploymentContractSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source="employee.person.full_name", read_only=True
    )
    contract_type_display = serializers.CharField(
        source="get_contract_type_display", read_only=True
    )

    class Meta:
        model = EmploymentContract
        fields = (
            "id",
            "employee",
            "employee_name",
            "contract_no",
            "contract_type",
            "contract_type_display",
            "starts_on",
            "ends_on",
            "workload_ratio",
            "base_salary_amount",
            "currency",
            "status",
            "termination_reason",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")

    def validate(self, attrs):
        starts_on = attrs.get("starts_on") or getattr(self.instance, "starts_on", None)
        ends_on = attrs.get("ends_on") or getattr(self.instance, "ends_on", None)
        if starts_on and ends_on and ends_on <= starts_on:
            raise serializers.ValidationError(
                {"ends_on": "تاریخ پایان قرارداد باید بعد از تاریخ شروع باشد."}
            )
        return attrs


class EmployeeAssignmentSerializer(serializers.ModelSerializer):
    position_title = serializers.CharField(source="position.title", read_only=True)
    campus_name = serializers.CharField(source="campus.name", read_only=True)

    class Meta:
        model = EmployeeAssignment
        fields = (
            "id",
            "employee",
            "position",
            "position_title",
            "campus",
            "campus_name",
            "allocation_percent",
            "is_primary",
            "cost_center_id",
            "effective_from",
            "effective_to",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")

    def validate(self, attrs):
        """
        بخش ۷.۴: مجموع تخصیص هم‌زمان نباید از ۱۰۰٪ بیشتر شود
        (اضافه‌تخصیص فقط با سیاست و هشدار).
        """
        employee = attrs.get("employee") or getattr(self.instance, "employee", None)
        effective_from = attrs.get("effective_from") or getattr(
            self.instance, "effective_from", None
        )
        percent = attrs.get("allocation_percent") or getattr(
            self.instance, "allocation_percent", 0
        )
        if not (employee and effective_from):
            return attrs

        from django.db.models import Q

        overlapping = EmployeeAssignment.objects.filter(
            employee=employee
        ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=effective_from))
        if self.instance:
            overlapping = overlapping.exclude(pk=self.instance.pk)

        total = overlapping.aggregate(total=Sum("allocation_percent"))["total"] or 0
        if total + percent > 100:
            raise serializers.ValidationError(
                {
                    "allocation_percent": (
                        f"مجموع تخصیص هم‌زمان این کارمند {total + percent}٪ می‌شود "
                        "که از ۱۰۰٪ بیشتر است."
                    )
                }
            )
        return attrs


class TeacherQualificationSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source="course.title", read_only=True)
    grade_level_title = serializers.CharField(
        source="grade_level.title", read_only=True
    )

    class Meta:
        model = TeacherQualification
        fields = (
            "id",
            "teacher_profile",
            "course",
            "course_title",
            "grade_level",
            "grade_level_title",
            "valid_until",
            "status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class TeacherProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="employee.person.full_name", read_only=True)
    employee_no = serializers.CharField(source="employee.employee_no", read_only=True)
    qualifications = TeacherQualificationSerializer(many=True, read_only=True)
    assigned_weekly_minutes = serializers.IntegerField(read_only=True)

    class Meta:
        model = TeacherProfile
        fields = (
            "id",
            "employee",
            "employee_no",
            "full_name",
            "required_weekly_hours",
            "assigned_weekly_minutes",
            "qualification_status",
            "specialization",
            "qualifications",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class TeachingAssignmentSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(
        source="teacher_profile.employee.person.full_name", read_only=True
    )
    course_title = serializers.CharField(
        source="course_offering.course.title", read_only=True
    )
    class_group_code = serializers.CharField(
        source="course_offering.class_group.code", read_only=True
    )

    class Meta:
        model = TeachingAssignment
        fields = (
            "id",
            "course_offering",
            "course_title",
            "class_group_code",
            "teacher_profile",
            "teacher_name",
            "responsibility",
            "share_percent",
            "effective_from",
            "effective_to",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class EmployeeListSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    national_id = serializers.CharField(source="person.national_id", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    primary_position = serializers.SerializerMethodField()
    is_teacher = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = (
            "id",
            "employee_no",
            "full_name",
            "national_id",
            "hired_on",
            "status",
            "status_display",
            "primary_position",
            "is_teacher",
        )

    def get_primary_position(self, obj) -> str | None:
        assignment = obj.assignments.filter(is_primary=True).first()
        return assignment.position.title if assignment else None

    def get_is_teacher(self, obj) -> bool:
        return hasattr(obj, "teacher_profile")


class EmployeeSerializer(serializers.ModelSerializer):
    person_detail = PersonListSerializer(source="person", read_only=True)
    full_name = serializers.CharField(read_only=True)
    contracts = EmploymentContractSerializer(many=True, read_only=True)
    assignments = EmployeeAssignmentSerializer(many=True, read_only=True)

    class Meta:
        model = Employee
        fields = (
            "id",
            "person",
            "person_detail",
            "full_name",
            "employee_no",
            "hired_on",
            "terminated_on",
            "status",
            "bank_account_masked",
            "emergency_contact",
            "contracts",
            "assignments",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class WorkShiftSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkShift
        fields = (
            "id",
            "campus",
            "title",
            "starts_at",
            "ends_at",
            "tolerance_minutes",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class EmployeeAttendanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source="employee.person.full_name", read_only=True
    )

    class Meta:
        model = EmployeeAttendance
        fields = (
            "id",
            "employee",
            "employee_name",
            "shift",
            "work_date",
            "check_in_at",
            "check_out_at",
            "worked_minutes",
            "overtime_minutes",
            "late_minutes",
            "source",
            "status",
            "note",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source="employee.person.full_name", read_only=True
    )
    leave_type_display = serializers.CharField(
        source="get_leave_type_display", read_only=True
    )
    substitute_name = serializers.CharField(
        source="substitute_employee.person.full_name", read_only=True
    )

    class Meta:
        model = LeaveRequest
        fields = (
            "id",
            "employee",
            "employee_name",
            "leave_type",
            "leave_type_display",
            "starts_at",
            "ends_at",
            "requested_minutes",
            "reason",
            "substitute_employee",
            "substitute_name",
            "status",
            "decided_at",
            "decision_note",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "status",
            "decided_at",
            "created_at",
            "updated_at",
            "version",
        )

    def validate(self, attrs):
        starts_at = attrs.get("starts_at") or getattr(self.instance, "starts_at", None)
        ends_at = attrs.get("ends_at") or getattr(self.instance, "ends_at", None)
        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError(
                {"ends_at": "پایان مرخصی باید بعد از شروع آن باشد."}
            )
        return attrs


class PayslipItemSerializer(serializers.ModelSerializer):
    item_type_display = serializers.CharField(
        source="get_item_type_display", read_only=True
    )

    class Meta:
        model = PayslipItem
        fields = (
            "id",
            "payslip",
            "item_type",
            "item_type_display",
            "code",
            "title",
            "amount",
            "quantity",
        )
        read_only_fields = ("id",)


class PayslipSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source="employee.person.full_name", read_only=True
    )
    items = PayslipItemSerializer(many=True, read_only=True)

    class Meta:
        model = Payslip
        fields = (
            "id",
            "payroll_run",
            "employee",
            "employee_name",
            "gross_amount",
            "deduction_amount",
            "net_amount",
            "currency",
            "status",
            "correction_of",
            "items",
            "created_at",
            "version",
        )
        read_only_fields = ("id", "created_at", "version")


class PayrollRunSerializer(serializers.ModelSerializer):
    payslip_count = serializers.IntegerField(source="payslips.count", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = PayrollRun
        fields = (
            "id",
            "school",
            "title",
            "period_from",
            "period_to",
            "status",
            "status_display",
            "calculated_at",
            "approved_at",
            "payslip_count",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "status",
            "calculated_at",
            "approved_at",
            "created_at",
            "updated_at",
            "version",
        )


class LeaveDecisionSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=400, required=False, allow_blank=True)
    substitute_employee = serializers.UUIDField(
        required=False, allow_null=True, help_text="کارمند جانشین در بازه مرخصی"
    )


class TeacherWorkloadSerializer(serializers.Serializer):
    """گزارش بار تدریس معلم (بخش ۱۱.۲ سند فرانت)."""

    teacherProfileId = serializers.UUIDField()
    teacherName = serializers.CharField()
    requiredWeeklyMinutes = serializers.IntegerField()
    assignedWeeklyMinutes = serializers.IntegerField()
    remainingMinutes = serializers.IntegerField()
    offerings = serializers.ListField(child=serializers.DictField())
