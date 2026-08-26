"""
سرویس‌های گردش کار، رویداد و اعلان.

مرجع: بخش ۱۳ (رویدادهای دامنه‌ای)، ۷.۱۱ (گردش تأیید) و ۱۱.۴ (اعلان و حریم خصوصی).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.context import get_current_context
from apps.core.exceptions import BusinessRuleViolation
from apps.core.enums import ApprovalDecision, NotificationChannel
from apps.workflow.enums import ApprovalStatus, NotificationPriority, NotificationStatus
from apps.workflow.models import (
    ApprovalRequest,
    ApprovalStep,
    Notification,
    NotificationPreference,
    NotificationTemplate,
    OutboxEvent,
    WorkflowDefinition,
)


def publish_event(
    *,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
    tenant_id: uuid.UUID | None = None,
    schema_version: int = 1,
) -> OutboxEvent:
    """
    ثبت رویداد در Outbox، درون همان تراکنش عملیات اصلی.

    بخش ۱۳.۲: «شناسه رویداد یکتا، زمان وقوع، Tenant، Aggregate، Correlation و
    Causation ثبت می‌شود» و «داده شخصی حداقلی است».
    """
    ctx = get_current_context()
    return OutboxEvent.objects.create(
        tenant_id=tenant_id or (ctx.tenant_id if ctx else None),
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        schema_version=schema_version,
        payload=payload,
        correlation_id=ctx.correlation_id if ctx else "",
    )


@transaction.atomic
def start_approval(
    *,
    subject_type: str,
    subject_id: uuid.UUID,
    workflow_code: str,
    subject_label: str = "",
    tenant_id: uuid.UUID | None = None,
) -> ApprovalRequest:
    """
    شروع گردش تأیید با Snapshot نسخه تعریف.

    بخش ۷.۱۱: «نسخه گردش تأیید هنگام شروع Snapshot می‌شود؛ تغییر تنظیمات،
    درخواست در جریان را بی‌قاعده تغییر نمی‌دهد.»
    """
    ctx = get_current_context()
    tenant_id = tenant_id or (ctx.tenant_id if ctx else None)

    definition = (
        WorkflowDefinition.objects.filter(
            tenant_id=tenant_id, code=workflow_code, is_active=True
        )
        .order_by("-version_no")
        .first()
    )
    if definition is None:
        raise BusinessRuleViolation(
            code="WORKFLOW_NOT_DEFINED",
            message=f"گردش تأیید «{workflow_code}» تعریف یا فعال نشده است.",
        )

    request = ApprovalRequest.objects.create(
        tenant_id=tenant_id,
        subject_type=subject_type,
        subject_id=subject_id,
        subject_label=subject_label,
        workflow_code=definition.code,
        workflow_version=definition.version_no,
        workflow_snapshot={"steps": definition.steps_definition},
        requested_by_id=ctx.user_id if ctx else None,
        status=ApprovalStatus.PENDING,
    )

    for step in definition.steps_definition:
        ApprovalStep.objects.create(
            tenant_id=tenant_id,
            request=request,
            sequence_no=step.get("sequence", 1),
            approver_type=step.get("approverType", "ROLE"),
            approver_role_code=step.get("roleCode", ""),
            approver_user_id=step.get("userId"),
        )

    return request


@transaction.atomic
def decide_step(
    step: ApprovalStep,
    decision: str,
    comment: str = "",
    *,
    actor_user_id: uuid.UUID | None = None,
    on_behalf_of_id: uuid.UUID | None = None,
) -> ApprovalRequest:
    """
    ثبت تصمیم یک گام و پیشبرد گردش.

    تصمیم به نام تصمیم‌گیرنده واقعی ثبت می‌شود؛ در صورت جانشینی، فرد اصلی در
    `decided_on_behalf_of_id` نگهداری می‌گردد (بخش ۷.۱۱).
    """
    request = step.request

    if request.status != ApprovalStatus.PENDING:
        raise BusinessRuleViolation(
            code="APPROVAL_ALREADY_COMPLETED",
            message="این درخواست تأیید قبلاً تعیین تکلیف شده است.",
            status_code=409,
        )
    if step.decision != ApprovalDecision.PENDING:
        raise BusinessRuleViolation(
            code="STEP_ALREADY_DECIDED",
            message="این گام قبلاً تصمیم‌گیری شده است.",
            status_code=409,
        )

    # گام‌ها باید به ترتیب تصمیم‌گیری شوند
    earlier_pending = request.steps.filter(
        sequence_no__lt=step.sequence_no, decision=ApprovalDecision.PENDING
    ).exists()
    if earlier_pending:
        raise BusinessRuleViolation(
            code="PREVIOUS_STEP_PENDING",
            message="گام‌های قبلی این گردش هنوز تصمیم‌گیری نشده‌اند.",
        )

    step.decision = decision
    step.comment = comment
    step.decided_by_id = actor_user_id
    step.decided_on_behalf_of_id = on_behalf_of_id
    step.decided_at = timezone.now()
    step.save()

    if decision == ApprovalDecision.REJECTED:
        request.status = ApprovalStatus.REJECTED
        request.completed_at = timezone.now()
        request.save(update_fields=["status", "completed_at"])
    elif not request.steps.filter(decision=ApprovalDecision.PENDING).exists():
        request.status = ApprovalStatus.APPROVED
        request.completed_at = timezone.now()
        request.save(update_fields=["status", "completed_at"])

    if request.status != ApprovalStatus.PENDING:
        publish_event(
            aggregate_type="workflow.ApprovalRequest",
            aggregate_id=request.id,
            event_type="ApprovalCompleted",
            payload={
                "requestId": str(request.id),
                "subjectType": request.subject_type,
                "subjectId": str(request.subject_id),
                "status": request.status,
            },
            tenant_id=request.tenant_id,
        )

    return request


def render_template(template_body: str, variables: dict[str, Any]) -> str:
    """جایگزینی ساده متغیرهای {{name}} در متن قالب."""
    rendered = template_body
    for key, value in variables.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return rendered


def _is_quiet_hour(preference: NotificationPreference | None, moment) -> bool:
    if not preference or not preference.quiet_hours_start or not preference.quiet_hours_end:
        return False
    now_time = timezone.localtime(moment).time()
    start = preference.quiet_hours_start
    end = preference.quiet_hours_end
    if start <= end:
        return start <= now_time <= end
    return now_time >= start or now_time <= end


@transaction.atomic
def queue_notification(
    *,
    recipient_person,
    template_code: str | None = None,
    channel: str = NotificationChannel.IN_APP,
    subject: str = "",
    body: str = "",
    variables: dict[str, Any] | None = None,
    priority: str = NotificationPriority.OPERATIONAL,
    deep_link: str = "",
    related_type: str = "",
    related_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
) -> Notification | None:
    """
    صف‌گذاری یک اعلان با رعایت ترجیح کانال و ساعات سکوت.

    بخش ۱۱.۴: پیام‌های تراکنشی و اضطراری از قواعد Opt-out و ساعات سکوت مستثنا
    هستند؛ پیام تبلیغاتی نیست.
    """
    ctx = get_current_context()
    tenant_id = tenant_id or (ctx.tenant_id if ctx else None)
    preference = getattr(recipient_person, "notification_preference", None)

    is_mandatory = priority in {
        NotificationPriority.TRANSACTIONAL,
        NotificationPriority.EMERGENCY,
    }

    if not is_mandatory and preference:
        channel_allowed = {
            NotificationChannel.SMS: preference.allow_sms,
            NotificationChannel.EMAIL: preference.allow_email,
            NotificationChannel.PUSH: preference.allow_push,
            NotificationChannel.IN_APP: True,
        }.get(channel, True)
        if not channel_allowed:
            return None
        if priority == NotificationPriority.PROMOTIONAL and not preference.allow_promotional:
            return None

    if template_code:
        template = (
            NotificationTemplate.objects.filter(
                tenant_id=tenant_id,
                code=template_code,
                channel=channel,
                is_active=True,
            )
            .order_by("-version_no")
            .first()
        )
        if template:
            subject = render_template(template.subject_template, variables or {})
            body = render_template(template.body_template, variables or {})

    scheduled_at = timezone.now()
    if not is_mandatory and _is_quiet_hour(preference, scheduled_at):
        # به ابتدای پنجره مجاز بعدی موکول می‌شود
        scheduled_at = scheduled_at.replace(
            hour=preference.quiet_hours_end.hour,
            minute=preference.quiet_hours_end.minute,
            second=0,
            microsecond=0,
        )

    return Notification.objects.create(
        tenant_id=tenant_id,
        recipient_person=recipient_person,
        channel=channel,
        priority=priority,
        subject=subject,
        body=body,
        deep_link=deep_link,
        scheduled_at=scheduled_at,
        status=NotificationStatus.QUEUED,
        related_type=related_type,
        related_id=related_id,
    )


def notify_student_guardians(
    student,
    *,
    subject: str,
    body: str,
    channel: str = NotificationChannel.IN_APP,
    priority: str = NotificationPriority.TRANSACTIONAL,
    deep_link: str = "",
) -> int:
    """
    اعلان به اولیای مجاز یک دانش‌آموز.

    بخش ۱۱.۴: «گیرنده اعلان دانش‌آموز از روی رابطه فعال و مجوز دریافت گزارش
    تعیین می‌شود، نه از یک شماره تلفن ثابت روی پرونده.»
    """
    from apps.students.models import StudentGuardian

    links = StudentGuardian.objects.filter(
        student=student, receives_reports=True
    ).select_related("guardian__person")

    sent = 0
    for link in links:
        if link.is_currently_effective and queue_notification(
            recipient_person=link.guardian.person,
            channel=channel,
            subject=subject,
            body=body,
            priority=priority,
            deep_link=deep_link,
            related_type="students.Student",
            related_id=student.id,
            tenant_id=student.tenant_id,
        ):
            sent += 1
    return sent


def generate_ticket_no(tenant_id) -> str:
    from apps.workflow.models import Ticket

    count = Ticket.objects.filter(tenant_id=tenant_id).count()
    return f"TCK-{timezone.now():%Y%m}-{count + 1:05d}"
