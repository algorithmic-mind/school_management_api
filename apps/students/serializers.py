"""سریالایزرهای ماژول امور دانش‌آموزان."""

from __future__ import annotations

from rest_framework import serializers

from apps.core.serializers import AUDIT_FIELDS
from apps.identity.serializers import PersonListSerializer, PersonSerializer
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


class GuardianSerializer(serializers.ModelSerializer):
    person_detail = PersonListSerializer(source="person", read_only=True)
    full_name = serializers.CharField(source="person.full_name", read_only=True)

    class Meta:
        model = Guardian
        fields = (
            "id",
            "person",
            "person_detail",
            "full_name",
            "occupation",
            "education_level",
            "workplace",
            "status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class StudentGuardianSerializer(serializers.ModelSerializer):
    guardian_name = serializers.CharField(
        source="guardian.person.full_name", read_only=True
    )
    student_name = serializers.CharField(
        source="student.person.full_name", read_only=True
    )
    relationship_display = serializers.CharField(
        source="get_relationship_type_display", read_only=True
    )
    guardian_mobile = serializers.SerializerMethodField()

    class Meta:
        model = StudentGuardian
        fields = (
            "id",
            "student",
            "student_name",
            "guardian",
            "guardian_name",
            "guardian_mobile",
            "relationship_type",
            "relationship_display",
            "has_custody",
            "can_pickup",
            "receives_reports",
            "financially_responsible",
            "is_emergency_contact",
            "contact_priority",
            "effective_from",
            "effective_to",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")

    def get_guardian_mobile(self, obj) -> str:
        contact = obj.guardian.person.contact_points.filter(
            contact_type="MOBILE", is_primary=True
        ).first()
        return contact.value if contact else ""


class StudentListSerializer(serializers.ModelSerializer):
    """نمای سبک فهرست دانش‌آموزان (بخش ۷.۱ سند فرانت)."""

    full_name = serializers.CharField(read_only=True)
    national_id = serializers.CharField(source="person.national_id", read_only=True)
    gender = serializers.CharField(source="person.gender", read_only=True)
    current_class = serializers.SerializerMethodField()
    current_grade = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Student
        fields = (
            "id",
            "student_no",
            "full_name",
            "national_id",
            "gender",
            "status",
            "status_display",
            "current_class",
            "current_grade",
            "joined_on",
        )

    def get_current_class(self, obj) -> str | None:
        enrollment = obj.current_enrollment
        if not enrollment:
            return None
        class_group = enrollment.current_class_group
        return class_group.code if class_group else None

    def get_current_grade(self, obj) -> str | None:
        enrollment = obj.current_enrollment
        return enrollment.grade_level.title if enrollment else None


class StudentSerializer(serializers.ModelSerializer):
    person_detail = PersonSerializer(source="person", read_only=True)
    full_name = serializers.CharField(read_only=True)
    guardians = StudentGuardianSerializer(
        source="guardian_links", many=True, read_only=True
    )

    class Meta:
        model = Student
        fields = (
            "id",
            "person",
            "person_detail",
            "full_name",
            "student_no",
            "joined_on",
            "status",
            "previous_school",
            "notes",
            "guardians",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "student_no", "created_at", "updated_at", "version")


class AdmissionApplicationSerializer(serializers.ModelSerializer):
    applicant_name = serializers.CharField(source="person.full_name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    grade_level_title = serializers.CharField(
        source="preferred_grade_level.title", read_only=True
    )
    campus_name = serializers.CharField(source="preferred_campus.name", read_only=True)

    class Meta:
        model = AdmissionApplication
        fields = (
            "id",
            "person",
            "applicant_name",
            "academic_year",
            "preferred_campus",
            "campus_name",
            "preferred_grade_level",
            "grade_level_title",
            "preferred_program",
            "application_no",
            "status",
            "status_display",
            "submitted_at",
            "reviewer_id",
            "interview_at",
            "entrance_score",
            "interview_score",
            "final_score",
            "waitlist_rank",
            "conditions",
            "decision_reason",
            "decided_at",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "status",
            "submitted_at",
            "decided_at",
            "created_at",
            "updated_at",
            "version",
        )


class ClassMembershipSerializer(serializers.ModelSerializer):
    class_group_code = serializers.CharField(source="class_group.code", read_only=True)
    student_name = serializers.CharField(
        source="enrollment.student.person.full_name", read_only=True
    )
    student_no = serializers.CharField(
        source="enrollment.student.student_no", read_only=True
    )

    class Meta:
        model = ClassMembership
        fields = (
            "id",
            "enrollment",
            "student_name",
            "student_no",
            "class_group",
            "class_group_code",
            "is_primary",
            "status",
            "effective_from",
            "effective_to",
            "exit_reason",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class EnrollmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="student.person.full_name", read_only=True
    )
    student_no = serializers.CharField(source="student.student_no", read_only=True)
    grade_level_title = serializers.CharField(
        source="grade_level.title", read_only=True
    )
    academic_year_title = serializers.CharField(
        source="academic_year.title", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    current_class_code = serializers.SerializerMethodField()
    class_memberships = ClassMembershipSerializer(many=True, read_only=True)

    class Meta:
        model = Enrollment
        fields = (
            "id",
            "student",
            "student_name",
            "student_no",
            "academic_year",
            "academic_year_title",
            "campus",
            "grade_level",
            "grade_level_title",
            "program",
            "admission_application",
            "enrollment_no",
            "enrolled_on",
            "status",
            "status_display",
            "current_class_code",
            "exit_date",
            "exit_reason",
            "class_memberships",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "enrollment_no",
            "status",
            "created_at",
            "updated_at",
            "version",
        )

    def get_current_class_code(self, obj) -> str | None:
        class_group = obj.current_class_group
        return class_group.code if class_group else None


class ConsentSerializer(serializers.ModelSerializer):
    consent_type_display = serializers.CharField(
        source="get_consent_type_display", read_only=True
    )
    guardian_name = serializers.CharField(
        source="guardian.person.full_name", read_only=True
    )

    class Meta:
        model = Consent
        fields = (
            "id",
            "student",
            "guardian",
            "guardian_name",
            "consent_type",
            "consent_type_display",
            "status",
            "granted_at",
            "revoked_at",
            "revoke_reason",
            "expires_at",
            "policy_version",
            "policy_text_snapshot",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "status",
            "revoked_at",
            "created_at",
            "updated_at",
            "version",
        )


class StudentTransferSerializer(serializers.ModelSerializer):
    from_class_code = serializers.CharField(
        source="from_class_group.code", read_only=True
    )
    to_class_code = serializers.CharField(source="to_class_group.code", read_only=True)

    class Meta:
        model = StudentTransfer
        fields = (
            "id",
            "student",
            "enrollment",
            "transfer_type",
            "from_class_group",
            "from_class_code",
            "to_class_group",
            "to_class_code",
            "effective_on",
            "reason",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class StudentStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentStatusHistory
        fields = (
            "id",
            "student",
            "from_status",
            "to_status",
            "reason_code",
            "reason",
            "changed_at",
        )
        read_only_fields = fields


# ---------------------------------------------------------------------------
# بدنه عملیات (Command)
# ---------------------------------------------------------------------------
class PlaceInClassSerializer(serializers.Serializer):
    class_group = serializers.UUIDField(help_text="شناسه کلاس مقصد")
    effective_from = serializers.DateField(
        required=False, help_text="تاریخ اثر؛ پیش‌فرض امروز"
    )


class TransferClassSerializer(serializers.Serializer):
    target_class_group = serializers.UUIDField(help_text="شناسه کلاس مقصد")
    reason = serializers.CharField(max_length=400, help_text="علت انتقال")
    effective_on = serializers.DateField(required=False)


class WithdrawSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=400)
    exit_date = serializers.DateField(required=False)


class AdmissionDecisionSerializer(serializers.Serializer):
    reason = serializers.CharField(
        max_length=400, required=False, allow_blank=True
    )
    conditions = serializers.CharField(
        max_length=1000, required=False, allow_blank=True,
        help_text="فقط برای پذیرش مشروط",
    )
    final_score = serializers.DecimalField(
        max_digits=6, decimal_places=2, required=False
    )


class ConvertAdmissionSerializer(serializers.Serializer):
    enrolled_on = serializers.DateField(required=False)


class Student360Serializer(serializers.Serializer):
    """
    پرونده ۳۶۰ درجه دانش‌آموز (بخش ۷.۲ سند فرانت و ۱۲.۲ سند تحلیل).

    هر بخش فقط در صورت داشتن مجوز پر می‌شود؛ در غیر این صورت `null` است.
    """

    student = StudentListSerializer()
    person = PersonSerializer()
    guardians = StudentGuardianSerializer(many=True)
    enrollments = EnrollmentSerializer(many=True)
    consents = ConsentSerializer(many=True)
    attendanceSummary = serializers.DictField(allow_null=True)
    financialSummary = serializers.DictField(allow_null=True)
    academicSummary = serializers.DictField(allow_null=True)
    healthSummary = serializers.DictField(allow_null=True)


class PromotionBatchSerializer(serializers.ModelSerializer):
    decision_count = serializers.IntegerField(source="decisions.count", read_only=True)

    class Meta:
        model = PromotionBatch
        fields = (
            "id",
            "source_year",
            "target_year",
            "title",
            "status",
            "executed_at",
            "decision_count",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "status",
            "executed_at",
            "created_at",
            "updated_at",
            "version",
        )


class PromotionDecisionRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="enrollment.student.person.full_name", read_only=True
    )

    class Meta:
        model = PromotionDecisionRecord
        fields = (
            "id",
            "batch",
            "enrollment",
            "student_name",
            "decision",
            "target_grade_level",
            "note",
            "applied",
        )
        read_only_fields = ("id", "applied")


class PromotionPreviewRowSerializer(serializers.Serializer):
    enrollmentId = serializers.UUIDField()
    studentNo = serializers.CharField()
    studentName = serializers.CharField()
    currentGrade = serializers.CharField()
    suggestedDecision = serializers.CharField()
    targetGradeLevelId = serializers.UUIDField(allow_null=True)
    targetGrade = serializers.CharField(allow_null=True)
    errors = serializers.ListField(child=serializers.CharField())


class PromotionPreviewSerializer(serializers.Serializer):
    """خروجی مرحله پیش‌نمایش عملیات گروهی (بخش ۱۱.۶)."""

    totalRows = serializers.IntegerField()
    validRows = serializers.IntegerField()
    invalidRows = serializers.IntegerField()
    rows = PromotionPreviewRowSerializer(many=True)
