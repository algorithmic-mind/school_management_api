"""Viewهای ماژول دفتر نمره و کارنامه."""

from __future__ import annotations

import django_filters as filters
from django.db import transaction
from django.db.models import Sum
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
from apps.core.viewsets import BaseModelViewSet, BaseReadOnlyViewSet
from apps.gradebook import services
from apps.gradebook.enums import GradeItemStatus
from apps.gradebook.models import (
    AssessmentCategory,
    CourseResult,
    GradeItem,
    ReportCard,
    ReportCardItem,
    ScoreChange,
    StudentScore,
)
from apps.gradebook.serializers import (
    AssessmentCategorySerializer,
    BulkGenerateReportCardSerializer,
    BulkScoreSerializer,
    CalculateResultSerializer,
    CourseResultSerializer,
    GenerateReportCardSerializer,
    GradebookSerializer,
    GradeItemSerializer,
    ReportCardItemSerializer,
    ReportCardSerializer,
    ScoreChangeSerializer,
    StudentScoreSerializer,
    UnlockGradeItemSerializer,
)
from apps.organization.models import CourseOffering, Term
from apps.students.models import ClassMembership, Enrollment

ERRORS = {
    400: OpenApiResponse(ErrorResponseSerializer, description="داده ورودی معتبر نیست"),
    403: OpenApiResponse(ErrorResponseSerializer, description="بدون مجوز"),
    404: OpenApiResponse(ErrorResponseSerializer, description="یافت نشد"),
    409: OpenApiResponse(ErrorResponseSerializer, description="قفل یا تعارض وضعیت"),
    422: OpenApiResponse(ErrorResponseSerializer, description="نقض قاعده کسب‌وکار"),
}


@extend_schema_view(
    list=extend_schema(tags=["Gradebook"], summary="دسته‌های ارزشیابی"),
    create=extend_schema(
        tags=["Gradebook"],
        summary="تعریف دسته ارزشیابی",
        description="مجموع وزن دسته‌های فعال هر درس باید دقیقاً ۱۰۰٪ باشد (بخش ۷.۷).",
    ),
)
class AssessmentCategoryViewSet(BaseModelViewSet):
    queryset = AssessmentCategory.objects.select_related("course_offering")
    serializer_class = AssessmentCategorySerializer
    filterset_fields = ("course_offering", "is_active")
    permission_resource = "grade"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "course_offering__course__school"
    campus_field = "course_offering__class_group__campus"
    academic_year_field = "course_offering__term__academic_year"
    class_group_field = "course_offering__class_group"
    course_offering_field = "course_offering"

    @extend_schema(
        tags=["Gradebook"],
        summary="اعتبارسنجی مجموع وزن دسته‌ها",
        parameters=[
            OpenApiParameter(
                "course_offering", str, required=True, description="شناسه ارائه درس"
            )
        ],
        responses={200: OperationResultSerializer, 422: ErrorResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="validate-weights")
    def validate_weights(self, request):
        offering_id = request.query_params.get("course_offering")
        if not offering_id:
            raise BusinessRuleViolation(
                code="MISSING_PARAMETER",
                message="پارامتر course_offering الزامی است.",
                status_code=400,
            )
        services.validate_category_weights(offering_id)
        return Response({"success": True, "message": "مجموع وزن‌ها معتبر است."})


@extend_schema_view(
    list=extend_schema(tags=["Gradebook"], summary="اقلام نمره"),
    create=extend_schema(tags=["Gradebook"], summary="ایجاد قلم نمره"),
)
class GradeItemViewSet(BaseModelViewSet):
    queryset = GradeItem.objects.select_related("category__course_offering")
    serializer_class = GradeItemSerializer
    filterset_fields = ("category", "source_type", "status")
    search_fields = ("title",)
    permission_resource = "grade"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "category__course_offering__course__school"
    campus_field = "category__course_offering__class_group__campus"
    academic_year_field = "category__course_offering__term__academic_year"
    class_group_field = "category__course_offering__class_group"
    course_offering_field = "category__course_offering"
    permission_map = {
        "lock": "grade.lock",
        "unlock": "grade.unlock",
        "bulk_scores": "grade.create",
    }

    @extend_schema(
        tags=["Gradebook"],
        summary="ثبت گروهی نمرات یک قلم",
        description=(
            "برای هر دانش‌آموز، `status` را دقیق انتخاب کنید: `ABSENT` برای "
            "غایب، `EXEMPT` برای معاف و `RECORDED` با `rawScore = 0` برای "
            "نمره صفر. این سه حالت با هم یکسان نیستند (بخش ۷.۷).\n\n"
            "اگر قلم نمره قفل باشد، فیلد `reason` الزامی است."
        ),
        request=BulkScoreSerializer,
        responses={200: OperationResultSerializer, **ERRORS},
        examples=[
            OpenApiExample(
                "ثبت گروهی",
                value={
                    "rows": [
                        {
                            "enrollment": "11111111-1111-1111-1111-111111111111",
                            "raw_score": 18.5,
                            "status": "RECORDED",
                        },
                        {
                            "enrollment": "22222222-2222-2222-2222-222222222222",
                            "status": "ABSENT",
                        },
                        {
                            "enrollment": "33333333-3333-3333-3333-333333333333",
                            "raw_score": 0,
                            "status": "RECORDED",
                            "comment": "پاسخ‌برگ سفید",
                        },
                    ]
                },
                request_only=True,
            )
        ],
    )
    @action(detail=True, methods=["post"], url_path="scores")
    @transaction.atomic
    def bulk_scores(self, request, pk=None):
        grade_item = self.get_object()
        body = BulkScoreSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        reason = body.validated_data.get("reason", "")

        affected = 0
        for row in body.validated_data["rows"]:
            services.record_score(
                grade_item,
                row["enrollment"],
                row.get("raw_score"),
                row["status"],
                comment=row.get("comment", ""),
                actor_id=request.user.id,
                reason=reason,
            )
            affected += 1

        return Response(
            {"success": True, "message": "نمرات ثبت شد.", "affected": affected}
        )

    @extend_schema(
        tags=["Gradebook"],
        summary="قفل قلم نمره",
        request=None,
        responses={200: GradeItemSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        grade_item = self.get_object()
        services.lock_grade_item(grade_item, request.user.id)
        return Response(self.get_serializer(grade_item).data)

    @extend_schema(
        tags=["Gradebook"],
        summary="بازگشایی قفل نمره",
        description="نیازمند علت و مجوز `grade.unlock` (بخش ۷.۷).",
        request=UnlockGradeItemSerializer,
        responses={200: GradeItemSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def unlock(self, request, pk=None):
        grade_item = self.get_object()
        body = UnlockGradeItemSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.unlock_grade_item(
            grade_item, body.validated_data["reason"], request.user.id
        )
        return Response(self.get_serializer(grade_item).data)


class StudentScoreFilter(filters.FilterSet):
    course_offering = filters.UUIDFilter(
        field_name="grade_item__category__course_offering_id", label="ارائه درس"
    )
    student = filters.UUIDFilter(
        field_name="enrollment__student_id", label="دانش‌آموز"
    )

    class Meta:
        model = StudentScore
        fields = ("grade_item", "enrollment", "status")


@extend_schema_view(
    list=extend_schema(tags=["Gradebook"], summary="نمرات دانش‌آموزان"),
)
class StudentScoreViewSet(BaseModelViewSet):
    queryset = StudentScore.objects.select_related(
        "grade_item", "enrollment__student__person"
    )
    serializer_class = StudentScoreSerializer
    filterset_class = StudentScoreFilter
    permission_resource = "grade"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "enrollment__campus__school"
    campus_field = "enrollment__campus"
    academic_year_field = "enrollment__academic_year"
    class_group_field = "grade_item__category__course_offering__class_group"
    course_offering_field = "grade_item__category__course_offering"
    self_student_field = "enrollment__student"

    @extend_schema(
        tags=["Gradebook"],
        summary="تاریخچه تغییرات نمره",
        responses={200: ScoreChangeSerializer(many=True)},
    )
    @action(detail=True, methods=["get"], url_path="changes")
    def changes(self, request, pk=None):
        score = self.get_object()
        return Response(ScoreChangeSerializer(score.changes.all(), many=True).data)


@extend_schema(
    tags=["Gradebook"],
    summary="دفتر نمره یک ارائه درس",
    description=(
        "جدول کامل دفتر نمره: دسته‌ها، ستون‌های نمره و ردیف دانش‌آموزان با "
        "نمرات ثبت‌شده. یک درخواست برای رندر کل صفحه دفتر نمره "
        "(بخش ۱۰.۱ سند فرانت).\n\n"
        "`weightsValid` نشان می‌دهد مجموع وزن دسته‌ها ۱۰۰٪ هست یا نه؛ اگر نه، "
        "فرانت باید هشدار نشان دهد و اجازه نهایی‌سازی ندهد."
    ),
    parameters=[
        OpenApiParameter(
            "course_offering", str, required=True, description="شناسه ارائه درس"
        )
    ],
    responses={200: GradebookSerializer, **ERRORS},
)
class GradebookView(BaseReadOnlyViewSet):
    """نمای تجمیعی دفتر نمره."""

    queryset = CourseOffering.objects.none()
    serializer_class = GradebookSerializer
    permission_resource = "grade"
    pagination_class = None

    def list(self, request, *args, **kwargs):
        offering_id = request.query_params.get("course_offering")
        if not offering_id:
            raise BusinessRuleViolation(
                code="MISSING_PARAMETER",
                message="پارامتر course_offering الزامی است.",
                status_code=400,
            )

        offering = get_object_or_404(
            CourseOffering.objects.select_related(
                "course", "class_group", "term"
            ),
            pk=offering_id,
        )

        categories = list(
            AssessmentCategory.objects.filter(
                course_offering=offering, is_active=True
            ).order_by("display_order")
        )
        weight_total = sum(category.weight_percent for category in categories)

        grade_items = list(
            GradeItem.objects.filter(category__in=categories)
            .select_related("category")
            .order_by("category__display_order", "due_on")
        )

        memberships = ClassMembership.objects.filter(
            class_group=offering.class_group, status="ACTIVE"
        ).select_related("enrollment__student__person")

        scores_by_enrollment: dict = {}
        for score in StudentScore.objects.filter(grade_item__in=grade_items):
            scores_by_enrollment.setdefault(score.enrollment_id, {})[
                str(score.grade_item_id)
            ] = {
                "rawScore": float(score.raw_score) if score.raw_score is not None else None,
                "status": score.status,
                "comment": score.comment,
            }

        results = {
            result.enrollment_id: result
            for result in CourseResult.objects.filter(course_offering=offering)
        }

        rows = []
        for membership in memberships:
            enrollment = membership.enrollment
            result = results.get(enrollment.id)
            rows.append(
                {
                    "enrollmentId": enrollment.id,
                    "studentNo": enrollment.student.student_no,
                    "studentName": enrollment.student.person.full_name,
                    "scores": scores_by_enrollment.get(enrollment.id, {}),
                    "finalScore": (
                        float(result.final_score)
                        if result and result.final_score is not None
                        else None
                    ),
                }
            )

        payload = {
            "courseOfferingId": offering.id,
            "courseTitle": offering.course.title,
            "classGroupCode": offering.class_group.code,
            "termTitle": offering.term.title,
            "categories": AssessmentCategorySerializer(categories, many=True).data,
            "columns": [
                {
                    "gradeItemId": item.id,
                    "title": item.title,
                    "categoryId": item.category_id,
                    "categoryTitle": item.category.title,
                    "maxScore": item.max_score,
                    "weight": item.weight,
                    "status": item.status,
                    "isLocked": item.status == GradeItemStatus.LOCKED,
                }
                for item in grade_items
            ],
            "rows": rows,
            "weightsValid": weight_total == 100,
        }
        return Response(payload)


@extend_schema_view(
    list=extend_schema(tags=["Gradebook"], summary="نتایج دروس"),
)
class CourseResultViewSet(BaseModelViewSet):
    queryset = CourseResult.objects.select_related(
        "course_offering__course", "enrollment__student__person"
    )
    serializer_class = CourseResultSerializer
    filterset_fields = ("course_offering", "enrollment", "result_status")
    permission_resource = "grade"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "enrollment__campus__school"
    campus_field = "enrollment__campus"
    academic_year_field = "enrollment__academic_year"
    class_group_field = "course_offering__class_group"
    course_offering_field = "course_offering"
    self_student_field = "enrollment__student"
    permission_map = {"calculate": "grade.update"}

    @extend_schema(
        tags=["Gradebook"],
        summary="محاسبه نتیجه درس",
        description=(
            "بر اساس وزن دسته‌ها و نمرات ثبت‌شده محاسبه می‌شود. Snapshot "
            "ورودی‌های محاسبه در `calculationInputs` ذخیره و "
            "`calculationVersion` یک واحد جلو می‌رود (بخش ۱۱.۵).\n\n"
            "اگر `enrollment` ارسال نشود، برای همه دانش‌آموزان فعال کلاس "
            "محاسبه می‌شود."
        ),
        request=CalculateResultSerializer,
        responses={200: OperationResultSerializer, **ERRORS},
    )
    @action(detail=False, methods=["post"])
    @transaction.atomic
    def calculate(self, request):
        body = CalculateResultSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        offering = get_object_or_404(
            CourseOffering.objects.select_related("course", "class_group"),
            pk=body.validated_data["course_offering"],
        )

        enrollment_id = body.validated_data.get("enrollment")
        if enrollment_id:
            enrollments = Enrollment.objects.filter(pk=enrollment_id)
        else:
            enrollments = Enrollment.objects.filter(
                class_memberships__class_group=offering.class_group,
                class_memberships__status="ACTIVE",
            ).distinct()

        affected = 0
        for enrollment in enrollments:
            services.calculate_course_result(offering, enrollment)
            affected += 1

        return Response(
            {"success": True, "message": "محاسبه انجام شد.", "affected": affected}
        )


@extend_schema_view(
    list=extend_schema(tags=["Gradebook"], summary="فهرست کارنامه‌ها"),
    retrieve=extend_schema(tags=["Gradebook"], summary="جزئیات کارنامه با اقلام"),
)
class ReportCardViewSet(BaseModelViewSet):
    queryset = ReportCard.objects.select_related(
        "enrollment__student__person", "term"
    ).prefetch_related("items")
    serializer_class = ReportCardSerializer
    filterset_fields = ("enrollment", "term", "status")
    permission_resource = "report_card"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "enrollment__campus__school"
    campus_field = "enrollment__campus"
    academic_year_field = "term__academic_year"
    self_student_field = "enrollment__student"
    permission_map = {
        "generate": "report_card.generate",
        "bulk_generate": "report_card.generate",
        "publish": "report_card.publish",
    }
    http_method_names = ["get", "post", "patch", "head", "options"]

    @extend_schema(
        tags=["Gradebook"],
        summary="تولید کارنامه",
        description=(
            "نسخه جدید کارنامه با Snapshot نتایج دروس ساخته می‌شود. نسخه "
            "منتشرشده قبلی به وضعیت «جایگزین‌شده» می‌رود و حذف نمی‌شود "
            "(بخش ۷.۷)."
        ),
        request=GenerateReportCardSerializer,
        responses={201: ReportCardSerializer, **ERRORS},
    )
    @action(detail=False, methods=["post"])
    def generate(self, request):
        body = GenerateReportCardSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        enrollment = get_object_or_404(
            Enrollment, pk=body.validated_data["enrollment"]
        )
        term = get_object_or_404(Term, pk=body.validated_data["term"])
        report_card = services.generate_report_card(enrollment, term)
        return Response(ReportCardSerializer(report_card).data, status=201)

    @extend_schema(
        tags=["Gradebook"],
        summary="تولید گروهی کارنامه یک کلاس",
        request=BulkGenerateReportCardSerializer,
        responses={200: OperationResultSerializer, **ERRORS},
    )
    @action(detail=False, methods=["post"], url_path="bulk-generate")
    @transaction.atomic
    def bulk_generate(self, request):
        body = BulkGenerateReportCardSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        term = get_object_or_404(Term, pk=body.validated_data["term"])
        enrollments = Enrollment.objects.filter(
            class_memberships__class_group_id=body.validated_data["class_group"],
            class_memberships__status="ACTIVE",
        ).distinct()

        affected = 0
        for enrollment in enrollments:
            services.generate_report_card(enrollment, term)
            affected += 1

        return Response(
            {"success": True, "message": "کارنامه‌ها تولید شد.", "affected": affected}
        )

    @extend_schema(
        tags=["Gradebook"],
        summary="انتشار کارنامه",
        description="پس از انتشار، رویداد `ReportCardPublished` منتشر می‌شود (بخش ۱۳.۱).",
        request=None,
        responses={200: ReportCardSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        report_card = self.get_object()
        services.publish_report_card(report_card, request.user.id)
        return Response(self.get_serializer(report_card).data)


@extend_schema_view(list=extend_schema(tags=["Gradebook"], summary="اقلام کارنامه"))
class ReportCardItemViewSet(BaseReadOnlyViewSet):
    queryset = ReportCardItem.objects.select_related("report_card", "course_result")
    serializer_class = ReportCardItemSerializer
    filterset_fields = ("report_card",)
    permission_resource = "report_card"
    # -- دامنه دسترسی: مسیر ORM این منبع تا هر بُعد محدوده --
    school_field = "report_card__enrollment__campus__school"
    campus_field = "report_card__enrollment__campus"
    academic_year_field = "report_card__term__academic_year"
    class_group_field = "course_result__course_offering__class_group"
    course_offering_field = "course_result__course_offering"
    self_student_field = "report_card__enrollment__student"
