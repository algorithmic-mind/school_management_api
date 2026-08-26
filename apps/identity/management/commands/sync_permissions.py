"""همگام‌سازی کاتالوگ مجوزها و نقش‌های سیستمی."""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import Tenant
from apps.core.permissions import ScopeType
from apps.identity.models import Permission, Role, RolePermission
from apps.identity.services import sync_permission_catalog

#: نقش‌های سیستمی و الگوی مجوزهای آنها (بخش ۳.۱ و ۳.۳ سند تحلیل).
#: "*" یعنی همه اعمال آن منبع.
SYSTEM_ROLES: dict[str, dict] = {
    "PRINCIPAL": {
        "title": "مدیر مدرسه",
        "scopes": [ScopeType.SCHOOL, ScopeType.CAMPUS],
        "requires_mfa": True,
        "permissions": [
            "school.*", "campus.*", "academic_year.*", "grade_level.*",
            "course.*", "class_group.*", "schedule.*", "room.*",
            "student.read", "enrollment.read", "guardian.read", "admission.*",
            "employee.read", "contract.read", "leave.approve",
            "attendance.read", "session.read", "grade.read", "report_card.*",
            "exam.read", "invoice.read", "payment.read", "refund.approve",
            "journal.read", "purchase_request.approve", "asset.read",
            "health.read", "behavior.*", "approval.*", "notification.*",
            "report.*", "audit.read",
        ],
    },
    "ACADEMIC_VP": {
        "title": "معاون آموزشی",
        "scopes": [ScopeType.CAMPUS, ScopeType.ACADEMIC_YEAR],
        "permissions": [
            "class_group.*", "schedule.*", "course.read", "grade_level.read",
            "course.read", "room.read", "academic_year.read",
            "student.read", "enrollment.read", "guardian.read",
            "session.*", "attendance.*", "assignment.*", "resource.*",
            "question.*", "exam.*", "attempt.read", "appeal.*",
            "grade.*", "report_card.*",
            "teaching_assignment.*", "employee.read",
            "approval.read", "approval.decide", "notification.create",
            "report.read",
        ],
    },
    "REGISTRAR": {
        "title": "معاون اجرایی و ثبت‌نام",
        "scopes": [ScopeType.CAMPUS],
        "permissions": [
            "person.*", "student.*", "guardian.*", "admission.*",
            "enrollment.*", "consent.*", "class_group.read",
            "grade_level.read", "academic_year.read",
            "notification.create", "report.read",
        ],
    },
    "TEACHER": {
        "title": "معلم",
        "scopes": [ScopeType.COURSE_OFFERING, ScopeType.CLASS_GROUP],
        "permissions": [
            "class_group.read", "schedule.read", "course.read",
            "student.read", "session.read", "session.create", "session.update",
            "attendance.read", "attendance.create", "attendance.update",
            "attendance.finalize",
            "assignment.*", "resource.*",
            "question.read", "question.create", "question.update",
            "exam.read", "exam.create", "exam.update", "exam.grade",
            "grade.read", "grade.create", "grade.update",
            "report_card.read", "health.read",
            "behavior.read", "behavior.create",
            "notification.read",
        ],
    },
    "ACCOUNTANT": {
        "title": "حسابدار",
        "scopes": [ScopeType.SCHOOL],
        "requires_mfa": True,
        "permissions": [
            "fee_plan.*", "invoice.*", "payment.*", "refund.read", "refund.create",
            "journal.read", "journal.create", "journal.post",
            "bank.*", "student.read", "guardian.read", "enrollment.read",
            "purchase_order.read", "report.*",
        ],
    },
    "CASHIER": {
        "title": "صندوق‌دار",
        "scopes": [ScopeType.CAMPUS],
        "permissions": [
            "invoice.read", "payment.read", "payment.create", "payment.allocate",
            "student.read", "guardian.read",
        ],
    },
    "HR_MANAGER": {
        "title": "مسئول منابع انسانی",
        "scopes": [ScopeType.SCHOOL],
        "requires_mfa": True,
        "permissions": [
            "person.*", "employee.*", "contract.*", "teaching_assignment.*",
            "leave.*", "payroll.*", "report.read",
        ],
    },
    "WAREHOUSE_KEEPER": {
        "title": "انباردار",
        "scopes": [ScopeType.CAMPUS],
        "permissions": [
            "item.*", "stock.*", "vendor.read",
            "purchase_request.read", "purchase_request.create",
            "purchase_order.read", "asset.read", "asset.assign",
        ],
    },
    "PROCUREMENT": {
        "title": "مسئول تدارکات",
        "scopes": [ScopeType.SCHOOL],
        "permissions": [
            "vendor.*", "item.read", "purchase_request.*", "purchase_order.*",
            "stock.read", "stock.receive", "asset.*",
        ],
    },
    "COUNSELOR": {
        "title": "مشاور",
        "scopes": [ScopeType.CAMPUS],
        "requires_mfa": True,
        "permissions": [
            "student.read", "guardian.read", "counseling.*",
            "behavior.read", "attendance.read", "grade.read",
        ],
    },
    "HEALTH_OFFICER": {
        "title": "مربی بهداشت",
        "scopes": [ScopeType.CAMPUS],
        "requires_mfa": True,
        "permissions": ["student.read", "guardian.read", "health.*"],
    },
    "LIBRARIAN": {
        "title": "کتابدار",
        "scopes": [ScopeType.CAMPUS],
        "permissions": ["library.*", "student.read", "person.read"],
    },
    "TRANSPORT_MANAGER": {
        "title": "مسئول حمل‌ونقل",
        "scopes": [ScopeType.CAMPUS],
        "permissions": ["transport.*", "student.read", "guardian.read"],
    },
    "GUARDIAN": {
        "title": "ولی/سرپرست",
        "scopes": [ScopeType.SELF],
        "permissions": [
            "student.read", "enrollment.read", "attendance.read",
            "attendance.justify", "grade.read", "report_card.read",
            "invoice.read", "payment.create", "consent.read", "consent.create",
            "notification.read", "approval.request", "library.read",
            "transport.read",
        ],
    },
    "STUDENT": {
        "title": "دانش‌آموز",
        "scopes": [ScopeType.SELF],
        "permissions": [
            "student.read", "schedule.read", "assignment.read",
            "assignment.update", "resource.read",
            "exam.read", "attempt.start", "attempt.save", "attempt.submit",
            "attempt.read", "appeal.create", "appeal.read",
            "grade.read", "report_card.read", "notification.read",
            "library.read",
        ],
    },
    "AUDITOR": {
        "title": "ناظر/بازرس",
        "scopes": [ScopeType.SCHOOL],
        "permissions": [
            "student.read", "enrollment.read", "grade.read", "report_card.read",
            "invoice.read", "payment.read", "journal.read", "stock.read",
            "asset.read", "audit.read", "report.read",
        ],
    },
    "SYS_ADMIN": {
        "title": "مدیر سامانه",
        "scopes": [ScopeType.TENANT],
        "requires_mfa": True,
        "permissions": [
            "person.*", "user.*", "role.*", "audit.*",
            "notification.*", "attachment.*", "approval.read", "report.read",
        ],
    },
}


def expand_patterns(patterns: list[str]) -> set[str]:
    """الگوی `resource.*` را به کدهای واقعی مجوز باز می‌کند."""
    all_codes = set(Permission.objects.values_list("code", flat=True))
    resolved: set[str] = set()
    for pattern in patterns:
        if pattern.endswith(".*"):
            prefix = pattern[:-1]
            resolved.update(code for code in all_codes if code.startswith(prefix))
        elif pattern in all_codes:
            resolved.add(pattern)
    return resolved


class Command(BaseCommand):
    help = "همگام‌سازی کاتالوگ مجوزها و ساخت نقش‌های سیستمی برای هر سازمان."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            dest="tenant_code",
            help="کد سازمان؛ در صورت نبود، برای همه سازمان‌ها اجرا می‌شود.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        created, existing = sync_permission_catalog()
        self.stdout.write(
            self.style.SUCCESS(
                f"کاتالوگ مجوزها همگام شد: {created} جدید، {existing} موجود."
            )
        )

        tenants = Tenant.objects.all()
        if options.get("tenant_code"):
            tenants = tenants.filter(code=options["tenant_code"])

        if not tenants.exists():
            self.stdout.write(
                self.style.WARNING("هیچ سازمانی یافت نشد؛ نقش‌ها ساخته نشدند.")
            )
            return

        for tenant in tenants:
            role_count = 0
            for code, spec in SYSTEM_ROLES.items():
                role, _ = Role.objects.update_or_create(
                    tenant=tenant,
                    code=code,
                    defaults={
                        "title": spec["title"],
                        "is_system": True,
                        "requires_mfa": spec.get("requires_mfa", False),
                        "allowed_scope_types": spec["scopes"],
                    },
                )
                codes = expand_patterns(spec["permissions"])
                permissions = Permission.objects.filter(code__in=codes)

                RolePermission.objects.filter(role=role).delete()
                RolePermission.objects.bulk_create(
                    [
                        RolePermission(role=role, permission=permission)
                        for permission in permissions
                    ]
                )
                role_count += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"سازمان «{tenant.name}»: {role_count} نقش سیستمی همگام شد."
                )
            )
