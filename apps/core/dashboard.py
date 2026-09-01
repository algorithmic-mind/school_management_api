"""
داشبورد مدیریتی: ویجت‌های تجمیعی صفحه اصلی.

مرجع: بخش ۱۴ سند تحلیل (گزارش‌ها و شاخص‌های مدیریتی) و بخش ۶.۱ سند فرانت
(WF-DASH-01).

**قاعده مجوز.** «ویجت فاقد مجوز اصلاً Render نمی‌شود» (بخش ۶.۱ سند فرانت).
پس هر ویجت مجوز لازم خودش را اعلام می‌کند و اگر کاربر آن را نداشته باشد،
اصلاً در پاسخ نمی‌آید — نه اینکه با مقدار صفر یا خطا برگردد. فرانت فقط
`widgets` را می‌پیماید و هرچه هست را می‌چیند.

**قاعده دامنه.** همه شمارش‌ها از محدوده مؤثر همان کاربر عبور می‌کنند
(:mod:`apps.identity.scopes`)؛ داشبورد مدیرِ یک شعبه، اعداد همان شعبه را
نشان می‌دهد، نه کل سازمان.

**تازگی داده.** هر ویجت `asOf` دارد. بخش ۶.۱: «هر Widget زمان آخرین
به‌روزرسانی، Scope و لینک Drill-down دارد» — `link` همان مسیر API‌ای است که
جزئیات همان عدد را می‌دهد.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from django.db.models import Count, F, Q, Sum
from django.utils import timezone


@dataclass
class Widget:
    """یک کارت داشبورد به‌همراه مجوزی که دیدنش را ممکن می‌کند."""

    key: str
    title: str
    permission: str
    builder: Callable
    link: str = ""


def _scope_filter(scope, paths: dict[str, str]) -> Q:
    """
    محدوده مؤثر کاربر را به شرط ORM برای یک مدل ترجمه می‌کند.

    `paths` مسیر ORM آن مدل تا هر بُعد است. بندهایی که روی این مدل قابل بیان
    نیستند، محدودیتی اعمال نمی‌کنند — همان قراردادی که در
    :class:`apps.core.viewsets.ScopedQuerysetMixin` هست، تا عدد داشبورد با
    فهرستی که کاربر با Drill-down می‌بیند یکی باشد.
    """
    if scope is None or scope.is_unrestricted:
        return Q()
    if not scope.clauses:
        return Q(pk__in=[])

    combined = Q()
    for clause in scope.clauses:
        if clause.self_only:
            # ویجت‌های این ماژول همه سازمانی‌اند و معادل «فقط رکوردهای خود»
            # ندارند. بازگرداندن شرطِ باز، شمارش کل مدرسه را به دانش‌آموز نشان
            # می‌داد؛ پس نتیجه تهی می‌شود. `build_dashboard` هم چنین کاربری را
            # پیش از رسیدن به اینجا کنار می‌گذارد و این فقط لایه دوم است.
            return Q(pk__in=[])
        path = paths.get(clause.dimension) if clause.dimension else None
        if path:
            combined |= Q(**{f"{path}_id": clause.value})
            continue
        school_path = paths.get("schools")
        if clause.school_id and school_path:
            combined |= Q(**{f"{school_path}_id": clause.school_id})
            continue
        return Q()  # این بند روی این مدل قابل بیان نیست
    return combined


# ---------------------------------------------------------------------------
# سازنده هر ویجت
# ---------------------------------------------------------------------------
def _active_students(context) -> dict:
    from apps.students.enums import EnrollmentStatus
    from apps.students.models import Enrollment

    queryset = Enrollment.objects.filter(
        tenant_id=context["tenant_id"], status=EnrollmentStatus.ACTIVE
    ).filter(
        _scope_filter(
            context["scope"],
            {
                "schools": "campus__school",
                "campuses": "campus",
                "academic_years": "academic_year",
            },
        )
    )
    if context["academic_year_id"]:
        queryset = queryset.filter(academic_year_id=context["academic_year_id"])

    by_grade = list(
        queryset.values("grade_level__title")
        .annotate(count=Count("id"))
        .order_by("-count")[:12]
    )
    return {
        "value": queryset.count(),
        "unit": "دانش‌آموز",
        "breakdown": [
            {"label": row["grade_level__title"], "value": row["count"]}
            for row in by_grade
        ],
    }


def _attendance_today(context) -> dict:
    from apps.teaching.enums import AttendanceStatus
    from apps.teaching.models import AttendanceRecord

    today = context["today"]
    queryset = AttendanceRecord.objects.filter(
        tenant_id=context["tenant_id"], session__starts_at__date=today
    ).filter(
        _scope_filter(
            context["scope"],
            {
                "schools": "enrollment__campus__school",
                "campuses": "enrollment__campus",
                "academic_years": "enrollment__academic_year",
                "class_groups": "session__course_offering__class_group",
                "course_offerings": "session__course_offering",
            },
        )
    )

    total = queryset.count()
    present = queryset.filter(
        attendance_status__in=[
            AttendanceStatus.PRESENT,
            AttendanceStatus.LATE,
            AttendanceStatus.SCHOOL_ACTIVITY,
        ]
    ).count()
    absent = queryset.filter(attendance_status=AttendanceStatus.ABSENT).count()
    excused = queryset.filter(attendance_status=AttendanceStatus.EXCUSED).count()

    return {
        # با نبود رکورد، درصد `null` است نه صفر: «هنوز ثبت نشده» با «همه غایب»
        # یکی نیست و فرانت باید این دو را متفاوت نشان دهد.
        "value": round(present * 100 / total, 1) if total else None,
        "unit": "درصد حضور",
        "breakdown": [
            {"label": "حاضر", "value": present},
            {"label": "غایب", "value": absent},
            {"label": "غیبت موجه", "value": excused},
            {"label": "کل رکورد امروز", "value": total},
        ],
    }


def _attendance_trend(context) -> dict:
    from apps.teaching.enums import AttendanceStatus
    from apps.teaching.models import AttendanceRecord

    today = context["today"]
    start = today - timedelta(days=29)
    queryset = (
        AttendanceRecord.objects.filter(
            tenant_id=context["tenant_id"],
            session__starts_at__date__gte=start,
            session__starts_at__date__lte=today,
        )
        .filter(
            _scope_filter(
                context["scope"],
                {
                    "schools": "enrollment__campus__school",
                    "campuses": "enrollment__campus",
                    "academic_years": "enrollment__academic_year",
                    "class_groups": "session__course_offering__class_group",
                    "course_offerings": "session__course_offering",
                },
            )
        )
        .values("session__starts_at__date", "attendance_status")
        .annotate(count=Count("id"))
    )

    days: dict = {}
    for row in queryset:
        day = days.setdefault(
            row["session__starts_at__date"],
            {"date": row["session__starts_at__date"], "present": 0, "absent": 0, "excused": 0},
        )
        status = row["attendance_status"]
        if status == AttendanceStatus.ABSENT:
            day["absent"] += row["count"]
        elif status == AttendanceStatus.EXCUSED:
            day["excused"] += row["count"]
        else:
            day["present"] += row["count"]

    return {
        "value": len(days),
        "unit": "روز دارای داده",
        "series": [days[key] for key in sorted(days)],
    }


def _tuition_collection(context) -> dict:
    from apps.finance.enums import InvoiceStatus
    from apps.finance.models import Invoice

    queryset = Invoice.objects.filter(tenant_id=context["tenant_id"]).exclude(
        status__in=[InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED]
    ).filter(
        _scope_filter(
            context["scope"],
            {
                "schools": "agreement__enrollment__campus__school",
                "campuses": "agreement__enrollment__campus",
                "academic_years": "agreement__fee_plan__academic_year",
            },
        )
    )

    totals = queryset.aggregate(
        invoiced=Sum("total_amount"), paid=Sum("paid_amount")
    )
    invoiced = int(totals["invoiced"] or 0)
    paid = int(totals["paid"] or 0)

    overdue = queryset.filter(
        due_date__lt=context["today"], total_amount__gt=F("paid_amount")
    ).aggregate(total=Sum("total_amount"), paid=Sum("paid_amount"))
    overdue_balance = int(overdue["total"] or 0) - int(overdue["paid"] or 0)

    week_ahead = queryset.filter(
        due_date__gte=context["today"],
        due_date__lte=context["today"] + timedelta(days=7),
        total_amount__gt=F("paid_amount"),
    ).aggregate(total=Sum("total_amount"), paid=Sum("paid_amount"))

    return {
        "value": round(paid * 100 / invoiced, 1) if invoiced else None,
        "unit": "درصد وصول",
        "currency": "IRR",
        "breakdown": [
            {"label": "مبلغ صورتحساب", "value": invoiced},
            {"label": "وصول‌شده", "value": paid},
            {"label": "مانده", "value": invoiced - paid},
            {"label": "معوق (سررسید گذشته)", "value": overdue_balance},
            {
                "label": "سررسید هفته آینده",
                "value": int(week_ahead["total"] or 0) - int(week_ahead["paid"] or 0),
            },
        ],
    }


def _pending_approvals(context) -> dict:
    from apps.workflow.enums import ApprovalStatus
    from apps.workflow.models import ApprovalRequest

    queryset = ApprovalRequest.objects.filter(
        tenant_id=context["tenant_id"],
        status=ApprovalStatus.PENDING,
    )
    by_workflow = list(
        queryset.values("workflow_code").annotate(count=Count("id")).order_by("-count")[:8]
    )
    return {
        "value": queryset.count(),
        "unit": "کار در انتظار",
        "breakdown": [
            {"label": row["workflow_code"], "value": row["count"]} for row in by_workflow
        ],
    }


def _class_capacity(context) -> dict:
    from apps.organization.enums import ClassGroupStatus
    from apps.organization.models import ClassGroup
    from apps.students.enums import ClassMembershipStatus

    queryset = ClassGroup.objects.filter(
        tenant_id=context["tenant_id"], status=ClassGroupStatus.ACTIVE
    ).filter(
        _scope_filter(
            context["scope"],
            {
                "schools": "campus__school",
                "campuses": "campus",
                "academic_years": "academic_year",
                "class_groups": "id",
            },
        )
    )
    if context["academic_year_id"]:
        queryset = queryset.filter(academic_year_id=context["academic_year_id"])

    queryset = queryset.annotate(
        occupied=Count(
            "class_memberships",
            filter=Q(class_memberships__status=ClassMembershipStatus.ACTIVE),
            distinct=True,
        )
    )

    rows = []
    near_full = 0
    for class_group in queryset.select_related("grade_level"):
        capacity = class_group.capacity or 0
        occupied = class_group.occupied
        ratio = round(occupied * 100 / capacity, 1) if capacity else None
        if ratio is not None and ratio >= 90:
            near_full += 1
        rows.append(
            {
                "classGroupId": str(class_group.id),
                "code": class_group.code,
                "gradeLevel": class_group.grade_level.title,
                "capacity": capacity,
                "occupied": occupied,
                "available": max(capacity - occupied, 0),
                "occupancyPercent": ratio,
            }
        )

    return {
        "value": near_full,
        "unit": "کلاس با اشغال ۹۰٪ به بالا",
        "rows": sorted(
            rows, key=lambda row: row["occupancyPercent"] or 0, reverse=True
        )[:15],
    }


def _expiring_contracts(context) -> dict:
    from apps.hr.enums import ContractStatus
    from apps.hr.models import EmploymentContract

    horizon = context["today"] + timedelta(days=60)
    queryset = EmploymentContract.objects.filter(
        tenant_id=context["tenant_id"],
        status=ContractStatus.ACTIVE,
        ends_on__isnull=False,
        ends_on__lte=horizon,
        ends_on__gte=context["today"],
    ).select_related("employee__person")

    return {
        "value": queryset.count(),
        "unit": "قرارداد رو به انقضا (۶۰ روز)",
        "rows": [
            {
                "contractId": str(contract.id),
                "employee": contract.employee.person.full_name,
                "endsOn": contract.ends_on,
            }
            for contract in queryset.order_by("ends_on")[:15]
        ],
    }


def _bank_discrepancies(context) -> dict:
    from apps.finance.enums import ReconciliationStatus
    from apps.finance.models import BankReconciliation

    queryset = BankReconciliation.objects.filter(
        tenant_id=context["tenant_id"],
        status__in=[ReconciliationStatus.OPEN, ReconciliationStatus.DISCREPANCY],
    ).filter(
        _scope_filter(context["scope"], {"schools": "bank_account__school"})
    )
    return {
        "value": queryset.count(),
        "unit": "مغایرت بانکی باز",
        "rows": [
            {
                "reconciliationId": str(item.id),
                "bankAccount": item.bank_account.title,
                "periodEnd": item.period_end,
                "difference": item.difference,
            }
            for item in queryset.select_related("bank_account").order_by("-period_end")[:10]
        ],
    }


def _stock_alerts(context) -> dict:
    from apps.inventory.models import StockBalance

    queryset = StockBalance.objects.filter(
        tenant_id=context["tenant_id"], on_hand_qty__lte=F("item__reorder_point")
    ).filter(
        _scope_filter(
            context["scope"],
            {"schools": "item__category__school", "campuses": "warehouse__campus"},
        )
    )
    return {
        "value": queryset.count(),
        "unit": "قلم زیر نقطه سفارش",
        "rows": [
            {
                "itemId": str(balance.item_id),
                "item": balance.item.title,
                "warehouse": balance.warehouse.title,
                "onHand": balance.on_hand_qty,
                "reorderPoint": balance.item.reorder_point,
            }
            for balance in queryset.select_related("item", "warehouse")[:15]
        ],
    }


#: فهرست ویجت‌ها به‌ترتیب نمایش در صفحه (بخش ۶.۱ سند فرانت).
WIDGETS: tuple[Widget, ...] = (
    Widget(
        "activeStudents", "دانش‌آموزان فعال", "student.read", _active_students,
        "/api/v1/students/students/?status=ACTIVE",
    ),
    Widget(
        "attendanceToday", "حضور امروز", "attendance.read", _attendance_today,
        "/api/v1/teaching/attendance/monitor/",
    ),
    Widget(
        "tuitionCollection", "وصول شهریه", "invoice.read", _tuition_collection,
        "/api/v1/finance/invoices/aging/",
    ),
    Widget(
        "pendingApprovals", "کارهای در انتظار تأیید", "approval.read", _pending_approvals,
        "/api/v1/workflow/my-tasks/",
    ),
    Widget(
        "attendanceTrend", "روند حضور ۳۰ روز اخیر", "attendance.read", _attendance_trend,
        "/api/v1/teaching/attendance/",
    ),
    Widget(
        "classCapacity", "ظرفیت کلاس‌ها", "class_group.read", _class_capacity,
        "/api/v1/org/class-groups/",
    ),
    Widget(
        "expiringContracts", "قراردادهای رو به انقضا", "contract.read", _expiring_contracts,
        "/api/v1/hr/contracts/",
    ),
    Widget(
        "bankDiscrepancies", "مغایرت‌های بانکی", "bank.read", _bank_discrepancies,
        "/api/v1/finance/reconciliations/",
    ),
    Widget(
        "stockAlerts", "موجودی زیر نقطه سفارش", "stock.read", _stock_alerts,
        "/api/v1/inventory/balances/",
    ),
)


def build_dashboard(request, *, keys: list[str] | None = None) -> dict:
    """
    داشبورد کاربر جاری.

    `keys` اجازه می‌دهد فرانت فقط ویجت‌های موردنیازش را بخواهد — صفحه‌ای که
    چهار کارت بالای صفحه را زودتر نشان می‌دهد، لازم نیست منتظر محاسبه روند
    سی‌روزه بماند.
    """
    from apps.core.context import get_current_context

    ctx = get_current_context()
    user = request.user
    context = {
        "tenant_id": ctx.tenant_id if ctx else None,
        "scope": getattr(ctx, "effective_scope", None) if ctx else None,
        "academic_year_id": ctx.academic_year_id if ctx else None,
        "today": timezone.localdate(),
    }

    def permitted(code: str) -> bool:
        return user.is_superuser or user.has_perm_code(code)

    scope = context["scope"]
    # همه ویجت‌های این داشبورد سازمانی‌اند: «تعداد دانش‌آموزان فعال»، «درصد
    # وصول شهریه» و مانند آن‌ها برای دانش‌آموز یا ولی معنایی ندارند و
    # نمایششان افشای تجمیعی است. پرتال آن‌ها (بخش ۱۶ سند فرانت) از منابع
    # خودشان تغذیه می‌شود، نه از این داشبورد.
    self_only = bool(scope is not None and getattr(scope, "self_only", False))

    now = timezone.now()
    widgets = []
    for widget in WIDGETS:
        if self_only:
            break
        if keys and widget.key not in keys:
            continue
        if not permitted(widget.permission):
            continue
        payload = widget.builder(context)
        widgets.append(
            {
                "key": widget.key,
                "title": widget.title,
                "link": widget.link,
                "asOf": now,
                **payload,
            }
        )

    return {
        "generatedAt": now,
        "date": context["today"],
        "selfServiceOnly": self_only,
        "scope": {
            "schoolId": ctx.school_id if ctx else None,
            "campusId": ctx.campus_id if ctx else None,
            "academicYearId": context["academic_year_id"],
        },
        "widgetCount": len(widgets),
        "widgets": widgets,
    }
