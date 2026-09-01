"""Viewهای ماژول خدمات دانش‌آموزی."""

from __future__ import annotations

from datetime import timedelta

import django_filters as filters
from django.db import transaction
from django.db.models import Count, Q, Sum
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

from apps.core.exceptions import BusinessRuleViolation, InvalidStateTransition
from apps.core.serializers import ErrorResponseSerializer, OperationResultSerializer
from apps.core.viewsets import BaseModelViewSet, BaseReadOnlyViewSet
from apps.welfare.enums import (
    BehaviorIncidentStatus,
    CopyStatus,
    LoanStatus,
    RouteRunStatus,
)
from apps.welfare.models import (
    BehaviorAction,
    BehaviorIncident,
    CounselingCase,
    CounselingSession,
    HealthAlert,
    HealthIncident,
    HealthProfile,
    LibraryCopy,
    LibraryLoan,
    LibraryTitle,
    RidershipEvent,
    RouteRun,
    RouteStop,
    StudentRouteAssignment,
    TransportRoute,
    Vehicle,
)
from apps.welfare.serializers import (
    BehaviorActionSerializer,
    BehaviorDecisionSerializer,
    BehaviorIncidentSerializer,
    CounselingCaseSerializer,
    CounselingSessionSerializer,
    CreateLoanSerializer,
    HealthAlertSafeSerializer,
    HealthAlertSerializer,
    HealthIncidentSerializer,
    HealthProfileSerializer,
    LibraryCopySerializer,
    LibraryLoanSerializer,
    LibraryTitleSerializer,
    RidershipEventSerializer,
    RouteManifestSerializer,
    RouteRunSerializer,
    RouteStopSerializer,
    StudentBehaviorSummarySerializer,
    StudentRouteAssignmentSerializer,
    TransportRouteSerializer,
    VehicleSerializer,
)

ERRORS = {
    400: OpenApiResponse(ErrorResponseSerializer, description="داده ورودی معتبر نیست"),
    403: OpenApiResponse(ErrorResponseSerializer, description="بدون مجوز"),
    404: OpenApiResponse(ErrorResponseSerializer, description="یافت نشد"),
    409: OpenApiResponse(ErrorResponseSerializer, description="تعارض وضعیت"),
    422: OpenApiResponse(ErrorResponseSerializer, description="نقض قاعده کسب‌وکار"),
}


# ===========================================================================
# سلامت
# ===========================================================================
@extend_schema_view(
    list=extend_schema(
        tags=["Welfare"],
        summary="پرونده‌های سلامت",
        description=(
            "داده سلامت «بسیار حساس» است و فقط با مجوز `health.read` در "
            "دسترس قرار می‌گیرد (بخش ۱۵.۲)."
        ),
    ),
    create=extend_schema(tags=["Welfare"], summary="ایجاد پرونده سلامت"),
)
class HealthProfileViewSet(BaseModelViewSet):
    queryset = HealthProfile.objects.select_related("student__person").prefetch_related(
        "alerts"
    )
    serializer_class = HealthProfileSerializer
    filterset_fields = ("student", "blood_type", "confidentiality_level")
    search_fields = ("student__student_no", "student__person__last_name")
    permission_resource = "health"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    self_student_field = "student"


@extend_schema_view(
    list=extend_schema(tags=["Welfare"], summary="هشدارهای سلامت"),
    create=extend_schema(tags=["Welfare"], summary="ثبت هشدار سلامت"),
)
class HealthAlertViewSet(BaseModelViewSet):
    queryset = HealthAlert.objects.select_related("health_profile__student__person")
    serializer_class = HealthAlertSerializer
    filterset_fields = ("health_profile", "alert_type", "severity", "status")
    permission_resource = "health"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    self_student_field = "student"
    permission_map = {"for_class": "attendance.read"}

    @extend_schema(
        tags=["Welfare"],
        summary="هشدارهای سلامت یک کلاس (نمای ایمن)",
        description=(
            "برای معلم و مسئول اردو. فقط `safeSummary` برمی‌گردد و "
            "`instructions` (جزئیات پزشکی) حذف می‌شود — بخش ۷.۱۰."
        ),
        parameters=[
            OpenApiParameter(
                "class_group", str, required=True, description="شناسه کلاس"
            )
        ],
        responses={200: HealthAlertSafeSerializer(many=True), **ERRORS},
    )
    @action(detail=False, methods=["get"], url_path="for-class")
    def for_class(self, request):
        class_group_id = request.query_params.get("class_group")
        if not class_group_id:
            raise BusinessRuleViolation(
                code="MISSING_PARAMETER",
                message="پارامتر class_group الزامی است.",
                status_code=400,
            )

        alerts = HealthAlert.objects.filter(
            status="ACTIVE",
            health_profile__student__enrollments__class_memberships__class_group_id=class_group_id,
            health_profile__student__enrollments__class_memberships__status="ACTIVE",
        ).distinct()
        return Response(HealthAlertSafeSerializer(alerts, many=True).data)


@extend_schema_view(
    list=extend_schema(tags=["Welfare"], summary="رخدادهای سلامت"),
    create=extend_schema(
        tags=["Welfare"],
        summary="ثبت رخداد سلامت",
        description="پس از ثبت، اولیای مجاز با پیام حداقلی مطلع می‌شوند (بخش ۱۱.۴).",
    ),
)
class HealthIncidentViewSet(BaseModelViewSet):
    queryset = HealthIncident.objects.select_related("student__person")
    serializer_class = HealthIncidentSerializer
    filterset_fields = ("student", "outcome")
    permission_resource = "health"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    self_student_field = "student"

    def perform_create(self, serializer):
        from apps.workflow.services import notify_student_guardians

        super().perform_create(serializer)
        incident = serializer.instance
        notify_student_guardians(
            incident.student,
            subject="اطلاع‌رسانی مدرسه",
            body=(
                "رخدادی مربوط به سلامت فرزند شما در مدرسه ثبت شد. "
                "برای مشاهده جزئیات وارد پرتال شوید."
            ),
            deep_link=f"/app/students/{incident.student_id}/health",
        )
        incident.guardian_notified_at = timezone.now()
        incident.save(update_fields=["guardian_notified_at"])


# ===========================================================================
# مشاوره
# ===========================================================================
@extend_schema_view(
    list=extend_schema(
        tags=["Welfare"],
        summary="پرونده‌های مشاوره",
        description="داده مشاوره «بسیار حساس» است و دسترسی آن محدود است (بخش ۱۵.۲).",
    ),
    create=extend_schema(tags=["Welfare"], summary="ایجاد پرونده مشاوره"),
)
class CounselingCaseViewSet(BaseModelViewSet):
    queryset = CounselingCase.objects.select_related("student__person")
    serializer_class = CounselingCaseSerializer
    filterset_fields = (
        "student",
        "counselor_employee_id",
        "status",
        "priority",
        "referral_source",
    )
    permission_resource = "counseling"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    self_student_field = "student"

    @extend_schema(
        tags=["Welfare"],
        summary="بستن پرونده مشاوره",
        request=None,
        responses={200: CounselingCaseSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        case = self.get_object()
        case.status = "CLOSED"
        case.closed_on = timezone.localdate()
        case.save(update_fields=["status", "closed_on"])
        return Response(self.get_serializer(case).data)


@extend_schema_view(
    list=extend_schema(
        tags=["Welfare"],
        summary="جلسات مشاوره",
        description=(
            "`protectedNote` فقط برای مشاور صاحب پرونده و نقش‌های دارای مجوز "
            "`counseling.update` پر می‌شود؛ برای بقیه رشته خالی برمی‌گردد."
        ),
    )
)
class CounselingSessionViewSet(BaseModelViewSet):
    queryset = CounselingSession.objects.select_related("case__student__person")
    serializer_class = CounselingSessionSerializer
    filterset_fields = ("case",)
    permission_resource = "counseling"


# ===========================================================================
# انضباط
# ===========================================================================
class BehaviorIncidentFilter(filters.FilterSet):
    date_from = filters.DateTimeFilter(field_name="occurred_at", lookup_expr="gte")
    date_to = filters.DateTimeFilter(field_name="occurred_at", lookup_expr="lte")
    class_group = filters.UUIDFilter(
        field_name="student__enrollments__class_memberships__class_group_id",
        label="کلاس",
    )

    class Meta:
        model = BehaviorIncident
        fields = ("student", "incident_type", "severity", "status")


@extend_schema_view(
    list=extend_schema(
        tags=["Welfare"],
        summary="رخدادهای رفتاری",
        description=(
            "شامل تخلف و تشویق. رخداد در وضعیت «گزارش‌شده» ثبت می‌شود و تا "
            "پیش از تصمیم، اتهام قطعی محسوب نمی‌شود (بخش ۷.۱۰)."
        ),
    ),
    create=extend_schema(tags=["Welfare"], summary="ثبت رخداد رفتاری"),
)
class BehaviorIncidentViewSet(BaseModelViewSet):
    queryset = BehaviorIncident.objects.select_related("student__person").prefetch_related(
        "actions"
    )
    serializer_class = BehaviorIncidentSerializer
    filterset_class = BehaviorIncidentFilter
    permission_resource = "behavior"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    self_student_field = "student"
    permission_map = {
        "investigate": "behavior.update",
        "decide": "behavior.resolve",
        "summary": "behavior.read",
    }

    @extend_schema(
        tags=["Welfare"],
        summary="شروع بررسی رخداد",
        request=None,
        responses={200: BehaviorIncidentSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def investigate(self, request, pk=None):
        incident = self.get_object()
        if incident.status != BehaviorIncidentStatus.REPORTED:
            raise InvalidStateTransition(
                entity="رخداد رفتاری", current=incident.status, action="investigate"
            )
        incident.status = BehaviorIncidentStatus.UNDER_INVESTIGATION
        incident.save(update_fields=["status"])
        return Response(self.get_serializer(incident).data)

    @extend_schema(
        tags=["Welfare"],
        summary="تصمیم درباره رخداد",
        description=(
            "با `substantiated = true` رخداد تأیید و امتیاز اعمال می‌شود؛ "
            "با `false` رخداد رد می‌گردد. مسیر اعتراض مستقل است (بخش ۷.۱۰)."
        ),
        request=BehaviorDecisionSerializer,
        responses={200: BehaviorIncidentSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        incident = self.get_object()
        body = BehaviorDecisionSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        if incident.status not in {
            BehaviorIncidentStatus.REPORTED,
            BehaviorIncidentStatus.UNDER_INVESTIGATION,
        }:
            raise InvalidStateTransition(
                entity="رخداد رفتاری", current=incident.status, action="decide"
            )

        incident.status = (
            BehaviorIncidentStatus.SUBSTANTIATED
            if body.validated_data["substantiated"]
            else BehaviorIncidentStatus.UNSUBSTANTIATED
        )
        incident.investigation_note = body.validated_data.get("investigation_note", "")
        incident.points = body.validated_data.get("points", 0)
        incident.decided_by_id = request.user.id
        incident.decided_at = timezone.now()
        incident.save()
        return Response(self.get_serializer(incident).data)

    @extend_schema(
        tags=["Welfare"],
        summary="خلاصه انضباطی دانش‌آموز",
        parameters=[
            OpenApiParameter("student", str, required=True, description="شناسه دانش‌آموز")
        ],
        responses={200: StudentBehaviorSummarySerializer, **ERRORS},
    )
    @action(detail=False, methods=["get"])
    def summary(self, request):
        student_id = request.query_params.get("student")
        if not student_id:
            raise BusinessRuleViolation(
                code="MISSING_PARAMETER",
                message="پارامتر student الزامی است.",
                status_code=400,
            )

        queryset = self.get_queryset().filter(
            student_id=student_id, status=BehaviorIncidentStatus.SUBSTANTIATED
        )
        by_severity = {
            row["severity"]: row["count"]
            for row in queryset.values("severity").annotate(count=Count("id"))
        }
        first = queryset.first()
        return Response(
            {
                "studentId": student_id,
                "studentName": first.student.person.full_name if first else "",
                "totalPoints": queryset.aggregate(total=Sum("points"))["total"] or 0,
                "incidentCount": queryset.exclude(incident_type="COMMENDATION").count(),
                "commendationCount": queryset.filter(
                    incident_type="COMMENDATION"
                ).count(),
                "bySeverity": by_severity,
            }
        )


@extend_schema_view(
    list=extend_schema(tags=["Welfare"], summary="اقدامات انضباطی"),
    create=extend_schema(tags=["Welfare"], summary="ثبت اقدام انضباطی"),
)
class BehaviorActionViewSet(BaseModelViewSet):
    queryset = BehaviorAction.objects.select_related("incident__student__person")
    serializer_class = BehaviorActionSerializer
    filterset_fields = ("incident", "action_type", "status")
    permission_resource = "behavior"

    def perform_create(self, serializer):
        super().perform_create(serializer)
        incident = serializer.instance.incident
        if incident.status == BehaviorIncidentStatus.SUBSTANTIATED:
            incident.status = BehaviorIncidentStatus.ACTION_TAKEN
            incident.save(update_fields=["status"])


# ===========================================================================
# کتابخانه
# ===========================================================================
@extend_schema_view(
    list=extend_schema(tags=["Welfare"], summary="عناوین کتابخانه"),
    create=extend_schema(tags=["Welfare"], summary="ثبت عنوان جدید"),
)
class LibraryTitleViewSet(BaseModelViewSet):
    queryset = LibraryTitle.objects.prefetch_related("copies")
    serializer_class = LibraryTitleSerializer
    filterset_fields = ("material_type", "language", "classification")
    search_fields = ("title", "author", "isbn", "subject")
    permission_resource = "library"


@extend_schema_view(list=extend_schema(tags=["Welfare"], summary="نسخه‌های کتابخانه"))
class LibraryCopyViewSet(BaseModelViewSet):
    queryset = LibraryCopy.objects.select_related("title_ref")
    serializer_class = LibraryCopySerializer
    filterset_fields = ("title_ref", "status", "is_loanable")
    search_fields = ("barcode", "title_ref__title")
    permission_resource = "library"


class LibraryLoanFilter(filters.FilterSet):
    overdue = filters.BooleanFilter(method="filter_overdue", label="سررسید گذشته")

    class Meta:
        model = LibraryLoan
        fields = ("copy", "borrower_person", "status", "fine_paid")

    def filter_overdue(self, queryset, name, value):
        now = timezone.now()
        if value:
            return queryset.filter(returned_at__isnull=True, due_at__lt=now)
        return queryset.exclude(returned_at__isnull=True, due_at__lt=now)


@extend_schema_view(
    list=extend_schema(
        tags=["Welfare"],
        summary="امانت‌های کتابخانه",
        parameters=[
            OpenApiParameter("overdue", bool, description="فقط امانت‌های سررسید گذشته")
        ],
    )
)
class LibraryLoanViewSet(BaseModelViewSet):
    queryset = LibraryLoan.objects.select_related(
        "copy__title_ref", "borrower_person"
    )
    serializer_class = LibraryLoanSerializer
    filterset_class = LibraryLoanFilter
    permission_resource = "library"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    self_person_field = "borrower_person"
    permission_map = {
        "create_loan": "library.loan",
        "return_loan": "library.return",
        "renew": "library.loan",
    }
    http_method_names = ["get", "post", "patch", "head", "options"]

    @extend_schema(
        tags=["Welfare"],
        summary="ثبت امانت",
        description=(
            "نسخه باید «موجود» و «قابل امانت» باشد. با ثبت امانت، وضعیت نسخه "
            "به «امانت داده‌شده» تغییر می‌کند (بخش ۷.۱۰)."
        ),
        request=CreateLoanSerializer,
        responses={201: LibraryLoanSerializer, **ERRORS},
        examples=[
            OpenApiExample(
                "امانت ۱۴ روزه",
                value={
                    "copy": "1c2d3e4f-5a6b-7c8d-9e0f-1a2b3c4d5e6f",
                    "borrower_person": "2d3e4f5a-6b7c-8d9e-0f1a-2b3c4d5e6f7a",
                    "loan_days": 14,
                },
                request_only=True,
            )
        ],
    )
    @action(detail=False, methods=["post"], url_path="create-loan")
    @transaction.atomic
    def create_loan(self, request):
        from apps.core.context import get_current_context

        body = CreateLoanSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data

        copy = get_object_or_404(
            LibraryCopy.objects.select_for_update(), pk=data["copy"]
        )
        if not copy.is_loanable:
            raise BusinessRuleViolation(
                code="COPY_NOT_LOANABLE",
                message="این نسخه قابل امانت نیست.",
                field_errors=[{"field": "copy", "reason": "not_loanable"}],
            )
        if copy.status != CopyStatus.AVAILABLE:
            raise BusinessRuleViolation(
                code="COPY_NOT_AVAILABLE",
                message=f"وضعیت این نسخه «{copy.get_status_display()}» است و قابل امانت نیست.",
                status_code=409,
            )

        ctx = get_current_context()
        now = timezone.now()
        loan = LibraryLoan.objects.create(
            tenant_id=ctx.tenant_id if ctx else None,
            copy=copy,
            borrower_person_id=data["borrower_person"],
            loaned_at=now,
            due_at=now + timedelta(days=data["loan_days"]),
            status=LoanStatus.ACTIVE,
        )
        copy.status = CopyStatus.ON_LOAN
        copy.save(update_fields=["status"])
        return Response(LibraryLoanSerializer(loan).data, status=201)

    @extend_schema(
        tags=["Welfare"],
        summary="بازگشت امانت",
        description="در صورت تأخیر، جریمه محاسبه و ثبت می‌شود.",
        request=None,
        responses={200: LibraryLoanSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="return")
    @transaction.atomic
    def return_loan(self, request, pk=None):
        loan = self.get_object()
        if loan.status != LoanStatus.ACTIVE:
            raise InvalidStateTransition(
                entity="امانت", current=loan.status, action="return"
            )

        now = timezone.now()
        loan.returned_at = now
        loan.status = LoanStatus.RETURNED
        if now > loan.due_at:
            overdue_days = (now - loan.due_at).days
            loan.fine_amount = overdue_days * 50_000  # ۵ هزار تومان در روز
        loan.save()

        copy = loan.copy
        copy.status = CopyStatus.AVAILABLE
        copy.save(update_fields=["status"])
        return Response(self.get_serializer(loan).data)

    @extend_schema(
        tags=["Welfare"],
        summary="تمدید امانت",
        request=CreateLoanSerializer,
        responses={200: LibraryLoanSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def renew(self, request, pk=None):
        loan = self.get_object()
        if loan.status != LoanStatus.ACTIVE:
            raise InvalidStateTransition(
                entity="امانت", current=loan.status, action="renew"
            )
        if loan.renewal_count >= 2:
            raise BusinessRuleViolation(
                code="RENEWAL_LIMIT_REACHED",
                message="حداکثر تعداد تمدید مجاز استفاده شده است.",
            )
        days = int(request.data.get("loan_days", 14))
        loan.due_at = loan.due_at + timedelta(days=days)
        loan.renewal_count += 1
        loan.save(update_fields=["due_at", "renewal_count"])
        return Response(self.get_serializer(loan).data)


# ===========================================================================
# حمل‌ونقل
# ===========================================================================
@extend_schema_view(
    list=extend_schema(
        tags=["Welfare"],
        summary="خودروها",
        description="`documentsValid` نشان می‌دهد معاینه فنی و بیمه معتبرند یا نه.",
    )
)
class VehicleViewSet(BaseModelViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer
    filterset_fields = ("status",)
    search_fields = ("plate_no", "model_name")
    permission_resource = "transport"


@extend_schema_view(
    list=extend_schema(
        tags=["Welfare"],
        summary="مسیرهای سرویس",
        description="`activeRiderCount` برای کنترل ظرفیت خودرو استفاده می‌شود.",
    ),
    create=extend_schema(tags=["Welfare"], summary="تعریف مسیر سرویس"),
)
class TransportRouteViewSet(BaseModelViewSet):
    queryset = TransportRoute.objects.select_related(
        "campus", "default_vehicle"
    ).prefetch_related("stops")
    serializer_class = TransportRouteSerializer
    filterset_fields = ("campus", "direction", "status")
    search_fields = ("code", "title")
    permission_resource = "transport"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "campus__school"
    campus_field = "campus"


@extend_schema_view(list=extend_schema(tags=["Welfare"], summary="ایستگاه‌های مسیر"))
class RouteStopViewSet(BaseModelViewSet):
    queryset = RouteStop.objects.select_related("route")
    serializer_class = RouteStopSerializer
    filterset_fields = ("route",)
    permission_resource = "transport"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "route__campus__school"
    campus_field = "route__campus"


@extend_schema_view(
    list=extend_schema(tags=["Welfare"], summary="انتساب‌های سرویس"),
    create=extend_schema(
        tags=["Welfare"],
        summary="انتساب دانش‌آموز به مسیر",
        description=(
            "تعداد دانش‌آموزان فعال مسیر نباید از ظرفیت خودرو بیشتر شود و "
            "مدارک خودرو باید معتبر باشد (بخش ۷.۱۰)."
        ),
        responses={201: StudentRouteAssignmentSerializer, **ERRORS},
    ),
)
class StudentRouteAssignmentViewSet(BaseModelViewSet):
    queryset = StudentRouteAssignment.objects.select_related(
        "student__person", "route", "pickup_stop"
    )
    serializer_class = StudentRouteAssignmentSerializer
    filterset_fields = ("student", "route", "status")
    permission_resource = "transport"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "route__campus__school"
    campus_field = "route__campus"
    self_student_field = "student"
    permission_map = {"create": "transport.assign"}

    def perform_create(self, serializer):
        route = serializer.validated_data["route"]
        vehicle = route.default_vehicle

        if vehicle:
            if route.active_rider_count + 1 > vehicle.capacity:
                raise BusinessRuleViolation(
                    code="ROUTE_CAPACITY_EXCEEDED",
                    message=(
                        f"ظرفیت خودرو «{vehicle.plate_no}» برابر {vehicle.capacity} "
                        "است و تکمیل شده."
                    ),
                    field_errors=[{"field": "route", "reason": "capacity"}],
                )

            today = timezone.localdate()
            expired = (
                vehicle.inspection_valid_until
                and vehicle.inspection_valid_until < today
            ) or (
                vehicle.insurance_valid_until
                and vehicle.insurance_valid_until < today
            )
            if expired:
                raise BusinessRuleViolation(
                    code="VEHICLE_DOCUMENTS_EXPIRED",
                    message=f"مدارک خودرو «{vehicle.plate_no}» معتبر نیست.",
                    field_errors=[{"field": "route", "reason": "vehicle_documents"}],
                )

        super().perform_create(serializer)


@extend_schema_view(
    list=extend_schema(tags=["Welfare"], summary="اجراهای مسیر"),
    create=extend_schema(tags=["Welfare"], summary="ثبت اجرای مسیر"),
)
class RouteRunViewSet(BaseModelViewSet):
    queryset = RouteRun.objects.select_related("route", "vehicle")
    serializer_class = RouteRunSerializer
    filterset_fields = ("route", "vehicle", "run_date", "direction", "status")
    permission_resource = "transport"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "route__campus__school"
    campus_field = "route__campus"
    permission_map = {"manifest": "transport.read", "depart": "transport.update", "complete": "transport.update"}

    @extend_schema(
        tags=["Welfare"],
        summary="فهرست مسافران اجرای مسیر",
        description=(
            "دانش‌آموزان منتسب به مسیر با آخرین رخداد سوار/پیاده‌شدن — برای "
            "کنسول راننده و مسئول سرویس (بخش ۱۴.۵ سند فرانت)."
        ),
        responses={200: RouteManifestSerializer, **ERRORS},
    )
    @action(detail=True, methods=["get"])
    def manifest(self, request, pk=None):
        run = self.get_object()
        assignments = StudentRouteAssignment.objects.filter(
            route=run.route, status="ACTIVE"
        ).select_related("student__person", "pickup_stop", "dropoff_stop")

        events = {}
        for event in RidershipEvent.objects.filter(route_run=run).order_by(
            "occurred_at"
        ):
            events[event.student_id] = event

        rows = []
        for assignment in assignments:
            event = events.get(assignment.student_id)
            rows.append(
                {
                    "studentId": assignment.student_id,
                    "studentNo": assignment.student.student_no,
                    "studentName": assignment.student.person.full_name,
                    "pickupStop": (
                        assignment.pickup_stop.title if assignment.pickup_stop else None
                    ),
                    "dropoffStop": (
                        assignment.dropoff_stop.title if assignment.dropoff_stop else None
                    ),
                    "lastEvent": event.event_type if event else None,
                    "lastEventAt": event.occurred_at if event else None,
                }
            )

        return Response(
            {
                "routeRunId": run.id,
                "routeCode": run.route.code,
                "runDate": run.run_date,
                "direction": run.direction,
                "vehiclePlate": run.vehicle.plate_no,
                "capacity": run.vehicle.capacity,
                "riderCount": len(rows),
                "rows": rows,
            }
        )

    @extend_schema(
        tags=["Welfare"],
        summary="اعلام حرکت",
        request=None,
        responses={200: RouteRunSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def depart(self, request, pk=None):
        run = self.get_object()
        run.status = RouteRunStatus.IN_PROGRESS
        run.departed_at = timezone.now()
        run.save(update_fields=["status", "departed_at"])
        return Response(self.get_serializer(run).data)

    @extend_schema(
        tags=["Welfare"],
        summary="پایان اجرای مسیر",
        request=None,
        responses={200: RouteRunSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        run = self.get_object()
        run.status = RouteRunStatus.COMPLETED
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "completed_at"])
        return Response(self.get_serializer(run).data)


@extend_schema_view(
    list=extend_schema(tags=["Welfare"], summary="رخدادهای سرویس"),
    create=extend_schema(
        tags=["Welfare"],
        summary="ثبت سوار/پیاده شدن",
        description=(
            "پس از ثبت، اولیای مجاز مطلع می‌شوند. توجه: نبود رخداد دستگاه "
            "به‌تنهایی اثبات غیبت نیست (بخش ۷.۱۰)."
        ),
    ),
)
class RidershipEventViewSet(BaseModelViewSet):
    queryset = RidershipEvent.objects.select_related(
        "route_run__route", "student__person", "stop"
    )
    serializer_class = RidershipEventSerializer
    filterset_fields = ("route_run", "student", "event_type", "source")
    permission_resource = "transport"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "route_run__route__campus__school"
    campus_field = "route_run__route__campus"

    def perform_create(self, serializer):
        from apps.workflow.services import notify_student_guardians

        super().perform_create(serializer)
        event = serializer.instance
        label = event.get_event_type_display()
        notify_student_guardians(
            event.student,
            subject="اطلاع سرویس مدرسه",
            body=f"وضعیت سرویس فرزند شما: {label}",
            deep_link=f"/app/students/{event.student_id}/transport",
        )
        event.guardian_notified_at = timezone.now()
        event.save(update_fields=["guardian_notified_at"])
