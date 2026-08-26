"""مسیرهای تدارکات، انبار و اموال."""

from rest_framework.routers import DefaultRouter

from apps.inventory.views import (
    AssetAssignmentViewSet,
    AssetViewSet,
    GoodsReceiptViewSet,
    ItemCategoryViewSet,
    ItemViewSet,
    MaintenanceOrderViewSet,
    PurchaseOrderLineViewSet,
    PurchaseOrderViewSet,
    PurchaseRequestLineViewSet,
    PurchaseRequestViewSet,
    StockBalanceViewSet,
    StockDocumentLineViewSet,
    StockDocumentViewSet,
    StockMovementViewSet,
    UnitOfMeasureViewSet,
    VendorViewSet,
    WarehouseViewSet,
)

router = DefaultRouter()
router.register("vendors", VendorViewSet, basename="vendor")
router.register("uoms", UnitOfMeasureViewSet, basename="uom")
router.register("item-categories", ItemCategoryViewSet, basename="item-category")
router.register("items", ItemViewSet, basename="item")
router.register("warehouses", WarehouseViewSet, basename="warehouse")
router.register("balances", StockBalanceViewSet, basename="stock-balance")
router.register("stock-documents", StockDocumentViewSet, basename="stock-document")
router.register("stock-document-lines", StockDocumentLineViewSet, basename="stock-document-line")
router.register("movements", StockMovementViewSet, basename="stock-movement")
router.register("purchase-requests", PurchaseRequestViewSet, basename="purchase-request")
router.register("purchase-request-lines", PurchaseRequestLineViewSet, basename="purchase-request-line")
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchase-order")
router.register("purchase-order-lines", PurchaseOrderLineViewSet, basename="purchase-order-line")
router.register("goods-receipts", GoodsReceiptViewSet, basename="goods-receipt")
router.register("assets", AssetViewSet, basename="asset")
router.register("asset-assignments", AssetAssignmentViewSet, basename="asset-assignment")
router.register("maintenance-orders", MaintenanceOrderViewSet, basename="maintenance-order")

urlpatterns = router.urls
