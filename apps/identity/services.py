"""سرویس‌های ماژول هویت: ثبت ممیزی و کاتالوگ مجوزها."""

from __future__ import annotations

import uuid
from typing import Any

from apps.core.context import get_current_context
from apps.identity.enums import AuditAction
from apps.identity.models import AuditLog

#: فیلدهایی که هرگز در ممیزی ثبت نمی‌شوند (بخش ۷.۳ و ۱۵.۲)
REDACTED_FIELDS = {
    "password",
    "new_password",
    "current_password",
    "token",
    "access",
    "refresh",
    "secret",
    "otp",
    "mfa_secret",
    "response_payload",
    "protected_note",
}


def redact(data: dict[str, Any]) -> dict[str, Any]:
    """حذف مقادیر راز از داده‌ای که قرار است ممیزی شود."""
    return {
        key: ("***" if key.lower() in REDACTED_FIELDS else value)
        for key, value in data.items()
    }


def record_audit(
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    entity_label: str = "",
    reason: str = "",
    changes: dict | None = None,
    classification: str | None = None,
    actor_username: str = "",
) -> AuditLog | None:
    """
    ثبت یک رکورد ممیزی Append-only.

    خطای ثبت ممیزی نباید عملیات اصلی را متوقف کند، اما باید در Log بیاید.
    """
    import logging

    ctx = get_current_context()
    try:
        return AuditLog.objects.create(
            tenant_id=ctx.tenant_id if ctx else None,
            actor_user_id=ctx.user_id if ctx else None,
            actor_username=actor_username,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_label=entity_label[:250],
            reason=reason[:500],
            correlation_id=ctx.correlation_id if ctx else "",
            changes=redact(changes or {}),
            classification=classification or "INTERNAL",
            client_ip=(ctx.client_ip or None) if ctx else None,
            user_agent=ctx.user_agent if ctx else "",
        )
    except Exception:  # pragma: no cover - ممیزی نباید مسیر اصلی را بشکند
        logging.getLogger(__name__).exception("ثبت رکورد ممیزی ناموفق بود.")
        return None


def audit_state_transition(instance, action_name: str, from_status: str, to_status: str):
    """ممیزی تغییر وضعیت موجودیت (بخش ۱۰)."""
    return record_audit(
        action=AuditAction.STATE_TRANSITION,
        entity_type=instance._meta.label,
        entity_id=getattr(instance, "id", None),
        entity_label=str(instance)[:250],
        changes={"action": action_name, "from": from_status, "to": to_status},
    )


# ---------------------------------------------------------------------------
# کاتالوگ مجوزهای پایه سامانه
# ---------------------------------------------------------------------------
#: (منبع، ماژول، عنوان فارسی، [اعمال], حساس؟)
PERMISSION_CATALOG: list[tuple[str, str, str, list[str], bool]] = [
    # --- IAM ---
    ("person", "identity", "اشخاص", ["read", "create", "update", "delete"], False),
    ("user", "identity", "حساب کاربری", ["read", "create", "update", "disable"], True),
    ("role", "identity", "نقش و مجوز", ["read", "create", "update", "delete"], True),
    ("audit", "identity", "گزارش ممیزی", ["read", "export"], True),
    # --- Organization ---
    ("school", "organization", "مدرسه", ["read", "create", "update"], False),
    ("campus", "organization", "شعبه", ["read", "create", "update"], False),
    ("academic_year", "organization", "سال تحصیلی",
     ["read", "create", "update", "activate", "close", "reopen"], True),
    ("grade_level", "organization", "پایه تحصیلی", ["read", "create", "update"], False),
    ("course", "organization", "درس", ["read", "create", "update", "delete"], False),
    ("class_group", "organization", "کلاس", ["read", "create", "update", "delete"], False),
    ("schedule", "organization", "برنامه هفتگی", ["read", "create", "update", "publish"], False),
    ("room", "organization", "اتاق", ["read", "create", "update"], False),
    # --- Students ---
    ("admission", "students", "پذیرش",
     ["read", "create", "update", "review", "approve", "reject"], False),
    ("student", "students", "دانش‌آموز", ["read", "create", "update", "delete"], False),
    ("guardian", "students", "ولی و سرپرست", ["read", "create", "update"], False),
    ("enrollment", "students", "ثبت‌نام",
     ["read", "create", "update", "activate", "transfer", "withdraw"], False),
    ("consent", "students", "رضایت‌نامه", ["read", "create", "revoke"], False),
    # --- HR ---
    ("employee", "hr", "پرسنل", ["read", "create", "update", "delete"], False),
    ("contract", "hr", "قرارداد", ["read", "create", "update", "close"], True),
    ("teaching_assignment", "hr", "انتساب تدریس", ["read", "create", "update"], False),
    ("leave", "hr", "مرخصی", ["read", "create", "approve"], False),
    ("payroll", "hr", "حقوق و دستمزد", ["read", "create", "run", "approve"], True),
    # --- Teaching ---
    ("session", "teaching", "جلسه درسی", ["read", "create", "update", "cancel"], False),
    ("attendance", "teaching", "حضور و غیاب",
     ["read", "create", "update", "finalize", "justify"], False),
    ("assignment", "teaching", "تکلیف", ["read", "create", "update", "publish", "grade"], False),
    ("resource", "teaching", "منابع آموزشی", ["read", "create", "update", "delete"], False),
    # --- Assessment ---
    ("question", "assessment", "بانک سؤال",
     ["read", "create", "update", "review", "approve", "retire"], False),
    ("exam", "assessment", "آزمون",
     ["read", "create", "update", "publish", "cancel", "grade", "finalize"], False),
    ("attempt", "assessment", "تلاش آزمون", ["read", "start", "save", "submit"], False),
    ("appeal", "assessment", "اعتراض به نمره", ["read", "create", "resolve"], False),
    # --- Gradebook ---
    ("grade", "gradebook", "دفتر نمره",
     ["read", "create", "update", "lock", "unlock", "publish"], False),
    ("report_card", "gradebook", "کارنامه", ["read", "generate", "publish"], False),
    # --- Finance ---
    ("fee_plan", "finance", "تعرفه شهریه", ["read", "create", "update"], False),
    ("invoice", "finance", "صورتحساب", ["read", "create", "issue", "cancel", "credit"], True),
    ("payment", "finance", "پرداخت", ["read", "create", "allocate", "void"], True),
    ("refund", "finance", "استرداد", ["read", "create", "approve"], True),
    ("journal", "finance", "سند حسابداری",
     ["read", "create", "post", "reverse", "close_period"], True),
    ("bank", "finance", "حساب بانکی و مغایرت", ["read", "create", "reconcile"], True),
    # --- Inventory ---
    ("vendor", "inventory", "تأمین‌کننده", ["read", "create", "update"], False),
    ("item", "inventory", "کالا", ["read", "create", "update"], False),
    ("purchase_request", "inventory", "درخواست خرید",
     ["read", "create", "submit", "approve", "reject"], False),
    ("purchase_order", "inventory", "سفارش خرید", ["read", "create", "issue", "close"], True),
    ("stock", "inventory", "انبار و موجودی", ["read", "receive", "issue", "transfer", "adjust"], False),
    ("asset", "inventory", "اموال", ["read", "create", "assign", "retire"], False),
    # --- Welfare ---
    ("health", "welfare", "پرونده سلامت", ["read", "create", "update"], True),
    ("counseling", "welfare", "مشاوره", ["read", "create", "update"], True),
    ("behavior", "welfare", "انضباط", ["read", "create", "update", "resolve"], False),
    ("library", "welfare", "کتابخانه", ["read", "create", "update", "loan", "return"], False),
    ("transport", "welfare", "حمل‌ونقل", ["read", "create", "update", "assign"], False),
    # --- Workflow ---
    ("approval", "workflow", "گردش تأیید", ["read", "request", "decide"], False),
    ("notification", "workflow", "اعلان", ["read", "create", "send", "broadcast"], False),
    ("attachment", "workflow", "پیوست", ["read", "create", "delete"], False),
    ("report", "workflow", "گزارش", ["read", "export"], False),
]

#: عنوان فارسی اعمال، برای ساخت خودکار عنوان مجوز
ACTION_TITLES = {
    "read": "مشاهده",
    "create": "ایجاد",
    "update": "ویرایش",
    "delete": "حذف",
    "activate": "فعال‌سازی",
    "close": "بستن",
    "reopen": "بازگشایی",
    "publish": "انتشار",
    "cancel": "لغو",
    "approve": "تأیید",
    "reject": "رد",
    "review": "بازبینی",
    "submit": "ارسال",
    "finalize": "نهایی‌سازی",
    "lock": "قفل",
    "unlock": "بازکردن قفل",
    "transfer": "انتقال",
    "withdraw": "ترک تحصیل",
    "revoke": "لغو",
    "justify": "توجیه",
    "grade": "تصحیح و نمره‌دهی",
    "generate": "تولید",
    "issue": "صدور",
    "allocate": "تخصیص",
    "void": "ابطال",
    "credit": "صدور یادداشت بستانکار",
    "post": "قطعی‌سازی",
    "reverse": "برگشت سند",
    "close_period": "بستن دوره",
    "reconcile": "مغایرت‌گیری",
    "receive": "رسید",
    "adjust": "تعدیل",
    "assign": "تخصیص",
    "retire": "بازنشستگی/اسقاط",
    "run": "اجرا",
    "export": "خروجی‌گیری",
    "disable": "غیرفعال‌سازی",
    "start": "شروع",
    "save": "ذخیره",
    "loan": "امانت",
    "return": "بازگشت",
    "resolve": "رسیدگی",
    "request": "درخواست",
    "decide": "تصمیم",
    "send": "ارسال",
    "broadcast": "ارسال گروهی",
}


def sync_permission_catalog() -> tuple[int, int]:
    """
    کاتالوگ مجوزها را با پایگاه داده همگام می‌کند.

    خروجی: (تعداد ایجادشده، تعداد موجود)
    """
    from apps.identity.models import Permission

    created = 0
    existing = 0
    for resource, module, title_fa, actions, sensitive in PERMISSION_CATALOG:
        for action in actions:
            code = f"{resource}.{action}"
            action_fa = ACTION_TITLES.get(action, action)
            _, was_created = Permission.objects.update_or_create(
                code=code,
                defaults={
                    "resource": resource,
                    "action": action,
                    "module": module,
                    "title": f"{action_fa} {title_fa}",
                    "is_sensitive": sensitive
                    or action in {"delete", "approve", "post", "reverse", "publish"},
                },
            )
            if was_created:
                created += 1
            else:
                existing += 1
    return created, existing
