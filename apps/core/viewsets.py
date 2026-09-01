"""
ViewSetهای پایه.

اصول اعمال‌شده (بخش ۱۲.۴ سند تحلیل):
- فیلتر Tenant/Scope در لایه دسترسی داده اجباری است و با Query ورودی دور نمی‌خورد.
- تغییر وضعیت از Endpoint صریح انجام می‌شود، نه `PATCH status`.
- ETag/Version برای جلوگیری از Lost Update.
- حذف عملیاتی، حذف نرم است.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from rest_framework import mixins, viewsets
from rest_framework.response import Response

from apps.core.context import get_current_context
from apps.core.exceptions import ConcurrencyConflict, ScopeViolation


class ScopedQuerysetMixin:
    """
    اعمال خودکار Tenant، محدوده مجاز کاربر و Context کاری روی Queryset.

    سه لایه فیلتر پشت سر هم:

    1. **Tenant** — مرز مالکیت داده.
    2. **محدوده مجاز** از انتساب‌های نقش کاربر (:mod:`apps.identity.scopes`).
       اجباری است و کلاینت راهی برای بازکردنش ندارد.
    3. **Context کاری** از هدرهای `X-School-Id` و مانند آن؛ فقط باریک‌تر
       می‌کند و پیش از رسیدن به اینجا با لایه دوم تطبیق داده شده است.

    بدون لایه دوم، نفرستادن هدر یعنی «هیچ فیلتری» — یعنی معلمِ یک شعبه با یک
    درخواست ساده، داده کل سازمان را می‌گرفت.

    **اعلام مسیرها روی View.** هر بُعد یک فیلد است که مسیر ORM آن مدل تا آن
    بُعد را نگه می‌دارد؛ `None` یعنی این منبع چنین بُعدی ندارد::

        school_field = "campus__school"
        campus_field = "campus"
        self_student_field = "student"   # برای قاعده SELF

    مسیر اعلام‌شده **نباید** از FK اختیاری بگذرد: ``filter(path__in=...)``
    رکوردهایی را که آن FK را خالی دارند بی‌صدا حذف می‌کند و نتیجه‌اش گم‌شدن
    داده است، نه محدودکردن دسترسی.

    **بندِ غیرقابل بیان.** اگر انتساب کاربر روی این منبع قابل ترجمه نباشد
    (مثلاً نقش سطح کلاس روی «فهرست تأمین‌کنندگان» که نه کلاس دارد و نه مدرسه)،
    آن بند محدودیتی اعمال نمی‌کند. سخت‌گیری بیشتر، داده‌ای را پنهان می‌کرد که
    کاربر امروز به‌درستی می‌بیند؛ مسئولیت این منابع با کنترل مجوز است، نه دامنه.
    """

    tenant_field: str | None = "tenant"
    school_field: str | None = None
    campus_field: str | None = None
    academic_year_field: str | None = None
    class_group_field: str | None = None
    course_offering_field: str | None = None

    #: مسیر ORM تا دانش‌آموزِ صاحب رکورد — پایه قاعده SELF برای دانش‌آموز و ولی.
    self_student_field: str | None = None
    #: مسیر ORM تا شخصِ صاحب رکورد، برای منابعی که دانش‌آموز ندارند.
    self_person_field: str | None = None

    #: نگاشت بُعد محدوده به نام فیلد View.
    SCOPE_FIELDS = {
        "schools": "school_field",
        "campuses": "campus_field",
        "academic_years": "academic_year_field",
        "class_groups": "class_group_field",
        "course_offerings": "course_offering_field",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        ctx = get_current_context()
        if ctx is None:
            return queryset.none()

        user = self.request.user
        if user.is_superuser and not ctx.tenant_id:
            return queryset

        if self.tenant_field and ctx.tenant_id:
            queryset = queryset.filter(**{f"{self.tenant_field}_id": ctx.tenant_id})

        queryset = self.apply_effective_scope(queryset, ctx)

        if self.school_field and ctx.school_id:
            queryset = queryset.filter(
                **{self.id_lookup(self.school_field): ctx.school_id}
            )

        if self.campus_field and ctx.campus_id:
            queryset = queryset.filter(
                **{self.id_lookup(self.campus_field): ctx.campus_id}
            )

        if self.academic_year_field and ctx.academic_year_id:
            queryset = queryset.filter(
                **{self.id_lookup(self.academic_year_field): ctx.academic_year_id}
            )

        return queryset

    # -- محدوده مجاز ----------------------------------------------------
    def apply_effective_scope(self, queryset, ctx):
        """بندهای محدوده کاربر را با «یا» ترکیب و روی Queryset اعمال می‌کند."""
        scope = getattr(ctx, "effective_scope", None)
        if scope is None or scope.is_unrestricted:
            return queryset
        if not scope.clauses:
            # کاربر بدون نقش فعال: هیچ داده سازمانی نمی‌بیند.
            return queryset.none()

        combined = Q()
        for clause in scope.clauses:
            condition = self.build_scope_clause(clause, ctx)
            if condition is None:
                # این بند روی این منبع قابل بیان نیست ⇒ بدون محدودیت.
                return queryset
            combined |= condition

        return queryset.filter(combined).distinct()

    @staticmethod
    def id_lookup(path: str, suffix: str = "") -> str:
        """
        مسیر اعلام‌شده را به Lookup روی ستون شناسه تبدیل می‌کند.

        مسیر معمولاً به یک FK اشاره دارد و `_id` می‌گیرد (`campus` →
        `campus_id`). ولی وقتی خودِ منبع همان بُعد است، مسیر `"id"` اعلام
        می‌شود و افزودن پسوند، `id_id` می‌ساخت که فیلدی وجود ندارد.
        """
        base = path if path == "id" or path.endswith("__id") else f"{path}_id"
        return f"{base}{suffix}"

    def build_scope_clause(self, clause, ctx):
        """
        یک بند محدوده را به شرط ORM ترجمه می‌کند.

        خروجی `None` یعنی «روی این منبع قابل بیان نیست».
        """
        if clause.self_only:
            return self.build_self_scope(ctx)

        if clause.dimension:
            path = getattr(self, self.SCOPE_FIELDS[clause.dimension], None)
            if path:
                return Q(**{self.id_lookup(path): clause.value})

        # بُعد باریک روی این منبع وجود ندارد؛ مدرسهٔ ضمنی همان بند را می‌گیریم.
        if clause.school_id and self.school_field:
            return Q(**{self.id_lookup(self.school_field): clause.school_id})

        return None

    def build_self_scope(self, ctx):
        """
        شرط قاعده SELF: فقط رکوردهای خودِ کاربر یا فرزندان تحت سرپرستی او.

        منبعی که هیچ‌یک از دو مسیر را اعلام نکرده باشد `None` برمی‌گرداند و
        محدود نمی‌شود؛ برای آن منابع باید مجوز نقش (`permission_resource`)
        دسترسی را ببندد.
        """
        from apps.identity.scopes import visible_student_ids

        person_id = getattr(self.request.user, "person_id", None)

        if self.self_student_field:
            return Q(
                **{
                    self.id_lookup(self.self_student_field, "__in"): visible_student_ids(
                        person_id
                    )
                }
            )
        if self.self_person_field:
            ids = {person_id} if person_id else set()
            return Q(**{self.id_lookup(self.self_person_field, "__in"): ids})
        return None


class OptimisticConcurrencyMixin:
    """
    کنترل هم‌زمانی خوش‌بینانه با هدر `If-Match` و فیلد `version`.

    اگر هدر ارسال شود و با نسخه فعلی رکورد نخواند، پاسخ 409 با کد
    `VERSION_CONFLICT` برمی‌گردد.
    """

    def check_version(self, instance) -> None:
        raw = self.request.META.get("HTTP_IF_MATCH", "").strip().strip('"')
        if not raw:
            return
        current = getattr(instance, "version", None)
        if current is None:
            return
        try:
            expected = int(raw)
        except ValueError:
            raise ConcurrencyConflict(expected=raw, actual=current)
        if expected != current:
            raise ConcurrencyConflict(expected=expected, actual=current)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        self.check_version(instance)
        return super().update(request, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        data = getattr(response, "data", None)
        if isinstance(data, dict) and "version" in data:
            response["ETag"] = f'"{data["version"]}"'
        return response


class TenantCreateMixin:
    """هنگام ایجاد، Tenant را از Context می‌گیرد نه از بدنه درخواست."""

    def perform_create(self, serializer):
        ctx = get_current_context()
        extra = {}
        model = serializer.Meta.model
        field_names = {f.name for f in model._meta.get_fields() if hasattr(f, "name")}

        if "tenant" in field_names and ctx and ctx.tenant_id:
            extra["tenant_id"] = ctx.tenant_id
        serializer.save(**extra)


class SoftDeleteMixin:
    """حذف = حذف نرم با ثبت علت از پارامتر `reason`."""

    def perform_destroy(self, instance):
        reason = self.request.query_params.get("reason", "")
        if hasattr(instance, "delete") and hasattr(instance, "deleted_at"):
            instance.delete(reason=reason)
        else:  # pragma: no cover
            instance.delete()


class BaseModelViewSet(
    ScopedQuerysetMixin,
    OptimisticConcurrencyMixin,
    TenantCreateMixin,
    SoftDeleteMixin,
    viewsets.ModelViewSet,
):
    """ViewSet استاندارد منابع عملیاتی سامانه."""

    lookup_field = "pk"

    def check_object_scope(self, request, obj) -> bool:
        """قابل بازنویسی در Viewهای دارای قاعده SELF یا Scope خاص."""
        return True


class BaseReadOnlyViewSet(
    ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet
):
    """منابع فقط‌خواندنی: نماهای گزارشی و داده مرجع."""


class TransitionMixin:
    """
    کمکی برای Endpointهای تغییر وضعیت (بخش ۱۰ سند تحلیل).

    نمونه استفاده در ViewSet:

        @action(detail=True, methods=["post"], url_path="submit")
        def submit(self, request, pk=None):
            return self.apply_transition("submit")
    """

    #: نگاشت اکشن → (وضعیت‌های مجاز مبدأ، وضعیت مقصد)
    transitions: dict[str, tuple[tuple[str, ...], str]] = {}
    status_field = "status"

    @transaction.atomic
    def apply_transition(
        self,
        action_name: str,
        *,
        serializer_class=None,
        on_success=None,
    ) -> Response:
        from apps.core.exceptions import InvalidStateTransition

        instance = self.get_object()
        allowed_from, target = self.transitions[action_name]
        current = getattr(instance, self.status_field)

        if current not in allowed_from:
            raise InvalidStateTransition(
                entity=instance._meta.verbose_name,
                current=current,
                action=action_name,
            )

        payload = {}
        if serializer_class is not None:
            body = serializer_class(data=self.request.data)
            body.is_valid(raise_exception=True)
            payload = body.validated_data

        setattr(instance, self.status_field, target)
        instance.save()

        if callable(on_success):
            on_success(instance, payload)

        output = self.get_serializer(instance)
        return Response(output.data)


class BulkPreviewMixin:
    """
    عملیات گروهی دو مرحله‌ای (بخش ۱۱.۶):
    ابتدا پیش‌نمایش/اعتبارسنجی، سپس Commit.
    """

    def build_preview(self, validated_rows: list[dict]) -> dict:
        return {
            "totalRows": len(validated_rows),
            "validRows": sum(1 for row in validated_rows if not row.get("errors")),
            "invalidRows": sum(1 for row in validated_rows if row.get("errors")),
            "rows": validated_rows,
        }


def ensure_in_scope(obj, *, ctx=None) -> None:
    """کنترل صریح Tenant برای اشیائی که از مسیر get_object نمی‌آیند."""
    ctx = ctx or get_current_context()
    if ctx is None or ctx.is_superuser:
        return
    obj_tenant_id = getattr(obj, "tenant_id", None)
    if obj_tenant_id and ctx.tenant_id and obj_tenant_id != ctx.tenant_id:
        raise ScopeViolation()


class ReadOnlyMixinSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """ترکیب سبک فهرست/جزئیات برای نماهای مشتق‌شده."""
