"""
داده پایه مشترک آزمون‌ها.

عمداً از `seed_demo` استفاده نمی‌شود: آن دستور برای نمایش ساخته شده و داده‌اش
با هر تغییر ممکن است جابه‌جا شود. آزمون باید روی داده‌ای بایستد که خودش
ساخته و اعداد انتظاری‌اش را می‌داند.
"""

from __future__ import annotations

from datetime import date

from apps.core.models import Tenant
from apps.core.permissions import ScopeType
from apps.finance.enums import AccountType, JournalStatus
from apps.finance.models import Account, CostCenter, FiscalYear, JournalEntry, JournalLine
from apps.identity.models import Person, Role, UserAccount, UserRoleAssignment
from apps.identity.services import sync_permission_catalog
from apps.organization.enums import SchoolType
from apps.organization.models import AcademicYear, Campus, GradeLevel, School
from apps.students.enums import EnrollmentStatus
from apps.students.models import Enrollment, Guardian, Student, StudentGuardian

PASSWORD = "TestPass!2026"
YEAR_START = date(2026, 3, 21)
YEAR_END = date(2027, 3, 20)


def make_tenant(code: str = "test-org") -> Tenant:
    return Tenant.objects.create(name="سازمان آزمون", code=code)


def make_school(tenant: Tenant, code: str, name: str) -> School:
    return School.objects.create(
        tenant=tenant, code=code, name=name, school_type=SchoolType.LOWER_SECONDARY
    )


def make_campus(tenant: Tenant, school: School, code: str = "CMP") -> Campus:
    return Campus.objects.create(
        tenant=tenant, school=school, code=code, name=f"شعبه {code}"
    )


def make_academic_year(tenant: Tenant, school: School) -> AcademicYear:
    return AcademicYear.objects.create(
        tenant=tenant,
        school=school,
        title="۱۴۰۵–۱۴۰۶",
        starts_on=YEAR_START,
        ends_on=YEAR_END,
        is_default=True,
    )


def make_grade_level(tenant: Tenant, school: School) -> GradeLevel:
    return GradeLevel.objects.create(
        tenant=tenant, school=school, code="G7", title="پایه هفتم", sequence_no=7
    )


def make_person(tenant: Tenant, first: str, last: str, national_id: str) -> Person:
    return Person.objects.create(
        tenant=tenant, first_name=first, last_name=last, national_id=national_id
    )


def make_student(tenant, campus, year, grade, *, index: int) -> Student:
    person = make_person(tenant, "دانش‌آموز", f"شماره{index}", f"1{index:09d}")
    student = Student.objects.create(
        tenant=tenant, person=person, student_no=f"STD-{index:04d}", joined_on=YEAR_START
    )
    Enrollment.objects.create(
        tenant=tenant,
        student=student,
        academic_year=year,
        campus=campus,
        grade_level=grade,
        enrollment_no=f"ENR-{index:04d}",
        enrolled_on=YEAR_START,
        status=EnrollmentStatus.ACTIVE,
    )
    return student


def make_user(
    tenant: Tenant,
    username: str,
    *,
    role_code: str | None = None,
    scope_type: str = ScopeType.SCHOOL,
    scope_id=None,
    person: Person | None = None,
    superuser: bool = False,
) -> UserAccount:
    user = UserAccount.objects.create_user(
        username=username, password=PASSWORD, tenant=tenant, person=person
    )
    if superuser:
        user.is_superuser = True
        user.is_staff = True
        user.save(update_fields=["is_superuser", "is_staff"])
    if role_code:
        UserRoleAssignment.objects.create(
            tenant=tenant,
            user=user,
            role=Role.objects.get(tenant=tenant, code=role_code),
            scope_type=scope_type,
            scope_id=scope_id,
            effective_from=YEAR_START,
        )
    return user


def sync_roles(tenant: Tenant) -> None:
    """کاتالوگ مجوزها و نقش‌های سیستمی همان سازمان."""
    from django.core.management import call_command

    sync_permission_catalog()
    call_command("sync_permissions", tenant_code=tenant.code, verbosity=0)


# ---------------------------------------------------------------------------
# داده حسابداری
# ---------------------------------------------------------------------------
def make_chart_of_accounts(tenant: Tenant, school: School, prefix: str = "") -> dict:
    """کدینگ حداقلی: صندوق، بانک، دریافتنی، پیش‌دریافت، سرمایه، درآمد، هزینه."""
    spec = [
        ("cash", f"{prefix}1101", "صندوق", AccountType.ASSET),
        ("bank", f"{prefix}1102", "بانک", AccountType.ASSET),
        ("receivable", f"{prefix}1201", "حساب‌های دریافتنی", AccountType.ASSET),
        ("prepaid", f"{prefix}2101", "پیش‌دریافت شهریه", AccountType.LIABILITY),
        ("capital", f"{prefix}3101", "سرمایه", AccountType.EQUITY),
        ("revenue", f"{prefix}4101", "درآمد شهریه", AccountType.REVENUE),
        ("expense", f"{prefix}5101", "هزینه حقوق", AccountType.EXPENSE),
    ]
    return {
        key: Account.objects.create(
            tenant=tenant, school=school, code=code, title=title, account_type=kind
        )
        for key, code, title, kind in spec
    }


def make_fiscal_year(tenant: Tenant, school: School, title: str = "۱۴۰۵") -> FiscalYear:
    return FiscalYear.objects.create(
        tenant=tenant, school=school, title=title, starts_on=YEAR_START, ends_on=YEAR_END
    )


def post_entry(
    tenant: Tenant,
    fiscal_year: FiscalYear,
    entry_no: str,
    entry_date: date,
    description: str,
    lines: list[tuple],
    *,
    cost_center: CostCenter | None = None,
    status: str = JournalStatus.POSTED,
) -> JournalEntry:
    """
    سند با خطوط داده‌شده می‌سازد.

    هر خط سه‌تایی «(حساب، بدهکار، بستانکار)» است. عمداً از سرویس
    `create_journal_entry` استفاده نمی‌شود تا بتوان سند پیش‌نویس هم ساخت و
    رفتار گزارش‌ها را در برابر آن سنجید.
    """
    entry = JournalEntry.objects.create(
        tenant=tenant,
        fiscal_year=fiscal_year,
        entry_no=entry_no,
        entry_date=entry_date,
        description=description,
        status=status,
    )
    for index, (account, debit, credit) in enumerate(lines, start=1):
        JournalLine.objects.create(
            tenant=tenant,
            journal_entry=entry,
            account=account,
            cost_center=cost_center,
            debit_amount=debit,
            credit_amount=credit,
            line_no=index,
        )
    return entry


def link_guardian(tenant: Tenant, student: Student, person: Person) -> Guardian:
    guardian = Guardian.objects.create(tenant=tenant, person=person)
    StudentGuardian.objects.create(
        tenant=tenant,
        student=student,
        guardian=guardian,
        relationship_type="FATHER",
        effective_from=YEAR_START,
        receives_reports=True,
        financially_responsible=True,
        contact_priority=1,
    )
    return guardian
