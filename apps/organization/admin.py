from django.apps import apps
from django.contrib import admin

from apps.core.admin import SchoolModelAdmin, register_auto
from apps.organization.models import (
    AcademicYear,
    ClassGroup,
    ScheduleEntry,
    School,
)


@admin.register(School)
class SchoolAdmin(SchoolModelAdmin):
    list_display = ("name", "code", "school_type", "status")
    list_filter = ("school_type", "status")
    search_fields = ("name", "code")


@admin.register(AcademicYear)
class AcademicYearAdmin(SchoolModelAdmin):
    list_display = ("title", "school", "starts_on", "ends_on", "status", "is_default")
    list_filter = ("status", "is_default", "school")
    search_fields = ("title",)


@admin.register(ClassGroup)
class ClassGroupAdmin(SchoolModelAdmin):
    list_display = ("code", "grade_level", "academic_year", "capacity", "status")
    list_filter = ("status", "academic_year", "grade_level")
    search_fields = ("code", "title")


@admin.register(ScheduleEntry)
class ScheduleEntryAdmin(SchoolModelAdmin):
    list_display = ("course_offering", "weekday", "starts_at", "ends_at", "room", "status")
    list_filter = ("weekday", "status")


# همه مدل‌های باقی‌مانده این اپ با پیکربندی مشتق‌شده از خود مدل ثبت می‌شوند؛
# ModelAdminهای بالا دست‌نویس‌اند و بازنویسی نمی‌شوند.
register_auto(*apps.get_app_config("organization").get_models())
