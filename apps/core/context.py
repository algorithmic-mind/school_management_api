"""
Context جاری درخواست (Tenant، Scope، کاربر، Correlation).

بخش ۱۲.۴ سند تحلیل: «فیلتر Tenant/Scope در لایه Repository اجباری و قابل
دورزدن توسط Query ورودی نیست.» این ماژول Contextِ مؤثر را در قالب
ContextVar نگهداری می‌کند تا مدل‌ها و Managerها به آن دسترسی داشته باشند.
"""

from __future__ import annotations

import contextvars
import uuid
from dataclasses import dataclass, field
from typing import Any

_current_context: contextvars.ContextVar["RequestContext | None"] = (
    contextvars.ContextVar("school_request_context", default=None)
)


@dataclass
class RequestContext:
    """Context مؤثر یک درخواست."""

    correlation_id: str = ""
    user_id: uuid.UUID | None = None
    tenant_id: uuid.UUID | None = None
    school_id: uuid.UUID | None = None
    campus_id: uuid.UUID | None = None
    academic_year_id: uuid.UUID | None = None
    idempotency_key: str = ""
    permissions: set[str] = field(default_factory=set)
    scopes: list[dict[str, Any]] = field(default_factory=list)
    #: محدوده مؤثر داده، ساخته‌شده از `scopes`
    #: (:class:`apps.identity.scopes.EffectiveScope`). لایه Queryset با این
    #: شیء فیلتر می‌کند، نه با هدرهای خام درخواست.
    effective_scope: Any = None
    is_superuser: bool = False
    client_ip: str = ""
    user_agent: str = ""


def set_current_context(ctx: RequestContext) -> contextvars.Token:
    return _current_context.set(ctx)


def get_current_context() -> RequestContext | None:
    return _current_context.get()


def reset_current_context(token: contextvars.Token) -> None:
    _current_context.reset(token)


def get_current_user_id() -> uuid.UUID | None:
    ctx = _current_context.get()
    return ctx.user_id if ctx else None


def get_current_tenant_id() -> uuid.UUID | None:
    ctx = _current_context.get()
    return ctx.tenant_id if ctx else None


def get_correlation_id() -> str:
    ctx = _current_context.get()
    return ctx.correlation_id if ctx else "-"
