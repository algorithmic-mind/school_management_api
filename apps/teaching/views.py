"""Viewهای ماژول آموزش روزانه، حضور و تکلیف."""

from __future__ import annotations

import django_filters as filters
from django.db import transaction
from django.db.models import Count, Q
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
from apps.core.viewsets import BaseModelViewSet
from apps.identity.services import record_audit
from apps.students.enums import ClassMembershipStatus
from apps.students.models import ClassMembership
from apps.teaching.enums import (
    AssignmentStatus,
    AttendanceStatus,
    FinalizationStatus,
    JustificationDecision,
    SessionStatus,
    SubmissionStatus,
)
from apps.teaching.models import (
    AbsenceJustification,
    Assignment,
    AssignmentSubmission,
    AttendanceRecord,
    LearningResource,
    LessonPlan,
    SessionTeacher,
    SubmissionFeedback,
    TeachingSession,
)
from apps.teaching.serializers import (
    AbsenceJustificationSerializer,
    AmendAttendanceSerializer,
    AssignmentSerializer,
    AssignmentSubmissionSerializer,
    AttendanceMonitorRowSerializer,
    AttendanceRecordSerializer,
    AttendanceRosterSerializer,
    BulkAttendanceSerializer,
    GradeSubmissionSerializer,
    LearningResourceSerializer,
    LessonPlanSerializer,
    SessionTeacherSerializer,
    StudentAttendanceSummarySerializer,
    SubmissionFeedbackSerializer,
    TeachingSessionSerializer,
)

ERRORS = {
    400: OpenApiResponse(ErrorResponseSerializer, description="داده ورودی معتبر نیست"),
    403: OpenApiResponse(ErrorResponseSerializer, description="بدون مجوز"),
    404: OpenApiResponse(ErrorResponseSerializer, description="یافت نشد"),
    409: OpenApiResponse(ErrorResponseSerializer, description="گذار وضعیت نامعتبر"),
    422: OpenApiResponse(ErrorResponseSerializer, description="نقض قاعده کسب‌وکار"),
}

#: نصاب حضور برای هشدار (بخش ۴.۳ — قابل انتقال به تنظیمات مدرسه)
ATTENDANCE_THRESHOLD_PERCENT = 80.0


class TeachingSessionFilter(filters.FilterSet):
    date = filters.DateFilter(field_name="starts_at__date", label="تاریخ جلسه")
    date_from = filters.DateFilter(field_name="starts_at", lookup_expr="gte")
    date_to = filters.DateFilter(field_name="starts_at", lookup_expr="lte")
    class_group = filters.UUIDFilter(
        field_name="course_offering__class_group_id", label="کلاس"
    )
    teacher_profile = filters.UUIDFilter(
        field_name="teachers__teacher_profile_id", label="معلم"
    )
    attendance_pending = filters.BooleanFilter(
        method="filter_attendance_pending", label="حضور ثبت‌نشده"
    )

    class Meta:
        model = TeachingSession
        fields = ("course_offering", "room", "session_type", "status")

    def filter_attendance_pending(self, queryset, name, value):
        if value:
            return queryset.filter(attendance_finalized_at__isnull=True)
        return queryset.filter(attendance_finalized_at__isnull=False)


@extend_schema_view(
    list=extend_schema(
        tags=["Teaching"],
        summary="فهرست جلسات درسی",
        description=(
            "برای صفحه «امروز من» معلم و پایش حضور. با `date` و "
            "`teacher_profile` می‌توان جلسات امروز یک معلم را گرفت."
        ),
        parameters=[
            OpenApiParameter("date", str, description="تاریخ جلسه (YYYY-MM-DD)"),
            OpenApiParameter("teacher_profile", str, description="شناسه پرونده معلم"),
            OpenApiParameter("attendance_pending", bool, description="فقط جلسات بدون حضور نهایی"),
        ],
    ),
    retrieve=extend_schema(tags=["Teaching"], summary="جزئیات جلسه"),
    create=extend_schema(tags=["Teaching"], summary="ایجاد جلسه درسی"),
)
class TeachingSessionViewSet(BaseModelViewSet):
    queryset = TeachingSession.objects.select_related(
        "course_offering__course", "course_offering__class_group", "room"
    ).prefetch_related("teachers__teacher_profile__employee__person")
    serializer_class = TeachingSessionSerializer
    filterset_class = TeachingSessionFilter
    ordering_fields = ("starts_at",)
    permission_resource = "session"
    permission_map = {
        "cancel": "session.cancel",
        "roster": "attendance.read",
        "record_attendance": "attendance.create",
        "finalize_attendance": "attendance.finalize",
    }

    @extend_schema(
        tags=["Teaching"],
        summary="لغو جلسه",
        request=AmendAttendanceSerializer,
        responses={200: TeachingSessionSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        session = self.get_object()
        reason = request.data.get("reason", "")
        if not reason:
            raise BusinessRuleViolation(
                code="REASON_REQUIRED",
                message="ثبت علت لغو جلسه الزامی است.",
                field_errors=[{"field": "reason", "reason": "required"}],
            )
        if session.status in {SessionStatus.HELD, SessionStatus.CANCELLED}:
            raise InvalidStateTransition(
                entity="جلسه درسی", current=session.status, action="cancel"
            )
        session.status = SessionStatus.CANCELLED
        session.cancel_reason = reason
        session.save(update_fields=["status", "cancel_reason"])
        return Response(self.get_serializer(session).data)

    @extend_schema(
        tags=["Teaching"],
        summary="فهرست حضور جلسه",
        description=(
            "فهرست دانش‌آموزان عضو فعال کلاس در زمان جلسه، به‌همراه وضعیت حضور "
            "ثبت‌شده (در صورت وجود). اگر حضور هنوز ثبت نشده باشد، وضعیت پیش‌فرض "
            "`PRESENT` برمی‌گردد تا معلم فقط استثناها را تغییر دهد "
            "(بخش ۸.۴ سند فرانت)."
        ),
        responses={200: AttendanceRosterSerializer, **ERRORS},
    )
    @action(detail=True, methods=["get"], url_path="roster")
    def roster(self, request, pk=None):
        session = self.get_object()
        rows = self._build_roster(session)
        return Response(
            {
                "sessionId": session.id,
                "classGroupCode": session.course_offering.class_group.code,
                "courseTitle": session.course_offering.course.title,
                "startsAt": session.starts_at,
                "finalizationStatus": (
                    FinalizationStatus.FINALIZED
                    if session.attendance_finalized_at
                    else FinalizationStatus.DRAFT
                ),
                "rows": rows,
            }
        )

    @staticmethod
    def _build_roster(session: TeachingSession) -> list[dict]:
        """
        بخش ۷.۵: «حضور فقط برای دانش‌آموزی ثبت می‌شود که در زمان جلسه عضو
        فعال کلاس بوده است.»
        """
        session_date = timezone.localtime(session.starts_at).date()
        memberships = (
            ClassMembership.objects.filter(
                class_group=session.course_offering.class_group,
                effective_from__lte=session_date,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=session_date))
            .filter(status=ClassMembershipStatus.ACTIVE)
            .select_related("enrollment__student__person")
        )

        existing = {
            record.enrollment_id: record
            for record in session.attendance_records.all()
        }

        rows = []
        for membership in memberships:
            enrollment = membership.enrollment
            record = existing.get(enrollment.id)
            rows.append(
                {
                    "enrollmentId": str(enrollment.id),
                    "studentNo": enrollment.student.student_no,
                    "studentName": enrollment.student.person.full_name,
                    "attendanceStatus": (
                        record.attendance_status if record else AttendanceStatus.PRESENT
                    ),
                    "lateMinutes": record.late_minutes if record else 0,
                    "earlyLeaveMinutes": record.early_leave_minutes if record else 0,
                    "reasonCode": record.reason_code if record else "",
                    "note": record.note if record else "",
                }
            )
        return rows

    @extend_schema(
        tags=["Teaching"],
        summary="ثبت گروهی حضور و غیاب",
        description=(
            "همه ردیف‌ها در یک تراکنش ثبت می‌شوند. اگر `finalize=true` باشد، "
            "پس از ثبت، حضور جلسه نهایی می‌گردد و تغییر بعدی نیازمند علت و "
            "مجوز `attendance.update` خواهد بود."
        ),
        request=BulkAttendanceSerializer,
        responses={200: OperationResultSerializer, **ERRORS},
        examples=[
            OpenApiExample(
                "درخواست",
                value={
                    "rows": [
                        {
                            "enrollmentId": "3f1c8a2b-9d4e-4f7a-8b1c-2d3e4f5a6b7c",
                            "attendanceStatus": "PRESENT",
                        },
                        {
                            "enrollmentId": "4a2d9b3c-0e5f-4a8b-9c2d-3e4f5a6b7c8d",
                            "attendanceStatus": "LATE",
                            "lateMinutes": 12,
                            "note": "تأخیر سرویس",
                        },
                        {
                            "enrollmentId": "5b3e0c4d-1f6a-4b9c-0d3e-4f5a6b7c8d9e",
                            "attendanceStatus": "ABSENT",
                            "reasonCode": "UNKNOWN",
                        },
                    ],
                    "finalize": True,
                },
                request_only=True,
            )
        ],
    )
    @action(detail=True, methods=["post"], url_path="attendance")
    @transaction.atomic
    def record_attendance(self, request, pk=None):
        session = self.get_object()
        body = BulkAttendanceSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        # بخش ۷.۵: اصلاح پس از نهایی‌شدن هم مجوز می‌خواهد و هم علت ثبت‌شده.
        is_amendment = bool(session.attendance_finalized_at)
        amend_reason = body.validated_data.get("reason", "")

        if is_amendment:
            if not request.user.has_perm_code("attendance.update"):
                raise BusinessRuleViolation(
                    code="ATTENDANCE_ALREADY_FINALIZED",
                    message="حضور این جلسه نهایی شده است و شما مجوز اصلاح آن را ندارید.",
                    status_code=409,
                )
            if not amend_reason:
                raise BusinessRuleViolation(
                    code="AMENDMENT_REASON_REQUIRED",
                    message=(
                        "حضور این جلسه نهایی شده است؛ برای اصلاح، ثبت علت الزامی است."
                    ),
                    field_errors=[{"field": "reason", "reason": "required"}],
                    status_code=409,
                )

        valid_enrollment_ids = {
            row["enrollmentId"] for row in self._build_roster(session)
        }

        affected = 0
        errors: list[dict[str, str]] = []
        for row in body.validated_data["rows"]:
            enrollment_id = str(row["enrollmentId"])
            if enrollment_id not in valid_enrollment_ids:
                errors.append(
                    {
                        "field": f"rows[{enrollment_id}]",
                        "reason": "دانش‌آموز در زمان این جلسه عضو فعال کلاس نبوده است.",
                    }
                )
                continue

            defaults = {
                "tenant_id": session.tenant_id,
                "attendance_status": row["attendanceStatus"],
                "late_minutes": row.get("lateMinutes", 0),
                "early_leave_minutes": row.get("earlyLeaveMinutes", 0),
                "reason_code": row.get("reasonCode", ""),
                "note": row.get("note", ""),
                "recorded_by_id": request.user.id,
            }
            if is_amendment:
                defaults["finalization_status"] = FinalizationStatus.AMENDED
                defaults["amended_reason"] = amend_reason

            AttendanceRecord.objects.update_or_create(
                session=session, enrollment_id=enrollment_id, defaults=defaults
            )
            affected += 1

        if errors:
            raise BusinessRuleViolation(
                code="ATTENDANCE_ROSTER_MISMATCH",
                message="برخی ردیف‌ها متعلق به این جلسه نیستند.",
                field_errors=errors,
            )

        if is_amendment:
            record_audit(
                action="UPDATE",
                entity_type="teaching.TeachingSession",
                entity_id=session.id,
                entity_label=str(session),
                reason=amend_reason,
                changes={"amendedRows": affected},
            )
        elif body.validated_data.get("finalize"):
            self._finalize(session)

        return Response(
            {
                "success": True,
                "message": "حضور اصلاح شد." if is_amendment else "حضور ثبت شد.",
                "affected": affected,
            }
        )

    @extend_schema(
        tags=["Teaching"],
        summary="نهایی‌سازی حضور جلسه",
        description="پس از نهایی‌سازی، رویداد `AttendanceFinalized` منتشر می‌شود (بخش ۱۳.۱).",
        request=None,
        responses={200: TeachingSessionSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="finalize-attendance")
    def finalize_attendance(self, request, pk=None):
        session = self.get_object()
        self._finalize(session)
        return Response(self.get_serializer(session).data)

    @staticmethod
    def _finalize(session: TeachingSession) -> None:
        from apps.workflow.services import publish_event

        session.attendance_records.update(
            finalization_status=FinalizationStatus.FINALIZED
        )
        session.attendance_finalized_at = timezone.now()
        session.status = SessionStatus.HELD
        session.save(update_fields=["attendance_finalized_at", "status"])

        publish_event(
            aggregate_type="teaching.TeachingSession",
            aggregate_id=session.id,
            event_type="AttendanceFinalized",
            payload={
                "sessionId": str(session.id),
                "courseOfferingId": str(session.course_offering_id),
                "finalizedAt": session.attendance_finalized_at.isoformat(),
            },
            tenant_id=session.tenant_id,
        )


@extend_schema_view(
    list=extend_schema(tags=["Teaching"], summary="معلمان جلسات")
)
class SessionTeacherViewSet(BaseModelViewSet):
    queryset = SessionTeacher.objects.select_related(
        "session", "teacher_profile__employee__person"
    )
    serializer_class = SessionTeacherSerializer
    filterset_fields = ("session", "teacher_profile", "duty")
    permission_resource = "session"


class AttendanceRecordFilter(filters.FilterSet):
    student = filters.UUIDFilter(
        field_name="enrollment__student_id", label="دانش‌آموز"
    )
    class_group = filters.UUIDFilter(
        field_name="session__course_offering__class_group_id", label="کلاس"
    )
    date_from = filters.DateFilter(field_name="session__starts_at", lookup_expr="gte")
    date_to = filters.DateFilter(field_name="session__starts_at", lookup_expr="lte")

    class Meta:
        model = AttendanceRecord
        fields = ("session", "enrollment", "attendance_status", "finalization_status")


@extend_schema_view(
    list=extend_schema(
        tags=["Teaching"],
        summary="رکوردهای حضور",
        description="برای گزارش حضور دانش‌آموز، کلاس یا بازه زمانی.",
    ),
    retrieve=extend_schema(tags=["Teaching"], summary="جزئیات رکورد حضور"),
)
class AttendanceRecordViewSet(BaseModelViewSet):
    queryset = AttendanceRecord.objects.select_related(
        "session__course_offering__course", "enrollment__student__person"
    )
    serializer_class = AttendanceRecordSerializer
    filterset_class = AttendanceRecordFilter
    permission_resource = "attendance"
    permission_map = {"amend": "attendance.update"}

    @extend_schema(
        tags=["Teaching"],
        summary="اصلاح حضور پس از نهایی‌سازی",
        description=(
            "بخش ۷.۵: «اصلاح بعد از نهایی‌شدن نیازمند علت و مجوز است.» "
            "رکورد به وضعیت `AMENDED` می‌رود و تغییر در ممیزی ثبت می‌شود."
        ),
        request=AmendAttendanceSerializer,
        responses={200: AttendanceRecordSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def amend(self, request, pk=None):
        record = self.get_object()
        body = AmendAttendanceSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        previous = record.attendance_status
        record.attendance_status = body.validated_data["attendance_status"]
        record.amended_reason = body.validated_data["reason"]
        record.finalization_status = FinalizationStatus.AMENDED
        record.save()

        record_audit(
            action="UPDATE",
            entity_type="teaching.AttendanceRecord",
            entity_id=record.id,
            entity_label=str(record),
            reason=body.validated_data["reason"],
            changes={"from": previous, "to": record.attendance_status},
        )
        return Response(self.get_serializer(record).data)

    @extend_schema(
        tags=["Teaching"],
        summary="خلاصه حضور دانش‌آموز",
        description=(
            "درصد حضور، شمارش به تفکیک وضعیت و تعداد غیبت متوالی، برای هشدار "
            "نصاب حضور و ارجاع به مشاور (بخش ۴.۳)."
        ),
        parameters=[
            OpenApiParameter(
                "enrollment", str, required=True, description="شناسه ثبت‌نام"
            )
        ],
        responses={200: StudentAttendanceSummarySerializer, **ERRORS},
    )
    @action(detail=False, methods=["get"], url_path="student-summary")
    def student_summary(self, request):
        enrollment_id = request.query_params.get("enrollment")
        if not enrollment_id:
            raise BusinessRuleViolation(
                code="MISSING_PARAMETER",
                message="پارامتر enrollment الزامی است.",
                status_code=400,
            )

        records = (
            self.get_queryset()
            .filter(enrollment_id=enrollment_id)
            .order_by("session__starts_at")
        )
        counts = {
            row["attendance_status"]: row["count"]
            for row in records.values("attendance_status").annotate(count=Count("id"))
        }
        total = sum(counts.values())
        present = counts.get(AttendanceStatus.PRESENT, 0) + counts.get(
            AttendanceStatus.LATE, 0
        )
        percent = round(present * 100 / total, 1) if total else None

        consecutive = 0
        best = 0
        for record in records:
            if record.attendance_status == AttendanceStatus.ABSENT:
                consecutive += 1
                best = max(best, consecutive)
            else:
                consecutive = 0

        first = records.first()
        return Response(
            {
                "enrollmentId": enrollment_id,
                "studentName": (
                    first.enrollment.student.person.full_name if first else ""
                ),
                "totalSessions": total,
                "byStatus": counts,
                "presentPercent": percent,
                "consecutiveAbsences": best,
                "belowThreshold": bool(
                    percent is not None and percent < ATTENDANCE_THRESHOLD_PERCENT
                ),
            }
        )

    @extend_schema(
        tags=["Teaching"],
        summary="پایش حضور کلاس‌ها",
        description=(
            "برای داشبورد «پایش حضور مدرسه» (بخش ۸.۵ سند فرانت): تعداد جلسات "
            "نهایی‌شده و در انتظار هر کلاس در تاریخ مشخص."
        ),
        parameters=[OpenApiParameter("date", str, description="تاریخ (YYYY-MM-DD)")],
        responses={200: AttendanceMonitorRowSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="monitor")
    def monitor(self, request):
        from apps.organization.models import ClassGroup

        target_date = request.query_params.get("date") or timezone.localdate().isoformat()
        sessions = TeachingSession.objects.filter(starts_at__date=target_date)

        rows = []
        class_groups = ClassGroup.objects.filter(
            course_offerings__sessions__starts_at__date=target_date
        ).distinct().select_related("grade_level")

        for class_group in class_groups:
            group_sessions = sessions.filter(
                course_offering__class_group=class_group
            )
            finalized = group_sessions.filter(
                attendance_finalized_at__isnull=False
            ).count()
            total = group_sessions.count()
            absent_today = AttendanceRecord.objects.filter(
                session__in=group_sessions,
                attendance_status=AttendanceStatus.ABSENT,
            ).count()
            rows.append(
                {
                    "classGroupId": class_group.id,
                    "classGroupCode": class_group.code,
                    "gradeLevel": class_group.grade_level.title,
                    "totalSessions": total,
                    "finalizedSessions": finalized,
                    "pendingSessions": total - finalized,
                    "absentToday": absent_today,
                }
            )
        return Response(rows)


@extend_schema_view(
    list=extend_schema(tags=["Teaching"], summary="درخواست‌های توجیه غیبت"),
    create=extend_schema(
        tags=["Teaching"],
        summary="ثبت درخواست توجیه غیبت",
        description="معمولاً توسط ولی از پرتال ثبت می‌شود (بخش ۴.۳).",
    ),
)
class AbsenceJustificationViewSet(BaseModelViewSet):
    queryset = AbsenceJustification.objects.select_related(
        "attendance__enrollment__student__person", "attendance__session"
    )
    serializer_class = AbsenceJustificationSerializer
    filterset_fields = ("decision",)
    permission_resource = "attendance"
    permission_map = {"approve": "attendance.justify", "reject": "attendance.justify"}

    @extend_schema(
        tags=["Teaching"],
        summary="پذیرش توجیه غیبت",
        description="با پذیرش، وضعیت حضور به «غیبت موجه» تغییر می‌کند.",
        request=None,
        responses={200: AbsenceJustificationSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def approve(self, request, pk=None):
        justification = self.get_object()
        justification.decision = JustificationDecision.APPROVED
        justification.decided_by_id = request.user.id
        justification.decided_at = timezone.now()
        justification.save()

        attendance = justification.attendance
        attendance.attendance_status = AttendanceStatus.EXCUSED
        attendance.finalization_status = FinalizationStatus.AMENDED
        attendance.amended_reason = "پذیرش توجیه غیبت توسط مدرسه"
        attendance.save()
        return Response(self.get_serializer(justification).data)

    @extend_schema(
        tags=["Teaching"],
        summary="رد توجیه غیبت",
        request=None,
        responses={200: AbsenceJustificationSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        justification = self.get_object()
        justification.decision = JustificationDecision.REJECTED
        justification.decided_by_id = request.user.id
        justification.decided_at = timezone.now()
        justification.decision_note = request.data.get("note", "")
        justification.save()
        return Response(self.get_serializer(justification).data)


@extend_schema_view(list=extend_schema(tags=["Teaching"], summary="طرح‌های درس"))
class LessonPlanViewSet(BaseModelViewSet):
    queryset = LessonPlan.objects.select_related("course_offering__course")
    serializer_class = LessonPlanSerializer
    filterset_fields = ("course_offering", "session", "status")
    search_fields = ("title",)
    permission_resource = "resource"


@extend_schema_view(
    list=extend_schema(tags=["Teaching"], summary="فهرست تکالیف"),
    create=extend_schema(tags=["Teaching"], summary="ایجاد تکلیف"),
)
class AssignmentViewSet(BaseModelViewSet):
    queryset = Assignment.objects.select_related(
        "course_offering__course", "course_offering__class_group"
    )
    serializer_class = AssignmentSerializer
    filterset_fields = ("course_offering", "status")
    ordering_fields = ("due_at", "created_at")
    search_fields = ("title",)
    permission_resource = "assignment"
    permission_map = {"publish": "assignment.publish", "close": "assignment.update"}

    @extend_schema(
        tags=["Teaching"],
        summary="انتشار تکلیف",
        request=None,
        responses={200: AssignmentSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        assignment = self.get_object()
        if assignment.status != AssignmentStatus.DRAFT:
            raise InvalidStateTransition(
                entity="تکلیف", current=assignment.status, action="publish"
            )
        assignment.status = AssignmentStatus.PUBLISHED
        assignment.published_at = timezone.now()
        assignment.save(update_fields=["status", "published_at"])
        return Response(self.get_serializer(assignment).data)

    @extend_schema(
        tags=["Teaching"],
        summary="بستن تکلیف",
        description="تحویل‌های ثبت‌نشده به وضعیت «ارسال‌نشده» می‌روند.",
        request=None,
        responses={200: AssignmentSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        assignment = self.get_object()
        assignment.status = AssignmentStatus.CLOSED
        assignment.save(update_fields=["status"])
        assignment.submissions.filter(status=SubmissionStatus.DRAFT).update(
            status=SubmissionStatus.MISSING
        )
        return Response(self.get_serializer(assignment).data)


@extend_schema_view(
    list=extend_schema(tags=["Teaching"], summary="تحویل‌های تکلیف"),
    create=extend_schema(tags=["Teaching"], summary="ایجاد پیش‌نویس تحویل"),
)
class AssignmentSubmissionViewSet(BaseModelViewSet):
    queryset = AssignmentSubmission.objects.select_related(
        "assignment", "enrollment__student__person"
    ).prefetch_related("feedbacks")
    serializer_class = AssignmentSubmissionSerializer
    filterset_fields = ("assignment", "enrollment", "status", "is_late")
    permission_resource = "assignment"
    permission_map = {"submit": "assignment.update", "grade": "assignment.grade"}

    @extend_schema(
        tags=["Teaching"],
        summary="ارسال نهایی تکلیف",
        description=(
            "تأخیر با Snapshot سیاست همان تکلیف محاسبه و ذخیره می‌شود؛ تغییر "
            "بعدی سیاست بر این ارسال اثر ندارد (بخش ۷.۵)."
        ),
        request=None,
        responses={200: AssignmentSubmissionSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        submission = self.get_object()
        assignment = submission.assignment

        if assignment.status != AssignmentStatus.PUBLISHED:
            raise BusinessRuleViolation(
                code="ASSIGNMENT_NOT_OPEN",
                message="این تکلیف در حال حاضر پذیرای تحویل نیست.",
            )

        now = timezone.now()
        is_late = now > assignment.due_at

        if is_late and not assignment.allow_late_submission:
            raise BusinessRuleViolation(
                code="LATE_SUBMISSION_NOT_ALLOWED",
                message="مهلت تحویل این تکلیف گذشته است.",
                field_errors=[{"field": "submittedAt", "reason": "past_due"}],
            )
        if assignment.close_at and now > assignment.close_at:
            raise BusinessRuleViolation(
                code="SUBMISSION_WINDOW_CLOSED",
                message="پنجره پذیرش تحویل با تأخیر بسته شده است.",
            )

        submission.submitted_at = now
        submission.is_late = is_late
        submission.late_minutes = (
            int((now - assignment.due_at).total_seconds() // 60) if is_late else 0
        )
        submission.status = (
            SubmissionStatus.LATE if is_late else SubmissionStatus.SUBMITTED
        )
        submission.policy_snapshot = {
            "dueAt": assignment.due_at.isoformat(),
            "allowLateSubmission": assignment.allow_late_submission,
            "latePenaltyPercent": float(assignment.late_penalty_percent),
            "maxScore": float(assignment.max_score),
        }
        submission.save()
        return Response(self.get_serializer(submission).data)

    @extend_schema(
        tags=["Teaching"],
        summary="تصحیح و ثبت نمره تحویل",
        description=(
            "جریمه تأخیر بر اساس Snapshot سیاست همان تحویل اعمال می‌شود. "
            "نمره خام و نمره نهایی هر دو در بازخورد قابل ردیابی‌اند."
        ),
        request=GradeSubmissionSerializer,
        responses={200: SubmissionFeedbackSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def grade(self, request, pk=None):
        submission = self.get_object()
        body = GradeSubmissionSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        raw_score = body.validated_data["score"]
        penalty_percent = submission.policy_snapshot.get("late_penalty_percent") or (
            submission.policy_snapshot.get("latePenaltyPercent") or 0
        )
        final_score = raw_score
        if submission.is_late and penalty_percent:
            final_score = raw_score * (1 - float(penalty_percent) / 100)

        feedback = SubmissionFeedback.objects.create(
            tenant_id=submission.tenant_id,
            submission=submission,
            reviewer_id=request.user.id,
            score=final_score,
            feedback=body.validated_data.get("feedback", ""),
            reviewed_at=timezone.now(),
        )
        submission.status = SubmissionStatus.GRADED
        submission.save(update_fields=["status"])
        return Response(SubmissionFeedbackSerializer(feedback).data)


@extend_schema_view(list=extend_schema(tags=["Teaching"], summary="بازخوردهای تکلیف"))
class SubmissionFeedbackViewSet(BaseModelViewSet):
    queryset = SubmissionFeedback.objects.select_related("submission")
    serializer_class = SubmissionFeedbackSerializer
    filterset_fields = ("submission", "is_final")
    permission_resource = "assignment"


@extend_schema_view(list=extend_schema(tags=["Teaching"], summary="منابع آموزشی"))
class LearningResourceViewSet(BaseModelViewSet):
    queryset = LearningResource.objects.select_related("course_offering__course")
    serializer_class = LearningResourceSerializer
    filterset_fields = ("course_offering", "resource_type", "visibility")
    search_fields = ("title",)
    permission_resource = "resource"
