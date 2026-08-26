from django.apps import apps
from django.contrib import admin

from apps.core.admin import SchoolModelAdmin, register_auto
from apps.students.models import (
    AdmissionApplication,
    Enrollment,
    Student,
)


@admin.register(Student)
class StudentAdmin(SchoolModelAdmin):
    list_display = ("student_no", "person", "status", "joined_on")
    list_filter = ("status",)
    search_fields = ("student_no", "person__first_name", "person__last_name")


@admin.register(Enrollment)
class EnrollmentAdmin(SchoolModelAdmin):
    list_display = ("enrollment_no", "student", "academic_year", "grade_level", "status")
    list_filter = ("status", "academic_year", "grade_level")
    search_fields = ("enrollment_no", "student__student_no")


@admin.register(AdmissionApplication)
class AdmissionApplicationAdmin(SchoolModelAdmin):
    list_display = ("application_no", "person", "academic_year", "status", "final_score")
    list_filter = ("status", "academic_year")


# همه مدل‌های باقی‌مانده این اپ با پیکربندی مشتق‌شده از خود مدل ثبت می‌شوند؛
# ModelAdminهای بالا دست‌نویس‌اند و بازنویسی نمی‌شوند.
register_auto(*apps.get_app_config("students").get_models())
