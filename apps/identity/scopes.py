"""
تبدیل انتساب‌های نقش به محدوده مؤثر داده.

بخش ۱۲.۴ سند تحلیل: «فیلتر Tenant/Scope در لایه Repository اجباری و قابل
دورزدن توسط Query ورودی نیست.» بخش ۱۵.۱: «کنترل دسترسی شیء و فیلد؛ جلوگیری
از IDOR با بررسی Scope روی هر درخواست.»

مسئله‌ای که این ماژول حل می‌کند: هدرهای `X-School-Id` / `X-Campus-Id` /
`X-Academic-Year-Id` را خودِ کلاینت می‌فرستد. اگر بدون کنترل پذیرفته شوند،
کاربرِ محدود به یک شعبه می‌تواند با عوض‌کردن هدر داده شعبه دیگر را ببیند؛ و
اگر هدر را اصلاً نفرستد، هیچ فیلتری اعمال نمی‌شود و کل سازمان را می‌بیند.

**مدل محاسبه.** هر انتساب نقش یک «بند» (:class:`ScopeClause`) می‌سازد و
بندها با **یای منطقی** ترکیب می‌شوند، نه «و». دلیلش ساده است: کسی که هم
حسابدار مدرسه است و هم معلم یک کلاس، باید مجموع هر دو را ببیند، نه اشتراک
آن‌ها را. اشتراک‌گرفتن، کاربر چندنقشی را عملاً از کار می‌انداخت.

**قرارداد شناسه خالی.** انتساب بدون `scope_id` یعنی «همان نوع دامنه، در کل
سازمان». نقش «حسابدار» با `scope_type=SCHOOL` و `scope_id=None` یعنی حسابدارِ
همه مدارس سازمان. برای محدودکردن به یک مدرسه باید `scope_id` پر شود.

**مدرسهٔ ضمنی.** هر بند، مدرسه‌اش را هم حمل می‌کند: شعبه، سال تحصیلی، کلاس و
ارائه درس همگی به یک مدرسه می‌رسند. اگر منبعی بُعد باریک بند را نداشته باشد
(مثلاً «کدینگ حساب» شعبه ندارد)، همین مدرسهٔ ضمنی برای محدودسازی به کار
می‌رود — وگرنه کاربرِ یک شعبه، کدینگ حساب همه مدارس را می‌دید.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from apps.core.permissions import ScopeType

#: نگاشت نوع دامنه به بُعدی که در Queryset محدود می‌کند.
SCOPE_DIMENSION = {
    ScopeType.SCHOOL: "schools",
    ScopeType.CAMPUS: "campuses",
    ScopeType.ACADEMIC_YEAR: "academic_years",
    ScopeType.CLASS_GROUP: "class_groups",
    ScopeType.COURSE_OFFERING: "course_offerings",
}

#: همه ابعادی که Queryset می‌تواند روی آن‌ها فیلتر کند.
DIMENSIONS = tuple(SCOPE_DIMENSION.values())


@dataclass(frozen=True)
class ScopeClause:
    """
    یک انتساب نقش، ترجمه‌شده به شرط داده.

    - `dimension` خالی و `self_only` نادرست ⇒ بند بدون محدودیت (کل سازمان).
    - `self_only` درست ⇒ فقط رکوردهای مرتبط با خودِ کاربر یا فرزندانش.
    - `school_id` مدرسهٔ ضمنیِ همین بند است، برای منابعی که بُعد باریک‌تر ندارند.
    """

    dimension: str | None = None
    value: uuid.UUID | None = None
    school_id: uuid.UUID | None = None
    self_only: bool = False

    @property
    def is_unrestricted(self) -> bool:
        return self.dimension is None and not self.self_only


@dataclass
class EffectiveScope:
    """محدوده مؤثر یک کاربر: مجموعه‌ای از بندها که با «یا» ترکیب می‌شوند."""

    clauses: list[ScopeClause] = field(default_factory=list)
    is_unrestricted: bool = False
    self_only: bool = False

    def dimension(self, name: str) -> set[uuid.UUID] | None:
        """
        مقادیر مجاز یک بُعد، یا `None` اگر آن بُعد محدود نشده باشد.

        `None` یعنی «این بُعد آزاد است» و مجموعه خالی یعنی «هیچ مقداری مجاز
        نیست». تفاوتشان مهم است: دومی باید نتیجه را تهی کند.
        """
        if self.is_unrestricted:
            return None
        values: set[uuid.UUID] = set()
        for clause in self.clauses:
            if clause.is_unrestricted:
                return None
            if clause.dimension == name and clause.value is not None:
                values.add(clause.value)
            elif name == "schools" and clause.school_id is not None:
                values.add(clause.school_id)
        return values

    def allows(self, name: str, value) -> bool:
        """آیا شناسه داده‌شده در بُعد مشخص مجاز است."""
        allowed = self.dimension(name)
        return True if allowed is None else value in allowed


def _implied_school(scope_type: str, scope_id) -> uuid.UUID | None:
    """
    مدرسهٔ متناظر با یک دامنه.

    برای دامنه‌های زیرِ مدرسه یک Query لازم است. تعداد انتساب‌های فعال هر کاربر
    کم است (معمولاً یک تا سه)، پس این هزینه ناچیز و فقط یک‌بار در هر درخواست
    است.
    """
    if scope_id is None:
        return None
    if scope_type == ScopeType.SCHOOL:
        return scope_id

    from apps.organization.models import AcademicYear, Campus, ClassGroup, CourseOffering

    lookup = {
        ScopeType.CAMPUS: (Campus, "school_id"),
        ScopeType.ACADEMIC_YEAR: (AcademicYear, "school_id"),
        ScopeType.CLASS_GROUP: (ClassGroup, "campus__school_id"),
        ScopeType.COURSE_OFFERING: (CourseOffering, "course__school_id"),
    }
    entry = lookup.get(scope_type)
    if entry is None:
        return None
    model, path = entry
    return model.objects.filter(pk=scope_id).values_list(path, flat=True).first()


def build_effective_scope(
    scopes: list[dict], *, is_superuser: bool = False
) -> EffectiveScope:
    """
    محدوده مؤثر را از فهرست انتساب‌های نقش می‌سازد.

    ورودی همان خروجی `UserAccount.get_effective_scopes()` است: دیکشنری‌هایی با
    کلیدهای `scope_type` و `scope_id`.
    """
    if is_superuser:
        return EffectiveScope(is_unrestricted=True)

    if not scopes:
        # کاربر بدون هیچ نقش فعالی: هیچ داده سازمانی نمی‌بیند.
        return EffectiveScope(clauses=[])

    clauses: list[ScopeClause] = []
    for assignment in scopes:
        scope_type = assignment.get("scope_type")
        scope_id = assignment.get("scope_id")

        if scope_type == ScopeType.TENANT:
            return EffectiveScope(is_unrestricted=True)

        if scope_type == ScopeType.SELF:
            clauses.append(ScopeClause(self_only=True))
            continue

        dimension = SCOPE_DIMENSION.get(scope_type)
        if dimension is None or scope_id is None:
            # نوع ناشناخته یا انتساب بدون شناسه = همان نقش در کل سازمان.
            clauses.append(ScopeClause())
            continue

        clauses.append(
            ScopeClause(
                dimension=dimension,
                value=scope_id,
                school_id=_implied_school(scope_type, scope_id),
            )
        )

    scope = EffectiveScope(clauses=clauses)
    scope.is_unrestricted = any(clause.is_unrestricted for clause in clauses)
    # «فقط رکوردهای خود» تنها وقتی حاکم است که هیچ نقش سازمانی دیگری نباشد.
    scope.self_only = bool(clauses) and all(clause.self_only for clause in clauses)
    return scope


def visible_student_ids(person_id) -> set[uuid.UUID]:
    """
    دانش‌آموزانی که یک شخص حق دیدن پرونده‌شان را دارد.

    یعنی خودش (اگر دانش‌آموز باشد) و فرزندانی که به‌عنوان ولی، گزارش آن‌ها را
    دریافت می‌کند (بخش ۳.۳ ماتریس دسترسی). مجموعه خالی یعنی هیچ‌کس — که در
    لایه Queryset به «نتیجه تهی» ترجمه می‌شود، نه «همه».
    """
    if not person_id:
        return set()

    from apps.students.models import Student, StudentGuardian

    own = set(
        Student.objects.filter(person_id=person_id).values_list("id", flat=True)
    )
    children = set(
        StudentGuardian.objects.filter(
            guardian__person_id=person_id, receives_reports=True
        ).values_list("student_id", flat=True)
    )
    return own | children
