from django.apps import apps
from django.contrib import admin

from apps.core.admin import SchoolModelAdmin, register_auto
from apps.workflow.models import (
    ApprovalRequest,
    Notification,
    OutboxEvent,
    Ticket,
)


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(SchoolModelAdmin):
    list_display = ("workflow_code", "subject_type", "subject_label", "status", "requested_at")
    list_filter = ("status", "workflow_code")
    search_fields = ("workflow_code", "subject_label")


@admin.register(Notification)
class NotificationAdmin(SchoolModelAdmin):
    list_display = ("subject", "recipient_person", "channel", "priority", "status")
    list_filter = ("channel", "status", "priority")


@admin.register(OutboxEvent)
class OutboxEventAdmin(SchoolModelAdmin):
    list_display = ("event_type", "aggregate_type", "occurred_at", "published_at", "retry_count")
    list_filter = ("event_type", "aggregate_type")
    readonly_fields = [f.name for f in OutboxEvent._meta.fields]


@admin.register(Ticket)
class TicketAdmin(SchoolModelAdmin):
    list_display = ("ticket_no", "subject", "category", "priority", "status")
    list_filter = ("status", "priority", "category")
    search_fields = ("ticket_no", "subject")


# همه مدل‌های باقی‌مانده این اپ با پیکربندی مشتق‌شده از خود مدل ثبت می‌شوند؛
# ModelAdminهای بالا دست‌نویس‌اند و بازنویسی نمی‌شوند.
register_auto(*apps.get_app_config("workflow").get_models())
