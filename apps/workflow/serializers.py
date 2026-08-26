"""سریالایزرهای ماژول گردش کار و ارتباطات."""

from __future__ import annotations

from rest_framework import serializers

from apps.core.serializers import AUDIT_FIELDS
from apps.workflow.models import (
    ApprovalRequest,
    ApprovalStep,
    Attachment,
    DeliveryAttempt,
    IntegrationMessage,
    Notification,
    NotificationPreference,
    NotificationTemplate,
    OutboxEvent,
    Ticket,
    TicketMessage,
    WorkflowDefinition,
)


class WorkflowDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowDefinition
        fields = (
            "id",
            "code",
            "title",
            "version_no",
            "subject_type",
            "steps_definition",
            "is_active",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class ApprovalStepSerializer(serializers.ModelSerializer):
    decision_display = serializers.CharField(
        source="get_decision_display", read_only=True
    )

    class Meta:
        model = ApprovalStep
        fields = (
            "id",
            "request",
            "sequence_no",
            "approver_type",
            "approver_role_code",
            "approver_user_id",
            "decision",
            "decision_display",
            "decided_by_id",
            "decided_on_behalf_of_id",
            "decided_at",
            "comment",
            "due_at",
        )
        read_only_fields = (
            "id",
            "decision",
            "decided_by_id",
            "decided_at",
        )


class ApprovalRequestSerializer(serializers.ModelSerializer):
    steps = ApprovalStepSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    current_step = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalRequest
        fields = (
            "id",
            "subject_type",
            "subject_id",
            "subject_label",
            "workflow_code",
            "workflow_version",
            "workflow_snapshot",
            "requested_by_id",
            "requested_at",
            "status",
            "status_display",
            "completed_at",
            "note",
            "current_step",
            "steps",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "status",
            "completed_at",
            "workflow_snapshot",
            "created_at",
            "updated_at",
            "version",
        )

    def get_current_step(self, obj) -> dict | None:
        step = obj.steps.filter(decision="PENDING").order_by("sequence_no").first()
        if not step:
            return None
        return {
            "id": str(step.id),
            "sequenceNo": step.sequence_no,
            "approverRoleCode": step.approver_role_code,
            "dueAt": step.due_at,
        }


class StartApprovalSerializer(serializers.Serializer):
    subject_type = serializers.CharField(
        max_length=80, help_text="مثلاً finance.Refund"
    )
    subject_id = serializers.UUIDField()
    workflow_code = serializers.CharField(max_length=60)
    subject_label = serializers.CharField(
        max_length=250, required=False, allow_blank=True
    )


class DecideStepSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=["APPROVED", "REJECTED", "RETURNED", "DELEGATED"]
    )
    comment = serializers.CharField(
        max_length=1000, required=False, allow_blank=True
    )
    on_behalf_of_id = serializers.UUIDField(
        required=False, allow_null=True, help_text="در صورت تصمیم به نیابت"
    )


class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        fields = (
            "id",
            "code",
            "title",
            "channel",
            "locale",
            "version_no",
            "subject_template",
            "body_template",
            "is_active",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = ("id", "created_at", "updated_at", "version")


class DeliveryAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryAttempt
        fields = (
            "id",
            "notification",
            "attempt_no",
            "provider",
            "provider_reference",
            "result",
            "error_message",
            "attempted_at",
        )
        read_only_fields = fields


class NotificationSerializer(serializers.ModelSerializer):
    recipient_name = serializers.CharField(
        source="recipient_person.full_name", read_only=True
    )
    channel_display = serializers.CharField(
        source="get_channel_display", read_only=True
    )
    attempts = DeliveryAttemptSerializer(many=True, read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "template",
            "recipient_person",
            "recipient_name",
            "channel",
            "channel_display",
            "priority",
            "subject",
            "body",
            "deep_link",
            "classification",
            "scheduled_at",
            "sent_at",
            "read_at",
            "status",
            "related_type",
            "related_id",
            "attempts",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "sent_at",
            "read_at",
            "status",
            "created_at",
            "updated_at",
            "version",
        )


class BroadcastSerializer(serializers.Serializer):
    """
    ارسال گروهی اعلان.

    بخش ۱۱.۴: «ارسال انبوه دارای پیش‌نمایش تعداد گیرندگان، نمونه پیام، تأیید
    و امکان توقف است.» بنابراین ابتدا `preview` و سپس `confirm=true`.
    """

    audience = serializers.ChoiceField(
        choices=[
            ("CLASS_GUARDIANS", "اولیای یک کلاس"),
            ("GRADE_GUARDIANS", "اولیای یک پایه"),
            ("ALL_STAFF", "همه کارکنان"),
            ("CLASS_STUDENTS", "دانش‌آموزان یک کلاس"),
        ]
    )
    target_id = serializers.UUIDField(
        required=False, allow_null=True, help_text="شناسه کلاس یا پایه"
    )
    channel = serializers.ChoiceField(
        choices=["IN_APP", "SMS", "EMAIL", "PUSH"], default="IN_APP"
    )
    subject = serializers.CharField(max_length=300, required=False, allow_blank=True)
    body = serializers.CharField(max_length=2000)
    priority = serializers.ChoiceField(
        choices=["TRANSACTIONAL", "OPERATIONAL", "PROMOTIONAL", "EMERGENCY"],
        default="OPERATIONAL",
    )
    confirm = serializers.BooleanField(
        default=False,
        help_text="در حالت false فقط پیش‌نمایش تعداد گیرندگان برمی‌گردد.",
    )


class BroadcastPreviewSerializer(serializers.Serializer):
    recipientCount = serializers.IntegerField()
    sampleMessage = serializers.CharField()
    channel = serializers.CharField()
    sent = serializers.BooleanField()


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = (
            "id",
            "person",
            "allow_sms",
            "allow_email",
            "allow_push",
            "allow_promotional",
            "quiet_hours_start",
            "quiet_hours_end",
            "preferred_locale",
        )
        read_only_fields = ("id",)


class AttachmentSerializer(serializers.ModelSerializer):
    is_available = serializers.BooleanField(read_only=True)

    class Meta:
        model = Attachment
        fields = (
            "id",
            "owner_type",
            "owner_id",
            "file",
            "original_name",
            "media_type",
            "size_bytes",
            "sha256",
            "classification",
            "scan_status",
            "scanned_at",
            "is_available",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "sha256",
            "size_bytes",
            "scan_status",
            "scanned_at",
            "created_at",
            "updated_at",
            "version",
        )


class OutboxEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = OutboxEvent
        fields = (
            "id",
            "aggregate_type",
            "aggregate_id",
            "event_type",
            "schema_version",
            "payload",
            "correlation_id",
            "occurred_at",
            "published_at",
            "retry_count",
            "last_error",
        )
        read_only_fields = fields


class IntegrationMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationMessage
        fields = (
            "id",
            "integration_code",
            "direction",
            "external_message_id",
            "correlation_id",
            "status",
            "error_message",
            "received_or_sent_at",
        )
        read_only_fields = ("id", "received_or_sent_at")


class TicketMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketMessage
        fields = (
            "id",
            "ticket",
            "author_user_id",
            "body",
            "is_internal",
            "created_at",
        )
        read_only_fields = ("id", "author_user_id", "created_at")


class TicketSerializer(serializers.ModelSerializer):
    requester_name = serializers.CharField(
        source="requester_person.full_name", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    messages = TicketMessageSerializer(many=True, read_only=True)

    class Meta:
        model = Ticket
        fields = (
            "id",
            "ticket_no",
            "requester_person",
            "requester_name",
            "category",
            "subject",
            "description",
            "priority",
            "status",
            "status_display",
            "assignee_user_id",
            "due_at",
            "resolved_at",
            "resolution",
            "messages",
            *AUDIT_FIELDS[1:],
        )
        read_only_fields = (
            "id",
            "ticket_no",
            "status",
            "resolved_at",
            "created_at",
            "updated_at",
            "version",
        )


class MyTaskSerializer(serializers.Serializer):
    """یک کار در Inbox «کارهای من» (بخش ۶.۲ سند فرانت)."""

    type = serializers.CharField(help_text="APPROVAL | TICKET | ATTENDANCE_PENDING")
    id = serializers.UUIDField()
    title = serializers.CharField()
    subtitle = serializers.CharField(allow_blank=True)
    dueAt = serializers.DateTimeField(allow_null=True)
    priority = serializers.CharField(allow_blank=True)
    link = serializers.CharField(help_text="مسیر پیشنهادی در فرانت")
