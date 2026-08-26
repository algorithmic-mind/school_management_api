"""سریالایزرهای ماژول دفتر نمره و کارنامه."""

from __future__ import annotations

from rest_framework import serializers

from apps.core.serializers import AUDIT_FIELDS
from apps.gradebook.models import (
    AssessmentCategory,
    CourseResult,
    GradeItem,
    ReportCard,
    ReportCardItem,
    ScoreChange,
    StudentScore,
)


class AssessmentCategorySerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(source="grade_items.count", read_only=True)

    class Meta:
        model = AssessmentCategory
        fields = (
            "id",
            "course_offering",
            "title",
            "weight_percent",
            "drop_policy",
            "display_order",
            "is_active",
            "item_count",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class GradeItemSerializer(serializers.ModelSerializer):
    category_title = serializers.CharField(source="category.title", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    recorded_count = serializers.SerializerMethodField()

    class Meta:
        model = GradeItem
        fields = (
            "id",
            "category",
            "category_title",
            "source_type",
            "source_id",
            "title",
            "max_score",
            "weight",
            "due_on",
            "status",
            "status_display",
            "locked_at",
            "recorded_count",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "status",
            "locked_at",
            "created_at",
            "updated_at",
            "version",
        )

    def get_recorded_count(self, obj) -> int:
        return obj.scores.exclude(status="NOT_RECORDED").count()


class StudentScoreSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="enrollment.student.person.full_name", read_only=True
    )
    student_no = serializers.CharField(
        source="enrollment.student.student_no", read_only=True
    )
    grade_item_title = serializers.CharField(source="grade_item.title", read_only=True)
    max_score = serializers.DecimalField(
        source="grade_item.max_score", max_digits=6, decimal_places=2, read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = StudentScore
        fields = (
            "id",
            "grade_item",
            "grade_item_title",
            "max_score",
            "enrollment",
            "student_name",
            "student_no",
            "raw_score",
            "normalized_score",
            "letter_grade",
            "qualitative_level",
            "status",
            "status_display",
            "comment",
            "recorded_at",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "normalized_score",
            "recorded_at",
            "created_at",
            "updated_at",
            "version",
        )


class ScoreChangeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScoreChange
        fields = (
            "id",
            "student_score",
            "old_score",
            "new_score",
            "old_status",
            "new_status",
            "reason",
            "changed_by_id",
            "changed_at",
            "approval_status",
            "approved_at",
        )
        read_only_fields = fields


class GradebookRowSerializer(serializers.Serializer):
    """یک ردیف (دانش‌آموز) در جدول دفتر نمره."""

    enrollmentId = serializers.UUIDField()
    studentNo = serializers.CharField()
    studentName = serializers.CharField()
    scores = serializers.DictField(
        child=serializers.DictField(),
        help_text="نگاشت gradeItemId → {rawScore, status, comment}",
    )
    categoryAverages = serializers.DictField(
        child=serializers.FloatField(allow_null=True), required=False
    )
    finalScore = serializers.FloatField(allow_null=True)


class GradebookColumnSerializer(serializers.Serializer):
    """یک ستون (قلم نمره) در جدول دفتر نمره."""

    gradeItemId = serializers.UUIDField()
    title = serializers.CharField()
    categoryId = serializers.UUIDField()
    categoryTitle = serializers.CharField()
    maxScore = serializers.DecimalField(max_digits=6, decimal_places=2)
    weight = serializers.DecimalField(max_digits=5, decimal_places=2)
    status = serializers.CharField()
    isLocked = serializers.BooleanField()


class GradebookSerializer(serializers.Serializer):
    """
    نمای کامل دفتر نمره یک ارائه درس.

    ساختار ستون/ردیف طوری است که فرانت بتواند مستقیماً جدول را رندر کند
    (بخش ۱۰.۱ سند فرانت).
    """

    courseOfferingId = serializers.UUIDField()
    courseTitle = serializers.CharField()
    classGroupCode = serializers.CharField()
    termTitle = serializers.CharField()
    categories = AssessmentCategorySerializer(many=True)
    columns = GradebookColumnSerializer(many=True)
    rows = GradebookRowSerializer(many=True)
    weightsValid = serializers.BooleanField(
        help_text="آیا مجموع وزن دسته‌های فعال دقیقاً ۱۰۰٪ است؟"
    )


class BulkScoreRowSerializer(serializers.Serializer):
    enrollment = serializers.UUIDField()
    raw_score = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False, allow_null=True
    )
    status = serializers.ChoiceField(
        choices=[
            "RECORDED",
            "ABSENT",
            "EXEMPT",
            "EXCUSED",
            "NOT_RECORDED",
            "PENDING_REVIEW",
        ],
        default="RECORDED",
    )
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class BulkScoreSerializer(serializers.Serializer):
    """
    ثبت گروهی نمرات یک قلم نمره.

    «غیبت»، «معاف»، «ثبت‌نشده» و «صفر» چهار حالت متفاوت‌اند و باید با
    `status` مناسب ارسال شوند، نه با نمره صفر (بخش ۷.۷).
    """

    rows = BulkScoreRowSerializer(many=True)
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=400,
        help_text="در صورت اصلاح نمره پس از قفل، الزامی است.",
    )


class CourseResultSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="enrollment.student.person.full_name", read_only=True
    )
    course_title = serializers.CharField(
        source="course_offering.course.title", read_only=True
    )
    result_status_display = serializers.CharField(
        source="get_result_status_display", read_only=True
    )

    class Meta:
        model = CourseResult
        fields = (
            "id",
            "course_offering",
            "course_title",
            "enrollment",
            "student_name",
            "continuous_score",
            "final_exam_score",
            "final_score",
            "letter_grade",
            "qualitative_level",
            "result_status",
            "result_status_display",
            "calculation_version",
            "calculated_at",
            "calculation_inputs",
            "teacher_comment",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "final_score",
            "calculation_version",
            "calculated_at",
            "calculation_inputs",
            "created_at",
            "updated_at",
            "version",
        )


class ReportCardItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportCardItem
        fields = (
            "id",
            "report_card",
            "course_result",
            "course_title",
            "displayed_score",
            "displayed_level",
            "credit",
            "teacher_comment",
            "display_order",
        )
        read_only_fields = fields


class ReportCardSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="enrollment.student.person.full_name", read_only=True
    )
    student_no = serializers.CharField(
        source="enrollment.student.student_no", read_only=True
    )
    term_title = serializers.CharField(source="term.title", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    items = ReportCardItemSerializer(many=True, read_only=True)

    class Meta:
        model = ReportCard
        fields = (
            "id",
            "enrollment",
            "student_name",
            "student_no",
            "term",
            "term_title",
            "version_no",
            "generated_at",
            "published_at",
            "status",
            "status_display",
            "average_score",
            "rank_in_class",
            "attendance_summary",
            "principal_comment",
            "verification_code",
            "items",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "version_no",
            "generated_at",
            "published_at",
            "status",
            "average_score",
            "verification_code",
            "created_at",
            "updated_at",
            "version",
        )


class GenerateReportCardSerializer(serializers.Serializer):
    enrollment = serializers.UUIDField()
    term = serializers.UUIDField()


class BulkGenerateReportCardSerializer(serializers.Serializer):
    """تولید گروهی کارنامه برای یک کلاس."""

    class_group = serializers.UUIDField()
    term = serializers.UUIDField()


class CalculateResultSerializer(serializers.Serializer):
    course_offering = serializers.UUIDField()
    enrollment = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="در صورت خالی بودن، برای همه دانش‌آموزان کلاس محاسبه می‌شود.",
    )


class UnlockGradeItemSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=400)
