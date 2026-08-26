"""سریالایزرهای ماژول بانک سؤال و آزمون."""

from __future__ import annotations

from rest_framework import serializers

from apps.assessment.models import (
    AttemptAnswer,
    Exam,
    ExamAttempt,
    ExamQuestion,
    ExamRegistration,
    ExamSection,
    ExamSession,
    GradeAppeal,
    GradeReview,
    ProctorEvent,
    Question,
    QuestionBank,
    QuestionOption,
    QuestionTag,
    QuestionVersion,
)
from apps.core.serializers import AUDIT_FIELDS


class QuestionBankSerializer(serializers.ModelSerializer):
    question_count = serializers.IntegerField(source="questions.count", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)

    class Meta:
        model = QuestionBank
        fields = (
            "id",
            "school",
            "owner_user_id",
            "title",
            "description",
            "course",
            "course_title",
            "visibility",
            "status",
            "question_count",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class QuestionTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionTag
        fields = ("id", "school", "tag_type", "value")
        read_only_fields = ("id",)


class QuestionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionOption
        fields = (
            "id",
            "question_version",
            "option_key",
            "body",
            "is_correct",
            "credit_percent",
            "display_order",
        )
        read_only_fields = ("id",)


class QuestionOptionPublicSerializer(serializers.ModelSerializer):
    """
    نمای گزینه برای دانش‌آموز — بدون افشای کلید پاسخ.

    بخش ۱۵.۲: «Log و Trace نباید متن پاسخ آزمون … را ذخیره کنند.» به‌طریق اولی
    پاسخ صحیح نباید در پاسخ API آزمون در حال اجرا برگردد.
    """

    class Meta:
        model = QuestionOption
        fields = ("id", "option_key", "body", "display_order")
        read_only_fields = fields


class QuestionVersionSerializer(serializers.ModelSerializer):
    options = QuestionOptionSerializer(many=True, read_only=True)
    question_type = serializers.CharField(
        source="question.question_type", read_only=True
    )
    difficulty_display = serializers.CharField(
        source="get_difficulty_display", read_only=True
    )

    class Meta:
        model = QuestionVersion
        fields = (
            "id",
            "question",
            "question_type",
            "version_no",
            "body",
            "explanation",
            "grading_rubric",
            "default_score",
            "difficulty",
            "difficulty_display",
            "locale",
            "grade_level",
            "correct_answer",
            "review_status",
            "reviewed_at",
            "media",
            "options",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "version_no",
            "review_status",
            "reviewed_at",
            "created_at",
            "updated_at",
            "version",
        )


class QuestionSerializer(serializers.ModelSerializer):
    current_version_detail = QuestionVersionSerializer(
        source="current_version", read_only=True
    )
    question_type_display = serializers.CharField(
        source="get_question_type_display", read_only=True
    )
    is_auto_graded = serializers.BooleanField(read_only=True)
    bank_title = serializers.CharField(source="bank.title", read_only=True)

    class Meta:
        model = Question
        fields = (
            "id",
            "bank",
            "bank_title",
            "question_type",
            "question_type_display",
            "lifecycle_status",
            "is_auto_graded",
            "current_version",
            "current_version_detail",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "lifecycle_status",
            "current_version",
            "created_at",
            "updated_at",
            "version",
        )


class QuestionCreateSerializer(serializers.Serializer):
    """
    ایجاد سؤال به‌همراه نسخه اول و گزینه‌ها در یک درخواست.

    این Endpoint برای «ویرایشگر سؤال» فرانت (بخش ۹.۲ سند فرانت) طراحی شده است.
    """

    bank = serializers.UUIDField()
    question_type = serializers.ChoiceField(
        choices=[choice[0] for choice in Question._meta.get_field("question_type").choices]
    )
    body = serializers.CharField()
    explanation = serializers.CharField(required=False, allow_blank=True)
    grading_rubric = serializers.CharField(required=False, allow_blank=True)
    default_score = serializers.DecimalField(
        max_digits=6, decimal_places=2, default=1
    )
    difficulty = serializers.CharField(default="MEDIUM")
    grade_level = serializers.UUIDField(required=False, allow_null=True)
    correct_answer = serializers.JSONField(required=False, default=dict)
    options = QuestionOptionSerializer(many=True, required=False)
    tag_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )


class ExamQuestionSerializer(serializers.ModelSerializer):
    question_body = serializers.CharField(
        source="question_version.body", read_only=True
    )
    question_type = serializers.CharField(
        source="question_version.question.question_type", read_only=True
    )

    class Meta:
        model = ExamQuestion
        fields = (
            "id",
            "section",
            "question_version",
            "question_body",
            "question_type",
            "score",
            "display_order",
            "is_required",
        )
        read_only_fields = ("id",)


class ExamSectionSerializer(serializers.ModelSerializer):
    questions = ExamQuestionSerializer(many=True, read_only=True)
    question_count = serializers.IntegerField(source="questions.count", read_only=True)

    class Meta:
        model = ExamSection
        fields = (
            "id",
            "exam",
            "title",
            "instructions",
            "display_order",
            "time_limit_minutes",
            "question_count",
            "questions",
        )
        read_only_fields = ("id",)


class ExamSessionSerializer(serializers.ModelSerializer):
    exam_title = serializers.CharField(source="exam.title", read_only=True)
    room_code = serializers.CharField(source="room.code", read_only=True)
    registration_count = serializers.IntegerField(
        source="registrations.count", read_only=True
    )

    class Meta:
        model = ExamSession
        fields = (
            "id",
            "exam",
            "exam_title",
            "room",
            "room_code",
            "title",
            "opens_at",
            "closes_at",
            "duration_minutes",
            "attempt_limit",
            "proctor_employee_id",
            "status",
            "registration_count",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")

    def validate(self, attrs):
        opens_at = attrs.get("opens_at") or getattr(self.instance, "opens_at", None)
        closes_at = attrs.get("closes_at") or getattr(self.instance, "closes_at", None)
        if opens_at and closes_at and closes_at <= opens_at:
            raise serializers.ValidationError(
                {"closes_at": "پایان پنجره باید بعد از شروع آن باشد."}
            )
        return attrs


class ExamSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(
        source="course_offering.course.title", read_only=True
    )
    class_group_code = serializers.CharField(
        source="course_offering.class_group.code", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    mode_display = serializers.CharField(source="get_mode_display", read_only=True)
    total_question_score = serializers.DecimalField(
        max_digits=8, decimal_places=2, read_only=True
    )
    section_count = serializers.IntegerField(source="sections.count", read_only=True)

    class Meta:
        model = Exam
        fields = (
            "id",
            "course_offering",
            "course_title",
            "class_group_code",
            "code",
            "title",
            "mode",
            "mode_display",
            "purpose",
            "max_score",
            "total_question_score",
            "instructions",
            "shuffle_questions",
            "shuffle_options",
            "allow_backtrack",
            "show_result_immediately",
            "status",
            "status_display",
            "published_at",
            "results_published_at",
            "appeal_deadline",
            "cancel_reason",
            "section_count",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "status",
            "published_at",
            "results_published_at",
            "created_at",
            "updated_at",
            "version",
        )


class ExamDetailSerializer(ExamSerializer):
    sections = ExamSectionSerializer(many=True, read_only=True)
    sessions = ExamSessionSerializer(many=True, read_only=True)

    class Meta(ExamSerializer.Meta):
        fields = ExamSerializer.Meta.fields + ("sections", "sessions")


class ExamRegistrationSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="enrollment.student.person.full_name", read_only=True
    )
    student_no = serializers.CharField(
        source="enrollment.student.student_no", read_only=True
    )

    class Meta:
        model = ExamRegistration
        fields = (
            "id",
            "exam_session",
            "enrollment",
            "student_name",
            "student_no",
            "seat_no",
            "extra_time_minutes",
            "registration_status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class AttemptAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttemptAnswer
        fields = (
            "id",
            "attempt",
            "exam_question",
            "response_payload",
            "attachment",
            "saved_at",
            "save_revision",
            "awarded_score",
            "grading_status",
            "time_spent_seconds",
        )
        read_only_fields = (
            "id",
            "saved_at",
            "save_revision",
            "awarded_score",
            "grading_status",
        )


class ExamAttemptSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="registration.enrollment.student.person.full_name", read_only=True
    )
    exam_title = serializers.CharField(
        source="registration.exam_session.exam.title", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    remaining_seconds = serializers.SerializerMethodField()

    class Meta:
        model = ExamAttempt
        fields = (
            "id",
            "registration",
            "student_name",
            "exam_title",
            "attempt_no",
            "started_at",
            "submitted_at",
            "last_saved_at",
            "expires_at",
            "remaining_seconds",
            "auto_score",
            "manual_score",
            "final_score",
            "status",
            "status_display",
            "calculation_version",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = fields

    def get_remaining_seconds(self, obj) -> int | None:
        from django.utils import timezone

        if not obj.expires_at:
            return None
        delta = (obj.expires_at - timezone.now()).total_seconds()
        return max(int(delta), 0)


class StartAttemptSerializer(serializers.Serializer):
    """بدنه شروع تلاش."""

    registration = serializers.UUIDField(help_text="شناسه ثبت‌نام آزمون")


class SaveAnswerSerializer(serializers.Serializer):
    """
    ذخیره خودکار پاسخ.

    قالب `responsePayload` بر اساس نوع سؤال:
    - چندگزینه‌ای: `{"selectedKeys": ["B"]}`
    - چندپاسخی: `{"selectedKeys": ["A", "C"]}`
    - عددی: `{"value": 3.14}`
    - کوتاه‌پاسخ/تشریحی: `{"text": "..."}`
    - تطبیقی: `{"pairs": {"1": "ب", "2": "الف"}}`
    - ترتیبی: `{"order": ["c", "a", "b"]}`
    """

    exam_question = serializers.UUIDField()
    response_payload = serializers.JSONField()
    time_spent_seconds = serializers.IntegerField(required=False, default=0)


class AttemptQuestionSerializer(serializers.Serializer):
    """سؤال در نمای دانش‌آموز — بدون کلید پاسخ."""

    examQuestionId = serializers.UUIDField()
    sectionTitle = serializers.CharField()
    questionType = serializers.CharField()
    body = serializers.CharField()
    score = serializers.DecimalField(max_digits=6, decimal_places=2)
    displayOrder = serializers.IntegerField()
    isRequired = serializers.BooleanField()
    options = QuestionOptionPublicSerializer(many=True)
    savedAnswer = serializers.JSONField(allow_null=True)


class AttemptPaperSerializer(serializers.Serializer):
    """برگه آزمون در حال اجرا (پوسته ایزوله آزمون — بخش ۹.۶ سند فرانت)."""

    attemptId = serializers.UUIDField()
    examTitle = serializers.CharField()
    instructions = serializers.CharField(allow_blank=True)
    maxScore = serializers.DecimalField(max_digits=6, decimal_places=2)
    allowBacktrack = serializers.BooleanField()
    expiresAt = serializers.DateTimeField(allow_null=True)
    remainingSeconds = serializers.IntegerField(allow_null=True)
    questions = AttemptQuestionSerializer(many=True)


class ProctorEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProctorEvent
        fields = (
            "id",
            "attempt",
            "event_type",
            "severity",
            "occurred_at",
            "evidence_ref",
            "note",
        )
        read_only_fields = ("id",)


class GradeReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeReview
        fields = (
            "id",
            "attempt_answer",
            "reviewer_id",
            "awarded_score",
            "feedback",
            "review_type",
            "is_anonymous",
            "reviewed_at",
        )
        read_only_fields = ("id", "reviewer_id", "reviewed_at")


class ManualGradeSerializer(serializers.Serializer):
    score = serializers.DecimalField(max_digits=8, decimal_places=2)
    feedback = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    review_type = serializers.ChoiceField(
        choices=["FIRST_PASS", "SECOND_PASS", "APPEAL", "MODERATION"],
        default="FIRST_PASS",
    )


class GradeAppealSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="attempt.registration.enrollment.student.person.full_name",
        read_only=True,
    )

    class Meta:
        model = GradeAppeal
        fields = (
            "id",
            "attempt",
            "student_name",
            "submitted_by_id",
            "reason",
            "status",
            "resolution",
            "resolved_at",
            "score_before",
            "score_after",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "status",
            "resolved_at",
            "score_before",
            "score_after",
            "created_at",
            "updated_at",
            "version",
        )


class ResolveAppealSerializer(serializers.Serializer):
    accepted = serializers.BooleanField(help_text="آیا اعتراض پذیرفته شد؟")
    resolution = serializers.CharField(max_length=2000)


class GradingQueueRowSerializer(serializers.Serializer):
    """یک قلم در صف تصحیح تشریحی (بخش ۹.۸ سند فرانت)."""

    attemptAnswerId = serializers.UUIDField()
    attemptId = serializers.UUIDField()
    examTitle = serializers.CharField()
    questionBody = serializers.CharField()
    responseText = serializers.CharField(allow_blank=True)
    maxScore = serializers.DecimalField(max_digits=6, decimal_places=2)
    gradingRubric = serializers.CharField(allow_blank=True)
    studentLabel = serializers.CharField(
        help_text="در حالت ناشناس‌سازی، به‌جای نام، شناسه مستعار برمی‌گردد."
    )


class QuestionAnalysisRowSerializer(serializers.Serializer):
    """تحلیل یک سؤال آزمون (بخش ۴.۴)."""

    examQuestionId = serializers.UUIDField()
    sectionTitle = serializers.CharField()
    questionBody = serializers.CharField()
    questionType = serializers.CharField()
    maxScore = serializers.FloatField()
    responseCount = serializers.IntegerField()
    correctPercent = serializers.FloatField(allow_null=True)
    averageScore = serializers.FloatField(allow_null=True)
    averageTimeSeconds = serializers.IntegerField()
