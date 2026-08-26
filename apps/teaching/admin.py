from django.apps import apps
from django.contrib import admin

from apps.core.admin import SchoolModelAdmin, register_auto
from apps.teaching.models import (
    Assignment,
    AttendanceRecord,
    TeachingSession,
)


@admin.register(TeachingSession)
class TeachingSessionAdmin(SchoolModelAdmin):
    list_display = ("course_offering", "starts_at", "session_type", "status")
    list_filter = ("status", "session_type")


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(SchoolModelAdmin):
    list_display = ("session", "enrollment", "attendance_status", "finalization_status")
    list_filter = ("attendance_status", "finalization_status")
    search_fields = ("enrollment__enrollment_no", "enrollment__student__student_no", "reason_code")


@admin.register(Assignment)
class AssignmentAdmin(SchoolModelAdmin):
    list_display = ("title", "course_offering", "due_at", "status")
    list_filter = ("status",)
    search_fields = ("title",)


# همه مدل‌های باقی‌مانده این اپ با پیکربندی مشتق‌شده از خود مدل ثبت می‌شوند؛
# ModelAdminهای بالا دست‌نویس‌اند و بازنویسی نمی‌شوند.
register_auto(*apps.get_app_config("teaching").get_models())
