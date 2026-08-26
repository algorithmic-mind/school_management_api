"""سریالایزرهای ماژول ساختار سازمانی و آموزشی."""

from __future__ import annotations

from rest_framework import serializers

from apps.core.serializers import AUDIT_FIELDS
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


class SchoolSerializer(serializers.ModelSerializer):
    school_type_display = serializers.CharField(
        source="get_school_type_display", read_only=True
    )
    campus_count = serializers.IntegerField(source="campuses.count", read_only=True)

    class Meta:
        model = School
        fields = (
            "id",
            "code",
            "name",
            "school_type",
            "school_type_display",
            "gender_policy",
            "registration_no",
            "currency",
            "timezone",
            "logo",
            "status",
            "campus_count",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class CampusSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source="school.name", read_only=True)

    class Meta:
        model = Campus
        fields = (
            "id",
            "school",
            "school_name",
            "code",
            "name",
            "address_line",
            "phone",
            "timezone",
            "status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class TermSerializer(serializers.ModelSerializer):
    class Meta:
        model = Term
        fields = (
            "id",
            "academic_year",
            "title",
            "starts_on",
            "ends_on",
            "sequence_no",
            "status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")

    def validate(self, attrs):
        starts_on = attrs.get("starts_on") or getattr(self.instance, "starts_on", None)
        ends_on = attrs.get("ends_on") or getattr(self.instance, "ends_on", None)
        year = attrs.get("academic_year") or getattr(
            self.instance, "academic_year", None
        )
        if starts_on and ends_on and ends_on <= starts_on:
            raise serializers.ValidationError(
                {"ends_on": "تاریخ پایان باید بعد از تاریخ شروع باشد."}
            )
        if year and starts_on and ends_on:
            # بازه سال تحصیلی باید همه ترم‌هایش را پوشش دهد (بخش ۷.۱)
            if starts_on < year.starts_on or ends_on > year.ends_on:
                raise serializers.ValidationError(
                    {
                        "starts_on": (
                            f"بازه ترم باید داخل بازه سال تحصیلی "
                            f"({year.starts_on} تا {year.ends_on}) باشد."
                        )
                    }
                )
        return attrs


class AcademicYearSerializer(serializers.ModelSerializer):
    terms = TermSerializer(many=True, read_only=True)
    school_name = serializers.CharField(source="school.name", read_only=True)
    is_editable = serializers.BooleanField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = AcademicYear
        fields = (
            "id",
            "school",
            "school_name",
            "title",
            "starts_on",
            "ends_on",
            "is_default",
            "status",
            "status_display",
            "is_editable",
            "closed_at",
            "close_note",
            "terms",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "status",
            "is_default",
            "closed_at",
            "created_at",
            "updated_at",
            "version",
        )

    def validate(self, attrs):
        starts_on = attrs.get("starts_on") or getattr(self.instance, "starts_on", None)
        ends_on = attrs.get("ends_on") or getattr(self.instance, "ends_on", None)
        if starts_on and ends_on and ends_on <= starts_on:
            raise serializers.ValidationError(
                {"ends_on": "تاریخ پایان سال باید بعد از تاریخ شروع باشد."}
            )
        return attrs


class GradeLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeLevel
        fields = (
            "id",
            "school",
            "code",
            "title",
            "sequence_no",
            "stage",
            "status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class StudyProgramSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudyProgram
        fields = (
            "id",
            "school",
            "code",
            "title",
            "description",
            "status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class CourseSerializer(serializers.ModelSerializer):
    assessment_scheme_display = serializers.CharField(
        source="get_assessment_scheme_display", read_only=True
    )

    class Meta:
        model = Course
        fields = (
            "id",
            "school",
            "code",
            "title",
            "credit",
            "assessment_scheme",
            "assessment_scheme_display",
            "max_score",
            "prerequisites",
            "status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class ProgramCourseSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source="course.title", read_only=True)
    grade_level_title = serializers.CharField(
        source="grade_level.title", read_only=True
    )

    class Meta:
        model = ProgramCourse
        fields = (
            "id",
            "program",
            "grade_level",
            "grade_level_title",
            "course",
            "course_title",
            "weekly_minutes",
            "is_required",
        )
        read_only_fields = ("id",)


class RoomSerializer(serializers.ModelSerializer):
    room_type_display = serializers.CharField(
        source="get_room_type_display", read_only=True
    )

    class Meta:
        model = Room
        fields = (
            "id",
            "campus",
            "code",
            "title",
            "room_type",
            "room_type_display",
            "building",
            "floor",
            "capacity",
            "status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class ClassGroupListSerializer(serializers.ModelSerializer):
    grade_level_title = serializers.CharField(source="grade_level.title", read_only=True)
    program_title = serializers.CharField(source="program.title", read_only=True)
    campus_name = serializers.CharField(source="campus.name", read_only=True)
    occupied_seats = serializers.IntegerField(read_only=True)
    available_seats = serializers.IntegerField(read_only=True)

    class Meta:
        model = ClassGroup
        fields = (
            "id",
            "code",
            "title",
            "campus",
            "campus_name",
            "academic_year",
            "grade_level",
            "grade_level_title",
            "program",
            "program_title",
            "capacity",
            "occupied_seats",
            "available_seats",
            "status",
        )


class ClassGroupSerializer(serializers.ModelSerializer):
    grade_level_title = serializers.CharField(source="grade_level.title", read_only=True)
    program_title = serializers.CharField(source="program.title", read_only=True)
    campus_name = serializers.CharField(source="campus.name", read_only=True)
    home_room_code = serializers.CharField(source="home_room.code", read_only=True)
    occupied_seats = serializers.IntegerField(read_only=True)
    available_seats = serializers.IntegerField(read_only=True)

    class Meta:
        model = ClassGroup
        fields = (
            "id",
            "campus",
            "campus_name",
            "academic_year",
            "grade_level",
            "grade_level_title",
            "program",
            "program_title",
            "home_room",
            "home_room_code",
            "homeroom_teacher_id",
            "code",
            "title",
            "capacity",
            "capacity_override_reason",
            "occupied_seats",
            "available_seats",
            "status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class CourseOfferingSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source="course.title", read_only=True)
    course_code = serializers.CharField(source="course.code", read_only=True)
    class_group_code = serializers.CharField(source="class_group.code", read_only=True)
    term_title = serializers.CharField(source="term.title", read_only=True)

    class Meta:
        model = CourseOffering
        fields = (
            "id",
            "class_group",
            "class_group_code",
            "term",
            "term_title",
            "course",
            "course_code",
            "course_title",
            "weekly_minutes",
            "status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class ScheduleEntrySerializer(serializers.ModelSerializer):
    weekday_display = serializers.CharField(source="get_weekday_display", read_only=True)
    course_title = serializers.CharField(
        source="course_offering.course.title", read_only=True
    )
    class_group_code = serializers.CharField(
        source="course_offering.class_group.code", read_only=True
    )
    room_code = serializers.CharField(source="room.code", read_only=True)

    class Meta:
        model = ScheduleEntry
        fields = (
            "id",
            "course_offering",
            "course_title",
            "class_group_code",
            "room",
            "room_code",
            "teacher_profile_id",
            "weekday",
            "weekday_display",
            "starts_at",
            "ends_at",
            "period_no",
            "effective_from",
            "effective_to",
            "status",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")

    def validate(self, attrs):
        starts_at = attrs.get("starts_at") or getattr(self.instance, "starts_at", None)
        ends_at = attrs.get("ends_at") or getattr(self.instance, "ends_at", None)
        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError(
                {"ends_at": "ساعت پایان باید بعد از ساعت شروع باشد."}
            )
        return attrs


class ScheduleConflictSerializer(serializers.Serializer):
    """خروجی بررسی تداخل برنامه."""

    type = serializers.CharField(
        help_text="ROOM_CONFLICT | TEACHER_CONFLICT | CLASS_CONFLICT"
    )
    message = serializers.CharField()
    conflictingEntryId = serializers.UUIDField()


class CalendarEventSerializer(serializers.ModelSerializer):
    event_type_display = serializers.CharField(
        source="get_event_type_display", read_only=True
    )

    class Meta:
        model = CalendarEvent
        fields = (
            "id",
            "school",
            "campus",
            "academic_year",
            "title",
            "event_type",
            "event_type_display",
            "starts_on",
            "ends_on",
            "is_working_day",
            "description",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class WeeklyTimetableSerializer(serializers.Serializer):
    """نمای برنامه هفتگی یک کلاس، برای رندر جدول در فرانت."""

    classGroupId = serializers.UUIDField()
    classGroupCode = serializers.CharField()
    entries = ScheduleEntrySerializer(many=True)


class YearCloseSerializer(serializers.Serializer):
    note = serializers.CharField(
        max_length=400, required=False, allow_blank=True, help_text="یادداشت بستن سال"
    )


class CloneYearSerializer(serializers.Serializer):
    target_academic_year = serializers.UUIDField(
        help_text="شناسه سال تحصیلی مقصد که ساختار در آن ایجاد می‌شود"
    )
