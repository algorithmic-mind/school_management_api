"""Endpointهای زیرساختی: سلامت سرویس و کاتالوگ شمارش‌ها."""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db import connection
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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
