"""
تکمیل خودکار قرارداد OpenAPI: عنوان، توضیح و نمونه فارسی.

**مسئله.** اکشن‌های استاندارد REST (فهرست، جزئیات، ایجاد، ویرایش، حذف) روی
۱۴۵ موجودیت سامانه تکرار می‌شوند. نوشتن دستی صدها `summary` تکراری هم پرهزینه
است و هم با افزوده‌شدن هر منبع تازه از قلم می‌افتد؛ نتیجه‌اش Swagger‌ای است که
نیمی از عملیاتش بی‌عنوان و با توضیح عمومیِ کلاس پایه ظاهر می‌شود.

**راه‌حل.** دو قطعه:

1. :class:`PersianAutoSchema` — عنوان و توضیح هر اکشن استاندارد را از
   `verbose_name` مدل و پیکربندی خودِ View می‌سازد، و پارامترهای واقعی اما
   نامستند (`If-Match`، `reason`) را اعلام می‌کند.
2. :func:`postprocess_persian_docs` — روی Schema نهایی: برچسب فارسی فیلدها،
   نمونه ورودی/خروجی هر Schema، توضیح فارسی پاسخ‌ها و پاسخ‌های خطای استاندارد.

**اولویت با اعلان صریح است.** هر `@extend_schema(summary=…, description=…)`
روی متن تولیدشده اینجا مقدم می‌شود، و هیچ `example` دستی بازنویسی نمی‌گردد.
مرجع: بخش ۱۲.۳ و ۱۲.۴ سند تحلیل.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import OpenApiParameter

from apps.core.schema_labels import label_for, to_snake

# ---------------------------------------------------------------------------
# اکشن‌های استاندارد ViewSet
# ---------------------------------------------------------------------------
SUMMARY_TEMPLATES: dict[str, str] = {
    "list": "فهرست {plural}",
    "retrieve": "جزئیات {singular}",
    "create": "ایجاد {singular}",
    "update": "ویرایش کامل {singular}",
    "partial_update": "ویرایش جزئی {singular}",
    "destroy": "حذف {singular}",
}

PERMISSION_VERBS: dict[str, str] = {
    "list": "read",
    "retrieve": "read",
    "create": "create",
    "update": "update",
    "partial_update": "update",
    "destroy": "delete",
}

#: کلاس‌های پایه‌ای که Docstring‌شان عمومی است و نباید توضیح عملیات شود.
_GENERIC_DOC_MODULES = ("apps.core.viewsets", "rest_framework")


class PersianAutoSchema(AutoSchema):
    """AutoSchema پیش‌فرض پروژه — رجوع به `DEFAULT_SCHEMA_CLASS` در تنظیمات."""

    # -- عنوان ---------------------------------------------------------
    def get_summary(self) -> str | None:
        action = self._standard_action()
        names = self._resource_names()
        if not action or not names:
            return super().get_summary()
        singular, plural = names
        return SUMMARY_TEMPLATES[action].format(singular=singular, plural=plural)

    # -- توضیح ---------------------------------------------------------
    def get_description(self) -> str:
        action = self._standard_action()
        names = self._resource_names()
        if not action or not names:
            return super().get_description()

        blocks: list[str] = []
        own_doc = self._own_view_doc()
        if own_doc:
            blocks.append(own_doc)
        blocks.extend(getattr(self, f"_describe_{action}")(*names))

        permission = self._permission_code(action)
        if permission:
            blocks.append(f"**مجوز لازم:** `{permission}`")
        return "\n\n".join(b for b in blocks if b)

    # -- پارامترهای واقعیِ نامستند --------------------------------------
    def get_override_parameters(self):
        parameters = list(super().get_override_parameters())
        action = self._standard_action()

        if action in ("update", "partial_update") and hasattr(self.view, "check_version"):
            parameters.append(
                OpenApiParameter(
                    name="If-Match",
                    type=str,
                    location=OpenApiParameter.HEADER,
                    required=False,
                    description=(
                        "نسخه رکوردی که ویرایش می‌کنید، به شکل `\"3\"`. مقدار آن همان "
                        "`version` پاسخ `GET` (و هدر `ETag`) است. اگر رکورد در این "
                        "فاصله تغییر کرده باشد، پاسخ `409` با کد `VERSION_CONFLICT` "
                        "است. ارسال‌نکردن این هدر یعنی صرف‌نظر از کنترل هم‌زمانی."
                    ),
                )
            )

        if action == "destroy" and self._has_field("deleted_at"):
            parameters.append(
                OpenApiParameter(
                    name="reason",
                    type=str,
                    location=OpenApiParameter.QUERY,
                    required=False,
                    description="علت حذف؛ روی رکورد و در ممیزی ثبت می‌شود.",
                )
            )

        return parameters

    # ------------------------------------------------------------------
    # سازنده‌های متن توضیح
    # ------------------------------------------------------------------
    def _describe_list(self, singular: str, plural: str) -> list[str]:
        blocks = [f"دریافت فهرست صفحه‌بندی‌شده {plural}."]

        if self._is_cursor_paginated():
            blocks.append(
                "**صفحه‌بندی** — از نوع Cursor برای داده پرتغییر: پارامترهای `cursor` "
                "و `page_size`. برای صفحه بعد، نشانی کامل فیلد `next` را صدا بزنید و "
                "`cursor` را خودتان نسازید."
            )
        else:
            blocks.append(
                "**صفحه‌بندی** — پارامترهای `page` و `page_size` (پیش‌فرض ۲۵، حداکثر "
                "۲۰۰). پاسخ در پاکت `count`، `pageCount`، `page`، `pageSize`، `next`، "
                "`previous` و `results` برمی‌گردد."
            )

        filters = self._filter_params()
        if filters:
            blocks.append("**فیلترها** — " + "، ".join(f"`{name}`" for name in filters))

        search_fields = getattr(self.view, "search_fields", None)
        if search_fields:
            blocks.append(
                "**جست‌وجو** — پارامتر `search` روی "
                + "، ".join(f"`{f.lstrip('^=@$')}`" for f in search_fields)
            )

        blocks.append(
            "**مرتب‌سازی** — پارامتر `ordering`؛ برای ترتیب نزولی نام فیلد را با `-` "
            "شروع کنید."
        )
        blocks.append(self._scope_note())
        return blocks

    def _describe_retrieve(self, singular: str, plural: str) -> list[str]:
        blocks = [f"دریافت جزئیات یک {singular} با شناسه UUID."]
        if self._has_field("version"):
            blocks.append(
                "پاسخ شامل فیلد `version` است و همان مقدار در هدر `ETag` هم برمی‌گردد؛ "
                "برای ویرایش امن، آن را در هدر `If-Match` بازگردانید."
            )
        blocks.append(
            f"اگر {singular} خارج از دامنه دسترسی کاربر باشد پاسخ `404` است، نه `403` "
            "— تا وجود یا نبود رکورد افشا نشود."
        )
        return blocks

    def _describe_create(self, singular: str, plural: str) -> list[str]:
        blocks = [f"ایجاد {singular} تازه."]
        bullets = [
            "فیلدهای `id`، `created_at`، `updated_at` و `version` فقط‌خواندنی‌اند و "
            "در بدنه پذیرفته نمی‌شوند."
        ]
        if self._has_field("tenant"):
            bullets.append(
                "سازمان (`tenant`) از Context کاربر جاری گرفته می‌شود؛ فرستادن آن در "
                "بدنه اثری ندارد."
            )
        bullets.append("پاسخ موفق `201` است و رکورد ساخته‌شده را کامل برمی‌گرداند.")
        blocks.append("\n".join(f"- {b}" for b in bullets))
        return blocks

    def _describe_update(self, singular: str, plural: str) -> list[str]:
        blocks = [
            f"جایگزینی کامل {singular}.",
            "همه فیلدهای الزامی باید ارسال شوند؛ هر فیلد اختیاری که نیاید به مقدار "
            "پیش‌فرض بازمی‌گردد. برای تغییر چند فیلد از `PATCH` استفاده کنید.",
        ]
        blocks.extend(self._concurrency_notes())
        return blocks

    def _describe_partial_update(self, singular: str, plural: str) -> list[str]:
        blocks = [
            f"ویرایش جزئی {singular}.",
            "فقط فیلدهایی که در بدنه می‌آیند تغییر می‌کنند؛ بقیه دست‌نخورده می‌مانند.",
        ]
        blocks.extend(self._concurrency_notes())
        return blocks

    def _describe_destroy(self, singular: str, plural: str) -> list[str]:
        if not self._has_field("deleted_at"):
            return [
                f"حذف {singular}.",
                "این منبع از نوع سند قطعی است و حذف فیزیکی ندارد؛ اگر عملیات مجاز "
                "نباشد پاسخ `422` با کد قاعده کسب‌وکار برمی‌گردد و اصلاح فقط با سند "
                "معکوس ممکن است (بخش ۷.۸ سند تحلیل).",
            ]
        return [
            f"حذف نرم {singular}.",
            f"{singular} از فهرست‌ها و جست‌وجوها خارج می‌شود اما با `deleted_at` در "
            "پایگاه داده می‌ماند و در ممیزی قابل ردیابی است.",
            "- علت حذف را در پارامتر Query `reason` بفرستید.\n"
            "- پاسخ موفق `204` و بدون بدنه است.",
        ]

    def _concurrency_notes(self) -> list[str]:
        blocks = []
        if hasattr(self.view, "check_version"):
            blocks.append(
                "**کنترل هم‌زمانی** — مقدار `version` رکورد را در هدر `If-Match` "
                "بفرستید. اگر رکورد در این فاصله تغییر کرده باشد پاسخ `409` با کد "
                "`VERSION_CONFLICT` است و باید نسخه تازه را بخوانید و تغییر را دوباره "
                "اعمال کنید."
            )
        if self._has_field("status"):
            blocks.append(
                "**تغییر وضعیت** — فیلد `status` از این مسیر تغییر نمی‌کند؛ برای هر "
                "گذار، Endpoint اختصاصی خودش وجود دارد (بخش ۱۰ سند تحلیل)."
            )
        return blocks

    def _scope_note(self) -> str:
        return (
            "**دامنه دسترسی** — خروجی همیشه به سازمان و Context کاری کاربر جاری محدود "
            "است. این فیلتر در لایه Queryset اعمال می‌شود و با پارامتر Query قابل دور "
            "زدن نیست."
        )

    # ------------------------------------------------------------------
    # کمکی‌ها
    # ------------------------------------------------------------------
    def _standard_action(self) -> str | None:
        action = getattr(self.view, "action", None)
        return action if action in SUMMARY_TEMPLATES else None

    def _model(self):
        queryset = getattr(self.view, "queryset", None)
        model = getattr(queryset, "model", None)
        if model is not None:
            return model
        try:
            return self.view.get_serializer_class().Meta.model
        except Exception:  # pragma: no cover - سریالایزر بدون مدل
            return None

    def _resource_names(self) -> tuple[str, str] | None:
        model = self._model()
        if model is None:
            return None
        meta = model._meta
        singular = str(meta.verbose_name)
        plural = str(meta.verbose_name_plural)
        if not singular:  # pragma: no cover
            return None
        return singular, plural

    def _has_field(self, name: str) -> bool:
        model = self._model()
        if model is None:
            return False
        return any(
            getattr(field, "name", None) == name for field in model._meta.get_fields()
        )

    def _permission_code(self, action: str) -> str | None:
        view = self.view
        explicit = getattr(view, "required_permissions", None)
        if explicit:
            return list(explicit)[0]
        mapped = (getattr(view, "permission_map", None) or {}).get(action)
        if mapped:
            return mapped if isinstance(mapped, str) else list(mapped)[0]
        resource = getattr(view, "permission_resource", None)
        if not resource:
            return None
        return f"{resource}.{PERMISSION_VERBS[action]}"

    def _is_cursor_paginated(self) -> bool:
        paginator = getattr(self.view, "pagination_class", None)
        return bool(paginator) and "Cursor" in paginator.__name__

    def _filter_params(self) -> list[str]:
        filterset_class = getattr(self.view, "filterset_class", None)
        if filterset_class is not None:
            declared = getattr(filterset_class, "base_filters", {})
            return list(declared)[:10]
        fields = getattr(self.view, "filterset_fields", None) or ()
        return list(fields)[:10]

    def _own_view_doc(self) -> str:
        """
        Docstring تعریف‌شده روی خودِ کلاس View.

        Docstring کلاس‌های پایه (`BaseModelViewSet` و مانند آن) عمومی است و اگر
        رها شود، توضیح هر شش عملیات یکسان و بی‌فایده می‌شود.
        """
        import inspect

        for klass in type(self.view).__mro__:
            doc = klass.__dict__.get("__doc__")
            if not doc or not doc.strip():
                continue
            if klass.__module__.startswith(_GENERIC_DOC_MODULES):
                return ""
            return inspect.cleandoc(doc).strip()
        return ""


# ===========================================================================
# پس‌پردازش Schema نهایی
# ===========================================================================
MAX_EXAMPLE_DEPTH = 3

_UUID_SAMPLE = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
_DATETIME_SAMPLE = "2026-09-23T08:30:00+03:30"
_DATE_SAMPLE = "2026-09-23"
_TIME_SAMPLE = "08:30:00"

#: فیلدهای «پایان» تاریخ متفاوتی می‌گیرند تا بازه نمونه معنادار باشد.
_END_DATETIME_SAMPLE = "2027-03-20T12:00:00+03:30"
_END_DATE_SAMPLE = "2027-03-20"
_END_FIELD_MARKERS = (
    "ends_at",
    "ends_on",
    "end_date",
    "effective_to",
    "effective_until",
    "valid_until",
    "expires_at",
    "expiry_date",
    "due_at",
    "due_on",
    "due_date",
    "period_end",
    "period_to",
    "warranty_until",
    "appeal_deadline",
    "closed_at",
    "closed_on",
    "exit_date",
    "quiet_hours_end",
)

#: نمونه مقدار برای فیلدهایی که حدس نوعی، مقدار بی‌معنی تولید می‌کند.
_VALUE_SAMPLES: dict[str, Any] = {
    "amount": 12500000,
    "total_amount": 45000000,
    "unit_amount": 2500000,
    "unit_price": 2500000,
    "unit_cost": 2500000,
    "tax_amount": 1125000,
    "discount_amount": 5000000,
    "balance": 32500000,
    "debit": 12500000,
    "credit": 0,
    "currency": "IRR",
    "national_id": "0012345678",
    "phone": "09121234567",
    "mobile": "09121234567",
    "guardian_mobile": "09123334455",
    "email": "user@example.school",
    "username": "s.mohammadi",
    "password": "P@ssw0rd!2026",
    "new_password": "P@ssw0rd!2026",
    "first_name": "سارا",
    "last_name": "محمدی",
    "father_name": "علی",
    "display_name": "سارا محمدی",
    "full_name": "سارا محمدی",
    "student_name": "سارا محمدی",
    "teacher_name": "مریم رضایی",
    "guardian_name": "علی محمدی",
    "employee_name": "مریم رضایی",
    "applicant_name": "سارا محمدی",
    "school_name": "دبیرستان نمونه",
    "campus_name": "شعبه مرکزی",
    "student_no": "14030127",
    "class_group_code": "G7-A",
    "course_title": "ریاضی ۷",
    "term_title": "نیم‌سال اول",
    "exam_title": "آزمون میان‌ترم ریاضی",
    "assignment_title": "تمرین سری سوم",
    "grade_level": "هفتم",
    "grade_level_title": "پایه هفتم",
    "letter_grade": "A",
    "birth_place": "تهران",
    "nationality": "ایرانی",
    "province": "تهران",
    "city": "تهران",
    "district": "منطقه ۳",
    "postal_code": "1234567890",
    "line": "خیابان نمونه، کوچه دوم، پلاک ۱۲",
    "address_line": "خیابان نمونه، کوچه دوم، پلاک ۱۲",
    "photo": "https://example.school/media/photos/sample.jpg",
    "logo": "https://example.school/media/logo.png",
    "invoice_no": "INV-1405-000137",
    "payment_no": "PAY-1405-000412",
    "receipt_no": "GRN-1405-000058",
    "entry_no": "JE-1405-000731",
    "document_no": "STK-1405-000094",
    "order_no": "PO-1405-000027",
    "request_no": "PR-1405-000019",
    "ticket_no": "TK-1405-000203",
    "contract_no": "HR-1405-0042",
    "serial_no": "SN-88213047",
    "asset_tag": "AST-004512",
    "passport_no": "K12345678",
    "item_sku": "STA-A4-80",
    "sku": "STA-A4-80",
    "barcode": "6260123456789",
    "warehouse_code": "WH-01",
    "route_code": "R-03",
    "room_code": "R-204",
    "class_group_code": "G7-A",
    "account_code": "1101",
    "fiscal_year": "1405",
    "reason": "اصلاح اطلاعات پس از بررسی پرونده",
    "comment": "توضیح کوتاه ثبت‌کننده",
    "note": "یادداشت داخلی",
    "description": "توضیح تکمیلی این رکورد",
    "message": "عملیات با موفقیت انجام شد.",
    "title": "عنوان نمونه",
    "code": "SAMPLE-001",
    "isbn": "9786001234567",
    "author": "محمدرضا کریمی",
    "publisher": "نشر نمونه",
    "vehicle_plate": "۱۲ الف ۳۴۵ ایران ۱۰",
    "url": "https://example.school/resources/sample.pdf",
    "timezone": "Asia/Tehran",
    "locale": "fa-IR",
    "preferred_locale": "fa-IR",
    "country": "IR",
    "latitude": 35.6892,
    "longitude": 51.389,
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "media_type": "application/pdf",
    "original_name": "sample.pdf",
    "size_bytes": 248576,
    "correlation_id": "8c4a1f2e",
    "version": 1,
    "page": 1,
    "page_size": 25,
    "page_count": 6,
    "count": 137,
    "next": "https://api.example.school/api/v1/<resource>/?page=3",
    "previous": "https://api.example.school/api/v1/<resource>/?page=1",
    "birth_date": "2012-09-26",
    "date_joined": "2024-08-31T09:00:00+03:30",
    "acquired_on": "2024-05-11",
    "issued_on": "2024-05-11",
}

#: پیکربندی پاسخ‌های خطای استاندارد — مرجع: بخش ۱۲.۳ سند تحلیل.
_ERROR_EXAMPLES: dict[str, dict[str, Any]] = {
    "ValidationError": {
        "summary": "خطای اعتبارسنجی ورودی",
        "description": "قالب یا مقدار یکی از فیلدهای بدنه درست نیست.",
        "value": {
            "code": "VALIDATION_ERROR",
            "message": "داده ورودی معتبر نیست.",
            "correlationId": "8c4a1f2e",
            "fieldErrors": [
                {"field": "title", "reason": "این فیلد نمی‌تواند خالی باشد."}
            ],
            "retryable": False,
        },
    },
    "Unauthenticated": {
        "summary": "احراز هویت نشده",
        "description": "توکن ارسال نشده، منقضی شده یا نامعتبر است.",
        "value": {
            "code": "AUTHENTICATION_REQUIRED",
            "message": "برای این عملیات باید وارد سامانه شوید.",
            "correlationId": "8c4a1f2e",
            "fieldErrors": [],
            "retryable": False,
        },
    },
    "PermissionDenied": {
        "summary": "بدون مجوز",
        "description": (
            "کاربر احراز هویت شده اما مجوز لازم را ندارد. اگر رکورد خارج از دامنه "
            "دسترسی باشد کد `SCOPE_FORBIDDEN` برمی‌گردد."
        ),
        "value": {
            "code": "PERMISSION_DENIED",
            "message": "شما مجوز لازم برای این عملیات را ندارید.",
            "correlationId": "8c4a1f2e",
            "fieldErrors": [],
            "retryable": False,
        },
    },
    "NotFound": {
        "summary": "یافت نشد",
        "description": "رکورد وجود ندارد، حذف نرم شده، یا خارج از دامنه دسترسی است.",
        "value": {
            "code": "RESOURCE_NOT_FOUND",
            "message": "منبع درخواستی یافت نشد.",
            "correlationId": "8c4a1f2e",
            "fieldErrors": [],
            "retryable": False,
        },
    },
    "VersionConflict": {
        "summary": "تعارض نسخه یا وضعیت",
        "description": (
            "رکورد پس از خواندن شما تغییر کرده (`VERSION_CONFLICT`)، گذار وضعیت "
            "مجاز نیست (`INVALID_STATE_TRANSITION`) یا دوره بسته است "
            "(`PERIOD_CLOSED`)."
        ),
        "value": {
            "code": "VERSION_CONFLICT",
            "message": (
                "این رکورد توسط کاربر دیگری تغییر کرده است. "
                "نسخه ارسالی 3 و نسخه فعلی 4 است."
            ),
            "correlationId": "8c4a1f2e",
            "fieldErrors": [],
            "retryable": True,
        },
    },
    "BusinessRule": {
        "summary": "نقض قاعده کسب‌وکار",
        "description": (
            "ورودی از نظر قالب درست است اما قاعده دامنه اجازه نمی‌دهد. مقدار `code` "
            "به قاعده نقض‌شده اشاره دارد؛ فرانت باید روی همان تصمیم بگیرد."
        ),
        "value": {
            "code": "CLASS_CAPACITY_EXCEEDED",
            "message": "ظرفیت کلاس تکمیل است.",
            "correlationId": "8c4a1f2e",
            "fieldErrors": [{"field": "class_group", "reason": "capacity"}],
            "retryable": False,
        },
    },
}

_ERROR_RESPONSES: dict[str, tuple[str, str]] = {
    "400": ("داده ورودی معتبر نیست.", "ValidationError"),
    "401": ("احراز هویت نشده است.", "Unauthenticated"),
    "403": ("مجوز لازم برای این عملیات وجود ندارد.", "PermissionDenied"),
    "404": ("رکورد یافت نشد یا خارج از دامنه دسترسی است.", "NotFound"),
    "409": ("تعارض نسخه یا وضعیت.", "VersionConflict"),
    "422": ("نقض قاعده کسب‌وکار.", "BusinessRule"),
}

_SUCCESS_DESCRIPTIONS: dict[str, str] = {
    "200": "عملیات با موفقیت انجام شد.",
    "201": "رکورد با موفقیت ایجاد شد.",
    "202": "درخواست پذیرفته شد و پردازش آن ادامه دارد.",
    "204": "عملیات با موفقیت انجام شد؛ بدنه پاسخ خالی است.",
}

_ETAG_HEADER = {
    "description": (
        "نسخه فعلی رکورد. همین مقدار را در هدر `If-Match` درخواست ویرایش بعدی "
        "بفرستید تا تغییرِ هم‌زمان کاربر دیگر بازنویسی نشود."
    ),
    "schema": {"type": "string", "example": '"3"'},
}


@lru_cache(maxsize=1)
def _enum_label_map() -> dict[str, str]:
    """
    نگاشت مقدار Enum به برچسب فارسی آن، از روی `enums.py` همه اپ‌ها.

    فیلدهای `*_display` در سریالایزرها برچسب فارسی مقدار انتخاب‌شده را
    برمی‌گردانند. نمونه‌ای که «متن نمونه» باشد به فرانت‌کار چیزی نمی‌گوید؛
    این نگاشت اجازه می‌دهد نمونه، همان برچسبی را نشان دهد که در عمل می‌آید.
    """
    import importlib

    from django.apps import apps as django_apps

    try:  # Django ≥ ۵.۰
        from django.db.models.enums import ChoicesType as _ChoicesMeta
    except ImportError:  # pragma: no cover
        from django.db.models.enums import ChoicesMeta as _ChoicesMeta

    mapping: dict[str, str] = {}
    for config in django_apps.get_app_configs():
        if not config.name.startswith("apps."):
            continue
        try:
            module = importlib.import_module(f"{config.name}.enums")
        except ModuleNotFoundError:
            continue
        for member in vars(module).values():
            if not isinstance(member, _ChoicesMeta):
                continue
            for value, label in member.choices:
                mapping.setdefault(str(value), str(label))
    return mapping


def _resolve_display_fields(sample: dict) -> None:
    """`status_display` را با برچسب فارسی مقدارِ `status` هم‌راستا می‌کند."""
    labels = _enum_label_map()
    for name in list(sample):
        key = to_snake(name)
        if not key.endswith("_display"):
            continue
        for sibling in sample:
            if to_snake(sibling) != key[: -len("_display")]:
                continue
            label = labels.get(str(sample[sibling]))
            if label:
                sample[name] = label
            break


# ---------------------------------------------------------------------------
# باز کردن $ref / allOf / oneOf
# ---------------------------------------------------------------------------
def _deref(schema: dict, schemas: dict, stack: tuple) -> tuple[dict | None, tuple]:
    """Schema را تا رسیدن به شکل ساده باز می‌کند. چرخه ارجاع → `None`."""
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        if name in stack:
            return None, stack
        target = schemas.get(name)
        if target is None:
            return None, stack
        merged = {**target, **{k: v for k, v in schema.items() if k != "$ref"}}
        return _deref(merged, schemas, stack + (name,))

    if "allOf" in schema:
        merged: dict = {}
        for part in schema["allOf"]:
            resolved, stack = _deref(part, schemas, stack)
            if resolved:
                merged.update(resolved)
        merged.update({k: v for k, v in schema.items() if k != "allOf"})
        return merged, stack

    variants = schema.get("oneOf") or schema.get("anyOf")
    if variants:
        for part in variants:
            resolved, next_stack = _deref(part, schemas, stack)
            if not resolved or resolved.get("type") == "null":
                continue
            if resolved.get("enum") in ([""], [None]):
                continue  # BlankEnum / NullEnum
            merged = {**resolved}
            merged.update(
                {k: v for k, v in schema.items() if k not in ("oneOf", "anyOf")}
            )
            return merged, next_stack
        return None, stack

    return schema, stack


def _string_sample(name: str, schema: dict) -> str:
    key = to_snake(name)
    fmt = schema.get("format")

    # نام فیلد بر قالب مقدم است: `latitude` با `format: decimal` باید مختصات
    # واقع‌نما بدهد نه «18.50»، و `birth_date` تاریخی در گذشته.
    if key in _VALUE_SAMPLES:
        return str(_VALUE_SAMPLES[key])

    if fmt == "uuid":
        return _UUID_SAMPLE
    if fmt == "date-time":
        return _END_DATETIME_SAMPLE if key in _END_FIELD_MARKERS else _DATETIME_SAMPLE
    if fmt == "date":
        return _END_DATE_SAMPLE if key in _END_FIELD_MARKERS else _DATE_SAMPLE
    if fmt == "time":
        return _TIME_SAMPLE
    if fmt == "email":
        return "user@example.school"
    if fmt == "uri":
        return "https://example.school/media/sample.pdf"
    if fmt == "binary":
        return "sample.pdf"
    if fmt == "decimal":
        return "18.50"

    if key.endswith("_display"):
        # مقدار واقعی از روی فیلد همزادش تعیین می‌شود؛ اینجا فقط مقدار پشتیبان است.
        return "برچسب فارسی مقدار"
    if key.endswith("_name") or key == "name":
        return "نام نمونه"
    if key.endswith("_title") or key == "title":
        return "عنوان نمونه"
    if key.endswith(("_code", "_no", "_sku")):
        return "SAMPLE-001"
    if key.endswith(("_note", "_reason", "_comment")):
        return "توضیح نمونه"
    return "متن نمونه"


def _number_sample(name: str, schema: dict, integer: bool) -> Any:
    key = to_snake(name)
    if key in _VALUE_SAMPLES:
        return _VALUE_SAMPLES[key]
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    if key.endswith("_amount") or key.endswith("_price") or key.endswith("_cost"):
        value: Any = 2500000
    elif key.endswith("_minutes"):
        value = 45
    elif key.endswith("_seconds"):
        value = 120
    elif key.endswith("_count") or key.startswith("total_"):
        value = 12
    elif key.endswith("_order"):
        value = 1
    elif integer:
        value = 3
    else:
        value = 18.5
    if minimum is not None and value < minimum:
        value = minimum
    if maximum is not None and value > maximum:
        value = maximum
    return int(value) if integer else value


def _sample(
    name: str, schema: dict, schemas: dict, *, for_request: bool, depth: int, stack: tuple
) -> Any:
    resolved, stack = _deref(schema, schemas, stack)
    if resolved is None:
        return None

    if "example" in resolved:
        return resolved["example"]

    enum = resolved.get("enum")
    if enum:
        for value in enum:
            if value not in (None, ""):
                return value
        return enum[0]

    if resolved.get("default") is not None:
        return resolved["default"]

    schema_type = resolved.get("type")

    if schema_type == "object" or "properties" in resolved:
        properties = resolved.get("properties")
        if not properties:
            return {}
        if depth >= MAX_EXAMPLE_DEPTH:
            return {}
        sample: dict[str, Any] = {}
        for prop_name, prop_schema in properties.items():
            if for_request and prop_schema.get("readOnly"):
                continue
            if not for_request and prop_schema.get("writeOnly"):
                continue
            value = _sample(
                prop_name,
                prop_schema,
                schemas,
                for_request=for_request,
                depth=depth + 1,
                stack=stack,
            )
            if value is not None:
                sample[prop_name] = value
        _resolve_display_fields(sample)
        return sample

    if schema_type == "array":
        if depth >= MAX_EXAMPLE_DEPTH:
            return []
        item = _sample(
            name,
            resolved.get("items") or {},
            schemas,
            for_request=for_request,
            depth=depth + 1,
            stack=stack,
        )
        return [] if item is None else [item]

    if schema_type == "boolean":
        return not to_snake(name).startswith(("is_deleted", "is_cancel"))
    if schema_type == "integer":
        return _number_sample(name, resolved, integer=True)
    if schema_type == "number":
        return _number_sample(name, resolved, integer=False)
    if schema_type == "string":
        return _string_sample(name, resolved)
    return None


# ---------------------------------------------------------------------------
# گام‌های پس‌پردازش
# ---------------------------------------------------------------------------
def _label_properties(schemas: dict) -> None:
    """برچسب فارسی فیلدهایی که `verbose_name` یا `help_text` ندارند."""
    for schema in schemas.values():
        for name, prop in (schema.get("properties") or {}).items():
            if not isinstance(prop, dict):
                continue
            label = label_for(name)

            # کلید خارجی: drf-spectacular عنوان را از کلید اصلیِ مدل مقصد
            # برمی‌دارد و همه‌جا «شناسه» می‌شود؛ نام فیلد را به آن می‌افزاییم.
            if prop.get("title") == "شناسه" and name != "id":
                if label:
                    prop["title"] = (
                        label if label.startswith("شناسه") else f"شناسه {label}"
                    )
                else:
                    prop.setdefault("description", "شناسه رکورد مرتبط (UUID)")
                continue

            if prop.get("title") or prop.get("description"):
                continue
            if label:
                prop["title"] = label


def _attach_component_examples(schemas: dict) -> None:
    """نمونه مقدار برای هر Schema شیء‌مانند — پایه نمونه ورودی و خروجی."""
    for name, schema in schemas.items():
        if not isinstance(schema, dict) or "example" in schema:
            continue
        if schema.get("type") != "object" or not schema.get("properties"):
            continue
        for_request = name.endswith("Request")
        example = _sample(
            name, schema, schemas, for_request=for_request, depth=0, stack=(name,)
        )
        if example:
            schema["example"] = example


def _is_public(operation: dict) -> bool:
    """عملیات بدون احراز هویت (`AllowAny`) — پاسخ ۴۰۱/۴۰۳ برایش بی‌معناست."""
    return any(not entry for entry in operation.get("security") or [])


def _shared_error_responses() -> dict:
    """
    شش پاسخ خطای استاندارد، یک بار در `components.responses`.

    بدون این اشتراک، بدنه کامل هر خطا در ۹۰۰ عملیات تکرار می‌شود و حجم فایل
    قرارداد چند برابر می‌گردد؛ Swagger UI هم کندتر بالا می‌آید.
    """
    return {
        example_key: {
            "description": description,
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                    "examples": {
                        example_key: {"$ref": f"#/components/examples/{example_key}"}
                    },
                }
            },
        }
        for description, example_key in _ERROR_RESPONSES.values()
    }


def _error_response(status_code: str) -> dict:
    _, example_key = _ERROR_RESPONSES[status_code]
    return {"$ref": f"#/components/responses/{example_key}"}


def _expected_error_codes(path: str, method: str, operation: dict) -> list[str]:
    is_detail = path.rstrip("/").endswith("}")
    codes: list[str] = []

    if not _is_public(operation):
        codes += ["401", "403"]
    if is_detail:
        codes.append("404")
    if method in ("post", "put", "patch"):
        codes += ["400", "422"]
    if method in ("put", "patch", "delete"):
        codes.append("409")
    if method == "get":
        codes.append("400")

    return sorted(set(codes))


def _has_version(schema: dict, schemas: dict) -> bool:
    resolved, _ = _deref(schema, schemas, ())
    return bool(resolved and "version" in (resolved.get("properties") or {}))


def _enrich_operations(result: dict, schemas: dict) -> None:
    for path, methods in result.get("paths", {}).items():
        for method, operation in methods.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            responses = operation.setdefault("responses", {})

            for status_code, response in responses.items():
                if not isinstance(response, dict):
                    continue
                if not response.get("description"):
                    response["description"] = _SUCCESS_DESCRIPTIONS.get(
                        status_code, _ERROR_RESPONSES.get(status_code, ("پاسخ سرویس",))[0]
                    )
                if status_code in ("200", "201") and "headers" not in response:
                    body = (
                        (response.get("content") or {})
                        .get("application/json", {})
                        .get("schema")
                    )
                    if isinstance(body, dict) and _has_version(body, schemas):
                        response["headers"] = {"ETag": dict(_ETAG_HEADER)}

            if "ErrorResponse" not in schemas:  # pragma: no cover
                continue
            for status_code in _expected_error_codes(path, method, operation):
                responses.setdefault(status_code, _error_response(status_code))


def postprocess_persian_docs(result, generator, request, public, **kwargs):
    """
    Hook پس‌پردازش — در `SPECTACULAR_SETTINGS["POSTPROCESSING_HOOKS"]` ثبت می‌شود.

    باید *پس از* `postprocess_schema_enums` اجرا شود تا Enumها به Schema مستقل
    تبدیل شده باشند و نمونه‌سازی بتواند مقدار واقعی آن‌ها را بردارد.
    """
    components = result.setdefault("components", {})
    schemas = components.setdefault("schemas", {})

    _label_properties(schemas)
    _attach_component_examples(schemas)

    if "ErrorResponse" in schemas:
        components.setdefault("examples", {}).update(_ERROR_EXAMPLES)
        components.setdefault("responses", {}).update(_shared_error_responses())

    _enrich_operations(result, schemas)
    return result
