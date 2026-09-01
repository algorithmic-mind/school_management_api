"""Endpointهای زیرساختی: سلامت سرویس و کاتالوگ شمارش‌ها."""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db import connection
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.dashboard import build_dashboard
from apps.core.serializers import ErrorResponseSerializer


@extend_schema(
    tags=["Reports"],
    summary="بررسی سلامت سرویس",
    description="برای Health Check زیرساخت و Load Balancer. نیازی به احراز هویت ندارد.",
    responses={
        200: {
            "type": "object",
            "properties": {
                "status": {"type": "string", "example": "ok"},
                "database": {"type": "string", "example": "ok"},
                "version": {"type": "string", "example": "1.0.0"},
            },
        }
    },
)
class HealthCheckView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        db_state = "ok"
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:  # pragma: no cover
            db_state = "unavailable"

        payload = {"status": "ok", "database": db_state, "version": "1.0.0"}
        http_status = (
            status.HTTP_200_OK if db_state == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return Response(payload, status=http_status)


@extend_schema(
    tags=["Reports"],
    summary="کاتالوگ شمارش‌ها و وضعیت‌ها",
    description=(
        "همه فهرست‌های مقادیر مجاز (وضعیت‌ها، انواع، دسته‌ها) را یک‌جا برمی‌گرداند "
        "تا فرانت‌اند بتواند Dropdownها و برچسب‌های فارسی را بدون Hardcode بسازد.\n\n"
        "هر آیتم شامل `value` (مقداری که به API ارسال می‌شود) و `label` "
        "(متن فارسی قابل نمایش) است."
    ),
    responses={
        200: {
            "type": "object",
            "additionalProperties": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "label": {"type": "string"},
                    },
                },
            },
        },
        401: ErrorResponseSerializer,
    },
    examples=[
        OpenApiExample(
            "نمونه پاسخ",
            value={
                "core.Gender": [
                    {"value": "MALE", "label": "مرد"},
                    {"value": "FEMALE", "label": "زن"},
                ],
                "students.EnrollmentStatus": [
                    {"value": "PENDING_DOCUMENTS", "label": "در انتظار مدارک"},
                    {"value": "ACTIVE", "label": "فعال"},
                ],
            },
            response_only=True,
        )
    ],
)
class EnumCatalogView(APIView):
    """
    فهرست همه TextChoices/IntegerChoices ماژول‌های سامانه.

    این Endpoint منبع واحد حقیقت برچسب‌های فارسی برای فرانت است.
    """

    permission_classes = [IsAuthenticated]

    ENUM_MODULES = [
        ("core", "apps.core.enums"),
        ("identity", "apps.identity.enums"),
        ("organization", "apps.organization.enums"),
        ("students", "apps.students.enums"),
        ("hr", "apps.hr.enums"),
        ("teaching", "apps.teaching.enums"),
        ("assessment", "apps.assessment.enums"),
        ("gradebook", "apps.gradebook.enums"),
        ("finance", "apps.finance.enums"),
        ("inventory", "apps.inventory.enums"),
        ("welfare", "apps.welfare.enums"),
        ("workflow", "apps.workflow.enums"),
    ]

    def get(self, request):
        import importlib

        from django.db.models.enums import ChoicesMeta

        catalog: dict[str, list[dict[str, str]]] = {}
        for prefix, module_path in self.ENUM_MODULES:
            try:
                module = importlib.import_module(module_path)
            except ModuleNotFoundError:
                continue
            for name in dir(module):
                if name.startswith("_"):
                    continue
                obj = getattr(module, name)
                if isinstance(obj, ChoicesMeta):
                    catalog[f"{prefix}.{name}"] = [
                        {"value": str(value), "label": str(label)}
                        for value, label in obj.choices
                    ]
        return Response(catalog)


@extend_schema(
    tags=["Reports"],
    summary="فهرست ماژول‌ها و منابع API",
    description=(
        "نقشه سریع منابع سامانه برای توسعه‌دهنده فرانت: نام ماژول، تعداد "
        "موجودیت‌ها و پیشوند مسیر REST هر ماژول."
    ),
    responses={
        200: {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "module": {"type": "string", "title": "شناسه ماژول"},
                    "title": {"type": "string", "title": "عنوان فارسی ماژول"},
                    "basePath": {"type": "string", "title": "پیشوند مسیر REST"},
                    "entityCount": {"type": "integer", "title": "تعداد موجودیت‌ها"},
                    "entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "title": "نام مدل‌ها",
                    },
                },
            },
        }
    },
    examples=[
        OpenApiExample(
            "نمونه پاسخ",
            value=[
                {
                    "module": "gradebook",
                    "title": "دفتر نمره و کارنامه",
                    "basePath": "/api/v1/gradebook/",
                    "entityCount": 7,
                    "entities": ["AssessmentCategory", "GradeItem", "StudentScore"],
                }
            ],
            response_only=True,
        )
    ],
)
class ModuleMapView(APIView):
    permission_classes = [IsAuthenticated]

    MODULE_META = {
        "core": ("زیرساخت مشترک", "/api/v1/"),
        "identity": ("هویت و دسترسی", "/api/v1/iam/"),
        "organization": ("ساختار سازمانی و آموزشی", "/api/v1/org/"),
        "students": ("پذیرش و امور دانش‌آموزان", "/api/v1/students/"),
        "hr": ("منابع انسانی", "/api/v1/hr/"),
        "teaching": ("آموزش، حضور و تکلیف", "/api/v1/teaching/"),
        "assessment": ("بانک سؤال و آزمون", "/api/v1/assessment/"),
        "gradebook": ("دفتر نمره و کارنامه", "/api/v1/gradebook/"),
        "finance": ("مالی و حسابداری", "/api/v1/finance/"),
        "inventory": ("خرید، انبار و اموال", "/api/v1/inventory/"),
        "welfare": ("خدمات دانش‌آموزی", "/api/v1/welfare/"),
        "workflow": ("گردش کار و ارتباطات", "/api/v1/workflow/"),
    }

    def get(self, request):
        result = []
        for app_label, (title, prefix) in self.MODULE_META.items():
            try:
                app_config = django_apps.get_app_config(app_label)
            except LookupError:  # pragma: no cover
                continue
            models = sorted(m.__name__ for m in app_config.get_models())
            result.append(
                {
                    "module": app_label,
                    "title": title,
                    "basePath": prefix,
                    "entityCount": len(models),
                    "entities": models,
                }
            )
        return Response(result)


@extend_schema(
    tags=["Reports"],
    summary="داشبورد نقش‌محور",
    description=(
        "همه ویجت‌های صفحه اصلی در یک درخواست (بخش ۱۴ سند تحلیل و ۶.۱ سند "
        "فرانت).\n\n"
        "- **ویجت بدون مجوز اصلاً برنمی‌گردد**، نه اینکه صفر یا خطا بدهد. فرانت "
        "فقط `widgets` را می‌پیماید و هرچه آمد را می‌چیند؛ لازم نیست خودش "
        "مجوزها را بررسی کند.\n"
        "- همه اعداد از محدوده دسترسی همان کاربر عبور می‌کنند؛ مدیر یک شعبه "
        "عدد همان شعبه را می‌بیند.\n"
        "- هر ویجت `link` دارد: مسیر API‌ای که جزئیات همان عدد را می‌دهد "
        "(Drill-down).\n"
        "- `value` برابر `null` یعنی «داده‌ای برای محاسبه نیست» — با صفر یکی "
        "نیست و باید متفاوت نمایش داده شود.\n\n"
        "با `widgets=activeStudents,attendanceToday` می‌توانید فقط بخشی را "
        "بخواهید؛ کارت‌های بالای صفحه این‌طور زودتر می‌آیند و منتظر محاسبه "
        "روند سی‌روزه نمی‌مانند."
    ),
    parameters=[
        OpenApiParameter(
            "widgets",
            str,
            description=(
                "کلید ویجت‌های موردنیاز، با کاما. خالی یعنی همه ویجت‌های مجاز."
            ),
        )
    ],
    responses={
        200: OpenApiResponse(description="ویجت‌های داشبورد"),
        401: ErrorResponseSerializer,
    },
    examples=[
        OpenApiExample(
            "نمونه پاسخ",
            value={
                "generatedAt": "2026-09-01T10:35:00+03:30",
                "date": "2026-09-01",
                "scope": {
                    "schoolId": "900a07a7-46dd-4f06-b81c-f22e996f269c",
                    "campusId": None,
                    "academicYearId": None,
                },
                "widgetCount": 2,
                "widgets": [
                    {
                        "key": "activeStudents",
                        "title": "دانش‌آموزان فعال",
                        "link": "/api/v1/students/students/?status=ACTIVE",
                        "asOf": "2026-09-01T10:35:00+03:30",
                        "value": 842,
                        "unit": "دانش‌آموز",
                        "breakdown": [{"label": "پایه هفتم", "value": 310}],
                    },
                    {
                        "key": "tuitionCollection",
                        "title": "وصول شهریه",
                        "link": "/api/v1/finance/invoices/aging/",
                        "asOf": "2026-09-01T10:35:00+03:30",
                        "value": 76.4,
                        "unit": "درصد وصول",
                        "currency": "IRR",
                        "breakdown": [
                            {"label": "مبلغ صورتحساب", "value": 18000000000},
                            {"label": "وصول‌شده", "value": 13750000000},
                        ],
                    },
                ],
            },
            response_only=True,
        )
    ],
)
class DashboardView(APIView):
    """داشبورد صفحه اصلی، متناسب با نقش و دامنه کاربر."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        raw = request.query_params.get("widgets", "")
        keys = [item for item in raw.replace(" ", "").split(",") if item]
        return Response(build_dashboard(request, keys=keys or None))
