"""میان‌افزارهای پایه: Correlation Id و Context کاری."""

from __future__ import annotations

import uuid

from django.utils.deprecation import MiddlewareMixin

from apps.core.context import (
    RequestContext,
    get_current_context,
    reset_current_context,
    set_current_context,
)

CORRELATION_HEADER = "HTTP_X_CORRELATION_ID"
SCHOOL_HEADER = "HTTP_X_SCHOOL_ID"
CAMPUS_HEADER = "HTTP_X_CAMPUS_ID"
YEAR_HEADER = "HTTP_X_ACADEMIC_YEAR_ID"
IDEMPOTENCY_HEADER = "HTTP_IDEMPOTENCY_KEY"


def _parse_uuid(raw: str | None) -> uuid.UUID | None:
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError):
        return None


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


class CorrelationIdMiddleware(MiddlewareMixin):
    """
    شناسه همبستگی برای ردیابی سرتاسری درخواست.

    بخش ۱۲.۳: correlationId جزو بدنه خطا است و در Log و ممیزی هم ثبت می‌شود.
    """

    def process_request(self, request):
        correlation_id = request.META.get(CORRELATION_HEADER) or uuid.uuid4().hex
        request.correlation_id = correlation_id

    def process_response(self, request, response):
        correlation_id = getattr(request, "correlation_id", None)
        if correlation_id:
            response["X-Correlation-Id"] = correlation_id
        return response


class RequestContextMiddleware(MiddlewareMixin):
    """
    Context مؤثر را از هدرها می‌سازد و در ContextVar می‌گذارد.

    هدرها: X-School-Id, X-Campus-Id, X-Academic-Year-Id, Idempotency-Key
    مجوزها و Scopeها پس از احراز هویت در `permissions.ScopedRBACPermission`
    تکمیل می‌شوند، چون احراز هویت DRF بعد از میان‌افزار اجرا می‌شود.
    """

    def process_request(self, request):
        ctx = RequestContext(
            correlation_id=getattr(request, "correlation_id", "") or uuid.uuid4().hex,
            school_id=_parse_uuid(request.META.get(SCHOOL_HEADER)),
            campus_id=_parse_uuid(request.META.get(CAMPUS_HEADER)),
            academic_year_id=_parse_uuid(request.META.get(YEAR_HEADER)),
            idempotency_key=request.META.get(IDEMPOTENCY_HEADER, ""),
            client_ip=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:400],
        )
        request._context_token = set_current_context(ctx)
        request.school_context = ctx

    def process_response(self, request, response):
        token = getattr(request, "_context_token", None)
        if token is not None:
            try:
                reset_current_context(token)
            except ValueError:  # pragma: no cover - Context در thread دیگر
                pass
        return response

    def process_exception(self, request, exception):
        ctx = get_current_context()
        if ctx is not None:
            ctx.correlation_id = getattr(request, "correlation_id", ctx.correlation_id)
        return None
