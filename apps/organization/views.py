"""Viewهای ماژول ساختار سازمانی و آموزشی."""

from __future__ import annotations

import django_filters as filters
from django.shortcuts import get_object_or_404
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
from apps.core.viewsets import BaseModelViewSet
from apps.organization import services
from apps.organization.enums import AcademicYearStatus, ScheduleStatus
from apps.organization.models import (
    AcademicYear,
    CalendarEvent,
    Campus,
    ClassGroup,
    Course,
    CourseOffering,
    GradeLevel,
    ProgramCourse,
    Room,
    ScheduleEntry,
    School,
    StudyProgram,
    Term,
)
from apps.organization.serializers import (
    AcademicYearSerializer,
    CalendarEventSerializer,
    CampusSerializer,
    ClassGroupListSerializer,
    ClassGroupSerializer,
    CloneYearSerializer,
    CourseOfferingSerializer,
    CourseSerializer,
    GradeLevelSerializer,
    ProgramCourseSerializer,
    RoomSerializer,
    ScheduleConflictSerializer,
    ScheduleEntrySerializer,
    SchoolSerializer,
    StudyProgramSerializer,
    TermSerializer,
    WeeklyTimetableSerializer,
    YearCloseSerializer,
)

ERRORS = {
    400: OpenApiResponse(ErrorResponseSerializer, description="داده ورودی معتبر نیست"),
    403: OpenApiResponse(ErrorResponseSerializer, description="بدون مجوز"),
    404: OpenApiResponse(ErrorResponseSerializer, description="یافت نشد"),
    422: OpenApiResponse(ErrorResponseSerializer, description="نقض قاعده کسب‌وکار"),
}


@extend_schema_view(
    list=extend_schema(tags=["Organization"], summary="فهرست مدارس"),
    retrieve=extend_schema(tags=["Organization"], summary="جزئیات مدرسه"),
    create=extend_schema(tags=["Organization"], summary="ایجاد مدرسه"),
    update=extend_schema(tags=["Organization"], summary="ویرایش مدرسه"),
    partial_update=extend_schema(tags=["Organization"], summary="ویرایش جزئی مدرسه"),
    destroy=extend_schema(tags=["Organization"], summary="حذف نرم مدرسه"),
)
class SchoolViewSet(BaseModelViewSet):
    queryset = School.objects.prefetch_related("campuses")
    serializer_class = SchoolSerializer
    filterset_fields = ("school_type", "status")
    search_fields = ("name", "code")
    permission_resource = "school"


@extend_schema_view(
    list=extend_schema(tags=["Organization"], summary="فهرست شعب"),
    retrieve=extend_schema(tags=["Organization"], summary="جزئیات شعبه"),
    create=extend_schema(tags=["Organization"], summary="ایجاد شعبه"),
)
class CampusViewSet(BaseModelViewSet):
    queryset = Campus.objects.select_related("school")
    serializer_class = CampusSerializer
    filterset_fields = ("school", "status")
    search_fields = ("name", "code")
    permission_resource = "campus"


@extend_schema_view(
    list=extend_schema(
        tags=["Organization"],
        summary="فهرست سال‌های تحصیلی",
        description="برای صفحه «سال و ترم» و همچنین Dropdown انتخاب محیط کاری.",
    ),
    retrieve=extend_schema(tags=["Organization"], summary="جزئیات سال تحصیلی به همراه ترم‌ها"),
    create=extend_schema(tags=["Organization"], summary="ایجاد سال تحصیلی"),
)
class AcademicYearViewSet(BaseModelViewSet):
    queryset = AcademicYear.objects.select_related("school").prefetch_related("terms")
    serializer_class = AcademicYearSerializer
    filterset_fields = ("school", "status", "is_default")
    search_fields = ("title",)
    ordering_fields = ("starts_on", "title")
    permission_resource = "academic_year"
    permission_map = {
        "activate": "academic_year.activate",
        "close": "academic_year.close",
        "reopen": "academic_year.reopen",
        "clone_structure": "academic_year.create",
    }

    @extend_schema(
        tags=["Organization"],
        summary="فعال‌سازی سال تحصیلی",
        description=(
            "Checklist فعال‌سازی را کنترل می‌کند (بخش ۱۱.۱): وجود ترم‌ها، پوشش "
            "بازه، و تعریف پایه‌ها. با موفقیت، این سال به سال پیش‌فرض مدرسه "
            "تبدیل می‌شود و سال پیش‌فرض قبلی از حالت پیش‌فرض خارج می‌گردد."
        ),
        request=None,
        responses={200: AcademicYearSerializer, **ERRORS},
        examples=[
            OpenApiExample(
                "خطای پیش‌نیاز ناقص",
                value={
                    "code": "ACADEMIC_YEAR_NOT_READY",
                    "message": "پیش‌نیازهای فعال‌سازی سال تحصیلی کامل نیست.",
                    "correlationId": "7b3d9e1a",
                    "fieldErrors": [
                        {"field": "terms", "reason": "حداقل یک ترم باید تعریف شود."}
                    ],
                    "retryable": False,
                },
                response_only=True,
                status_codes=["422"],
            )
        ],
    )
    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        year = self.get_object()
        if year.status == AcademicYearStatus.ACTIVE:
            raise BusinessRuleViolation(
                code="ALREADY_ACTIVE", message="این سال تحصیلی از قبل فعال است."
            )
        services.activate_academic_year(year)
        return Response(self.get_serializer(year).data)

    @extend_schema(
        tags=["Organization"],
        summary="بستن سال تحصیلی",
        description=(
            "پیش از بستن، وجود ثبت‌نام‌های در وضعیت میانی کنترل می‌شود. "
            "سال بسته فقط‌خواندنی است."
        ),
        request=YearCloseSerializer,
        responses={200: AcademicYearSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        year = self.get_object()
        body = YearCloseSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.close_academic_year(year, body.validated_data.get("note", ""))
        return Response(self.get_serializer(year).data)

    @extend_schema(
        tags=["Organization"],
        summary="بازگشایی سال بسته",
        description="عملیات حساس؛ نیازمند مجوز سطح بالا و ثبت علت (بخش ۱۱.۱).",
        request=YearCloseSerializer,
        responses={200: AcademicYearSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="reopen")
    def reopen(self, request, pk=None):
        year = self.get_object()
        body = YearCloseSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        if year.status != AcademicYearStatus.CLOSED:
            raise BusinessRuleViolation(
                code="YEAR_NOT_CLOSED", message="فقط سال بسته قابل بازگشایی است."
            )
        year.status = AcademicYearStatus.ACTIVE
        year.close_note = body.validated_data.get("note", "")
        year.closed_at = None
        year.save(update_fields=["status", "close_note", "closed_at"])
        return Response(self.get_serializer(year).data)

    @extend_schema(
        tags=["Organization"],
        summary="ایجاد ساختار سال جدید از روی سال جاری",
        description=(
            "فقط ساختار (کلاس‌ها) کپی می‌شود. دانش‌آموز، بدهی، نمره و حضور "
            "کپی نمی‌شوند (بخش ۱۱.۱)."
        ),
        request=CloneYearSerializer,
        responses={200: OperationResultSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="clone-structure")
    def clone_structure(self, request, pk=None):
        source = self.get_object()
        body = CloneYearSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        target = get_object_or_404(
            AcademicYear, pk=body.validated_data["target_academic_year"]
        )
        result = services.clone_year_structure(source, target)
        return Response(
            {
                "success": True,
                "message": "ساختار سال کپی شد.",
                "affected": result["createdClassGroups"],
            }
        )


@extend_schema_view(
    list=extend_schema(tags=["Organization"], summary="فهرست ترم‌ها"),
    create=extend_schema(tags=["Organization"], summary="ایجاد ترم"),
)
class TermViewSet(BaseModelViewSet):
    queryset = Term.objects.select_related("academic_year")
    serializer_class = TermSerializer
    filterset_fields = ("academic_year", "status")
    ordering_fields = ("sequence_no", "starts_on")
    permission_resource = "academic_year"


@extend_schema_view(
    list=extend_schema(tags=["Organization"], summary="فهرست پایه‌های تحصیلی"),
    create=extend_schema(tags=["Organization"], summary="ایجاد پایه"),
)
class GradeLevelViewSet(BaseModelViewSet):
    queryset = GradeLevel.objects.select_related("school")
    serializer_class = GradeLevelSerializer
    filterset_fields = ("school", "status", "stage")
    ordering_fields = ("sequence_no", "title")
    permission_resource = "grade_level"


@extend_schema_view(list=extend_schema(tags=["Organization"], summary="فهرست رشته‌ها"))
class StudyProgramViewSet(BaseModelViewSet):
    queryset = StudyProgram.objects.select_related("school")
    serializer_class = StudyProgramSerializer
    filterset_fields = ("school", "status")
    search_fields = ("title", "code")
    permission_resource = "course"


@extend_schema_view(
    list=extend_schema(tags=["Organization"], summary="فهرست دروس"),
    create=extend_schema(tags=["Organization"], summary="تعریف درس"),
)
class CourseViewSet(BaseModelViewSet):
    queryset = Course.objects.select_related("school").prefetch_related("prerequisites")
    serializer_class = CourseSerializer
    filterset_fields = ("school", "status", "assessment_scheme")
    search_fields = ("title", "code")
    permission_resource = "course"


@extend_schema_view(
    list=extend_schema(
        tags=["Organization"],
        summary="نگاشت درس به رشته و پایه",
        description="برنامه درسی مصوب هر رشته/پایه با ساعات هفتگی.",
    )
)
class ProgramCourseViewSet(BaseModelViewSet):
    queryset = ProgramCourse.objects.select_related("program", "grade_level", "course")
    serializer_class = ProgramCourseSerializer
    filterset_fields = ("program", "grade_level", "course", "is_required")
    permission_resource = "course"


@extend_schema_view(list=extend_schema(tags=["Organization"], summary="فهرست اتاق‌ها"))
class RoomViewSet(BaseModelViewSet):
    queryset = Room.objects.select_related("campus")
    serializer_class = RoomSerializer
    filterset_fields = ("campus", "room_type", "status")
    search_fields = ("code", "title", "building")
    permission_resource = "room"


class ClassGroupFilter(filters.FilterSet):
    has_free_seats = filters.BooleanFilter(
        method="filter_free_seats", label="فقط کلاس‌های دارای ظرفیت خالی"
    )

    class Meta:
        model = ClassGroup
        fields = ("campus", "academic_year", "grade_level", "program", "status")

    def filter_free_seats(self, queryset, name, value):
        from django.db.models import Count, F, Q

        queryset = queryset.annotate(
            occupied=Count(
                "class_memberships",
                filter=Q(class_memberships__status="ACTIVE"),
                distinct=True,
            )
        )
        if value:
            return queryset.filter(occupied__lt=F("capacity"))
        return queryset.filter(occupied__gte=F("capacity"))


@extend_schema_view(
    list=extend_schema(
        tags=["Organization"],
        summary="فهرست کلاس‌ها",
        description=(
            "هر رکورد شامل `occupiedSeats` و `availableSeats` است تا فرانت "
            "بتواند نوار ظرفیت را بدون درخواست اضافی رسم کند."
        ),
        parameters=[
            OpenApiParameter(
                "has_free_seats", bool, description="فقط کلاس‌های دارای ظرفیت خالی"
            )
        ],
    ),
    retrieve=extend_schema(tags=["Organization"], summary="جزئیات کلاس"),
    create=extend_schema(tags=["Organization"], summary="ایجاد کلاس"),
)
class ClassGroupViewSet(BaseModelViewSet):
    queryset = ClassGroup.objects.select_related(
        "campus", "academic_year", "grade_level", "program", "home_room"
    )
    serializer_class = ClassGroupSerializer
    filterset_class = ClassGroupFilter
    search_fields = ("code", "title")
    permission_resource = "class_group"
    academic_year_field = "academic_year"
    campus_field = "campus"

    def get_serializer_class(self):
        if self.action == "list":
            return ClassGroupListSerializer
        return ClassGroupSerializer

    @extend_schema(
        tags=["Organization"],
        summary="برنامه هفتگی کلاس",
        description=(
            "همه اقلام برنامه هفتگی کلاس در همه ارائه‌های درس آن، مرتب بر اساس "
            "روز و ساعت. مناسب رندر مستقیم جدول برنامه (بخش ۸.۳ سند فرانت)."
        ),
        responses={200: WeeklyTimetableSerializer},
    )
    @action(detail=True, methods=["get"], url_path="timetable")
    def timetable(self, request, pk=None):
        class_group = self.get_object()
        entries = (
            ScheduleEntry.objects.filter(
                course_offering__class_group=class_group
            )
            .select_related("course_offering__course", "room")
            .order_by("weekday", "starts_at")
        )
        payload = {
            "classGroupId": class_group.id,
            "classGroupCode": class_group.code,
            "entries": ScheduleEntrySerializer(entries, many=True).data,
        }
        return Response(payload)

    @extend_schema(
        tags=["Organization"],
        summary="ارائه‌های درس کلاس",
        responses={200: CourseOfferingSerializer(many=True)},
    )
    @action(detail=True, methods=["get"], url_path="offerings")
    def offerings(self, request, pk=None):
        class_group = self.get_object()
        offerings = CourseOffering.objects.filter(
            class_group=class_group
        ).select_related("course", "term")
        return Response(CourseOfferingSerializer(offerings, many=True).data)


@extend_schema_view(
    list=extend_schema(tags=["Organization"], summary="فهرست ارائه‌های درس"),
    create=extend_schema(tags=["Organization"], summary="ایجاد ارائه درس برای کلاس"),
)
class CourseOfferingViewSet(BaseModelViewSet):
    queryset = CourseOffering.objects.select_related(
        "class_group", "term", "course"
    )
    serializer_class = CourseOfferingSerializer
    filterset_fields = ("class_group", "term", "course", "status")
    permission_resource = "class_group"

    @extend_schema(
        tags=["Organization"],
        summary="انتشار برنامه هفتگی این ارائه درس",
        description="پیش از انتشار، تداخل معلم/اتاق/کلاس بررسی می‌شود.",
        request=None,
        responses={200: OperationResultSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="publish-schedule")
    def publish_schedule(self, request, pk=None):
        offering = self.get_object()
        count = services.publish_schedule(offering.id)
        return Response(
            {"success": True, "message": "برنامه منتشر شد.", "affected": count}
        )


@extend_schema_view(
    list=extend_schema(
        tags=["Organization"],
        summary="فهرست اقلام برنامه هفتگی",
        parameters=[
            OpenApiParameter("weekday", int, description="۰=شنبه … ۶=جمعه"),
            OpenApiParameter("teacher_profile_id", str, description="فیلتر بر اساس معلم"),
        ],
    ),
    create=extend_schema(
        tags=["Organization"],
        summary="افزودن قلم برنامه",
        description=(
            "پیش از ذخیره، تداخل با برنامه معلم، اتاق و کلاس بررسی می‌شود. "
            "در صورت تداخل، خطای `SCHEDULE_CONFLICT` با جزئیات هر تداخل در "
            "`fieldErrors` برمی‌گردد."
        ),
        responses={201: ScheduleEntrySerializer, **ERRORS},
    ),
)
class ScheduleEntryViewSet(BaseModelViewSet):
    queryset = ScheduleEntry.objects.select_related(
        "course_offering__course", "course_offering__class_group", "room"
    )
    serializer_class = ScheduleEntrySerializer
    filterset_fields = (
        "course_offering",
        "room",
        "teacher_profile_id",
        "weekday",
        "status",
    )
    ordering_fields = ("weekday", "starts_at")
    permission_resource = "schedule"

    def perform_create(self, serializer):
        super().perform_create(serializer)
        services.validate_schedule_entry(serializer.instance)

    def perform_update(self, serializer):
        serializer.save()
        services.validate_schedule_entry(serializer.instance)

    @extend_schema(
        tags=["Organization"],
        summary="بررسی تداخل بدون ذخیره",
        description=(
            "برای اعتبارسنجی زنده در فرم برنامه‌ریزی. قلم را ذخیره نمی‌کند و "
            "فقط فهرست تداخل‌ها را برمی‌گرداند."
        ),
        request=ScheduleEntrySerializer,
        responses={200: ScheduleConflictSerializer(many=True)},
    )
    @action(detail=False, methods=["post"], url_path="check-conflicts")
    def check_conflicts(self, request):
        serializer = ScheduleEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        candidate = ScheduleEntry(**serializer.validated_data)
        conflicts = services.detect_schedule_conflicts(candidate)
        return Response(conflicts)


@extend_schema_view(
    list=extend_schema(
        tags=["Organization"],
        summary="تقویم آموزشی",
        description="تعطیلات، بازه امتحانات، جلسات اولیا و مناسبت‌ها.",
    )
)
class CalendarEventViewSet(BaseModelViewSet):
    queryset = CalendarEvent.objects.select_related("school", "campus", "academic_year")
    serializer_class = CalendarEventSerializer
    filterset_fields = ("school", "campus", "academic_year", "event_type", "is_working_day")
    ordering_fields = ("starts_on",)
    permission_resource = "academic_year"
