"""
قالب یکسان خطا برای کل وب‌سرویس.

بخش ۱۲.۳ سند تحلیل:

    {
      "code": "CLASS_CAPACITY_EXCEEDED",
      "message": "ظرفیت کلاس تکمیل است.",
      "correlationId": "01J...",
      "fieldErrors": [{"field": "classGroupId", "reason": "capacity"}],
      "retryable": false
    }

«پیام فنی داخلی، Stack Trace، شناسه راز یا داده شخصی در پاسخ Client نمایش
داده نمی‌شود.»
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.core.context import get_correlation_id

logger = logging.getLogger(__name__)


class BusinessRuleViolation(APIException):
    """
    نقض قاعده کسب‌وکار — با کد معنایی که فرانت می‌تواند روی آن تصمیم بگیرد.

    مثال: BusinessRuleViolation("CLASS_CAPACITY_EXCEEDED", "ظرفیت کلاس تکمیل است.")
    """

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "BUSINESS_RULE_VIOLATION"
    default_detail = "اجرای این عملیات با قواعد کسب‌وکار سازگار نیست."

    def __init__(
        self,
        code: str | None = None,
        message: str | None = None,
        field_errors: list[dict[str, str]] | None = None,
        retryable: bool = False,
        status_code: int | None = None,
    ):
        self.code = code or self.default_code
        self.message = message or self.default_detail
        self.field_errors = field_errors or []
        self.retryable = retryable
        if status_code:
            self.status_code = status_code
        super().__init__(detail=self.message, code=self.code)


class InvalidStateTransition(BusinessRuleViolation):
    """تغییر وضعیت غیرمجاز در ماشین حالت (بخش ۱۰ سند تحلیل)."""

    def __init__(self, entity: str, current: str, action: str):
        super().__init__(
            code="INVALID_STATE_TRANSITION",
            message=f"در وضعیت «{current}» امکان اجرای «{action}» روی {entity} وجود ندارد.",
            retryable=False,
            status_code=status.HTTP_409_CONFLICT,
        )


class ConcurrencyConflict(BusinessRuleViolation):
    """نسخه رکورد تغییر کرده است (If-Match / Lost Update)."""

    def __init__(self, expected: int | str, actual: int | str):
        super().__init__(
            code="VERSION_CONFLICT",
            message=(
                "این رکورد توسط کاربر دیگری تغییر کرده است. "
                f"نسخه ارسالی {expected} و نسخه فعلی {actual} است."
            ),
            retryable=True,
            status_code=status.HTTP_409_CONFLICT,
        )


class ScopeViolation(BusinessRuleViolation):
    """دسترسی خارج از دامنه مجاز کاربر (جلوگیری از IDOR — بخش ۱۵.۱)."""

    def __init__(self, message: str = "این رکورد در دامنه دسترسی شما نیست."):
        super().__init__(
            code="SCOPE_FORBIDDEN",
            message=message,
            retryable=False,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class PeriodClosed(BusinessRuleViolation):
    """دوره مالی یا سال تحصیلی بسته است (بخش ۷.۸ و ۱۱.۱)."""

    def __init__(self, period: str):
        super().__init__(
            code="PERIOD_CLOSED",
            message=f"دوره «{period}» بسته است؛ ثبت یا تغییر سند در آن مجاز نیست.",
            retryable=False,
            status_code=status.HTTP_409_CONFLICT,
        )


# --------------------------------------------------------------------------
# نگاشت استثناهای استاندارد به کد معنایی
# --------------------------------------------------------------------------
_STATUS_CODE_MAP: dict[int, str] = {
    400: "VALIDATION_ERROR",
    401: "AUTHENTICATION_REQUIRED",
    403: "PERMISSION_DENIED",
    404: "RESOURCE_NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    406: "NOT_ACCEPTABLE",
    409: "CONFLICT",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "BUSINESS_RULE_VIOLATION",
    429: "RATE_LIMIT_EXCEEDED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}

_STATUS_MESSAGE_MAP: dict[int, str] = {
    400: "داده ورودی معتبر نیست.",
    401: "برای این عملیات باید وارد سامانه شوید.",
    403: "شما مجوز لازم برای این عملیات را ندارید.",
    404: "منبع درخواستی یافت نشد.",
    405: "این متد برای این منبع مجاز نیست.",
    409: "درخواست با وضعیت فعلی منبع تعارض دارد.",
    422: "اجرای این عملیات با قواعد کسب‌وکار سازگار نیست.",
    429: "تعداد درخواست‌ها بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید.",
    500: "خطای داخلی سامانه رخ داد.",
    503: "سرویس موقتاً در دسترس نیست.",
}

_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def _flatten_field_errors(
    detail: Any, prefix: str = ""
) -> list[dict[str, str]]:
    """تبدیل ساختار تودرتوی خطای DRF به فهرست مسطح fieldErrors."""
    errors: list[dict[str, str]] = []

    if isinstance(detail, dict):
        for key, value in detail.items():
            field = f"{prefix}.{key}" if prefix else str(key)
            errors.extend(_flatten_field_errors(value, field))
    elif isinstance(detail, list):
        for index, value in enumerate(detail):
            if isinstance(value, (dict, list)):
                field = f"{prefix}[{index}]" if prefix else f"[{index}]"
                errors.extend(_flatten_field_errors(value, field))
            else:
                errors.append({"field": prefix or "non_field_errors", "reason": str(value)})
    else:
        errors.append({"field": prefix or "non_field_errors", "reason": str(detail)})

    return errors


def build_error_payload(
    code: str,
    message: str,
    field_errors: list[dict[str, str]] | None = None,
    retryable: bool = False,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "correlationId": get_correlation_id(),
        "fieldErrors": field_errors or [],
        "retryable": retryable,
    }


def api_exception_handler(exc, context):
    """Exception handler سراسری DRF با قالب خطای بخش ۱۲.۳."""

    # نگاشت استثناهای Django به معادل DRF
    if isinstance(exc, DjangoValidationError):
        from rest_framework.exceptions import ValidationError as DRFValidationError

        exc = DRFValidationError(detail=getattr(exc, "message_dict", exc.messages))
    elif isinstance(exc, DjangoPermissionDenied):
        from rest_framework.exceptions import PermissionDenied

        exc = PermissionDenied()
    elif isinstance(exc, Http404):
        from rest_framework.exceptions import NotFound

        exc = NotFound()
    elif isinstance(exc, IntegrityError):
        logger.warning("IntegrityError: %s", exc)
        payload = build_error_payload(
            code="DATA_INTEGRITY_VIOLATION",
            message="این عملیات با قیدهای یکتایی یا ارجاعی پایگاه داده تعارض دارد.",
            retryable=False,
        )
        return Response(payload, status=status.HTTP_409_CONFLICT)

    response = drf_exception_handler(exc, context)

    if response is None:
        # خطای پیش‌بینی‌نشده: جزئیات فقط در Log، نه در پاسخ (بخش ۱۲.۳)
        logger.exception("Unhandled exception in %s", context.get("view"))
        payload = build_error_payload(
            code="INTERNAL_ERROR",
            message=_STATUS_MESSAGE_MAP[500],
            retryable=True,
        )
        return Response(payload, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    status_code = response.status_code

    if isinstance(exc, BusinessRuleViolation):
        payload = build_error_payload(
            code=exc.code,
            message=exc.message,
            field_errors=exc.field_errors,
            retryable=exc.retryable,
        )
        response.data = payload
        return response

    detail = getattr(exc, "detail", None)
    field_errors: list[dict[str, str]] = []
    message = _STATUS_MESSAGE_MAP.get(status_code, "خطا در پردازش درخواست.")

    if isinstance(detail, dict):
        field_errors = _flatten_field_errors(detail)
    elif isinstance(detail, list):
        field_errors = _flatten_field_errors(detail)
    elif detail is not None:
        message = str(detail)

    code = _STATUS_CODE_MAP.get(status_code, "REQUEST_FAILED")
    default_code = getattr(exc, "default_code", None)
    if default_code and status_code in (401, 403, 429):
        code = str(default_code).upper()

    payload = build_error_payload(
        code=code,
        message=message,
        field_errors=field_errors,
        retryable=status_code in _RETRYABLE_STATUSES,
    )

    if status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        wait = getattr(exc, "wait", None)
        if wait:
            response["Retry-After"] = str(int(wait))

    response.data = payload
    return response
