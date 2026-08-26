from django.apps import apps
from django.contrib import admin

from apps.core.admin import SchoolModelAdmin, register_auto
from apps.hr.models import (
    Employee,
    EmploymentContract,
    TeachingAssignment,
)


@admin.register(Employee)
class EmployeeAdmin(SchoolModelAdmin):
    list_display = ("employee_no", "person", "status", "hired_on")
    list_filter = ("status",)
    search_fields = ("employee_no", "person__first_name", "person__last_name")


@admin.register(EmploymentContract)
class EmploymentContractAdmin(SchoolModelAdmin):
    list_display = ("contract_no", "employee", "contract_type", "starts_on", "status")
    list_filter = ("contract_type", "status")


@admin.register(TeachingAssignment)
class TeachingAssignmentAdmin(SchoolModelAdmin):
    list_display = ("teacher_profile", "course_offering", "responsibility", "share_percent")
    list_filter = ("responsibility",)


# همه مدل‌های باقی‌مانده این اپ با پیکربندی مشتق‌شده از خود مدل ثبت می‌شوند؛
# ModelAdminهای بالا دست‌نویس‌اند و بازنویسی نمی‌شوند.
register_auto(*apps.get_app_config("hr").get_models())
