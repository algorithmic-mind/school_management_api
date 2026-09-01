"""مسیرهای مالی و حسابداری."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.finance.views import (
    AccountingReportViewSet,
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
router.register("reports", AccountingReportViewSet, basename="accounting-report")

#: میان‌بُرهای گزارش‌های حسابداری.
#:
#: مسیر رسمی هر گزارش زیر `reports/` است، ولی صفحه «اسناد و دفتر کل» فرانت
#: به‌طور طبیعی سراغ `finance/general-ledger/` می‌رود. این نام‌های کوتاه به
#: همان Actionها وصل‌اند — یک پیاده‌سازی، دو مسیر — تا هیچ‌کدام ۴۰۴ ندهد.
#:
#: نام میان‌بُر نباید با هیچ منبع Router یکی باشد: این مسیرها پیش از Router
#: می‌نشینند و هم‌نامی، منبع اصلی را می‌پوشاند. گزارش مرکز هزینه به همین دلیل
#: میان‌بُر ندارد و فقط زیر `reports/cost-centers/` است، چون
#: `finance/cost-centers/` خودش فهرست مراکز هزینه است.
_REPORT_ALIASES = {
    "general-ledger": "general_ledger",
    "trial-balance": "trial_balance",
    "income-statement": "income_statement",
    "balance-sheet": "balance_sheet",
    "daybook": "daybook",
}

alias_patterns = [
    path(
        f"{url_path}/",
        AccountingReportViewSet.as_view({"get": action_name}),
        name=f"accounting-report-{url_path}",
    )
    for url_path, action_name in _REPORT_ALIASES.items()
]

urlpatterns = alias_patterns + router.urls
