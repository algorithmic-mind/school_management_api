"""سریالایزرهای ماژول خدمات دانش‌آموزی."""

from __future__ import annotations

from rest_framework import serializers

from apps.core.serializers import AUDIT_FIELDS
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


# ---------------------------------------------------------------------------
# سلامت
# ---------------------------------------------------------------------------
class HealthAlertSerializer(serializers.ModelSerializer):
    """نمای کامل هشدار — فقط برای نقش‌های دارای مجوز `health.read`."""

    alert_type_display = serializers.CharField(
        source="get_alert_type_display", read_only=True
    )
    severity_display = serializers.CharField(
        source="get_severity_display", read_only=True
    )

    class Meta:
        model = HealthAlert
        fields = (
            "id",
            "health_profile",
            "alert_type",
            "alert_type_display",
            "title",
            "safe_summary",
            "instructions",
            "severity",
            "severity_display",
            "valid_until",
            "status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class HealthAlertSafeSerializer(serializers.ModelSerializer):
    """
    نمای محدود هشدار برای معلم و مسئول اردو.

    بخش ۷.۱۰: «Alert سلامت فقط حداقل اطلاعات لازم برای اقدام ایمن را نشان
    می‌دهد.» بنابراین `instructions` در این نما برنمی‌گردد.
    """

    alert_type_display = serializers.CharField(
        source="get_alert_type_display", read_only=True
    )

    class Meta:
        model = HealthAlert
        fields = (
            "id",
            "alert_type",
            "alert_type_display",
            "title",
            "safe_summary",
            "severity",
        )
        read_only_fields = fields


class HealthProfileSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="student.person.full_name", read_only=True
    )
    student_no = serializers.CharField(source="student.student_no", read_only=True)
    alerts = HealthAlertSerializer(many=True, read_only=True)
    active_alert_count = serializers.SerializerMethodField()

    class Meta:
        model = HealthProfile
        fields = (
            "id",
            "student",
            "student_name",
            "student_no",
            "blood_type",
            "height_cm",
            "weight_kg",
            "accessibility_needs",
            "emergency_contact_name",
            "emergency_contact_phone",
            "family_physician",
            "insurance_no",
            "confidentiality_level",
            "alerts",
            "active_alert_count",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")

    def get_active_alert_count(self, obj) -> int:
        return obj.alerts.filter(status="ACTIVE").count()


class HealthIncidentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="student.person.full_name", read_only=True
    )
    outcome_display = serializers.CharField(
        source="get_outcome_display", read_only=True
    )

    class Meta:
        model = HealthIncident
        fields = (
            "id",
            "student",
            "student_name",
            "occurred_at",
            "location",
            "description",
            "action_taken",
            "outcome",
            "outcome_display",
            "guardian_notified_at",
            "confidentiality_level",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "guardian_notified_at",
            "created_at",
            "updated_at",
            "version",
        )


# ---------------------------------------------------------------------------
# مشاوره
# ---------------------------------------------------------------------------
class CounselingSessionSerializer(serializers.ModelSerializer):
    """
    جلسه مشاوره.

    `protectedNote` فقط برای مشاور صاحب پرونده و نقش‌های دارای مجوز فیلدی
    برگردانده می‌شود؛ در غیر این صورت رشته خالی است (بخش ۷.۱۰).
    """

    class Meta:
        model = CounselingSession
        fields = (
            "id",
            "case",
            "held_at",
            "duration_minutes",
            "summary",
            "protected_note",
            "next_followup_at",
            "attendees",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is None:
            data["protected_note"] = ""
            return data

        user = request.user
        is_owner = (
            instance.case.counselor_employee_id
            and user.person_id
            and str(instance.case.counselor_employee_id) == str(user.person_id)
        )
        if not (user.is_superuser or is_owner or user.has_perm_code("counseling.update")):
            data["protected_note"] = ""
        return data


class CounselingCaseSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="student.person.full_name", read_only=True
    )
    student_no = serializers.CharField(source="student.student_no", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    session_count = serializers.IntegerField(source="sessions.count", read_only=True)

    class Meta:
        model = CounselingCase
        fields = (
            "id",
            "student",
            "student_name",
            "student_no",
            "counselor_employee_id",
            "referral_source",
            "subject",
            "priority",
            "status",
            "status_display",
            "opened_on",
            "closed_on",
            "action_plan",
            "confidentiality_level",
            "session_count",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


# ---------------------------------------------------------------------------
# انضباط
# ---------------------------------------------------------------------------
class BehaviorActionSerializer(serializers.ModelSerializer):
    action_type_display = serializers.CharField(
        source="get_action_type_display", read_only=True
    )

    class Meta:
        model = BehaviorAction
        fields = (
            "id",
            "incident",
            "action_type",
            "action_type_display",
            "details",
            "effective_from",
            "effective_until",
            "status",
            "completed_at",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class BehaviorIncidentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="student.person.full_name", read_only=True
    )
    student_no = serializers.CharField(source="student.student_no", read_only=True)
    incident_type_display = serializers.CharField(
        source="get_incident_type_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    actions = BehaviorActionSerializer(many=True, read_only=True)

    class Meta:
        model = BehaviorIncident
        fields = (
            "id",
            "student",
            "student_name",
            "student_no",
            "occurred_at",
            "location",
            "incident_type",
            "incident_type_display",
            "severity",
            "description",
            "witnesses",
            "student_statement",
            "status",
            "status_display",
            "investigation_note",
            "decided_at",
            "points",
            "guardian_notified_at",
            "actions",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "status",
            "decided_at",
            "guardian_notified_at",
            "created_at",
            "updated_at",
            "version",
        )


class BehaviorDecisionSerializer(serializers.Serializer):
    """تصمیم درباره یک رخداد رفتاری."""

    substantiated = serializers.BooleanField(
        help_text="آیا تخلف تأیید شد؟ (بخش ۷.۱۰: رخداد اتهام قطعی نیست)"
    )
    investigation_note = serializers.CharField(
        max_length=2000, required=False, allow_blank=True
    )
    points = serializers.IntegerField(
        required=False, default=0, help_text="منفی برای تخلف، مثبت برای تشویق"
    )


class StudentBehaviorSummarySerializer(serializers.Serializer):
    studentId = serializers.UUIDField()
    studentName = serializers.CharField()
    totalPoints = serializers.IntegerField()
    incidentCount = serializers.IntegerField()
    commendationCount = serializers.IntegerField()
    bySeverity = serializers.DictField(child=serializers.IntegerField())


# ---------------------------------------------------------------------------
# کتابخانه
# ---------------------------------------------------------------------------
class LibraryTitleSerializer(serializers.ModelSerializer):
    copy_count = serializers.IntegerField(source="copies.count", read_only=True)
    available_count = serializers.SerializerMethodField()

    class Meta:
        model = LibraryTitle
        fields = (
            "id",
            "isbn",
            "title",
            "author",
            "publisher",
            "publish_year",
            "material_type",
            "classification",
            "subject",
            "language",
            "copy_count",
            "available_count",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")

    def get_available_count(self, obj) -> int:
        return obj.copies.filter(status="AVAILABLE").count()


class LibraryCopySerializer(serializers.ModelSerializer):
    title_name = serializers.CharField(source="title_ref.title", read_only=True)

    class Meta:
        model = LibraryCopy
        fields = (
            "id",
            "title_ref",
            "title_name",
            "barcode",
            "location",
            "is_loanable",
            "acquisition_cost",
            "status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class LibraryLoanSerializer(serializers.ModelSerializer):
    borrower_name = serializers.CharField(
        source="borrower_person.full_name", read_only=True
    )
    copy_barcode = serializers.CharField(source="copy.barcode", read_only=True)
    title_name = serializers.CharField(source="copy.title_ref.title", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = LibraryLoan
        fields = (
            "id",
            "copy",
            "copy_barcode",
            "title_name",
            "borrower_person",
            "borrower_name",
            "loaned_at",
            "due_at",
            "returned_at",
            "renewal_count",
            "fine_amount",
            "fine_paid",
            "status",
            "is_overdue",
            "note",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "returned_at",
            "renewal_count",
            "status",
            "created_at",
            "updated_at",
            "version",
        )


class CreateLoanSerializer(serializers.Serializer):
    """
    ثبت امانت.

    امانت فقط برای نسخه «موجود» و «قابل امانت» مجاز است (بخش ۷.۱۰).
    """

    copy = serializers.UUIDField()
    borrower_person = serializers.UUIDField()
    loan_days = serializers.IntegerField(default=14, min_value=1, max_value=180)


class ReturnLoanSerializer(serializers.Serializer):
    condition_note = serializers.CharField(
        max_length=300, required=False, allow_blank=True, default=""
    )
    mark_lost = serializers.BooleanField(default=False)


# ---------------------------------------------------------------------------
# حمل‌ونقل
# ---------------------------------------------------------------------------
class VehicleSerializer(serializers.ModelSerializer):
    documents_valid = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = (
            "id",
            "plate_no",
            "model_name",
            "capacity",
            "inspection_valid_until",
            "insurance_valid_until",
            "status",
            "documents_valid",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")

    def get_documents_valid(self, obj) -> bool:
        """مدارک راننده/خودرو باید معتبر باشد (بخش ۷.۱۰)."""
        from django.utils import timezone

        today = timezone.localdate()
        if obj.inspection_valid_until and obj.inspection_valid_until < today:
            return False
        if obj.insurance_valid_until and obj.insurance_valid_until < today:
            return False
        return True


class RouteStopSerializer(serializers.ModelSerializer):
    class Meta:
        model = RouteStop
        fields = (
            "id",
            "route",
            "title",
            "address_line",
            "latitude",
            "longitude",
            "sequence_no",
            "scheduled_time",
        )
        read_only_fields = ("id",)


class TransportRouteSerializer(serializers.ModelSerializer):
    stops = RouteStopSerializer(many=True, read_only=True)
    campus_name = serializers.CharField(source="campus.name", read_only=True)
    vehicle_plate = serializers.CharField(
        source="default_vehicle.plate_no", read_only=True
    )
    vehicle_capacity = serializers.IntegerField(
        source="default_vehicle.capacity", read_only=True
    )
    active_rider_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = TransportRoute
        fields = (
            "id",
            "campus",
            "campus_name",
            "code",
            "title",
            "direction",
            "default_vehicle",
            "vehicle_plate",
            "vehicle_capacity",
            "default_driver_employee_id",
            "monthly_fee",
            "status",
            "active_rider_count",
            "stops",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class StudentRouteAssignmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="student.person.full_name", read_only=True
    )
    route_code = serializers.CharField(source="route.code", read_only=True)
    pickup_stop_title = serializers.CharField(
        source="pickup_stop.title", read_only=True
    )

    class Meta:
        model = StudentRouteAssignment
        fields = (
            "id",
            "student",
            "student_name",
            "route",
            "route_code",
            "pickup_stop",
            "pickup_stop_title",
            "dropoff_stop",
            "effective_from",
            "effective_to",
            "status",
            "note",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class RouteRunSerializer(serializers.ModelSerializer):
    route_code = serializers.CharField(source="route.code", read_only=True)
    vehicle_plate = serializers.CharField(source="vehicle.plate_no", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    event_count = serializers.IntegerField(
        source="ridership_events.count", read_only=True
    )

    class Meta:
        model = RouteRun
        fields = (
            "id",
            "route",
            "route_code",
            "vehicle",
            "vehicle_plate",
            "driver_employee_id",
            "supervisor_employee_id",
            "run_date",
            "direction",
            "departed_at",
            "completed_at",
            "status",
            "status_display",
            "event_count",
            "note",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class RidershipEventSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="student.person.full_name", read_only=True
    )
    event_type_display = serializers.CharField(
        source="get_event_type_display", read_only=True
    )

    class Meta:
        model = RidershipEvent
        fields = (
            "id",
            "route_run",
            "student",
            "student_name",
            "stop",
            "event_type",
            "event_type_display",
            "occurred_at",
            "source",
            "guardian_notified_at",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "guardian_notified_at",
            "created_at",
            "updated_at",
            "version",
        )


class RouteManifestRowSerializer(serializers.Serializer):
    studentId = serializers.UUIDField()
    studentNo = serializers.CharField()
    studentName = serializers.CharField()
    pickupStop = serializers.CharField(allow_null=True)
    dropoffStop = serializers.CharField(allow_null=True)
    lastEvent = serializers.CharField(allow_null=True)
    lastEventAt = serializers.DateTimeField(allow_null=True)


class RouteManifestSerializer(serializers.Serializer):
    """فهرست مسافران یک اجرای مسیر (بخش ۱۴.۵ سند فرانت)."""

    routeRunId = serializers.UUIDField()
    routeCode = serializers.CharField()
    runDate = serializers.DateField()
    direction = serializers.CharField()
    vehiclePlate = serializers.CharField()
    capacity = serializers.IntegerField()
    riderCount = serializers.IntegerField()
    rows = RouteManifestRowSerializer(many=True)
