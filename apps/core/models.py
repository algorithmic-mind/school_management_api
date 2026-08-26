"""
مدل‌های پایه و مشترک همه ماژول‌ها.

مرجع: بخش ۵.۱ سند تحلیل — «قواعد عمومی شناسه و تاریخچه»
- کلید داخلی همه موجودیت‌ها UUID است.
- هر جدول عملیاتی created_at/created_by/updated_at/updated_by/version دارد.
- version برای کنترل هم‌زمانی خوش‌بینانه است.
- داده قابل غیرفعال‌سازی status یا archived_at دارد؛ deleted_at فقط حذف نرم.
- جدول‌های تاریخچه effective_from/effective_to دارند.
- هر رکورد به tenant وابسته است.
"""

from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.context import get_current_user_id


class RecordStatus(models.TextChoices):
    """وضعیت عمومی رکوردهای مرجع."""

    DRAFT = "DRAFT", _("پیش‌نویس")
    ACTIVE = "ACTIVE", _("فعال")
    INACTIVE = "INACTIVE", _("غیرفعال")
    ARCHIVED = "ARCHIVED", _("بایگانی‌شده")


class UUIDModel(models.Model):
    """کلید اصلی UUID برای همه موجودیت‌ها."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name=_("شناسه"),
    )

    class Meta:
        abstract = True


class AuditableModel(models.Model):
    """ردپای ایجاد/ویرایش و شماره نسخه برای کنترل هم‌زمانی خوش‌بینانه."""

    created_at = models.DateTimeField(
        auto_now_add=True, db_index=True, verbose_name=_("زمان ایجاد")
    )
    created_by_id = models.UUIDField(
        null=True, blank=True, editable=False, verbose_name=_("ایجادکننده")
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("زمان ویرایش"))
    updated_by_id = models.UUIDField(
        null=True, blank=True, editable=False, verbose_name=_("ویرایش‌کننده")
    )
    version = models.PositiveIntegerField(default=1, verbose_name=_("نسخه رکورد"))

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        actor_id = get_current_user_id()
        if self._state.adding:
            if actor_id and not self.created_by_id:
                self.created_by_id = actor_id
        else:
            # هر ویرایش، نسخه را یک واحد جلو می‌برد (If-Match / ETag)
            self.version = (self.version or 0) + 1
        if actor_id:
            self.updated_by_id = actor_id
        return super().save(*args, **kwargs)


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)

    def delete(self):
        """حذف نرم گروهی."""
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class SoftDeleteManager(models.Manager):
    """پیش‌فرض فقط رکوردهای حذف‌نشده را برمی‌گرداند."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(
            deleted_at__isnull=True
        )

    def with_deleted(self):
        return SoftDeleteQuerySet(self.model, using=self._db)


class SoftDeleteModel(models.Model):
    """
    حذف نرم.

    طبق بخش ۱ سند: «حذف» در داده‌های عملیاتی به‌صورت غیرفعال‌سازی یا حذف نرم
    انجام می‌شود؛ اسناد مالی قطعی و سوابق ممیزی حذف فیزیکی ندارند.
    """

    deleted_at = models.DateTimeField(
        null=True, blank=True, db_index=True, verbose_name=_("زمان حذف نرم")
    )
    deleted_by_id = models.UUIDField(null=True, blank=True, editable=False)
    delete_reason = models.CharField(
        max_length=300, blank=True, verbose_name=_("علت حذف")
    )

    objects = SoftDeleteManager()
    all_objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, reason: str = ""):
        self.deleted_at = timezone.now()
        self.deleted_by_id = get_current_user_id()
        self.delete_reason = reason
        self.save(update_fields=["deleted_at", "deleted_by_id", "delete_reason"])

    def restore(self):
        self.deleted_at = None
        self.deleted_by_id = None
        self.delete_reason = ""
        self.save(update_fields=["deleted_at", "deleted_by_id", "delete_reason"])

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)


class EffectiveDatedModel(models.Model):
    """
    بازه اعتبار برای انتساب‌های زمان‌مند.

    بخش ۵.۱: بازه‌های هم‌پوشان برای یک انتساب ممنوع است.
    """

    effective_from = models.DateField(db_index=True, verbose_name=_("معتبر از"))
    effective_to = models.DateField(
        null=True, blank=True, db_index=True, verbose_name=_("معتبر تا")
    )

    class Meta:
        abstract = True

    @property
    def is_currently_effective(self) -> bool:
        today = timezone.localdate()
        if self.effective_from and self.effective_from > today:
            return False
        if self.effective_to and self.effective_to < today:
            return False
        return True


class Tenant(UUIDModel, AuditableModel):
    """
    مستأجر/سازمان — مرز مالکیت و جداسازی داده (بخش ۵ واژگان).
    """

    name = models.CharField(max_length=200, verbose_name=_("نام سازمان"))
    code = models.SlugField(max_length=60, unique=True, verbose_name=_("کد یکتا"))
    status = models.CharField(
        max_length=20, choices=RecordStatus.choices, default=RecordStatus.ACTIVE
    )
    default_currency = models.CharField(
        max_length=3, default="IRR", verbose_name=_("واحد پول پیش‌فرض")
    )
    default_timezone = models.CharField(max_length=64, default="Asia/Tehran")

    class Meta:
        verbose_name = _("سازمان")
        verbose_name_plural = _("سازمان‌ها")
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class TenantOwnedModel(models.Model):
    """هر رکورد عملیاتی به یک Tenant وابسته است (بخش ۵.۱)."""

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_set",
        db_index=True,
        verbose_name=_("سازمان"),
    )

    class Meta:
        abstract = True


class BaseModel(UUIDModel, AuditableModel, SoftDeleteModel):
    """پایه استاندارد موجودیت‌های عملیاتی غیر مالی."""

    class Meta:
        abstract = True


class BaseTenantModel(UUIDModel, TenantOwnedModel, AuditableModel, SoftDeleteModel):
    """پایه استاندارد موجودیت‌های عملیاتی وابسته به سازمان."""

    class Meta:
        abstract = True


class ImmutableLedgerModel(UUIDModel, TenantOwnedModel, AuditableModel):
    """
    پایه اسناد قطعی مالی/انبار: بدون حذف نرم و بدون حذف فیزیکی.

    بخش ۷.۸ و ۷.۹: سند Posted ویرایش یا حذف نمی‌شود؛ اصلاح با سند معکوس است.
    """

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):  # pragma: no cover - محافظ
        raise NotImplementedError(
            "اسناد قطعی حذف نمی‌شوند؛ برای اصلاح از سند برگشتی استفاده کنید."
        )
