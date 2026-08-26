from django.apps import apps
from django.contrib import admin

from apps.core.admin import ImmutableModelAdmin, SchoolModelAdmin, register_auto
from apps.finance.models import (
    Account,
    Invoice,
    JournalEntry,
    Payment,
)


@admin.register(Invoice)
class InvoiceAdmin(SchoolModelAdmin):
    list_display = ("invoice_no", "agreement", "due_date", "total_amount", "paid_amount", "status")
    list_filter = ("status", "due_date")
    search_fields = ("invoice_no",)


@admin.register(Payment)
class PaymentAdmin(SchoolModelAdmin):
    list_display = ("payment_no", "payer_person", "method", "amount", "status", "received_at")
    list_filter = ("method", "status")
    search_fields = ("payment_no", "gateway_reference")


@admin.register(JournalEntry)
class JournalEntryAdmin(ImmutableModelAdmin):
    list_display = ("entry_no", "entry_date", "description", "source_type", "status")
    list_filter = ("status", "source_type")
    search_fields = ("entry_no", "description")


@admin.register(Account)
class AccountAdmin(SchoolModelAdmin):
    list_display = ("code", "title", "account_type", "allows_posting", "is_active")
    list_filter = ("account_type", "allows_posting", "is_active")
    search_fields = ("code", "title")


# همه مدل‌های باقی‌مانده این اپ با پیکربندی مشتق‌شده از خود مدل ثبت می‌شوند؛
# ModelAdminهای بالا دست‌نویس‌اند و بازنویسی نمی‌شوند.
register_auto(*apps.get_app_config("finance").get_models())
