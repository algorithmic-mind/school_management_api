from django.apps import apps
from django.contrib import admin

from apps.core.admin import SchoolModelAdmin, register_auto
from apps.inventory.models import (
    Asset,
    Item,
    PurchaseRequest,
    StockBalance,
    StockDocument,
)


@admin.register(Item)
class ItemAdmin(SchoolModelAdmin):
    list_display = ("sku", "title", "category", "lot_tracked", "serial_tracked", "status")
    list_filter = ("status", "lot_tracked", "serial_tracked", "is_capital_asset")
    search_fields = ("sku", "title", "barcode")


@admin.register(StockDocument)
class StockDocumentAdmin(SchoolModelAdmin):
    list_display = ("document_no", "warehouse", "document_type", "document_at", "status")
    list_filter = ("document_type", "status")
    search_fields = ("document_no",)


@admin.register(StockBalance)
class StockBalanceAdmin(SchoolModelAdmin):
    list_display = ("item", "warehouse", "lot_no", "on_hand_qty", "reserved_qty")
    list_filter = ("warehouse",)
    search_fields = ("item__sku", "item__title")


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(SchoolModelAdmin):
    list_display = ("request_no", "title", "campus", "status", "estimated_amount")
    list_filter = ("status",)
    search_fields = ("request_no", "title")


@admin.register(Asset)
class AssetAdmin(SchoolModelAdmin):
    list_display = ("asset_tag", "title", "lifecycle_status", "condition_status", "acquired_on")
    list_filter = ("lifecycle_status", "condition_status")
    search_fields = ("asset_tag", "title", "serial_no")


# همه مدل‌های باقی‌مانده این اپ با پیکربندی مشتق‌شده از خود مدل ثبت می‌شوند؛
# ModelAdminهای بالا دست‌نویس‌اند و بازنویسی نمی‌شوند.
register_auto(*apps.get_app_config("inventory").get_models())
