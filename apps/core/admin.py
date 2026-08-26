"""
زیرساخت مشترک پنل مدیریت.

**مسئله.** سامانه ۱۴۵ موجودیت دارد. نوشتن دستی `ModelAdmin` برای هرکدام یعنی
هزار سطر پیکربندی تکراری که با افزوده‌شدن هر مدل تازه از قلم می‌افتد؛ نتیجه‌اش
پنلی است که در آن ۹۷ موجودیت فقط یک ستون بی‌نام دارند، جست‌وجو ندارند و
کلیدهای خارجی‌شان با `select` هزارتایی رندر می‌شود.

**راه‌حل.** :func:`register_auto` پیکربندی را از خودِ مدل مشتق می‌کند:
`verbose_name` فیلدها، نوع فیلد و وجود `choices` تعیین می‌کند چه چیزی ستون
فهرست، چه چیزی فیلتر و چه چیزی فیلد جست‌وجو شود.

`ModelAdmin` دست‌نویس همیشه مقدم است؛ این ماژول فقط جای خالی را پر می‌کند —
همان الگوی `apps/core/field_labels.py` برای برچسب فیلدها.
"""

from __future__ import annotations

from django.contrib import admin, messages
from django.db import models

from apps.core.models import ImmutableLedgerModel, Tenant

# ---------------------------------------------------------------------------
# دسته‌بندی فیلدها
# ---------------------------------------------------------------------------
#: فیلدهای ردپا؛ در فرم به بخش جمع‌شونده «اطلاعات ممیزی» منتقل می‌شوند.
AUDIT_FIELDS = (
    "created_at",
    "created_by_id",
    "updated_at",
    "updated_by_id",
    "version",
    "deleted_at",
    "deleted_by_id",
    "delete_reason",
)

#: نام‌هایی که معمولاً معرّف رکوردند — به‌ترتیب اولویت برای ستون اول فهرست.
_IDENTIFYING_NAMES = (
    "title",
    "name",
    "full_name",
    "code",
    "label",
    "subject",
    "username",
    "body",
)

#: فیلدهایی که در فهرست ارزش ستون‌شدن ندارند.
_LIST_EXCLUDED = frozenset(AUDIT_FIELDS) | {"id", "tenant"}

_LONG_TEXT_MAX_LENGTH = 200

MAX_LIST_DISPLAY = 7
MAX_LIST_FILTER = 5
MAX_SEARCH_FIELDS = 5


def _concrete_fields(model) -> list:
    return [f for f in model._meta.get_fields() if isinstance(f, models.Field)]


def _is_short_text(field) -> bool:
    return (
        isinstance(field, models.CharField)
        and not field.choices
        and (field.max_length or 0) <= _LONG_TEXT_MAX_LENGTH
    )


def _is_listable(field) -> bool:
    """آیا فیلد به‌درستی در یک ستون فهرست جا می‌شود؟"""
    if field.name in _LIST_EXCLUDED or field.primary_key:
        return False
    return not isinstance(
        field,
        (
            models.ManyToManyField,
            models.TextField,
            models.JSONField,
            models.FileField,
            models.BinaryField,
        ),
    )


def derive_list_display(model) -> tuple[str, ...]:
    """
    ستون‌های فهرست: معرّف رکورد، سپس مالک، وضعیت، تاریخ و در پایان زمان ایجاد.

    ترتیب عمداً ثابت است تا فهرست همه ماژول‌ها یک‌شکل خوانده شود.
    """
    fields = {f.name: f for f in _concrete_fields(model) if _is_listable(f)}
    picked: list[str] = []

    def take(name: str) -> None:
        if name in fields and name not in picked and len(picked) < MAX_LIST_DISPLAY:
            picked.append(name)

    for name in _IDENTIFYING_NAMES:
        if len(picked) >= 2:
            break
        take(name)

    # شماره‌ها و کدهای شناسایی: student_no، invoice_no، asset_tag …
    for name, field in fields.items():
        if len(picked) >= 3:
            break
        if _is_short_text(field) and name.endswith(("_no", "_code", "_tag", "_sku")):
            take(name)

    for name, field in fields.items():  # مالک/والد
        if len(picked) >= 5:
            break
        if isinstance(field, models.ForeignKey):
            take(name)

    for name, field in fields.items():  # وضعیت و نوع
        if field.choices:
            take(name)

    for name, field in fields.items():  # یک تاریخ معنادار
        if isinstance(field, (models.DateField, models.DateTimeField)):
            take(name)
            break

    for name, field in fields.items():
        if isinstance(field, models.BooleanField):
            take(name)
            break

    if "created_at" in {f.name for f in _concrete_fields(model)}:
        take("created_at")

    return tuple(picked) or ("__str__",)


def derive_list_filter(model) -> tuple[str, ...]:
    """
    فیلتر فقط روی فیلدهای با دامنه محدود.

    کلید خارجی عمداً کنار گذاشته شده: فیلتر روی آن، یک `select` با همه رکوردهای
    جدول مقصد می‌سازد که روی داده واقعی هم کند است و هم بی‌استفاده.
    """
    picked: list[str] = []
    for field in _concrete_fields(model):
        if len(picked) >= MAX_LIST_FILTER:
            break
        if field.name in AUDIT_FIELDS:
            continue
        if field.choices or isinstance(field, models.BooleanField):
            picked.append(field.name)
    return tuple(picked)


def derive_search_fields(model) -> tuple[str, ...]:
    """فیلدهای متنی کوتاهی که کاربر واقعاً با آن‌ها دنبال رکورد می‌گردد."""
    fields = {f.name: f for f in _concrete_fields(model)}
    picked: list[str] = []

    def take(name: str) -> None:
        if name in fields and name not in picked and len(picked) < MAX_SEARCH_FIELDS:
            if _is_short_text(fields[name]):
                picked.append(name)

    for name in _IDENTIFYING_NAMES:
        take(name)
    for name in ("first_name", "last_name", "national_id"):
        take(name)
    for name, field in fields.items():
        if len(picked) >= MAX_SEARCH_FIELDS:
            break
        if _is_short_text(field) and name.endswith(("_no", "_code", "_tag", "_sku")):
            take(name)

    return tuple(picked)


def _split_relations(model) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """
    کلیدهای خارجی را بین «جست‌وجوی خودکار» و «انتخاب با شناسه» تقسیم می‌کند.

    اگر مدل مقصد فیلد متنی قابل جست‌وجو داشته باشد، `autocomplete` تجربه بهتری
    می‌دهد؛ در غیر این صورت تنها گزینه امن `raw_id` است، چون autocomplete بدون
    `search_fields` روی مدل مقصد خطای `admin.E040` می‌دهد.
    """
    autocomplete: list[str] = []
    raw_id: list[str] = []
    for field in model._meta.get_fields():
        if not isinstance(field, (models.ForeignKey, models.ManyToManyField)):
            continue
        if getattr(field.remote_field, "parent_link", False):
            continue  # پیوند ارث‌بری چندجدولی، فیلد قابل ویرایش نیست
        if _is_through_m2m(field):
            continue
        target = field.remote_field.model
        if derive_search_fields(target):
            autocomplete.append(field.name)
        else:
            raw_id.append(field.name)
    return tuple(autocomplete), tuple(raw_id)


def _has_field(model, name: str) -> bool:
    return any(f.name == name for f in _concrete_fields(model))


def _is_through_m2m(field) -> bool:
    """
    رابطه چندبه‌چند با مدل واسط صریح.

    جنگو چنین فیلدی را نه در فرم می‌پذیرد و نه در `autocomplete_fields`؛ خودِ
    مدل واسط جداگانه ثبت می‌شود و ویرایش از آنجا انجام می‌گیرد.
    """
    if not isinstance(field, models.ManyToManyField):
        return False
    through = field.remote_field.through
    return through is not None and not through._meta.auto_created


# ---------------------------------------------------------------------------
# فیلتر و اکشن حذف نرم
# ---------------------------------------------------------------------------
class SoftDeleteFilter(admin.SimpleListFilter):
    """
    حذف نرم را در پنل قابل مشاهده می‌کند.

    مدیر پنل باید بتواند رکورد حذف‌شده را ببیند و برگرداند؛ Manager پیش‌فرض مدل
    آن را پنهان می‌کند، پس فیلتر روی `all_objects` کار می‌کند و حالت پیش‌فرض
    همچنان «فقط فعال» است.
    """

    title = "وضعیت حذف"
    parameter_name = "deleted"

    def lookups(self, request, model_admin):
        return (("0", "فقط فعال"), ("1", "فقط حذف‌شده"), ("all", "همه"))

    def queryset(self, request, queryset):
        value = self.value()
        if value == "1":
            return queryset.filter(deleted_at__isnull=False)
        if value == "all":
            return queryset
        return queryset.filter(deleted_at__isnull=True)

    def choices(self, changelist):
        """گزینه پیش‌فرض «فقط فعال» است، نه «همه»."""
        selected = self.value() or "0"
        for value, title in self.lookup_choices:
            yield {
                "selected": str(value) == selected,
                "query_string": changelist.get_query_string(
                    {self.parameter_name: value}
                ),
                "display": title,
            }


class SchoolModelAdmin(admin.ModelAdmin):
    """
    رفتار مشترک همه ModelAdminهای سامانه.

    قابل استفاده مستقیم به‌عنوان کلاس پایه برای ModelAdminهای دست‌نویس هم هست.
    """

    list_per_page = 50
    save_on_top = True
    show_facets = admin.ShowFacets.NEVER  # شمارش وجهی روی جدول‌های بزرگ گران است

    @admin.action(description="بازگردانی رکوردهای حذف‌شده")
    def restore_selected(self, request, queryset):
        restored = 0
        for obj in queryset:
            if getattr(obj, "deleted_at", None) is not None:
                obj.restore()
                restored += 1
        self.message_user(
            request,
            f"{restored} رکورد بازگردانی شد."
            if restored
            else "هیچ رکورد حذف‌شده‌ای در انتخاب شما نبود.",
            messages.SUCCESS if restored else messages.WARNING,
        )

    def get_queryset(self, request):
        """
        اگر :class:`SoftDeleteFilter` روی فهرست باشد، Queryset روی `all_objects`
        می‌رود تا فیلتر بتواند رکورد حذف‌شده را هم نشان دهد.

        بدون آن فیلتر، Manager پیش‌فرض مدل دست‌نخورده می‌ماند؛ وگرنه رکوردهای
        حذف‌شده بی‌آنکه راهی برای کنارگذاشتن‌شان باشد در فهرست ظاهر می‌شدند.
        """
        if SoftDeleteFilter not in (self.list_filter or ()):
            return super().get_queryset(request)

        queryset = self.model.all_objects.all()
        ordering = self.get_ordering(request)
        if ordering:
            queryset = queryset.order_by(*ordering)
        if self.list_select_related and self.list_select_related is not True:
            queryset = queryset.select_related(*self.list_select_related)
        return queryset


class ImmutableModelAdmin(SchoolModelAdmin):
    """
    سند قطعی: فقط خواندنی.

    بخش ۷.۸ سند تحلیل: «سند قطعی تغییرناپذیر است؛ اصلاح فقط با سند برگشتی.»
    اگر پنل اجازه ویرایش بدهد، همین قاعده از مسیر پشتی نقض می‌شود.
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# ثبت خودکار
# ---------------------------------------------------------------------------
def build_admin_class(model) -> type[SchoolModelAdmin]:
    """کلاس ModelAdmin مشتق‌شده از ساختار مدل."""
    soft_delete = _has_field(model, "deleted_at")
    immutable = issubclass(model, ImmutableLedgerModel)

    list_display = derive_list_display(model)
    list_filter = list(derive_list_filter(model))
    if soft_delete:
        list_filter.insert(0, SoftDeleteFilter)

    autocomplete_fields, raw_id_fields = _split_relations(model)

    audit_present = tuple(f for f in AUDIT_FIELDS if _has_field(model, f))
    editable = tuple(
        f.name
        for f in model._meta.get_fields()
        if getattr(f, "editable", False)
        and not f.auto_created
        and f.name not in AUDIT_FIELDS
        and not _is_through_m2m(f)
    )

    # کلید خارجی‌هایی که در فهرست ستون دارند با یک Join خوانده می‌شوند تا هر
    # سطر یک کوئری اضافه نزند.
    select_related = tuple(
        f.name
        for f in _concrete_fields(model)
        if isinstance(f, models.ForeignKey) and f.name in list_display
    )

    attrs: dict = {
        "list_display": list_display,
        "list_filter": tuple(list_filter),
        "list_select_related": select_related,
        "readonly_fields": audit_present,
        "autocomplete_fields": autocomplete_fields,
        "raw_id_fields": raw_id_fields,
        "__doc__": f"پیکربندی خودکار برای {model._meta.verbose_name}.",
    }

    search_fields = derive_search_fields(model)
    if search_fields:
        attrs["search_fields"] = search_fields

    if _has_field(model, "created_at"):
        attrs["ordering"] = ("-created_at",)

    if editable:
        fieldsets = [(None, {"fields": editable})]
        if audit_present:
            fieldsets.append(
                (
                    "اطلاعات ممیزی",
                    {"classes": ("collapse",), "fields": audit_present},
                )
            )
        attrs["fieldsets"] = tuple(fieldsets)

    if soft_delete:
        attrs["actions"] = ["restore_selected"]

    base = ImmutableModelAdmin if immutable else SchoolModelAdmin
    return type(f"{model.__name__}Admin", (base,), attrs)


def register_auto(*models_to_register) -> None:
    """
    ثبت مدل‌ها با پیکربندی مشتق‌شده.

    مدلی که قبلاً ثبت شده باشد نادیده گرفته می‌شود، پس `ModelAdmin` دست‌نویس
    هرگز بازنویسی نمی‌گردد.
    """
    for model in models_to_register:
        if model in admin.site._registry:
            continue
        admin.site.register(model, build_admin_class(model))


@admin.register(Tenant)
class TenantAdmin(SchoolModelAdmin):
    list_display = ("name", "code", "status", "default_currency", "created_at")
    search_fields = ("name", "code")
    list_filter = ("status",)
