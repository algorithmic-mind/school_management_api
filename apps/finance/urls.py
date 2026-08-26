"""مسیرهای مالی و حسابداری."""

from rest_framework.routers import DefaultRouter

from apps.finance.views import (
    AccountViewSet,
    BankAccountViewSet,
    BankReconciliationViewSet,
    CostCenterViewSet,
    DiscountAwardViewSet,
    FamilyBalanceViewSet,
    FeePlanItemViewSet,
    FeePlanViewSet,
    FiscalYearViewSet,
    InvoiceLineViewSet,
    InvoiceViewSet,
    JournalEntryViewSet,
    JournalLineViewSet,
    PaymentAllocationViewSet,
    PaymentViewSet,
    RefundViewSet,
    StudentFinancialAgreementViewSet,
)

router = DefaultRouter()
router.register("fiscal-years", FiscalYearViewSet, basename="fiscal-year")
router.register("accounts", AccountViewSet, basename="account")
router.register("cost-centers", CostCenterViewSet, basename="cost-center")
router.register("fee-plans", FeePlanViewSet, basename="fee-plan")
router.register("fee-plan-items", FeePlanItemViewSet, basename="fee-plan-item")
router.register("agreements", StudentFinancialAgreementViewSet, basename="financial-agreement")
router.register("discounts", DiscountAwardViewSet, basename="discount-award")
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("invoice-lines", InvoiceLineViewSet, basename="invoice-line")
router.register("payments", PaymentViewSet, basename="payment")
router.register("allocations", PaymentAllocationViewSet, basename="payment-allocation")
router.register("refunds", RefundViewSet, basename="refund")
router.register("journal-entries", JournalEntryViewSet, basename="journal-entry")
router.register("journal-lines", JournalLineViewSet, basename="journal-line")
router.register("bank-accounts", BankAccountViewSet, basename="bank-account")
router.register("reconciliations", BankReconciliationViewSet, basename="bank-reconciliation")
router.register("family-balance", FamilyBalanceViewSet, basename="family-balance")

urlpatterns = router.urls
