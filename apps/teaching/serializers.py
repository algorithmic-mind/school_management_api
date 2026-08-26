"""سریالایزرهای ماژول آموزش روزانه."""

from __future__ import annotations

from rest_framework import serializers

from apps.core.serializers import AUDIT_FIELDS
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


class SessionTeacherSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(
        source="teacher_profile.employee.person.full_name", read_only=True
    )

    class Meta:
        model = SessionTeacher
        fields = ("id", "session", "teacher_profile", "teacher_name", "duty")
        read_only_fields = ("id",)


class TeachingSessionSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(
        source="course_offering.course.title", read_only=True
    )
    class_group_code = serializers.CharField(
        source="course_offering.class_group.code", read_only=True
    )
    room_code = serializers.CharField(source="room.code", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    teachers = SessionTeacherSerializer(many=True, read_only=True)
    attendance_summary = serializers.SerializerMethodField()

    class Meta:
        model = TeachingSession
        fields = (
            "id",
            "course_offering",
            "course_title",
            "class_group_code",
            "schedule_entry",
            "room",
            "room_code",
            "starts_at",
            "ends_at",
            "session_type",
            "status",
            "status_display",
            "topic",
            "cancel_reason",
            "attendance_finalized_at",
            "teachers",
            "attendance_summary",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "attendance_finalized_at",
            "created_at",
            "updated_at",
            "version",
        )

    def get_attendance_summary(self, obj) -> dict:
        from django.db.models import Count

        rows = obj.attendance_records.values("attendance_status").annotate(
            count=Count("id")
        )
        return {row["attendance_status"]: row["count"] for row in rows}

    def validate(self, attrs):
        starts_at = attrs.get("starts_at") or getattr(self.instance, "starts_at", None)
        ends_at = attrs.get("ends_at") or getattr(self.instance, "ends_at", None)
        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError(
                {"ends_at": "پایان جلسه باید بعد از شروع آن باشد."}
            )
        return attrs


class AttendanceRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="enrollment.student.person.full_name", read_only=True
    )
    student_no = serializers.CharField(
        source="enrollment.student.student_no", read_only=True
    )
    status_display = serializers.CharField(
        source="get_attendance_status_display", read_only=True
    )
    has_justification = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceRecord
        fields = (
            "id",
            "session",
            "enrollment",
            "student_name",
            "student_no",
            "attendance_status",
            "status_display",
            "late_minutes",
            "early_leave_minutes",
            "reason_code",
            "note",
            "finalization_status",
            "amended_reason",
            "has_justification",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "finalization_status",
            "created_at",
            "updated_at",
            "version",
        )

    def get_has_justification(self, obj) -> bool:
        return hasattr(obj, "justification")


class AttendanceRosterRowSerializer(serializers.Serializer):
    """یک ردیف فهرست حضور برای ثبت گروهی."""

    enrollmentId = serializers.UUIDField()
    studentNo = serializers.CharField(read_only=True)
    studentName = serializers.CharField(read_only=True)
    attendanceStatus = serializers.CharField()
    lateMinutes = serializers.IntegerField(required=False, default=0)
    earlyLeaveMinutes = serializers.IntegerField(required=False, default=0)
    reasonCode = serializers.CharField(required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")


class AttendanceRosterSerializer(serializers.Serializer):
    """
    فهرست حضور یک جلسه.

    خروجی GET برای رندر فرم ثبت حضور و ورودی POST برای ثبت گروهی
    (بخش ۸.۴ سند فرانت).
    """

    sessionId = serializers.UUIDField(read_only=True)
    classGroupCode = serializers.CharField(read_only=True)
    courseTitle = serializers.CharField(read_only=True)
    startsAt = serializers.DateTimeField(read_only=True)
    finalizationStatus = serializers.CharField(read_only=True)
    rows = AttendanceRosterRowSerializer(many=True)


class BulkAttendanceSerializer(serializers.Serializer):
    """بدنه ثبت گروهی حضور."""

    rows = AttendanceRosterRowSerializer(many=True)
    finalize = serializers.BooleanField(
        default=False,
        help_text="اگر true باشد، پس از ثبت، حضور جلسه نهایی می‌شود.",
    )
    reason = serializers.CharField(
        max_length=400,
        required=False,
        allow_blank=True,
        default="",
        help_text=(
            "علت اصلاح. اگر حضور جلسه قبلاً نهایی شده باشد، این فیلد الزامی است "
            "(بخش ۷.۵: اصلاح پس از نهایی‌شدن نیازمند علت و مجوز است)."
        ),
    )


class AmendAttendanceSerializer(serializers.Serializer):
    """اصلاح حضور پس از نهایی‌سازی — نیازمند علت (بخش ۷.۵)."""

    attendance_status = serializers.CharField()
    reason = serializers.CharField(max_length=400)


class AbsenceJustificationSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="attendance.enrollment.student.person.full_name", read_only=True
    )
    session_date = serializers.DateTimeField(
        source="attendance.session.starts_at", read_only=True
    )

    class Meta:
        model = AbsenceJustification
        fields = (
            "id",
            "attendance",
            "student_name",
            "session_date",
            "submitted_by_guardian_id",
            "reason",
            "evidence_file",
            "decision",
            "decided_at",
            "decision_note",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "decision",
            "decided_at",
            "created_at",
            "updated_at",
            "version",
        )


class LessonPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonPlan
        fields = (
            "id",
            "course_offering",
            "session",
            "title",
            "objectives",
            "content",
            "planned_for",
            "status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class AssignmentSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(
        source="course_offering.course.title", read_only=True
    )
    class_group_code = serializers.CharField(
        source="course_offering.class_group.code", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    submission_stats = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = (
            "id",
            "course_offering",
            "course_title",
            "class_group_code",
            "title",
            "description",
            "opens_at",
            "due_at",
            "close_at",
            "max_score",
            "allow_late_submission",
            "late_penalty_percent",
            "max_attempts",
            "status",
            "status_display",
            "published_at",
            "submission_stats",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "status",
            "published_at",
            "created_at",
            "updated_at",
            "version",
        )

    def get_submission_stats(self, obj) -> dict:
        from django.db.models import Count

        rows = obj.submissions.values("status").annotate(count=Count("id"))
        return {row["status"]: row["count"] for row in rows}

    def validate(self, attrs):
        opens_at = attrs.get("opens_at") or getattr(self.instance, "opens_at", None)
        due_at = attrs.get("due_at") or getattr(self.instance, "due_at", None)
        if opens_at and due_at and due_at <= opens_at:
            raise serializers.ValidationError(
                {"due_at": "مهلت تحویل باید بعد از زمان بازشدن تکلیف باشد."}
            )
        return attrs


class SubmissionFeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubmissionFeedback
        fields = (
            "id",
            "submission",
            "reviewer_id",
            "score",
            "feedback",
            "reviewed_at",
            "is_final",
        )
        read_only_fields = ("id", "reviewer_id", "reviewed_at")


class AssignmentSubmissionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="enrollment.student.person.full_name", read_only=True
    )
    student_no = serializers.CharField(
        source="enrollment.student.student_no", read_only=True
    )
    assignment_title = serializers.CharField(source="assignment.title", read_only=True)
    feedbacks = SubmissionFeedbackSerializer(many=True, read_only=True)

    class Meta:
        model = AssignmentSubmission
        fields = (
            "id",
            "assignment",
            "assignment_title",
            "enrollment",
            "student_name",
            "student_no",
            "attempt_no",
            "submitted_at",
            "content",
            "attachment",
            "status",
            "is_late",
            "late_minutes",
            "policy_snapshot",
            "feedbacks",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "status",
            "is_late",
            "late_minutes",
            "policy_snapshot",
            "submitted_at",
            "created_at",
            "updated_at",
            "version",
        )


class GradeSubmissionSerializer(serializers.Serializer):
    score = serializers.DecimalField(max_digits=6, decimal_places=2)
    feedback = serializers.CharField(
        max_length=2000, required=False, allow_blank=True
    )


class LearningResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearningResource
        fields = (
            "id",
            "course_offering",
            "resource_type",
            "title",
            "description",
            "file",
            "url",
            "visibility",
            "published_at",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class AttendanceMonitorRowSerializer(serializers.Serializer):
    """ردیف پایش حضور مدرسه (بخش ۸.۵ سند فرانت)."""

    classGroupId = serializers.UUIDField()
    classGroupCode = serializers.CharField()
    gradeLevel = serializers.CharField()
    totalSessions = serializers.IntegerField()
    finalizedSessions = serializers.IntegerField()
    pendingSessions = serializers.IntegerField()
    absentToday = serializers.IntegerField()


class StudentAttendanceSummarySerializer(serializers.Serializer):
    """خلاصه حضور یک دانش‌آموز برای هشدار نصاب حضور (بخش ۴.۳)."""

    enrollmentId = serializers.UUIDField()
    studentName = serializers.CharField()
    totalSessions = serializers.IntegerField()
    byStatus = serializers.DictField(child=serializers.IntegerField())
    presentPercent = serializers.FloatField(allow_null=True)
    consecutiveAbsences = serializers.IntegerField()
    belowThreshold = serializers.BooleanField()
