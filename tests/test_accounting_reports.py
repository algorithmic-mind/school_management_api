"""
آزمون گزارش‌های حسابداری (بخش ۱۴.۳ سند تحلیل).

اعداد این آزمون دستی محاسبه شده‌اند تا اگر منطق محاسبه عوض شود، آزمون
بشکند — نه اینکه خروجی کد را با خودش بسنجد.

دفتر آزمون:

| سند | تاریخ | بدهکار | بستانکار |
|---|---|---|---|
| آورده اولیه | ۰۴-۰۱ | بانک ۵٬۰۰۰ | سرمایه ۵٬۰۰۰ |
| صدور صورتحساب | ۰۵-۱۰ | دریافتنی ۳٬۰۰۰ | درآمد ۳٬۰۰۰ |
| دریافت نقدی | ۰۶-۱۵ | صندوق ۱٬۲۰۰ | دریافتنی ۱٬۲۰۰ |
| پرداخت حقوق | ۰۷-۲۰ | هزینه ۸۰۰ | بانک ۸۰۰ |
| پیش‌دریافت | ۰۸-۰۵ | بانک ۴۰۰ | پیش‌دریافت ۴۰۰ |

(ارقام به میلیون ریال)
"""

from __future__ import annotations

from datetime import date

from django.test import TestCase

from apps.finance import reports
from apps.finance.enums import JournalStatus
from tests import factories

M = 1_000_000


class AccountingReportsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = factories.make_tenant()
        cls.school = factories.make_school(cls.tenant, "SCH01", "مدرسه یکم")
        cls.accounts = factories.make_chart_of_accounts(cls.tenant, cls.school)
        cls.fiscal_year = factories.make_fiscal_year(cls.tenant, cls.school)

        account = cls.accounts
        spec = [
            ("JV-001", date(2026, 4, 1), "آورده اولیه",
             [(account["bank"], 5000 * M, 0), (account["capital"], 0, 5000 * M)]),
            ("JV-002", date(2026, 5, 10), "صدور صورتحساب",
             [(account["receivable"], 3000 * M, 0), (account["revenue"], 0, 3000 * M)]),
            ("JV-003", date(2026, 6, 15), "دریافت نقدی",
             [(account["cash"], 1200 * M, 0), (account["receivable"], 0, 1200 * M)]),
            ("JV-004", date(2026, 7, 20), "پرداخت حقوق",
             [(account["expense"], 800 * M, 0), (account["bank"], 0, 800 * M)]),
            ("JV-005", date(2026, 8, 5), "پیش‌دریافت",
             [(account["bank"], 400 * M, 0), (account["prepaid"], 0, 400 * M)]),
        ]
        for entry_no, entry_date, description, lines in spec:
            factories.post_entry(
                cls.tenant, cls.fiscal_year, entry_no, entry_date, description, lines
            )

    # -- تراز آزمایشی ---------------------------------------------------
    def test_trial_balance_is_balanced_and_matches_hand_calculation(self):
        payload = reports.trial_balance(tenant_id=self.tenant.id)

        self.assertTrue(payload["totals"]["isBalanced"])
        self.assertEqual(payload["rowCount"], 7)
        self.assertEqual(payload["totals"]["periodDebit"], 10_400 * M)
        self.assertEqual(payload["totals"]["periodCredit"], 10_400 * M)

        by_code = {row["accountCode"]: row for row in payload["rows"]}
        self.assertEqual(by_code["1101"]["closingDebit"], 1200 * M)
        self.assertEqual(by_code["1102"]["closingDebit"], 4600 * M)
        self.assertEqual(by_code["1201"]["closingDebit"], 1800 * M)
        self.assertEqual(by_code["2101"]["closingCredit"], 400 * M)
        self.assertEqual(by_code["3101"]["closingCredit"], 5000 * M)
        self.assertEqual(by_code["4101"]["closingCredit"], 3000 * M)
        self.assertEqual(by_code["5101"]["closingDebit"], 800 * M)

    def test_trial_balance_hides_zero_rows_unless_asked(self):
        # حسابی که هیچ گردشی ندارد نباید گزارش را شلوغ کند.
        factories.make_chart_of_accounts(self.tenant, self.school, prefix="9")
        payload = reports.trial_balance(tenant_id=self.tenant.id)
        self.assertEqual(payload["rowCount"], 7)

    # -- دفتر کل --------------------------------------------------------
    def test_general_ledger_running_balance_starts_from_opening(self):
        """مانده تجمعی باید از مانده ابتدای دوره شروع شود، نه از صفر."""
        payload = reports.general_ledger(
            tenant_id=self.tenant.id, date_from="2026-07-01", date_to="2026-12-31"
        )
        bank = next(a for a in payload["accounts"] if a["accountCode"] == "1102")

        self.assertEqual(bank["openingBalance"], 5000 * M)
        self.assertEqual(bank["periodDebit"], 400 * M)
        self.assertEqual(bank["periodCredit"], 800 * M)
        self.assertEqual(bank["closingBalance"], 4600 * M)
        # نخستین ردیف دوره: ۵۰۰۰ − ۸۰۰
        self.assertEqual(bank["rows"][0]["balance"], 4200 * M)
        self.assertEqual(bank["rows"][-1]["balance"], 4600 * M)

    def test_general_ledger_without_date_from_has_no_opening(self):
        payload = reports.general_ledger(tenant_id=self.tenant.id)
        bank = next(a for a in payload["accounts"] if a["accountCode"] == "1102")
        self.assertEqual(bank["openingBalance"], 0)
        self.assertEqual(bank["closingBalance"], 4600 * M)

    def test_general_ledger_max_rows_flags_truncation(self):
        payload = reports.general_ledger(
            tenant_id=self.tenant.id, max_rows_per_account=1
        )
        bank = next(a for a in payload["accounts"] if a["accountCode"] == "1102")
        self.assertEqual(len(bank["rows"]), 1)
        self.assertTrue(bank["rowsTruncated"])
        # جمع‌ها نباید با بریدن ردیف‌ها تغییر کند.
        self.assertEqual(bank["closingBalance"], 4600 * M)
        self.assertEqual(bank["rowCount"], 3)

    def test_draft_entries_are_invisible_to_reports(self):
        factories.post_entry(
            self.tenant,
            self.fiscal_year,
            "JV-DRAFT",
            date(2026, 9, 1),
            "سند پیش‌نویس",
            [
                (self.accounts["cash"], 9_999 * M, 0),
                (self.accounts["revenue"], 0, 9_999 * M),
            ],
            status=JournalStatus.DRAFT,
        )
        payload = reports.trial_balance(tenant_id=self.tenant.id)
        by_code = {row["accountCode"]: row for row in payload["rows"]}
        self.assertEqual(by_code["1101"]["closingDebit"], 1200 * M)
        self.assertTrue(payload["totals"]["isBalanced"])

    # -- صورت‌های مالی ---------------------------------------------------
    def test_income_statement(self):
        payload = reports.income_statement(tenant_id=self.tenant.id)
        self.assertEqual(payload["revenue"]["total"], 3000 * M)
        self.assertEqual(payload["expense"]["total"], 800 * M)
        self.assertEqual(payload["netIncome"], 2200 * M)
        self.assertAlmostEqual(payload["netMarginPercent"], 73.33, places=2)

    def test_income_statement_margin_is_null_without_revenue(self):
        """درآمد صفر یعنی «حاشیه بی‌معناست»، نه «حاشیه صفر»."""
        payload = reports.income_statement(
            tenant_id=self.tenant.id, date_from="2026-07-01", date_to="2026-07-31"
        )
        self.assertEqual(payload["revenue"]["total"], 0)
        self.assertIsNone(payload["netMarginPercent"])

    def test_balance_sheet_equation_holds(self):
        payload = reports.balance_sheet(tenant_id=self.tenant.id)
        self.assertEqual(payload["totalAssets"], 7600 * M)
        self.assertEqual(payload["liability"]["total"], 400 * M)
        self.assertEqual(payload["equity"]["retainedResult"], 2200 * M)
        self.assertEqual(payload["equity"]["total"], 7200 * M)
        self.assertEqual(payload["difference"], 0)
        self.assertTrue(payload["isBalanced"])

    # -- گردش تک‌حساب ----------------------------------------------------
    def test_account_ledger_matches_general_ledger(self):
        payload = reports.account_ledger(
            self.accounts["bank"], "2026-07-01", "2026-12-31"
        )
        self.assertEqual(payload["accountCode"], "1102")
        self.assertEqual(payload["openingBalance"], 5000 * M)
        self.assertEqual(payload["closingBalance"], 4600 * M)
        self.assertEqual(len(payload["rows"]), 2)

    def test_account_ledger_of_untouched_account_is_empty_not_missing(self):
        extra = factories.make_chart_of_accounts(self.tenant, self.school, prefix="9")
        payload = reports.account_ledger(extra["cash"])
        self.assertEqual(payload["closingBalance"], 0)
        self.assertEqual(payload["rows"], [])

    # -- جداسازی سازمان --------------------------------------------------
    def test_reports_never_cross_tenants(self):
        other_tenant = factories.make_tenant("other-org")
        other_school = factories.make_school(other_tenant, "SCH01", "مدرسه دیگر")
        other_accounts = factories.make_chart_of_accounts(other_tenant, other_school)
        other_year = factories.make_fiscal_year(other_tenant, other_school)
        factories.post_entry(
            other_tenant,
            other_year,
            "JV-X",
            date(2026, 6, 1),
            "سند سازمان دیگر",
            [
                (other_accounts["cash"], 1_000 * M, 0),
                (other_accounts["revenue"], 0, 1_000 * M),
            ],
        )

        mine = reports.trial_balance(tenant_id=self.tenant.id)
        self.assertEqual(mine["totals"]["periodDebit"], 10_400 * M)

        theirs = reports.trial_balance(tenant_id=other_tenant.id)
        self.assertEqual(theirs["totals"]["periodDebit"], 1_000 * M)

    def test_school_scope_narrows_reports(self):
        second = factories.make_school(self.tenant, "SCH02", "مدرسه دوم")
        second_accounts = factories.make_chart_of_accounts(
            self.tenant, second, prefix="9"
        )
        second_year = factories.make_fiscal_year(self.tenant, second, "۱۴۰۵ دوم")
        factories.post_entry(
            self.tenant,
            second_year,
            "JV-S2",
            date(2026, 6, 1),
            "سند مدرسه دوم",
            [
                (second_accounts["cash"], 777 * M, 0),
                (second_accounts["revenue"], 0, 777 * M),
            ],
        )

        whole = reports.trial_balance(tenant_id=self.tenant.id)
        self.assertEqual(whole["totals"]["periodDebit"], 11_177 * M)

        limited = reports.trial_balance(
            tenant_id=self.tenant.id, schools=[self.school.id]
        )
        self.assertEqual(limited["totals"]["periodDebit"], 10_400 * M)

        # مجموعه خالی یعنی «هیچ مدرسه‌ای مجاز نیست»، نه «بدون فیلتر».
        none_allowed = reports.trial_balance(tenant_id=self.tenant.id, schools=[])
        self.assertEqual(none_allowed["rowCount"], 0)

    # -- دفتر روزنامه و مراکز هزینه --------------------------------------
    def test_daybook_groups_lines_under_entries(self):
        payload = reports.daybook(tenant_id=self.tenant.id)
        self.assertEqual(payload["entryCount"], 5)
        self.assertEqual(payload["totals"]["debit"], payload["totals"]["credit"])
        first = payload["entries"][0]
        self.assertEqual(first["entryNo"], "JV-001")
        self.assertEqual(len(first["lines"]), 2)

    def test_cost_center_report_buckets_unassigned_lines(self):
        payload = reports.cost_center_report(tenant_id=self.tenant.id)
        self.assertEqual(payload["totals"]["revenue"], 3000 * M)
        self.assertEqual(payload["totals"]["expense"], 800 * M)
        self.assertEqual(payload["totals"]["net"], 2200 * M)
        self.assertEqual(len(payload["rows"]), 1)
        self.assertIsNone(payload["rows"][0]["costCenterId"])
