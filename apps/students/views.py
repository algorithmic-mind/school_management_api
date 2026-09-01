"""Viewهای ماژول امور دانش‌آموزان."""

from __future__ import annotations

import django_filters as filters
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleViolation
from apps.core.serializers import ErrorResponseSerializer, OperationResultSerializer
from apps.core.viewsets import BaseModelViewSet, BaseReadOnlyViewSet
from apps.organization.models import ClassGroup
from apps.students import services
from apps.students.enums import AdmissionStatus, ConsentStatus, EnrollmentStatus
from apps.students.models import (
    AdmissionApplication,
    ClassMembership,
    Consent,
    Enrollment,
    Guardian,
    PromotionBatch,
    PromotionDecisionRecord,
    Student,
    StudentGuardian,
    StudentStatusHistory,
    StudentTransfer,
)
from apps.students.serializers import (
    AdmissionApplicationSerializer,
    AdmissionDecisionSerializer,
    ClassMembershipSerializer,
    ConsentSerializer,
    ConvertAdmissionSerializer,
    EnrollmentSerializer,
    GuardianSerializer,
    PlaceInClassSerializer,
    PromotionBatchSerializer,
    PromotionDecisionRecordSerializer,
    PromotionPreviewSerializer,
    Student360Serializer,
    StudentGuardianSerializer,
    StudentListSerializer,
    StudentSerializer,
    StudentStatusHistorySerializer,
    StudentTransferSerializer,
    TransferClassSerializer,
    WithdrawSerializer,
)

ERRORS = {
    400: OpenApiResponse(ErrorResponseSerializer, description="داده ورودی معتبر نیست"),
    403: OpenApiResponse(ErrorResponseSerializer, description="بدون مجوز"),
    404: OpenApiResponse(ErrorResponseSerializer, description="یافت نشد"),
    409: OpenApiResponse(ErrorResponseSerializer, description="گذار وضعیت نامعتبر"),
    422: OpenApiResponse(ErrorResponseSerializer, description="نقض قاعده کسب‌وکار"),
}


class StudentFilter(filters.FilterSet):
    academic_year = filters.UUIDFilter(
        field_name="enrollments__academic_year_id", label="سال تحصیلی"
    )
    class_group = filters.UUIDFilter(
        field_name="enrollments__class_memberships__class_group_id",
        label="کلاس",
    )
    grade_level = filters.UUIDFilter(
        field_name="enrollments__grade_level_id", label="پایه"
    )
    campus = filters.UUIDFilter(field_name="enrollments__campus_id", label="شعبه")
    gender = filters.CharFilter(field_name="person__gender")
    enrollment_status = filters.CharFilter(field_name="enrollments__status")

    class Meta:
        model = Student
        fields = ("status", "student_no")


@extend_schema_view(
    list=extend_schema(
        tags=["Students"],
        summary="فهرست دانش‌آموزان",
        description=(
            "فهرست اصلی دانش‌آموزان با فیلترهای سال، شعبه، پایه، کلاس و وضعیت "
            "(بخش ۱۲.۲ سند تحلیل). هر ردیف شامل کلاس و پایه جاری است تا فرانت "
            "نیازی به درخواست اضافی نداشته باشد."
        ),
        parameters=[
            OpenApiParameter("academic_year", str, description="شناسه سال تحصیلی"),
            OpenApiParameter("class_group", str, description="شناسه کلاس"),
            OpenApiParameter("grade_level", str, description="شناسه پایه"),
            OpenApiParameter("search", str, description="جست‌وجو در نام و شماره دانش‌آموزی"),
        ],
        responses={200: StudentListSerializer, **ERRORS},
    ),
    retrieve=extend_schema(tags=["Students"], summary="جزئیات دانش‌آموز"),
    create=extend_schema(tags=["Students"], summary="ایجاد پرونده دانش‌آموز"),
    update=extend_schema(tags=["Students"], summary="ویرایش پرونده دانش‌آموز"),
    destroy=extend_schema(tags=["Students"], summary="حذف نرم پرونده دانش‌آموز"),
)
class StudentViewSet(BaseModelViewSet):
    queryset = Student.objects.select_related("person").prefetch_related(
        "enrollments__grade_level", "guardian_links__guardian__person"
    )
    serializer_class = StudentSerializer
    filterset_class = StudentFilter
    search_fields = (
        "student_no",
        "person__first_name",
        "person__last_name",
        "person__national_id",
    )
    ordering_fields = ("student_no", "joined_on", "created_at")
    permission_resource = "student"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    self_student_field = "id"

    def get_serializer_class(self):
        if self.action == "list":
            return StudentListSerializer
        return StudentSerializer

    def perform_create(self, serializer):
        from apps.core.context import get_current_context

        ctx = get_current_context()
        student_no = services.generate_student_no(
            ctx.tenant_id if ctx else None,
            serializer.validated_data.get("joined_on"),
        )
        serializer.save(tenant_id=ctx.tenant_id if ctx else None, student_no=student_no)

    def check_object_scope(self, request, obj) -> bool:
        """
        قاعده SELF و دسترسی ولی (بخش ۳.۳).

        دانش‌آموز فقط پرونده خود و ولی فقط فرزند مجاز خود را می‌بیند.

        داشتن مجوز `student.read` به‌تنهایی کافی نیست: نقش‌های «دانش‌آموز» و
        «ولی» هم همین مجوز را دارند و اگر مبنای تصمیم قرار می‌گرفت، هر
        دانش‌آموز می‌توانست پرونده هر دانش‌آموز دیگری را با شناسه‌اش بخواند.
        مجوز تعیین می‌کند «کدام نوع داده»، و دامنه تعیین می‌کند «کدام
        رکوردها» — این دو جای هم را نمی‌گیرند.
        """
        from apps.core.context import get_current_context

        user = request.user
        if user.is_superuser:
            return True

        ctx = get_current_context()
        scope = getattr(ctx, "effective_scope", None) if ctx else None
        organizational = scope is not None and not scope.self_only
        if organizational and user.has_perm_code("student.read"):
            return True

        if user.person_id and obj.person_id == user.person_id:
            return True
        return StudentGuardian.objects.filter(
            student=obj,
            guardian__person_id=user.person_id,
            receives_reports=True,
        ).exists()

    @extend_schema(
        tags=["Students"],
        summary="پرونده ۳۶۰ درجه دانش‌آموز",
        description=(
            "همه بخش‌های مجاز پرونده در یک درخواست: هویت، اولیا، ثبت‌نام‌ها، "
            "رضایت‌نامه‌ها و خلاصه حضور/مالی/تحصیلی/سلامت.\n\n"
            "بخش‌هایی که کاربر مجوز دیدنشان را ندارد `null` برمی‌گردند، نه خطا؛ "
            "این کار رندر Tabها را در فرانت ساده می‌کند (بخش ۷.۲ سند فرانت)."
        ),
        responses={200: Student360Serializer, **ERRORS},
    )
    @action(detail=True, methods=["get"], url_path="profile-360")
    def profile_360(self, request, pk=None):
        student = self.get_object()
        user = request.user

        def allowed(code: str) -> bool:
            return user.is_superuser or user.has_perm_code(code)

        enrollments = student.enrollments.select_related(
            "academic_year", "grade_level", "campus"
        )

        payload = {
            "student": StudentListSerializer(student).data,
            "person": None,
            "guardians": [],
            "enrollments": EnrollmentSerializer(enrollments, many=True).data,
            "consents": [],
            "attendanceSummary": None,
            "financialSummary": None,
            "academicSummary": None,
            "healthSummary": None,
        }

        from apps.identity.serializers import PersonSerializer

        payload["person"] = PersonSerializer(student.person).data

        if allowed("guardian.read"):
            payload["guardians"] = StudentGuardianSerializer(
                student.guardian_links.select_related("guardian__person"), many=True
            ).data

        if allowed("consent.read"):
            payload["consents"] = ConsentSerializer(
                student.consents.all(), many=True
            ).data

        if allowed("attendance.read"):
            payload["attendanceSummary"] = self._attendance_summary(student)

        if allowed("invoice.read"):
            payload["financialSummary"] = self._financial_summary(student)

        if allowed("grade.read"):
            payload["academicSummary"] = self._academic_summary(student)

        if allowed("health.read"):
            payload["healthSummary"] = self._health_summary(student)

        return Response(payload)

    # -- خلاصه‌های مشتق‌شده (بخش ۱۱.۵: داده محاسباتی) --------------------
    @staticmethod
    def _attendance_summary(student) -> dict:
        from django.db.models import Count

        from apps.teaching.models import AttendanceRecord

        rows = (
            AttendanceRecord.objects.filter(enrollment__student=student)
            .values("attendance_status")
            .annotate(count=Count("id"))
        )
        counts = {row["attendance_status"]: row["count"] for row in rows}
        total = sum(counts.values())
        present = counts.get("PRESENT", 0) + counts.get("LATE", 0)
        return {
            "totalSessions": total,
            "byStatus": counts,
            "presentPercent": round(present * 100 / total, 1) if total else None,
        }

    @staticmethod
    def _financial_summary(student) -> dict:
        """
        خلاصه مالی دانش‌آموز.

        صورتحساب پیش‌نویس و لغوشده مطالبه رسمی نیستند و در جمع نمی‌آیند —
        همان قاعده‌ای که در `StudentFinancialAgreement.total_invoiced` اعمال
        می‌شود، تا عدد پرونده ۳۶۰ با ماژول مالی یکی بماند.
        """
        from django.db.models import Sum

        from apps.finance.enums import InvoiceStatus
        from apps.finance.models import Invoice

        aggregate = (
            Invoice.objects.filter(agreement__enrollment__student=student)
            .exclude(status__in=[InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED])
            .aggregate(total=Sum("total_amount"), paid=Sum("paid_amount"))
        )
        total = aggregate["total"] or 0
        paid = aggregate["paid"] or 0
        return {
            "totalInvoiced": total,
            "totalPaid": paid,
            "balance": total - paid,
            "currency": "IRR",
        }

    @staticmethod
    def _academic_summary(student) -> dict:
        from django.db.models import Avg

        from apps.gradebook.models import CourseResult

        aggregate = CourseResult.objects.filter(
            enrollment__student=student
        ).aggregate(average=Avg("final_score"))
        return {
            "averageScore": (
                float(aggregate["average"]) if aggregate["average"] is not None else None
            )
        }

    @staticmethod
    def _health_summary(student) -> dict:
        from apps.welfare.models import HealthAlert, HealthProfile

        profile = HealthProfile.objects.filter(student=student).first()
        if not profile:
            return {"hasProfile": False, "activeAlerts": 0}
        return {
            "hasProfile": True,
            "bloodType": profile.blood_type,
            "activeAlerts": HealthAlert.objects.filter(
                health_profile=profile, status="ACTIVE"
            ).count(),
        }

    @extend_schema(
        tags=["Students"],
        summary="تاریخچه وضعیت دانش‌آموز",
        responses={200: StudentStatusHistorySerializer(many=True)},
    )
    @action(detail=True, methods=["get"], url_path="status-history")
    def status_history(self, request, pk=None):
        student = self.get_object()
        return Response(
            StudentStatusHistorySerializer(
                student.status_history.all(), many=True
            ).data
        )


@extend_schema_view(
    list=extend_schema(tags=["Students"], summary="فهرست اولیا"),
    create=extend_schema(tags=["Students"], summary="ایجاد پرونده ولی"),
)
class GuardianViewSet(BaseModelViewSet):
    queryset = Guardian.objects.select_related("person")
    serializer_class = GuardianSerializer
    search_fields = ("person__first_name", "person__last_name", "person__national_id")
    permission_resource = "guardian"

    @extend_schema(
        tags=["Students"],
        summary="فرزندان تحت سرپرستی",
        description="برای پرتال ولی: فهرست دانش‌آموزانی که این ولی مجاز به مشاهده آنهاست.",
        responses={200: StudentGuardianSerializer(many=True)},
    )
    @action(detail=True, methods=["get"], url_path="students")
    def students(self, request, pk=None):
        guardian = self.get_object()
        links = guardian.student_links.select_related("student__person")
        return Response(StudentGuardianSerializer(links, many=True).data)


@extend_schema_view(
    list=extend_schema(
        tags=["Students"],
        summary="فهرست روابط ولی و دانش‌آموز",
        description=(
            "این رابطه منبع حقیقت دسترسی ولی است. چهار پرچم `hasCustody`، "
            "`canPickup`، `receivesReports` و `financiallyResponsible` مستقل "
            "از یکدیگرند (بخش ۷.۲)."
        ),
    ),
    create=extend_schema(tags=["Students"], summary="اتصال ولی به دانش‌آموز"),
)
class StudentGuardianViewSet(BaseModelViewSet):
    queryset = StudentGuardian.objects.select_related(
        "student__person", "guardian__person"
    )
    serializer_class = StudentGuardianSerializer
    filterset_fields = (
        "student",
        "guardian",
        "relationship_type",
        "has_custody",
        "can_pickup",
        "receives_reports",
        "financially_responsible",
    )
    permission_resource = "guardian"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    self_student_field = "student"


class AdmissionFilter(filters.FilterSet):
    submitted_from = filters.DateTimeFilter(
        field_name="submitted_at", lookup_expr="gte"
    )
    submitted_to = filters.DateTimeFilter(field_name="submitted_at", lookup_expr="lte")

    class Meta:
        model = AdmissionApplication
        fields = (
            "academic_year",
            "preferred_campus",
            "preferred_grade_level",
            "status",
            "reviewer_id",
        )


@extend_schema_view(
    list=extend_schema(
        tags=["Students"],
        summary="Pipeline پذیرش",
        description="فهرست درخواست‌های پذیرش با فیلتر وضعیت، برای نمای Kanban پذیرش.",
    ),
    retrieve=extend_schema(tags=["Students"], summary="جزئیات درخواست پذیرش"),
    create=extend_schema(tags=["Students"], summary="ثبت درخواست پذیرش (پیش‌ثبت‌نام)"),
)
class AdmissionApplicationViewSet(BaseModelViewSet):
    queryset = AdmissionApplication.objects.select_related(
        "person", "academic_year", "preferred_campus", "preferred_grade_level"
    )
    serializer_class = AdmissionApplicationSerializer
    filterset_class = AdmissionFilter
    search_fields = ("application_no", "person__first_name", "person__last_name")
    ordering_fields = ("created_at", "final_score", "waitlist_rank")
    permission_resource = "admission"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "academic_year__school"
    academic_year_field = "academic_year"
    permission_map = {
        "submit": "admission.update",
        "assign_reviewer": "admission.review",
        "waitlist": "admission.review",
        "accept": "admission.approve",
        "accept_conditionally": "admission.approve",
        "reject": "admission.reject",
        "withdraw": "admission.update",
        "convert": "enrollment.create",
    }

    def _transition(self, action_name: str):
        application = self.get_object()
        services.apply_transition(
            application, services.ADMISSION_TRANSITIONS, action_name, "درخواست پذیرش"
        )
        return application

    @extend_schema(
        tags=["Students"],
        summary="ارسال درخواست پذیرش",
        request=None,
        responses={200: AdmissionApplicationSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        application = self._transition("submit")
        application.submitted_at = timezone.now()
        application.save(update_fields=["submitted_at"])
        return Response(self.get_serializer(application).data)

    @extend_schema(
        tags=["Students"],
        summary="ارجاع به بررسی‌کننده",
        request=None,
        responses={200: AdmissionApplicationSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="assign-reviewer")
    def assign_reviewer(self, request, pk=None):
        application = self._transition("assign_reviewer")
        application.reviewer_id = request.user.id
        application.save(update_fields=["reviewer_id"])
        return Response(self.get_serializer(application).data)

    @extend_schema(
        tags=["Students"],
        summary="انتقال به فهرست انتظار",
        request=None,
        responses={200: AdmissionApplicationSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def waitlist(self, request, pk=None):
        application = self._transition("waitlist")
        last_rank = (
            AdmissionApplication.objects.filter(
                academic_year=application.academic_year,
                status=AdmissionStatus.WAITLISTED,
            )
            .exclude(pk=application.pk)
            .order_by("-waitlist_rank")
            .values_list("waitlist_rank", flat=True)
            .first()
        )
        application.waitlist_rank = (last_rank or 0) + 1
        application.save(update_fields=["waitlist_rank"])
        return Response(self.get_serializer(application).data)

    @extend_schema(
        tags=["Students"],
        summary="پذیرش درخواست",
        request=AdmissionDecisionSerializer,
        responses={200: AdmissionApplicationSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        body = AdmissionDecisionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        application = self._transition("accept")
        application.decision_reason = body.validated_data.get("reason", "")
        application.decided_at = timezone.now()
        application.decided_by_id = request.user.id
        if body.validated_data.get("final_score") is not None:
            application.final_score = body.validated_data["final_score"]
        application.save()
        return Response(self.get_serializer(application).data)

    @extend_schema(
        tags=["Students"],
        summary="پذیرش مشروط",
        request=AdmissionDecisionSerializer,
        responses={200: AdmissionApplicationSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="accept-conditionally")
    def accept_conditionally(self, request, pk=None):
        body = AdmissionDecisionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        application = self._transition("accept_conditionally")
        application.conditions = body.validated_data.get("conditions", "")
        application.save(update_fields=["conditions"])
        return Response(self.get_serializer(application).data)

    @extend_schema(
        tags=["Students"],
        summary="رد درخواست",
        request=AdmissionDecisionSerializer,
        responses={200: AdmissionApplicationSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        body = AdmissionDecisionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        application = self._transition("reject")
        application.decision_reason = body.validated_data.get("reason", "")
        application.decided_at = timezone.now()
        application.decided_by_id = request.user.id
        application.save()
        return Response(self.get_serializer(application).data)

    @extend_schema(
        tags=["Students"],
        summary="تبدیل پذیرش به ثبت‌نام",
        description=(
            "پرونده دانش‌آموز (در صورت نبود) ساخته می‌شود و ثبت‌نام در وضعیت "
            "«در انتظار مدارک» ایجاد می‌گردد (بخش ۹.۱ و ۹.۲)."
        ),
        request=ConvertAdmissionSerializer,
        responses={201: EnrollmentSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        application = self.get_object()
        body = ConvertAdmissionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        enrollment = services.convert_admission_to_enrollment(
            application, body.validated_data.get("enrolled_on")
        )
        return Response(EnrollmentSerializer(enrollment).data, status=201)


class EnrollmentFilter(filters.FilterSet):
    class_group = filters.UUIDFilter(
        field_name="class_memberships__class_group_id", label="کلاس"
    )

    class Meta:
        model = Enrollment
        fields = ("student", "academic_year", "campus", "grade_level", "program", "status")


@extend_schema_view(
    list=extend_schema(tags=["Students"], summary="فهرست ثبت‌نام‌ها"),
    retrieve=extend_schema(tags=["Students"], summary="جزئیات ثبت‌نام"),
    create=extend_schema(tags=["Students"], summary="ایجاد ثبت‌نام مستقیم"),
)
class EnrollmentViewSet(BaseModelViewSet):
    queryset = Enrollment.objects.select_related(
        "student__person", "academic_year", "campus", "grade_level", "program"
    ).prefetch_related("class_memberships__class_group")
    serializer_class = EnrollmentSerializer
    filterset_class = EnrollmentFilter
    search_fields = (
        "enrollment_no",
        "student__student_no",
        "student__person__first_name",
        "student__person__last_name",
    )
    permission_resource = "enrollment"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "campus__school"
    campus_field = "campus"
    academic_year_field = "academic_year"
    self_student_field = "student"
    permission_map = {
        "approve_documents": "enrollment.update",
        "confirm_finance": "enrollment.update",
        "place_in_class": "enrollment.activate",
        "transfer": "enrollment.transfer",
        "withdraw": "enrollment.withdraw",
        "suspend": "enrollment.update",
        "reinstate": "enrollment.update",
    }

    def perform_create(self, serializer):
        from apps.core.context import get_current_context

        ctx = get_current_context()
        academic_year = serializer.validated_data["academic_year"]
        serializer.save(
            tenant_id=ctx.tenant_id if ctx else None,
            enrollment_no=services.generate_enrollment_no(
                ctx.tenant_id if ctx else None, academic_year
            ),
        )

    @extend_schema(
        tags=["Students"],
        summary="تأیید مدارک ثبت‌نام",
        request=None,
        responses={200: EnrollmentSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="approve-documents")
    def approve_documents(self, request, pk=None):
        enrollment = self.get_object()
        services.apply_transition(
            enrollment, services.ENROLLMENT_TRANSITIONS, "approve_documents", "ثبت‌نام"
        )
        return Response(self.get_serializer(enrollment).data)

    @extend_schema(
        tags=["Students"],
        summary="تأیید شرط مالی ثبت‌نام",
        request=None,
        responses={200: EnrollmentSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="confirm-finance")
    def confirm_finance(self, request, pk=None):
        enrollment = self.get_object()
        services.apply_transition(
            enrollment, services.ENROLLMENT_TRANSITIONS, "confirm_finance", "ثبت‌نام"
        )
        return Response(self.get_serializer(enrollment).data)

    @extend_schema(
        tags=["Students"],
        summary="تخصیص کلاس و فعال‌سازی ثبت‌نام",
        description=(
            "ظرفیت کلاس، تطابق سال تحصیلی و پایه کنترل می‌شود. با موفقیت، "
            "ثبت‌نام از «در انتظار تخصیص کلاس» به «فعال» می‌رود."
        ),
        request=PlaceInClassSerializer,
        responses={200: EnrollmentSerializer, **ERRORS},
        examples=[
            OpenApiExample(
                "خطای تکمیل ظرفیت",
                value={
                    "code": "CLASS_CAPACITY_EXCEEDED",
                    "message": "ظرفیت کلاس تکمیل است.",
                    "correlationId": "3a7f2b9c",
                    "fieldErrors": [{"field": "classGroupId", "reason": "capacity"}],
                    "retryable": False,
                },
                response_only=True,
                status_codes=["422"],
            )
        ],
    )
    @action(detail=True, methods=["post"], url_path="place-in-class")
    def place_in_class(self, request, pk=None):
        enrollment = self.get_object()
        body = PlaceInClassSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        class_group = get_object_or_404(
            ClassGroup, pk=body.validated_data["class_group"]
        )
        services.place_in_class(
            enrollment, class_group, body.validated_data.get("effective_from")
        )
        enrollment.refresh_from_db()
        return Response(self.get_serializer(enrollment).data)

    @extend_schema(
        tags=["Students"],
        summary="انتقال بین کلاس‌ها",
        description="سابقه انتقال ثبت می‌شود و عضویت قبلی بسته می‌گردد (بخش ۹.۱۰).",
        request=TransferClassSerializer,
        responses={200: StudentTransferSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def transfer(self, request, pk=None):
        enrollment = self.get_object()
        body = TransferClassSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        target = get_object_or_404(
            ClassGroup, pk=body.validated_data["target_class_group"]
        )
        transfer = services.transfer_class(
            enrollment,
            target,
            body.validated_data["reason"],
            body.validated_data.get("effective_on"),
        )
        return Response(StudentTransferSerializer(transfer).data)

    @extend_schema(
        tags=["Students"],
        summary="ترک تحصیل",
        request=WithdrawSerializer,
        responses={200: EnrollmentSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        enrollment = self.get_object()
        body = WithdrawSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.withdraw_student(
            enrollment,
            body.validated_data["reason"],
            body.validated_data.get("exit_date"),
        )
        enrollment.refresh_from_db()
        return Response(self.get_serializer(enrollment).data)

    @extend_schema(
        tags=["Students"],
        summary="تعلیق ثبت‌نام",
        request=WithdrawSerializer,
        responses={200: EnrollmentSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        enrollment = self.get_object()
        services.apply_transition(
            enrollment, services.ENROLLMENT_TRANSITIONS, "suspend", "ثبت‌نام"
        )
        return Response(self.get_serializer(enrollment).data)

    @extend_schema(
        tags=["Students"],
        summary="بازگشت از تعلیق",
        request=None,
        responses={200: EnrollmentSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def reinstate(self, request, pk=None):
        enrollment = self.get_object()
        services.apply_transition(
            enrollment, services.ENROLLMENT_TRANSITIONS, "reinstate", "ثبت‌نام"
        )
        return Response(self.get_serializer(enrollment).data)


@extend_schema_view(
    list=extend_schema(
        tags=["Students"],
        summary="فهرست عضویت‌های کلاس",
        description="برای ساخت لیست حضور و غیاب و فهرست دانش‌آموزان یک کلاس.",
    )
)
class ClassMembershipViewSet(BaseModelViewSet):
    queryset = ClassMembership.objects.select_related(
        "enrollment__student__person", "class_group"
    )
    serializer_class = ClassMembershipSerializer
    filterset_fields = ("enrollment", "class_group", "status", "is_primary")
    permission_resource = "enrollment"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "enrollment__campus__school"
    campus_field = "enrollment__campus"
    academic_year_field = "enrollment__academic_year"
    class_group_field = "class_group"
    self_student_field = "enrollment__student"


@extend_schema_view(
    list=extend_schema(tags=["Students"], summary="فهرست رضایت‌نامه‌ها"),
    create=extend_schema(
        tags=["Students"],
        summary="ثبت رضایت‌نامه",
        description="نسخه متن سیاست در زمان اخذ رضایت Snapshot می‌شود (بخش ۷.۲).",
    ),
)
class ConsentViewSet(BaseModelViewSet):
    queryset = Consent.objects.select_related("student__person", "guardian__person")
    serializer_class = ConsentSerializer
    filterset_fields = ("student", "guardian", "consent_type", "status")
    permission_resource = "consent"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    self_student_field = "student"
    permission_map = {"revoke": "consent.revoke"}

    @extend_schema(
        tags=["Students"],
        summary="لغو رضایت‌نامه",
        description="رضایت لغوشده حذف نمی‌شود؛ فقط وضعیت آن تغییر می‌کند (بخش ۷.۲).",
        request=WithdrawSerializer,
        responses={200: ConsentSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        consent = self.get_object()
        body = WithdrawSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        if consent.status != ConsentStatus.GRANTED:
            raise BusinessRuleViolation(
                code="CONSENT_NOT_ACTIVE",
                message="فقط رضایت فعال قابل لغو است.",
            )
        consent.status = ConsentStatus.REVOKED
        consent.revoked_at = timezone.now()
        consent.revoke_reason = body.validated_data["reason"]
        consent.save()
        return Response(self.get_serializer(consent).data)


@extend_schema_view(
    list=extend_schema(tags=["Students"], summary="سوابق انتقال دانش‌آموزان")
)
class StudentTransferViewSet(BaseReadOnlyViewSet):
    queryset = StudentTransfer.objects.select_related(
        "student__person", "from_class_group", "to_class_group"
    )
    serializer_class = StudentTransferSerializer
    filterset_fields = ("student", "enrollment", "transfer_type")
    permission_resource = "enrollment"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "enrollment__campus__school"
    campus_field = "enrollment__campus"
    academic_year_field = "enrollment__academic_year"
    self_student_field = "enrollment__student"


@extend_schema_view(
    list=extend_schema(tags=["Students"], summary="دسته‌های ارتقای پایه"),
    create=extend_schema(tags=["Students"], summary="ایجاد دسته ارتقای پایه"),
)
class PromotionBatchViewSet(BaseModelViewSet):
    queryset = PromotionBatch.objects.select_related("source_year", "target_year")
    serializer_class = PromotionBatchSerializer
    filterset_fields = ("source_year", "target_year", "status")
    permission_resource = "enrollment"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "source_year__school"
    academic_year_field = "source_year"
    permission_map = {"preview": "enrollment.read", "commit": "enrollment.create"}

    @extend_schema(
        tags=["Students"],
        summary="پیش‌نمایش ارتقای پایه",
        description=(
            "مرحله اول عملیات گروهی (بخش ۱۱.۶): تصمیم پیشنهادی هر دانش‌آموز "
            "بدون هیچ تغییری در داده. مرحله دوم `commit` است."
        ),
        request=None,
        responses={200: PromotionPreviewSerializer, **ERRORS},
    )
    @action(detail=True, methods=["get"], url_path="preview")
    def preview(self, request, pk=None):
        batch = self.get_object()
        rows = services.preview_promotion(batch)
        return Response(
            {
                "totalRows": len(rows),
                "validRows": sum(1 for row in rows if not row["errors"]),
                "invalidRows": sum(1 for row in rows if row["errors"]),
                "rows": rows,
            }
        )

    @extend_schema(
        tags=["Students"],
        summary="ثبت تصمیم‌های ارتقا",
        description=(
            "تصمیم‌های پیش‌نمایش را به‌صورت رکورد مستقل ذخیره می‌کند. اجرای "
            "واقعی ثبت‌نام سال بعد در گام جداگانه و قابل تکرار انجام می‌شود."
        ),
        request=PromotionDecisionRecordSerializer(many=True),
        responses={200: OperationResultSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="commit")
    def commit(self, request, pk=None):
        batch = self.get_object()
        serializer = PromotionDecisionRecordSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        created = 0
        for row in serializer.validated_data:
            _, was_created = PromotionDecisionRecord.objects.update_or_create(
                batch=batch,
                enrollment=row["enrollment"],
                defaults={
                    "tenant_id": batch.tenant_id,
                    "decision": row["decision"],
                    "target_grade_level": row.get("target_grade_level"),
                    "note": row.get("note", ""),
                },
            )
            created += int(was_created)
        batch.status = "COMMITTED"
        batch.executed_at = timezone.now()
        batch.save(update_fields=["status", "executed_at"])
        return Response({"success": True, "affected": created})


@extend_schema_view(list=extend_schema(tags=["Students"], summary="تصمیم‌های ارتقا"))
class PromotionDecisionRecordViewSet(BaseModelViewSet):
    queryset = PromotionDecisionRecord.objects.select_related(
        "batch", "enrollment__student__person"
    )
    serializer_class = PromotionDecisionRecordSerializer
    filterset_fields = ("batch", "decision", "applied")
    permission_resource = "enrollment"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "batch__source_year__school"
    campus_field = "enrollment__campus"
    academic_year_field = "batch__source_year"
    self_student_field = "enrollment__student"
