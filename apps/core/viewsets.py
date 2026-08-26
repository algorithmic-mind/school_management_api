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
from rest_framework import mixins, viewsets
from rest_framework.response import Response

from apps.core.context import get_current_context
from apps.core.exceptions import ConcurrencyConflict, ScopeViolation


class ScopedQuerysetMixin:
    """
    اعمال خودکار Tenant و Context کاری روی Queryset.

    فیلدهای اختیاری روی View:
        tenant_field = "tenant"          مسیر ORM تا Tenant
        school_field = "school"          مسیر ORM تا مدرسه
        campus_field = "campus"          مسیر ORM تا شعبه
        academic_year_field = "academic_year"
    مقدار `None` یعنی این بُعد روی مدل وجود ندارد و فیلتر نمی‌شود.
    """

    tenant_field: str | None = "tenant"
    school_field: str | None = None
    campus_field: str | None = None
    academic_year_field: str | None = None

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

        if self.school_field and ctx.school_id:
            queryset = queryset.filter(**{f"{self.school_field}_id": ctx.school_id})

        if self.campus_field and ctx.campus_id:
            queryset = queryset.filter(**{f"{self.campus_field}_id": ctx.campus_id})

        if self.academic_year_field and ctx.academic_year_id:
            queryset = queryset.filter(
                **{f"{self.academic_year_field}_id": ctx.academic_year_id}
            )

        return queryset


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
