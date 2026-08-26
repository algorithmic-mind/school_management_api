from django.apps import apps
from django.contrib import admin

from apps.core.admin import SchoolModelAdmin, register_auto
from apps.welfare.models import (
    BehaviorIncident,
    HealthProfile,
    LibraryLoan,
    TransportRoute,
)


@admin.register(HealthProfile)
class HealthProfileAdmin(SchoolModelAdmin):
    list_display = ("student", "blood_type", "confidentiality_level")
    search_fields = ("student__student_no",)


@admin.register(BehaviorIncident)
class BehaviorIncidentAdmin(SchoolModelAdmin):
    list_display = ("student", "incident_type", "severity", "status", "occurred_at")
    list_filter = ("incident_type", "severity", "status")


@admin.register(LibraryLoan)
class LibraryLoanAdmin(SchoolModelAdmin):
    list_display = ("copy", "borrower_person", "loaned_at", "due_at", "status")
    list_filter = ("status",)


@admin.register(TransportRoute)
class TransportRouteAdmin(SchoolModelAdmin):
    list_display = ("code", "title", "campus", "direction", "status")
    list_filter = ("direction", "status")
    search_fields = ("code", "title")


# همه مدل‌های باقی‌مانده این اپ با پیکربندی مشتق‌شده از خود مدل ثبت می‌شوند؛
# ModelAdminهای بالا دست‌نویس‌اند و بازنویسی نمی‌شوند.
register_auto(*apps.get_app_config("welfare").get_models())
