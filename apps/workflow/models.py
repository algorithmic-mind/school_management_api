"""
مدل‌های گردش تأیید، اعلان، فایل و یکپارچه‌سازی.

مرجع: بخش ۷.۱۱ سند تحلیل.

قیدهای مهم:
- نسخه گردش تأیید هنگام شروع Snapshot می‌شود.
- اعلان تراکنشی با تبلیغاتی مخلوط نمی‌شود و قواعد Opt-out متفاوت دارد.
- payload رویداد Outbox فاقد داده حساس غیرضروری است.
- فایل تا تکمیل اسکن بدافزار در دسترس کاربر نهایی قرار نمی‌گیرد.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.enums import ApprovalDecision, DataClassification, NotificationChannel
from apps.core.models import BaseTenantModel, Tenant, UUIDModel
from apps.identity.models import Person
from apps.workflow.enums import (
    ApprovalStatus,
    DeliveryResult,
    IntegrationDirection,
    IntegrationStatus,
    NotificationPriority,
    NotificationStatus,
    ScanStatus,
    TicketPriority,
    TicketStatus,
)


class WorkflowDefinition(BaseTenantModel):
    """تعریف نسخه‌دار گردش تأیید."""

    code = models.CharField(max_length=60, db_index=True, verbose_name=_("کد گردش"))
    title = models.CharField(max_length=200)
    version_no = models.PositiveSmallIntegerField(default=1)
    subject_type = models.CharField(
        max_length=80,
        verbose_name=_("نوع موضوع"),
        help_text=_("مثلاً finance.Refund یا inventory.PurchaseRequest"),
    )
    steps_definition = models.JSONField(
        default=list,
        verbose_name=_("تعریف گام‌ها"),
        help_text=_('مثلاً [{"sequence": 1, "roleCode": "ACCOUNTANT"}]'),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("تعریف گردش تأیید")
        verbose_name_plural = _("تعاریف گردش تأیید")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code", "version_no"], name="uq_workflow_code_version"
            )
        ]

    def __str__(self) -> str:
        return f"{self.code} v{self.version_no}"


class ApprovalRequest(BaseTenantModel):
    """درخواست تأیید برای یک موضوع."""

    subject_type = models.CharField(max_length=80, db_index=True)
    subject_id = models.UUIDField(db_index=True)
    subject_label = models.CharField(max_length=250, blank=True)
    workflow_code = models.CharField(max_length=60)
    workflow_version = models.PositiveSmallIntegerField(default=1)
    workflow_snapshot = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Snapshot تعریف گردش در زمان شروع"),
    )
    requested_by_id = models.UUIDField(null=True, blank=True)
    requested_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=400, blank=True)

    class Meta:
        verbose_name = _("درخواست تأیید")
        verbose_name_plural = _("درخواست‌های تأیید")
        ordering = ("-requested_at",)
        indexes = [
            models.Index(fields=["subject_type", "subject_id"]),
            models.Index(fields=["status", "-requested_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.workflow_code} — {self.subject_label or self.subject_id}"


class ApprovalStep(BaseTenantModel):
    """
    گام تأیید.

    بخش ۷.۱۱: «تأییدکننده غایب می‌تواند جانشین زمان‌دار داشته باشد؛ تصمیم به
    نام تصمیم‌گیرنده واقعی ثبت می‌شود.»
    """

    request = models.ForeignKey(
        ApprovalRequest, on_delete=models.CASCADE, related_name="steps"
    )
    sequence_no = models.PositiveSmallIntegerField()
    approver_type = models.CharField(
        max_length=20,
        default="ROLE",
        help_text=_("ROLE یا USER"),
    )
    approver_role_code = models.CharField(max_length=60, blank=True)
    approver_user_id = models.UUIDField(null=True, blank=True)
    decision = models.CharField(
        max_length=20,
        choices=ApprovalDecision.choices,
        default=ApprovalDecision.PENDING,
    )
    decided_by_id = models.UUIDField(
        null=True, blank=True, verbose_name=_("تصمیم‌گیرنده واقعی")
    )
    decided_on_behalf_of_id = models.UUIDField(
        null=True, blank=True, verbose_name=_("به نیابت از")
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("گام تأیید")
        verbose_name_plural = _("گام‌های تأیید")
        ordering = ("sequence_no",)
        constraints = [
            models.UniqueConstraint(
                fields=["request", "sequence_no"], name="uq_approval_step_sequence"
            )
        ]

    def __str__(self) -> str:
        return f"گام {self.sequence_no} — {self.get_decision_display()}"


class NotificationTemplate(BaseTenantModel):
    """قالب نسخه‌دار پیام."""

    code = models.CharField(max_length=60, db_index=True)
    title = models.CharField(max_length=200)
    channel = models.CharField(max_length=15, choices=NotificationChannel.choices)
    locale = models.CharField(max_length=10, default="fa")
    version_no = models.PositiveSmallIntegerField(default=1)
    subject_template = models.CharField(max_length=300, blank=True)
    body_template = models.TextField(
        verbose_name=_("متن قالب"),
        help_text=_("متغیرها با {{variable}} نوشته می‌شوند."),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("قالب اعلان")
        verbose_name_plural = _("قالب‌های اعلان")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code", "channel", "locale", "version_no"],
                name="uq_notification_template",
            )
        ]

    def __str__(self) -> str:
        return f"{self.code} ({self.channel})"


class Notification(BaseTenantModel):
    """
    یک اعلان برای یک گیرنده.

    بخش ۱۱.۴: «متن کامل اطلاعات حساس در Push/SMS قرار نمی‌گیرد؛ پیام کاربر را
    به پرتال امن هدایت می‌کند.»
    """

    template = models.ForeignKey(
        NotificationTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    recipient_person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="notifications"
    )
    channel = models.CharField(max_length=15, choices=NotificationChannel.choices)
    priority = models.CharField(
        max_length=20,
        choices=NotificationPriority.choices,
        default=NotificationPriority.OPERATIONAL,
    )
    subject = models.CharField(max_length=300, blank=True)
    body = models.TextField(verbose_name=_("متن رندرشده"))
    deep_link = models.CharField(
        max_length=400, blank=True, verbose_name=_("پیوند پرتال امن")
    )
    classification = models.CharField(
        max_length=20,
        choices=DataClassification.choices,
        default=DataClassification.INTERNAL,
    )
    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=NotificationStatus.choices,
        default=NotificationStatus.QUEUED,
        db_index=True,
    )
    related_type = models.CharField(max_length=80, blank=True)
    related_id = models.UUIDField(null=True, blank=True)

    class Meta:
        verbose_name = _("اعلان")
        verbose_name_plural = _("اعلان‌ها")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["recipient_person", "status"]),
            models.Index(fields=["status", "scheduled_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.subject or self.body[:40]} → {self.recipient_person}"


class DeliveryAttempt(BaseTenantModel):
    """تلاش ارسال اعلان از طریق یک ارائه‌دهنده."""

    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name="attempts"
    )
    attempt_no = models.PositiveSmallIntegerField(default=1)
    provider = models.CharField(max_length=60)
    provider_reference = models.CharField(max_length=200, blank=True)
    result = models.CharField(max_length=20, choices=DeliveryResult.choices)
    error_message = models.CharField(max_length=400, blank=True)
    attempted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = _("تلاش ارسال")
        verbose_name_plural = _("تلاش‌های ارسال")
        ordering = ("-attempted_at",)


class NotificationPreference(BaseTenantModel):
    """
    ترجیح کانال و ساعات سکوت گیرنده.

    بخش ۱۱.۴: «ترجیح کانال، ساعات سکوت، زبان ترجیحی و الزام قانونی پیام در
    تصمیم ارسال لحاظ می‌شود.»
    """

    person = models.OneToOneField(
        Person, on_delete=models.CASCADE, related_name="notification_preference"
    )
    allow_sms = models.BooleanField(default=True)
    allow_email = models.BooleanField(default=True)
    allow_push = models.BooleanField(default=True)
    allow_promotional = models.BooleanField(default=False)
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    preferred_locale = models.CharField(max_length=10, default="fa")

    class Meta:
        verbose_name = _("ترجیح اعلان")
        verbose_name_plural = _("ترجیحات اعلان")


class Attachment(BaseTenantModel):
    """
    پیوست عمومی با فراداده و وضعیت اسکن.

    بخش ۵.۱: «فایل‌ها در Object Storage نگهداری و در پایگاه داده فقط فراداده،
    هش، مالک، طبقه‌بندی و مجوز ذخیره می‌شود.»
    """

    owner_type = models.CharField(max_length=80, db_index=True)
    owner_id = models.UUIDField(db_index=True)
    file = models.FileField(upload_to="attachments/")
    original_name = models.CharField(max_length=250, blank=True)
    media_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    classification = models.CharField(
        max_length=20,
        choices=DataClassification.choices,
        default=DataClassification.INTERNAL,
    )
    scan_status = models.CharField(
        max_length=15, choices=ScanStatus.choices, default=ScanStatus.PENDING
    )
    scanned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("پیوست")
        verbose_name_plural = _("پیوست‌ها")
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["owner_type", "owner_id"])]

    def __str__(self) -> str:
        return self.original_name or str(self.file)

    @property
    def is_available(self) -> bool:
        """فایل تا تکمیل اسکن سالم در دسترس نیست (بخش ۷.۱۱)."""
        return self.scan_status == ScanStatus.CLEAN


class OutboxEvent(UUIDModel):
    """
    رویداد دامنه‌ای در الگوی Transactional Outbox.

    بخش ۱۳.۲: «انتشار حداقل یک‌بار است؛ مصرف‌کننده باید تکرار را تشخیص دهد.»
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="outbox_events", null=True
    )
    aggregate_type = models.CharField(max_length=80, db_index=True)
    aggregate_id = models.UUIDField(db_index=True)
    event_type = models.CharField(max_length=80, db_index=True)
    schema_version = models.PositiveSmallIntegerField(default=1)
    payload = models.JSONField(default=dict)
    correlation_id = models.CharField(max_length=64, blank=True)
    causation_id = models.CharField(max_length=64, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=400, blank=True)

    class Meta:
        verbose_name = _("رویداد Outbox")
        verbose_name_plural = _("رویدادهای Outbox")
        ordering = ("occurred_at",)
        indexes = [
            models.Index(fields=["published_at", "occurred_at"]),
            models.Index(fields=["aggregate_type", "aggregate_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} @ {self.occurred_at:%Y-%m-%d %H:%M}"


class IntegrationMessage(BaseTenantModel):
    """پیام یکپارچه‌سازی با سرویس خارجی."""

    integration_code = models.CharField(max_length=60, db_index=True)
    direction = models.CharField(max_length=15, choices=IntegrationDirection.choices)
    external_message_id = models.CharField(max_length=200, blank=True, db_index=True)
    correlation_id = models.CharField(max_length=64, blank=True)
    payload_digest = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=20,
        choices=IntegrationStatus.choices,
        default=IntegrationStatus.RECEIVED,
    )
    error_message = models.CharField(max_length=400, blank=True)
    received_or_sent_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = _("پیام یکپارچه‌سازی")
        verbose_name_plural = _("پیام‌های یکپارچه‌سازی")
        ordering = ("-received_or_sent_at",)


class Ticket(BaseTenantModel):
    """تیکت و درخواست خدمت (بخش ۴.۸)."""

    ticket_no = models.CharField(max_length=30, db_index=True)
    requester_person = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name="tickets"
    )
    category = models.CharField(max_length=60, verbose_name=_("دسته درخواست"))
    subject = models.CharField(max_length=250)
    description = models.TextField(blank=True)
    priority = models.CharField(
        max_length=15, choices=TicketPriority.choices, default=TicketPriority.NORMAL
    )
    status = models.CharField(
        max_length=25, choices=TicketStatus.choices, default=TicketStatus.OPEN
    )
    assignee_user_id = models.UUIDField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True, verbose_name=_("مهلت SLA"))
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution = models.TextField(blank=True)

    class Meta:
        verbose_name = _("تیکت")
        verbose_name_plural = _("تیکت‌ها")
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "ticket_no"], name="uq_ticket_tenant_no"
            )
        ]

    def __str__(self) -> str:
        return f"{self.ticket_no} — {self.subject}"


class TicketMessage(BaseTenantModel):
    """پیام‌های رفت‌وبرگشت یک تیکت."""

    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="messages"
    )
    author_user_id = models.UUIDField(null=True, blank=True)
    body = models.TextField()
    is_internal = models.BooleanField(
        default=False, verbose_name=_("یادداشت داخلی (برای درخواست‌کننده نمایش داده نمی‌شود)")
    )

    class Meta:
        verbose_name = _("پیام تیکت")
        verbose_name_plural = _("پیام‌های تیکت")
        ordering = ("created_at",)
