"""
گزارش‌های حسابداری: دفتر کل، تراز آزمایشی، سود و زیان و صورت وضعیت مالی.

مرجع: بخش ۱۴.۳ سند تحلیل — «تراز آزمایشی، دفتر کل، سود و زیان و صورت وضعیت
مالی» و بخش ۷.۸ (حسابداری دوبل).

قواعد مشترک همه گزارش‌های این ماژول:

- فقط اسناد **قطعی** (`POSTED`) در گزارش می‌آیند. سند پیش‌نویس یا لغوشده هیچ
  اثری روی مانده ندارد؛ سند برگشتی خودش یک سند قطعی جداگانه است و اثر
  معکوسش به‌طور طبیعی در گردش دیده می‌شود.
- مانده هر حساب همیشه «بدهکار منهای بستانکار» است. تبدیل به دو ستون
  بدهکار/بستانکار فقط در لایه نمایش انجام می‌شود (`_split`) تا در محاسبه
  علامت گم نشود.
- «مانده ابتدای دوره» جمع گردش پیش از `date_from` است؛ بدون آن، مانده تجمعی
  گزارش با مانده واقعی حساب فرق می‌کند.
- مبالغ عدد صحیح ریال‌اند (بخش ۱: بدون اعشار شناور).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Iterable

from django.db.models import QuerySet, Sum

from apps.finance.enums import AccountType, JournalStatus
from apps.finance.models import Account, JournalLine

#: حساب‌هایی که در صورت وضعیت مالی (ترازنامه) می‌آیند.
BALANCE_SHEET_TYPES = (AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY)

#: حساب‌هایی که در صورت سود و زیان می‌آیند.
INCOME_STATEMENT_TYPES = (AccountType.REVENUE, AccountType.EXPENSE)

#: ماهیت طبیعی هر گروه حساب: ۱+ بدهکار، ۱− بستانکار.
NATURAL_SIDE = {
    AccountType.ASSET: 1,
    AccountType.EXPENSE: 1,
    AccountType.LIABILITY: -1,
    AccountType.EQUITY: -1,
    AccountType.REVENUE: -1,
}


def _split(balance: int) -> tuple[int, int]:
    """مانده علامت‌دار را به جفت (بدهکار، بستانکار) نمایشی تبدیل می‌کند."""
    return (balance, 0) if balance >= 0 else (0, -balance)


def _to_date(value: Any) -> date | None:
    """پارامتر تاریخ را از رشته یا شیء تاریخ می‌پذیرد؛ خالی را رد نمی‌کند."""
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _posted_lines(tenant_id=None) -> QuerySet:
    """پایه همه گزارش‌ها: خطوط اسناد قطعی، محدود به سازمان جاری."""
    queryset = JournalLine.objects.filter(journal_entry__status=JournalStatus.POSTED)
    if tenant_id:
        queryset = queryset.filter(tenant_id=tenant_id)
    return queryset


def _apply_filters(
    queryset: QuerySet,
    *,
    school=None,
    schools: Iterable | None = None,
    fiscal_year=None,
    accounts: Iterable | None = None,
    account_types: Iterable[str] | None = None,
    cost_center=None,
) -> QuerySet:
    """
    فیلترهای مشترک گزارش‌ها؛ هر کدام خالی باشد اعمال نمی‌شود.

    `schools` محدوده مجاز کاربر است و `school` انتخاب خودِ او. این دو با هم
    «و» می‌شوند: انتخاب کاربر فقط می‌تواند محدوده مجاز را باریک‌تر کند. مقدار
    `[]` یعنی هیچ مدرسه‌ای مجاز نیست و نتیجه باید تهی شود — که `__in=[]`
    طبیعتاً همان را می‌دهد. تفاوتش با `None` (بدون محدودیت) عمدی است.
    """
    if schools is not None:
        queryset = queryset.filter(account__school_id__in=list(schools))
    if school:
        queryset = queryset.filter(account__school=school)
    if fiscal_year:
        queryset = queryset.filter(journal_entry__fiscal_year=fiscal_year)
    if accounts is not None:
        queryset = queryset.filter(account__in=accounts)
    if account_types:
        queryset = queryset.filter(account__account_type__in=list(account_types))
    if cost_center:
        queryset = queryset.filter(cost_center=cost_center)
    return queryset


def _account_payload(account: Account) -> dict:
    return {
        "accountId": str(account.id),
        "accountCode": account.code,
        "accountTitle": account.title,
        "accountType": account.account_type,
        "accountTypeDisplay": account.get_account_type_display(),
    }


def _net_balances(queryset: QuerySet) -> dict[Any, int]:
    """نگاشت «شناسه حساب → مانده خالص» برای یک مجموعه خط سند."""
    return {
        row["account_id"]: int(row["debit"] or 0) - int(row["credit"] or 0)
        for row in queryset.values("account_id").annotate(
            debit=Sum("debit_amount"), credit=Sum("credit_amount")
        )
    }


# ---------------------------------------------------------------------------
# دفتر کل
# ---------------------------------------------------------------------------
def general_ledger(
    *,
    tenant_id=None,
    school=None,
    schools: Iterable | None = None,
    fiscal_year=None,
    accounts: Iterable[Account] | None = None,
    account_types: Iterable[str] | None = None,
    cost_center=None,
    date_from=None,
    date_to=None,
    include_empty: bool = False,
    max_rows_per_account: int | None = None,
) -> dict:
    """
    دفتر کل: ریز گردش هر حساب با مانده ابتدا، گردش دوره و مانده پایان.

    برخلاف «گردش حساب» که یک حساب را برمی‌گرداند، اینجا همه حساب‌های دارای
    گردش (یا همه حساب‌های انتخابی) یک‌جا می‌آیند — همان چیزی که صفحه «اسناد و
    دفتر کل» فرانت لازم دارد.

    `include_empty=True` حساب‌های بدون هیچ گردشی را هم با ردیف خالی نشان
    می‌دهد؛ پیش‌فرض خاموش است تا فهرست کامل کدینگ، گزارش را شلوغ نکند.
    """
    date_from = _to_date(date_from)
    date_to = _to_date(date_to)

    base = _apply_filters(
        _posted_lines(tenant_id),
        school=school,
        schools=schools,
        fiscal_year=fiscal_year,
        accounts=accounts,
        account_types=account_types,
        cost_center=cost_center,
    )

    period = base
    if date_from:
        period = period.filter(journal_entry__entry_date__gte=date_from)
    if date_to:
        period = period.filter(journal_entry__entry_date__lte=date_to)

    # مانده ابتدای دوره = گردش خالص پیش از تاریخ شروع.
    opening_map: dict[Any, int] = {}
    if date_from:
        opening_map = _net_balances(
            base.filter(journal_entry__entry_date__lt=date_from)
        )

    account_ids = set(period.values_list("account_id", flat=True).distinct())
    account_ids.update(opening_map)
    if include_empty:
        candidates = Account.objects.all()
        if tenant_id:
            candidates = candidates.filter(tenant_id=tenant_id)
        if schools is not None:
            candidates = candidates.filter(school_id__in=list(schools))
        if school:
            candidates = candidates.filter(school=school)
        if accounts is not None:
            candidates = candidates.filter(pk__in=[item.pk for item in accounts])
        if account_types:
            candidates = candidates.filter(account_type__in=list(account_types))
        account_ids.update(candidates.values_list("id", flat=True))

    account_objects = {
        account.id: account for account in Account.objects.filter(id__in=account_ids)
    }

    lines_by_account: dict[Any, list[JournalLine]] = {}
    for line in period.select_related("journal_entry", "cost_center").order_by(
        "journal_entry__entry_date", "journal_entry__entry_no", "line_no"
    ):
        lines_by_account.setdefault(line.account_id, []).append(line)

    accounts_payload: list[dict] = []
    total_opening = total_debit = total_credit = 0

    for account in sorted(account_objects.values(), key=lambda item: item.code):
        opening = opening_map.get(account.id, 0)
        running = opening
        rows = []
        account_lines = lines_by_account.get(account.id, [])
        for line in account_lines:
            running += line.debit_amount - line.credit_amount
            rows.append(
                {
                    "entryId": str(line.journal_entry_id),
                    "lineId": str(line.id),
                    "entryNo": line.journal_entry.entry_no,
                    "entryDate": line.journal_entry.entry_date,
                    "sourceType": line.journal_entry.source_type,
                    "sourceTypeDisplay": line.journal_entry.get_source_type_display(),
                    "description": line.description or line.journal_entry.description,
                    "costCenter": line.cost_center.title if line.cost_center else None,
                    "debit": line.debit_amount,
                    "credit": line.credit_amount,
                    "balance": running,
                }
            )

        period_debit = sum(line.debit_amount for line in account_lines)
        period_credit = sum(line.credit_amount for line in account_lines)
        closing = opening + period_debit - period_credit

        truncated = False
        if max_rows_per_account and len(rows) > max_rows_per_account:
            rows = rows[:max_rows_per_account]
            truncated = True

        opening_debit, opening_credit = _split(opening)
        closing_debit, closing_credit = _split(closing)

        accounts_payload.append(
            {
                **_account_payload(account),
                "openingBalance": opening,
                "openingDebit": opening_debit,
                "openingCredit": opening_credit,
                "periodDebit": period_debit,
                "periodCredit": period_credit,
                "closingBalance": closing,
                "closingDebit": closing_debit,
                "closingCredit": closing_credit,
                "rowCount": len(account_lines),
                "rowsTruncated": truncated,
                "rows": rows,
            }
        )
        total_opening += opening
        total_debit += period_debit
        total_credit += period_credit

    return {
        "dateFrom": date_from,
        "dateTo": date_to,
        "currency": "IRR",
        "accountCount": len(accounts_payload),
        "totals": {
            "openingBalance": total_opening,
            "periodDebit": total_debit,
            "periodCredit": total_credit,
            "closingBalance": total_opening + total_debit - total_credit,
            "isBalanced": total_debit == total_credit,
        },
        "accounts": accounts_payload,
    }


def account_ledger(account: Account, date_from=None, date_to=None, *, cost_center=None) -> dict:
    """
    گردش یک حساب — همان دفتر کل با فیلتر یک حساب.

    امضای تابع برای سازگاری با `GET /finance/accounts/{id}/ledger/` حفظ شده است.
    """
    payload = general_ledger(
        tenant_id=account.tenant_id,
        accounts=[account],
        cost_center=cost_center,
        date_from=date_from,
        date_to=date_to,
        include_empty=True,
    )
    detail = (
        payload["accounts"][0]
        if payload["accounts"]
        else {
            **_account_payload(account),
            "openingBalance": 0,
            "openingDebit": 0,
            "openingCredit": 0,
            "periodDebit": 0,
            "periodCredit": 0,
            "closingBalance": 0,
            "closingDebit": 0,
            "closingCredit": 0,
            "rowCount": 0,
            "rowsTruncated": False,
            "rows": [],
        }
    )
    return {
        "dateFrom": payload["dateFrom"],
        "dateTo": payload["dateTo"],
        "currency": "IRR",
        **detail,
    }


# ---------------------------------------------------------------------------
# تراز آزمایشی
# ---------------------------------------------------------------------------
def trial_balance(
    *,
    tenant_id=None,
    school=None,
    schools: Iterable | None = None,
    fiscal_year=None,
    cost_center=None,
    date_from=None,
    date_to=None,
    include_zero: bool = False,
) -> dict:
    """
    تراز آزمایشی شش‌ستونی: مانده ابتدا، گردش دوره و مانده پایان هر حساب.

    `isBalanced` کنترل سلامت دفتر است: در حسابداری دوبل جمع ستون بدهکار و
    بستانکار باید در هر سه جفت ستون برابر باشد. نابرابری یعنی سندی خارج از
    مسیر سرویس‌ها ثبت شده است.
    """
    date_from = _to_date(date_from)
    date_to = _to_date(date_to)

    base = _apply_filters(
        _posted_lines(tenant_id),
        school=school,
        schools=schools,
        fiscal_year=fiscal_year,
        cost_center=cost_center,
    )

    period = base
    if date_from:
        period = period.filter(journal_entry__entry_date__gte=date_from)
    if date_to:
        period = period.filter(journal_entry__entry_date__lte=date_to)

    opening_map: dict[Any, int] = {}
    if date_from:
        opening_map = _net_balances(
            base.filter(journal_entry__entry_date__lt=date_from)
        )

    period_map: dict[Any, tuple[int, int]] = {
        row["account_id"]: (int(row["debit"] or 0), int(row["credit"] or 0))
        for row in period.values("account_id").annotate(
            debit=Sum("debit_amount"), credit=Sum("credit_amount")
        )
    }

    account_ids = set(period_map) | set(opening_map)
    accounts = Account.objects.filter(id__in=account_ids).order_by("code")

    rows = []
    totals = {
        "openingDebit": 0,
        "openingCredit": 0,
        "periodDebit": 0,
        "periodCredit": 0,
        "closingDebit": 0,
        "closingCredit": 0,
    }
    for account in accounts:
        opening = opening_map.get(account.id, 0)
        period_debit, period_credit = period_map.get(account.id, (0, 0))
        closing = opening + period_debit - period_credit
        if not include_zero and not (opening or period_debit or period_credit):
            continue

        opening_debit, opening_credit = _split(opening)
        closing_debit, closing_credit = _split(closing)
        rows.append(
            {
                **_account_payload(account),
                "openingDebit": opening_debit,
                "openingCredit": opening_credit,
                "periodDebit": period_debit,
                "periodCredit": period_credit,
                "closingDebit": closing_debit,
                "closingCredit": closing_credit,
                "closingBalance": closing,
            }
        )
        totals["openingDebit"] += opening_debit
        totals["openingCredit"] += opening_credit
        totals["periodDebit"] += period_debit
        totals["periodCredit"] += period_credit
        totals["closingDebit"] += closing_debit
        totals["closingCredit"] += closing_credit

    return {
        "dateFrom": date_from,
        "dateTo": date_to,
        "currency": "IRR",
        "rowCount": len(rows),
        "totals": {
            **totals,
            "isBalanced": (
                totals["openingDebit"] == totals["openingCredit"]
                and totals["periodDebit"] == totals["periodCredit"]
                and totals["closingDebit"] == totals["closingCredit"]
            ),
        },
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# صورت سود و زیان و صورت وضعیت مالی
# ---------------------------------------------------------------------------
def _grouped_balances(
    *,
    tenant_id,
    school,
    schools,
    fiscal_year,
    cost_center,
    date_from,
    date_to,
    account_types: Iterable[str],
    cumulative: bool,
) -> dict[Any, int]:
    """
    مانده حساب‌های یک گروه.

    `cumulative=True` یعنی از ابتدای تاریخ تا `date_to` جمع می‌شود (ترازنامه)،
    و `False` یعنی فقط گردش داخل بازه (سود و زیان).
    """
    queryset = _apply_filters(
        _posted_lines(tenant_id),
        school=school,
        schools=schools,
        fiscal_year=fiscal_year,
        account_types=account_types,
        cost_center=cost_center,
    )
    if date_from and not cumulative:
        queryset = queryset.filter(journal_entry__entry_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(journal_entry__entry_date__lte=date_to)
    return _net_balances(queryset)


def _section(balances: dict[Any, int], account_type: str) -> tuple[list[dict], int]:
    """ردیف‌های یک گروه حساب به‌همراه جمع آن، با علامت طبیعی همان گروه."""
    accounts = Account.objects.filter(
        id__in=balances, account_type=account_type
    ).order_by("code")
    sign = NATURAL_SIDE[account_type]
    rows = []
    total = 0
    for account in accounts:
        amount = balances.get(account.id, 0) * sign
        if amount == 0:
            continue
        rows.append({**_account_payload(account), "amount": amount})
        total += amount
    return rows, total


def income_statement(
    *,
    tenant_id=None,
    school=None,
    schools: Iterable | None = None,
    fiscal_year=None,
    cost_center=None,
    date_from=None,
    date_to=None,
) -> dict:
    """
    صورت سود و زیان دوره.

    درآمد با ماهیت بستانکار و هزینه با ماهیت بدهکار مثبت گزارش می‌شوند، پس
    `netIncome = درآمد − هزینه` مستقیم قابل خواندن است.
    """
    date_from = _to_date(date_from)
    date_to = _to_date(date_to)

    balances = _grouped_balances(
        tenant_id=tenant_id,
        school=school,
        schools=schools,
        fiscal_year=fiscal_year,
        cost_center=cost_center,
        date_from=date_from,
        date_to=date_to,
        account_types=INCOME_STATEMENT_TYPES,
        cumulative=False,
    )
    revenue_rows, revenue_total = _section(balances, AccountType.REVENUE)
    expense_rows, expense_total = _section(balances, AccountType.EXPENSE)
    net = revenue_total - expense_total

    margin = None
    if revenue_total:
        margin = float(
            (Decimal(net) / Decimal(revenue_total) * 100).quantize(Decimal("0.01"))
        )

    return {
        "dateFrom": date_from,
        "dateTo": date_to,
        "currency": "IRR",
        "revenue": {"total": revenue_total, "rows": revenue_rows},
        "expense": {"total": expense_total, "rows": expense_rows},
        "netIncome": net,
        "netMarginPercent": margin,
    }


def balance_sheet(
    *,
    tenant_id=None,
    school=None,
    schools: Iterable | None = None,
    fiscal_year=None,
    as_of=None,
) -> dict:
    """
    صورت وضعیت مالی در یک تاریخ مشخص.

    سود و زیان انباشته دوره به‌عنوان یک ردیف محاسباتی به حقوق صاحبان سرمایه
    اضافه می‌شود؛ بدون آن، معادله حسابداری تا پیش از بستن حساب‌های موقت تراز
    نمی‌شود.
    """
    as_of = _to_date(as_of)

    balances = _grouped_balances(
        tenant_id=tenant_id,
        school=school,
        schools=schools,
        fiscal_year=fiscal_year,
        cost_center=None,
        date_from=None,
        date_to=as_of,
        account_types=BALANCE_SHEET_TYPES,
        cumulative=True,
    )
    asset_rows, asset_total = _section(balances, AccountType.ASSET)
    liability_rows, liability_total = _section(balances, AccountType.LIABILITY)
    equity_rows, equity_total = _section(balances, AccountType.EQUITY)

    result = income_statement(
        tenant_id=tenant_id,
        school=school,
        schools=schools,
        fiscal_year=fiscal_year,
        date_from=None,
        date_to=as_of,
    )
    retained = result["netIncome"]
    equity_with_result = equity_total + retained

    return {
        "asOf": as_of,
        "currency": "IRR",
        "asset": {"total": asset_total, "rows": asset_rows},
        "liability": {"total": liability_total, "rows": liability_rows},
        "equity": {
            "total": equity_with_result,
            "rows": equity_rows,
            "retainedResult": retained,
        },
        "totalAssets": asset_total,
        "totalLiabilitiesAndEquity": liability_total + equity_with_result,
        "difference": asset_total - (liability_total + equity_with_result),
        "isBalanced": asset_total == liability_total + equity_with_result,
    }


# ---------------------------------------------------------------------------
# دفتر روزنامه و گزارش مرکز هزینه
# ---------------------------------------------------------------------------
def daybook(
    *,
    tenant_id=None,
    school=None,
    schools: Iterable | None = None,
    fiscal_year=None,
    date_from=None,
    date_to=None,
) -> dict:
    """دفتر روزنامه: اسناد قطعی به‌ترتیب تاریخ، با ریز خطوط هر سند."""
    date_from = _to_date(date_from)
    date_to = _to_date(date_to)

    queryset = _apply_filters(
        _posted_lines(tenant_id),
        school=school,
        schools=schools,
        fiscal_year=fiscal_year,
    )
    if date_from:
        queryset = queryset.filter(journal_entry__entry_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(journal_entry__entry_date__lte=date_to)

    entries: dict[Any, dict] = {}
    for line in queryset.select_related(
        "journal_entry", "account", "cost_center"
    ).order_by("journal_entry__entry_date", "journal_entry__entry_no", "line_no"):
        entry = line.journal_entry
        payload = entries.setdefault(
            entry.id,
            {
                "entryId": str(entry.id),
                "entryNo": entry.entry_no,
                "entryDate": entry.entry_date,
                "description": entry.description,
                "sourceType": entry.source_type,
                "sourceTypeDisplay": entry.get_source_type_display(),
                "totalDebit": 0,
                "totalCredit": 0,
                "lines": [],
            },
        )
        payload["lines"].append(
            {
                "accountCode": line.account.code,
                "accountTitle": line.account.title,
                "costCenter": line.cost_center.title if line.cost_center else None,
                "description": line.description,
                "debit": line.debit_amount,
                "credit": line.credit_amount,
            }
        )
        payload["totalDebit"] += line.debit_amount
        payload["totalCredit"] += line.credit_amount

    rows = list(entries.values())
    return {
        "dateFrom": date_from,
        "dateTo": date_to,
        "currency": "IRR",
        "entryCount": len(rows),
        "totals": {
            "debit": sum(row["totalDebit"] for row in rows),
            "credit": sum(row["totalCredit"] for row in rows),
        },
        "entries": rows,
    }


def cost_center_report(
    *,
    tenant_id=None,
    school=None,
    schools: Iterable | None = None,
    fiscal_year=None,
    date_from=None,
    date_to=None,
) -> dict:
    """
    درآمد و هزینه به تفکیک مرکز هزینه (بخش ۱۴.۳).

    خطوط بدون مرکز هزینه زیر عنوان «بدون مرکز هزینه» می‌آیند تا جمع گزارش با
    صورت سود و زیان بخواند.
    """
    date_from = _to_date(date_from)
    date_to = _to_date(date_to)

    queryset = _apply_filters(
        _posted_lines(tenant_id),
        school=school,
        schools=schools,
        fiscal_year=fiscal_year,
        account_types=INCOME_STATEMENT_TYPES,
    )
    if date_from:
        queryset = queryset.filter(journal_entry__entry_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(journal_entry__entry_date__lte=date_to)

    rows: dict[Any, dict] = {}
    for row in queryset.values(
        "cost_center_id",
        "cost_center__code",
        "cost_center__title",
        "account__account_type",
    ).annotate(debit=Sum("debit_amount"), credit=Sum("credit_amount")):
        key = row["cost_center_id"]
        payload = rows.setdefault(
            key,
            {
                "costCenterId": str(key) if key else None,
                "costCenterCode": row["cost_center__code"] or "",
                "costCenterTitle": row["cost_center__title"] or "بدون مرکز هزینه",
                "revenue": 0,
                "expense": 0,
            },
        )
        net = int(row["debit"] or 0) - int(row["credit"] or 0)
        if row["account__account_type"] == AccountType.REVENUE:
            payload["revenue"] += -net
        else:
            payload["expense"] += net

    result = []
    for payload in sorted(rows.values(), key=lambda item: item["costCenterCode"]):
        payload["net"] = payload["revenue"] - payload["expense"]
        result.append(payload)

    return {
        "dateFrom": date_from,
        "dateTo": date_to,
        "currency": "IRR",
        "totals": {
            "revenue": sum(row["revenue"] for row in result),
            "expense": sum(row["expense"] for row in result),
            "net": sum(row["net"] for row in result),
        },
        "rows": result,
    }
