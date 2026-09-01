"""
کنترل دسترسی RBAC + Scope.

بخش ۳.۲ سند تحلیل:
- Role: مجموعه مجوزها
- Permission: عمل دقیق روی منبع، مانند `student.read`
- Scope: محدوده اعمال نقش (سازمان، مدرسه، شعبه، سال، کلاس، درس، خودِ رکورد)
- Policy: شرط پویا
- Segregation of Duties: ایجادکننده سند نباید تأییدکننده همان سند باشد.

بخش ۱۵.۱: «کنترل دسترسی شیء و فیلد؛ جلوگیری از IDOR با بررسی Scope روی هر
درخواست.»
"""

from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.core.context import get_current_context

# نگاشت متد HTTP به عمل مجوز
METHOD_ACTION_MAP = {
    "GET": "read",
    "HEAD": "read",
    "OPTIONS": "read",
    "POST": "create",
    "PUT": "update",
    "PATCH": "update",
    "DELETE": "delete",
}


class ScopeType:
    """انواع دامنه دسترسی (بخش ۳.۲)."""

    TENANT = "TENANT"
    SCHOOL = "SCHOOL"
    CAMPUS = "CAMPUS"
    ACADEMIC_YEAR = "ACADEMIC_YEAR"
    CLASS_GROUP = "CLASS_GROUP"
    COURSE_OFFERING = "COURSE_OFFERING"
    SELF = "SELF"

    CHOICES = [
        (TENANT, "کل سازمان"),
        (SCHOOL, "مدرسه"),
        (CAMPUS, "شعبه"),
        (ACADEMIC_YEAR, "سال تحصیلی"),
        (CLASS_GROUP, "کلاس"),
        (COURSE_OFFERING, "ارائه درس"),
        (SELF, "فقط رکوردهای خود"),
    ]


def hydrate_context_from_user(request) -> None:
    """
    مجوزها، Scopeها و محدوده مؤثر کاربر را در Context جاری می‌نشاند.

    میان‌افزار فقط هدرها را می‌خواند؛ کاربر هنوز شناخته نشده است، چون احراز
    هویت DRF بعد از میان‌افزار اجرا می‌شود. پس تکمیل Context اینجا انجام
    می‌گیرد و از لایه احراز هویت صدا زده می‌شود
    (:mod:`apps.identity.authentication`) تا **هر** درخواست احرازشده — حتی
    Viewهایی که `permission_classes` خودشان را جایگزین کرده‌اند — Context
    کامل داشته باشد.

    این تابع بی‌اثرِ تکرار است: بار دوم چیزی را دوباره محاسبه نمی‌کند.
    """
    ctx = get_current_context()
    if ctx is None:
        return

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return

    ctx.user_id = user.id
    ctx.is_superuser = bool(user.is_superuser)
    ctx.tenant_id = getattr(user, "tenant_id", None)

    if not ctx.permissions:
        ctx.permissions = user.get_effective_permission_codes()
    if not ctx.scopes:
        ctx.scopes = user.get_effective_scopes()
    if ctx.effective_scope is None:
        from apps.identity.scopes import build_effective_scope

        ctx.effective_scope = build_effective_scope(
            ctx.scopes, is_superuser=ctx.is_superuser
        )
        _narrow_context_to_scope(ctx)


def _narrow_context_to_scope(ctx) -> None:
    """
    هدرهای Context را با محدوده مجاز کاربر تطبیق می‌دهد.

    هدر فقط اجازه دارد محدوده را **باریک‌تر** کند. اگر کلاینت شناسه‌ای بیرون
    از محدوده مجاز بفرستد، به‌جای خطا نادیده گرفته می‌شود و فیلتر روی محدوده
    مجاز خودِ کاربر می‌ماند؛ نتیجه‌اش «داده‌ای نیست» است، نه افشای داده.
    خطاندادن عمدی است: پاسخ ۴۰۳ به شناسه معتبرِ خارج از دسترس، خودش وجود آن
    مدرسه/شعبه را تأیید می‌کند.
    """
    scope = ctx.effective_scope
    if scope is None or scope.is_unrestricted:
        return

    for dimension, attribute in (
        ("schools", "school_id"),
        ("campuses", "campus_id"),
        ("academic_years", "academic_year_id"),
    ):
        requested = getattr(ctx, attribute, None)
        if requested is not None and not scope.allows(dimension, requested):
            setattr(ctx, attribute, None)


class ScopedRBACPermission(BasePermission):
    """
    مجوز پیش‌فرض همه Viewها.

    View می‌تواند با یکی از راه‌های زیر منبع مجوز را اعلام کند:

    1. `permission_resource = "student"` → کد مجوز از متد HTTP ساخته می‌شود:
       GET → `student.read`, POST → `student.create`, ...
    2. `permission_map = {"publish": "grade.publish"}` برای اکشن‌های سفارشی.
    3. `required_permissions = ["student.read"]` برای کد ثابت.

    Viewهای عمومی با `permission_classes = [AllowAny]` از این کلاس عبور می‌کنند.
    """

    message = "شما مجوز لازم برای این عملیات را ندارید."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        hydrate_context_from_user(request)

        if user.is_superuser:
            return True

        required = self.get_required_permissions(request, view)
        if not required:
            # منبعی اعلام نشده: فقط احراز هویت کافی است.
            return True

        ctx = get_current_context()
        granted = ctx.permissions if ctx else set()
        return any(code in granted for code in required)

    def has_object_permission(self, request, view, obj) -> bool:
        user = request.user
        if user.is_superuser:
            return True

        ctx = get_current_context()
        if ctx is None:
            return False

        # جداسازی Tenant — پایه جلوگیری از IDOR
        obj_tenant_id = getattr(obj, "tenant_id", None)
        if obj_tenant_id and ctx.tenant_id and obj_tenant_id != ctx.tenant_id:
            return False

        # قاعده SELF: کاربر فقط به رکوردهای خودش دسترسی دارد.
        checker = getattr(view, "check_object_scope", None)
        if callable(checker):
            return bool(checker(request, obj))

        return True

    # ------------------------------------------------------------------
    @staticmethod
    def get_required_permissions(request, view) -> list[str]:
        explicit = getattr(view, "required_permissions", None)
        if explicit:
            return list(explicit)

        action = getattr(view, "action", None)
        permission_map = getattr(view, "permission_map", None) or {}
        if action and action in permission_map:
            value = permission_map[action]
            return [value] if isinstance(value, str) else list(value)

        resource = getattr(view, "permission_resource", None)
        if not resource:
            return []

        verb = METHOD_ACTION_MAP.get(request.method, "read")
        # اکشن‌های سفارشی ViewSet که در permission_map نیامده‌اند
        if action and action not in {
            "list", "retrieve", "create", "update", "partial_update", "destroy"
        }:
            return [f"{resource}.{action}", f"{resource}.{verb}"]
        return [f"{resource}.{verb}"]


class ReadOnly(BasePermission):
    """فقط متدهای امن مجازند — برای نقش ناظر/بازرس (بخش ۳.۱)."""

    def has_permission(self, request, view) -> bool:
        return request.method in SAFE_METHODS


class IsSelfOrHasPermission(BasePermission):
    """
    دسترسی به رکورد خودِ کاربر بدون نیاز به مجوز سازمانی.

    مورد استفاده: دانش‌آموز فقط پرونده خودش، ولی فقط فرزند مجاز
    (بخش ۳.۳ ماتریس دسترسی).
    """

    owner_field = "person_id"

    def has_object_permission(self, request, view, obj) -> bool:
        user = request.user
        if user.is_superuser:
            return True
        owner_field = getattr(view, "owner_field", self.owner_field)
        owner_id = getattr(obj, owner_field, None)
        return bool(owner_id and user.person_id and owner_id == user.person_id)
