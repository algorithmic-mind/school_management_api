from django.apps import apps
from django.contrib import admin

from apps.core.admin import SchoolModelAdmin, register_auto
from apps.gradebook.models import (
    GradeItem,
    ReportCard,
    StudentScore,
)


@admin.register(GradeItem)
class GradeItemAdmin(SchoolModelAdmin):
    list_display = ("title", "category", "max_score", "status", "due_on")
    list_filter = ("status", "source_type")


@admin.register(StudentScore)
class StudentScoreAdmin(SchoolModelAdmin):
    list_display = ("enrollment", "grade_item", "raw_score", "status")
    list_filter = ("status",)


@admin.register(ReportCard)
class ReportCardAdmin(SchoolModelAdmin):
    list_display = ("enrollment", "term", "version_no", "status", "average_score")
    list_filter = ("status", "term")
    search_fields = ("verification_code", "enrollment__student__student_no")


# همه مدل‌های باقی‌مانده این اپ با پیکربندی مشتق‌شده از خود مدل ثبت می‌شوند؛
# ModelAdminهای بالا دست‌نویس‌اند و بازنویسی نمی‌شوند.
register_auto(*apps.get_app_config("gradebook").get_models())
