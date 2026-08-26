from django.apps import apps
from django.contrib import admin

from apps.core.admin import SchoolModelAdmin, register_auto
from apps.assessment.models import (
    Exam,
    ExamAttempt,
    Question,
)


@admin.register(Exam)
class ExamAdmin(SchoolModelAdmin):
    list_display = ("code", "title", "mode", "purpose", "status", "max_score")
    list_filter = ("mode", "purpose", "status")
    search_fields = ("code", "title")


@admin.register(Question)
class QuestionAdmin(SchoolModelAdmin):
    list_display = ("id", "bank", "question_type", "lifecycle_status")
    list_filter = ("question_type", "lifecycle_status")


@admin.register(ExamAttempt)
class ExamAttemptAdmin(SchoolModelAdmin):
    list_display = ("registration", "attempt_no", "status", "final_score", "submitted_at")
    list_filter = ("status",)


# همه مدل‌های باقی‌مانده این اپ با پیکربندی مشتق‌شده از خود مدل ثبت می‌شوند؛
# ModelAdminهای بالا دست‌نویس‌اند و بازنویسی نمی‌شوند.
register_auto(*apps.get_app_config("assessment").get_models())
