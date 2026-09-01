"""Viewهای ماژول منابع انسانی."""

from __future__ import annotations

import django_filters as filters
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleViolation, InvalidStateTransition
from apps.core.serializers import ErrorResponseSerializer, OperationResultSerializer
from apps.core.viewsets import BaseModelViewSet
from apps.hr.enums import ContractStatus, EmployeeStatus, LeaveStatus, PayrollStatus
from apps.hr.models import (
    Employee,
    EmployeeAssignment,
    EmployeeAttendance,
    EmploymentContract,
    LeaveRequest,
    OrgUnit,
    PayrollRun,
    Payslip,
    Position,
    TeacherProfile,
    TeacherQualification,
    TeachingAssignment,
    WorkShift,
)
from apps.hr.serializers import (
    EmployeeAssignmentSerializer,
    EmployeeAttendanceSerializer,
    EmployeeListSerializer,
    EmployeeSerializer,
    EmploymentContractSerializer,
    LeaveDecisionSerializer,
    LeaveRequestSerializer,
    OrgUnitSerializer,
    PayrollRunSerializer,
    PayslipSerializer,
    PositionSerializer,
    TeacherProfileSerializer,
    TeacherQualificationSerializer,
    TeacherWorkloadSerializer,
    TeachingAssignmentSerializer,
    WorkShiftSerializer,
)
from apps.identity.services import record_audit

ERRORS = {
    400: OpenApiResponse(ErrorResponseSerializer, description="داده ورودی معتبر نیست"),
    403: OpenApiResponse(ErrorResponseSerializer, description="بدون مجوز"),
    404: OpenApiResponse(ErrorResponseSerializer, description="یافت نشد"),
    409: OpenApiResponse(ErrorResponseSerializer, description="گذار وضعیت نامعتبر"),
    422: OpenApiResponse(ErrorResponseSerializer, description="نقض قاعده کسب‌وکار"),
}


@extend_schema_view(list=extend_schema(tags=["HR"], summary="واحدهای سازمانی"))
class OrgUnitViewSet(BaseModelViewSet):
    queryset = OrgUnit.objects.select_related("campus", "parent")
    serializer_class = OrgUnitSerializer
    filterset_fields = ("campus", "parent")
    search_fields = ("title", "code")
    permission_resource = "employee"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "campus__school"
    campus_field = "campus"


@extend_schema_view(list=extend_schema(tags=["HR"], summary="پست‌های سازمانی"))
class PositionViewSet(BaseModelViewSet):
    queryset = Position.objects.select_related("org_unit")
    serializer_class = PositionSerializer
    filterset_fields = ("org_unit", "position_type")
    search_fields = ("title", "code")
    permission_resource = "employee"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "org_unit__campus__school"
    campus_field = "org_unit__campus"


class EmployeeFilter(filters.FilterSet):
    campus = filters.UUIDFilter(field_name="assignments__campus_id", label="شعبه")
    position_type = filters.CharFilter(
        field_name="assignments__position__position_type", label="نوع پست"
    )
    is_teacher = filters.BooleanFilter(
        method="filter_is_teacher", label="فقط معلمان"
    )

    class Meta:
        model = Employee
        fields = ("status", "employee_no")

    def filter_is_teacher(self, queryset, name, value):
        return queryset.filter(teacher_profile__isnull=not value)


@extend_schema_view(
    list=extend_schema(
        tags=["HR"],
        summary="فهرست پرسنل",
        description="فهرست کارکنان با پست اصلی و نشانگر معلم بودن (بخش ۱۱.۱ سند فرانت).",
    ),
    retrieve=extend_schema(tags=["HR"], summary="پرونده کارمند"),
    create=extend_schema(tags=["HR"], summary="ایجاد پرونده پرسنلی"),
)
class EmployeeViewSet(BaseModelViewSet):
    queryset = Employee.objects.select_related("person").prefetch_related(
        "contracts", "assignments__position", "teacher_profile"
    )
    serializer_class = EmployeeSerializer
    filterset_class = EmployeeFilter
    search_fields = (
        "employee_no",
        "person__first_name",
        "person__last_name",
        "person__national_id",
    )
    permission_resource = "employee"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    self_person_field = "person"

    def get_serializer_class(self):
        if self.action == "list":
            return EmployeeListSerializer
        return EmployeeSerializer

    @extend_schema(
        tags=["HR"],
        summary="پایان همکاری کارمند",
        description=(
            "قراردادهای فعال بسته می‌شوند و چک‌لیست تسویه دارایی/دسترسی "
            "(Offboarding) باید جداگانه پیگیری شود (بخش ۴.۵)."
        ),
        request=LeaveDecisionSerializer,
        responses={200: EmployeeSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="terminate")
    def terminate(self, request, pk=None):
        employee = self.get_object()
        body = LeaveDecisionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        note = body.validated_data.get("note", "")

        employee.status = EmployeeStatus.TERMINATED
        employee.terminated_on = timezone.localdate()
        employee.save(update_fields=["status", "terminated_on"])
        employee.contracts.filter(status=ContractStatus.ACTIVE).update(
            status=ContractStatus.TERMINATED, termination_reason=note
        )
        record_audit(
            action="UPDATE",
            entity_type="hr.Employee",
            entity_id=employee.id,
            entity_label=str(employee),
            reason=note,
            changes={"status": EmployeeStatus.TERMINATED},
        )
        return Response(self.get_serializer(employee).data)


@extend_schema_view(
    list=extend_schema(tags=["HR"], summary="فهرست قراردادها"),
    create=extend_schema(tags=["HR"], summary="ایجاد قرارداد"),
)
class EmploymentContractViewSet(BaseModelViewSet):
    queryset = EmploymentContract.objects.select_related("employee__person")
    serializer_class = EmploymentContractSerializer
    filterset_fields = ("employee", "contract_type", "status")
    permission_resource = "contract"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    self_person_field = "employee__person"
    permission_map = {"activate": "contract.update", "close": "contract.close"}

    @extend_schema(
        tags=["HR"],
        summary="فعال‌سازی قرارداد",
        request=None,
        responses={200: EmploymentContractSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        contract = self.get_object()
        if contract.status != ContractStatus.DRAFT:
            raise InvalidStateTransition(
                entity="قرارداد", current=contract.status, action="activate"
            )
        contract.status = ContractStatus.ACTIVE
        contract.save(update_fields=["status"])
        contract.employee.status = EmployeeStatus.ACTIVE
        contract.employee.save(update_fields=["status"])
        return Response(self.get_serializer(contract).data)

    @extend_schema(
        tags=["HR"],
        summary="خاتمه قرارداد",
        request=LeaveDecisionSerializer,
        responses={200: EmploymentContractSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        contract = self.get_object()
        body = LeaveDecisionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        contract.status = ContractStatus.TERMINATED
        contract.termination_reason = body.validated_data.get("note", "")
        contract.save(update_fields=["status", "termination_reason"])
        return Response(self.get_serializer(contract).data)


@extend_schema_view(
    list=extend_schema(
        tags=["HR"],
        summary="انتساب‌های سازمانی",
        description="مجموع درصد تخصیص هم‌زمان هر کارمند در زمان ایجاد کنترل می‌شود.",
    )
)
class EmployeeAssignmentViewSet(BaseModelViewSet):
    queryset = EmployeeAssignment.objects.select_related(
        "employee__person", "position", "campus"
    )
    serializer_class = EmployeeAssignmentSerializer
    filterset_fields = ("employee", "position", "campus", "is_primary")
    permission_resource = "employee"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "campus__school"
    campus_field = "campus"


@extend_schema_view(
    list=extend_schema(tags=["HR"], summary="فهرست معلمان"),
    retrieve=extend_schema(tags=["HR"], summary="پرونده معلم"),
)
class TeacherProfileViewSet(BaseModelViewSet):
    queryset = TeacherProfile.objects.select_related("employee__person").prefetch_related(
        "qualifications__course"
    )
    serializer_class = TeacherProfileSerializer
    filterset_fields = ("qualification_status",)
    search_fields = (
        "employee__person__first_name",
        "employee__person__last_name",
        "specialization",
    )
    permission_resource = "employee"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    self_person_field = "employee__person"

    @extend_schema(
        tags=["HR"],
        summary="بار تدریس معلم",
        description=(
            "مقایسه بار موظف با بار انتساب‌یافته، به همراه فهرست ارائه‌های درس. "
            "برای هشدار «اضافه‌بار» در صفحه انتساب تدریس."
        ),
        responses={200: TeacherWorkloadSerializer},
    )
    @action(detail=True, methods=["get"], url_path="workload")
    def workload(self, request, pk=None):
        profile = self.get_object()
        assignments = profile.teaching_assignments.select_related(
            "course_offering__course", "course_offering__class_group"
        )
        required = int(profile.required_weekly_hours * 60)
        assigned = profile.assigned_weekly_minutes
        payload = {
            "teacherProfileId": profile.id,
            "teacherName": profile.employee.person.full_name,
            "requiredWeeklyMinutes": required,
            "assignedWeeklyMinutes": assigned,
            "remainingMinutes": required - assigned,
            "offerings": [
                {
                    "courseOfferingId": str(a.course_offering_id),
                    "course": a.course_offering.course.title,
                    "classGroup": a.course_offering.class_group.code,
                    "responsibility": a.responsibility,
                    "sharePercent": float(a.share_percent),
                }
                for a in assignments
            ],
        }
        return Response(payload)


@extend_schema_view(list=extend_schema(tags=["HR"], summary="صلاحیت‌های تدریس"))
class TeacherQualificationViewSet(BaseModelViewSet):
    queryset = TeacherQualification.objects.select_related(
        "teacher_profile__employee__person", "course", "grade_level"
    )
    serializer_class = TeacherQualificationSerializer
    filterset_fields = ("teacher_profile", "course", "grade_level", "status")
    permission_resource = "teaching_assignment"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "course__school"


@extend_schema_view(
    list=extend_schema(tags=["HR"], summary="انتساب‌های تدریس"),
    create=extend_schema(
        tags=["HR"],
        summary="انتساب معلم به ارائه درس",
        description=(
            "صلاحیت تدریس معلم برای درس و پایه، و وجود قرارداد فعال بررسی "
            "می‌شود (بخش ۷.۴)."
        ),
        responses={201: TeachingAssignmentSerializer, **ERRORS},
    ),
)
class TeachingAssignmentViewSet(BaseModelViewSet):
    queryset = TeachingAssignment.objects.select_related(
        "course_offering__course",
        "course_offering__class_group",
        "teacher_profile__employee__person",
    )
    serializer_class = TeachingAssignmentSerializer
    filterset_fields = ("course_offering", "teacher_profile", "responsibility")
    permission_resource = "teaching_assignment"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "course_offering__course__school"
    campus_field = "course_offering__class_group__campus"
    academic_year_field = "course_offering__term__academic_year"
    class_group_field = "course_offering__class_group"
    course_offering_field = "course_offering"

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._validate_assignment(serializer.instance)

    @staticmethod
    def _validate_assignment(assignment: TeachingAssignment) -> None:
        profile = assignment.teacher_profile
        offering = assignment.course_offering

        has_active_contract = profile.employee.contracts.filter(
            status=ContractStatus.ACTIVE
        ).exists()
        if not has_active_contract:
            raise BusinessRuleViolation(
                code="TEACHER_NO_ACTIVE_CONTRACT",
                message="این معلم قرارداد فعال ندارد.",
                field_errors=[{"field": "teacherProfileId", "reason": "no_active_contract"}],
            )

        qualified = profile.qualifications.filter(
            course=offering.course_id, status="APPROVED"
        ).exists()
        if not qualified:
            raise BusinessRuleViolation(
                code="TEACHER_NOT_QUALIFIED",
                message=(
                    f"صلاحیت تدریس درس «{offering.course.title}» برای این معلم "
                    "ثبت و تأیید نشده است."
                ),
                field_errors=[{"field": "teacherProfileId", "reason": "not_qualified"}],
            )


@extend_schema_view(list=extend_schema(tags=["HR"], summary="شیفت‌های کاری"))
class WorkShiftViewSet(BaseModelViewSet):
    queryset = WorkShift.objects.select_related("campus")
    serializer_class = WorkShiftSerializer
    filterset_fields = ("campus",)
    permission_resource = "employee"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "campus__school"
    campus_field = "campus"


@extend_schema_view(
    list=extend_schema(tags=["HR"], summary="کارکرد پرسنل"),
    create=extend_schema(tags=["HR"], summary="ثبت کارکرد روزانه"),
)
class EmployeeAttendanceViewSet(BaseModelViewSet):
    queryset = EmployeeAttendance.objects.select_related("employee__person", "shift")
    serializer_class = EmployeeAttendanceSerializer
    filterset_fields = ("employee", "work_date", "source", "status")
    ordering_fields = ("work_date",)
    permission_resource = "employee"


@extend_schema_view(
    list=extend_schema(tags=["HR"], summary="درخواست‌های مرخصی"),
    create=extend_schema(tags=["HR"], summary="ثبت درخواست مرخصی"),
)
class LeaveRequestViewSet(BaseModelViewSet):
    queryset = LeaveRequest.objects.select_related(
        "employee__person", "substitute_employee__person"
    )
    serializer_class = LeaveRequestSerializer
    filterset_fields = ("employee", "leave_type", "status")
    ordering_fields = ("starts_at",)
    permission_resource = "leave"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    self_person_field = "employee__person"
    permission_map = {
        "submit": "leave.create",
        "approve": "leave.approve",
        "reject": "leave.approve",
        "cancel": "leave.create",
    }

    @extend_schema(
        tags=["HR"],
        summary="ارسال درخواست مرخصی",
        request=None,
        responses={200: LeaveRequestSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        leave = self.get_object()
        if leave.status != LeaveStatus.DRAFT:
            raise InvalidStateTransition(
                entity="درخواست مرخصی", current=leave.status, action="submit"
            )
        leave.status = LeaveStatus.SUBMITTED
        leave.save(update_fields=["status"])
        return Response(self.get_serializer(leave).data)

    @extend_schema(
        tags=["HR"],
        summary="تأیید مرخصی",
        description=(
            "تأییدکننده نباید خودِ درخواست‌دهنده باشد (تفکیک وظایف — بخش ۱۶.۲)."
        ),
        request=LeaveDecisionSerializer,
        responses={200: LeaveRequestSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        leave = self.get_object()
        body = LeaveDecisionSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        if leave.status != LeaveStatus.SUBMITTED:
            raise InvalidStateTransition(
                entity="درخواست مرخصی", current=leave.status, action="approve"
            )
        if leave.employee.person_id == request.user.person_id:
            raise BusinessRuleViolation(
                code="SEGREGATION_OF_DUTIES",
                message="تأیید مرخصی خودِ کاربر مجاز نیست.",
                status_code=403,
            )

        substitute_id = body.validated_data.get("substitute_employee")
        if substitute_id:
            leave.substitute_employee = get_object_or_404(Employee, pk=substitute_id)
        leave.status = LeaveStatus.APPROVED
        leave.decided_by_id = request.user.id
        leave.decided_at = timezone.now()
        leave.decision_note = body.validated_data.get("note", "")
        leave.save()
        return Response(self.get_serializer(leave).data)

    @extend_schema(
        tags=["HR"],
        summary="رد مرخصی",
        request=LeaveDecisionSerializer,
        responses={200: LeaveRequestSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        leave = self.get_object()
        body = LeaveDecisionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        if leave.status != LeaveStatus.SUBMITTED:
            raise InvalidStateTransition(
                entity="درخواست مرخصی", current=leave.status, action="reject"
            )
        leave.status = LeaveStatus.REJECTED
        leave.decided_by_id = request.user.id
        leave.decided_at = timezone.now()
        leave.decision_note = body.validated_data.get("note", "")
        leave.save()
        return Response(self.get_serializer(leave).data)


@extend_schema_view(
    list=extend_schema(tags=["HR"], summary="اجراهای حقوق و دستمزد"),
    create=extend_schema(tags=["HR"], summary="ایجاد دوره حقوق"),
)
class PayrollRunViewSet(BaseModelViewSet):
    queryset = PayrollRun.objects.select_related("school").prefetch_related("payslips")
    serializer_class = PayrollRunSerializer
    filterset_fields = ("school", "status")
    permission_resource = "payroll"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "school"
    permission_map = {"calculate": "payroll.run", "approve": "payroll.approve"}

    @extend_schema(
        tags=["HR"],
        summary="محاسبه حقوق دوره",
        description=(
            "فیش پایه برای کارکنان دارای قرارداد فعال تولید می‌شود. قواعد قانونی "
            "محل استقرار (بیمه، مالیات) به افزونه محلی سپرده می‌شود (بخش ۲.۲)."
        ),
        request=None,
        responses={200: OperationResultSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def calculate(self, request, pk=None):
        run = self.get_object()
        if run.status not in {PayrollStatus.DRAFT, PayrollStatus.CALCULATED}:
            raise InvalidStateTransition(
                entity="اجرای حقوق", current=run.status, action="calculate"
            )

        contracts = EmploymentContract.objects.filter(
            status=ContractStatus.ACTIVE, employee__tenant_id=run.tenant_id
        ).select_related("employee")

        created = 0
        for contract in contracts:
            gross = contract.base_salary_amount
            _, was_created = Payslip.objects.get_or_create(
                payroll_run=run,
                employee=contract.employee,
                correction_of=None,
                defaults={
                    "tenant_id": run.tenant_id,
                    "gross_amount": gross,
                    "deduction_amount": 0,
                    "net_amount": gross,
                    "currency": contract.currency,
                    "status": "CALCULATED",
                },
            )
            created += int(was_created)

        run.status = PayrollStatus.CALCULATED
        run.calculated_at = timezone.now()
        run.save(update_fields=["status", "calculated_at"])
        return Response(
            {"success": True, "message": "محاسبه انجام شد.", "affected": created}
        )

    @extend_schema(
        tags=["HR"],
        summary="تأیید اجرای حقوق",
        request=None,
        responses={200: PayrollRunSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        run = self.get_object()
        if run.status != PayrollStatus.CALCULATED:
            raise InvalidStateTransition(
                entity="اجرای حقوق", current=run.status, action="approve"
            )
        run.status = PayrollStatus.APPROVED
        run.approved_by_id = request.user.id
        run.approved_at = timezone.now()
        run.save(update_fields=["status", "approved_by_id", "approved_at"])
        return Response(self.get_serializer(run).data)


@extend_schema_view(
    list=extend_schema(
        tags=["HR"],
        summary="فیش‌های حقوقی",
        description="فیش قطعی تغییرناپذیر است؛ اصلاح با فیش مابه‌التفاوت انجام می‌شود.",
    ),
    retrieve=extend_schema(tags=["HR"], summary="جزئیات فیش حقوقی"),
)
class PayslipViewSet(BaseModelViewSet):
    queryset = Payslip.objects.select_related(
        "employee__person", "payroll_run"
    ).prefetch_related("items")
    serializer_class = PayslipSerializer
    filterset_fields = ("payroll_run", "employee", "status")
    permission_resource = "payroll"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "payroll_run__school"
    self_person_field = "employee__person"
    http_method_names = ["get", "post", "head", "options"]

    def perform_destroy(self, instance):  # pragma: no cover - محافظ
        raise BusinessRuleViolation(
            code="PAYSLIP_IMMUTABLE",
            message="فیش حقوقی حذف نمی‌شود؛ از فیش مابه‌التفاوت استفاده کنید.",
        )
