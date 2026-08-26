"""Viewهای ماژول گردش کار، اعلان و تیکت."""

from __future__ import annotations

import django_filters as filters
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessRuleViolation
from apps.core.pagination import AuditCursorPagination, TimelineCursorPagination
from apps.core.serializers import ErrorResponseSerializer, OperationResultSerializer
from apps.core.viewsets import BaseModelViewSet, BaseReadOnlyViewSet
from apps.workflow import services
from apps.workflow.enums import ApprovalStatus, NotificationStatus, TicketStatus
from apps.workflow.models import (
    ApprovalRequest,
    ApprovalStep,
    Attachment,
    IntegrationMessage,
    Notification,
    NotificationPreference,
    NotificationTemplate,
    OutboxEvent,
    Ticket,
    TicketMessage,
    WorkflowDefinition,
)
from apps.workflow.serializers import (
    ApprovalRequestSerializer,
    ApprovalStepSerializer,
    AttachmentSerializer,
    BroadcastPreviewSerializer,
    BroadcastSerializer,
    DecideStepSerializer,
    IntegrationMessageSerializer,
    MyTaskSerializer,
    NotificationPreferenceSerializer,
    NotificationSerializer,
    NotificationTemplateSerializer,
    OutboxEventSerializer,
    StartApprovalSerializer,
    TicketMessageSerializer,
    TicketSerializer,
    WorkflowDefinitionSerializer,
)

ERRORS = {
    400: OpenApiResponse(ErrorResponseSerializer, description="داده ورودی معتبر نیست"),
    403: OpenApiResponse(ErrorResponseSerializer, description="بدون مجوز"),
    404: OpenApiResponse(ErrorResponseSerializer, description="یافت نشد"),
    409: OpenApiResponse(ErrorResponseSerializer, description="تعارض وضعیت"),
    422: OpenApiResponse(ErrorResponseSerializer, description="نقض قاعده کسب‌وکار"),
}


@extend_schema_view(
    list=extend_schema(tags=["Workflow"], summary="تعاریف گردش تأیید"),
    create=extend_schema(
        tags=["Workflow"],
        summary="تعریف گردش تأیید",
        description=(
            "`stepsDefinition` آرایه‌ای از گام‌هاست، مثلاً:\n"
            '`[{"sequence": 1, "roleCode": "ACCOUNTANT"}, '
            '{"sequence": 2, "roleCode": "PRINCIPAL"}]`'
        ),
    ),
)
class WorkflowDefinitionViewSet(BaseModelViewSet):
    queryset = WorkflowDefinition.objects.all()
    serializer_class = WorkflowDefinitionSerializer
    filterset_fields = ("code", "subject_type", "is_active")
    permission_resource = "approval"


@extend_schema_view(
    list=extend_schema(tags=["Workflow"], summary="درخواست‌های تأیید"),
    retrieve=extend_schema(tags=["Workflow"], summary="جزئیات درخواست تأیید"),
)
class ApprovalRequestViewSet(BaseModelViewSet):
    queryset = ApprovalRequest.objects.prefetch_related("steps")
    serializer_class = ApprovalRequestSerializer
    filterset_fields = ("subject_type", "subject_id", "workflow_code", "status")
    permission_resource = "approval"
    permission_map = {"start": "approval.request", "cancel": "approval.request"}
    http_method_names = ["get", "post", "head", "options"]

    @extend_schema(
        tags=["Workflow"],
        summary="شروع گردش تأیید",
        description=(
            "نسخه فعال تعریف گردش Snapshot می‌شود و گام‌ها ساخته می‌شوند "
            "(بخش ۷.۱۱)."
        ),
        request=StartApprovalSerializer,
        responses={201: ApprovalRequestSerializer, **ERRORS},
    )
    @action(detail=False, methods=["post"], url_path="start")
    def start(self, request):
        body = StartApprovalSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        approval = services.start_approval(
            subject_type=body.validated_data["subject_type"],
            subject_id=body.validated_data["subject_id"],
            workflow_code=body.validated_data["workflow_code"],
            subject_label=body.validated_data.get("subject_label", ""),
        )
        return Response(ApprovalRequestSerializer(approval).data, status=201)

    @extend_schema(
        tags=["Workflow"],
        summary="لغو درخواست تأیید",
        request=None,
        responses={200: ApprovalRequestSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        approval = self.get_object()
        if approval.status != ApprovalStatus.PENDING:
            raise BusinessRuleViolation(
                code="APPROVAL_ALREADY_COMPLETED",
                message="فقط درخواست در جریان قابل لغو است.",
                status_code=409,
            )
        approval.status = ApprovalStatus.CANCELLED
        approval.completed_at = timezone.now()
        approval.save(update_fields=["status", "completed_at"])
        return Response(self.get_serializer(approval).data)


@extend_schema_view(list=extend_schema(tags=["Workflow"], summary="گام‌های تأیید"))
class ApprovalStepViewSet(BaseModelViewSet):
    queryset = ApprovalStep.objects.select_related("request")
    serializer_class = ApprovalStepSerializer
    filterset_fields = ("request", "decision", "approver_role_code", "approver_user_id")
    permission_resource = "approval"
    permission_map = {"decide": "approval.decide"}
    http_method_names = ["get", "post", "head", "options"]

    @extend_schema(
        tags=["Workflow"],
        summary="ثبت تصمیم گام تأیید",
        description=(
            "گام‌ها به ترتیب `sequenceNo` تصمیم‌گیری می‌شوند. رد یک گام، کل "
            "درخواست را رد می‌کند. با تکمیل همه گام‌ها رویداد "
            "`ApprovalCompleted` منتشر می‌شود."
        ),
        request=DecideStepSerializer,
        responses={200: ApprovalRequestSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        step = self.get_object()
        body = DecideStepSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        # تفکیک وظایف: ایجادکننده نباید تأییدکننده نهایی باشد (بخش ۳.۲ و ۱۶.۲)
        if step.request.requested_by_id == request.user.id:
            raise BusinessRuleViolation(
                code="SEGREGATION_OF_DUTIES",
                message="ایجادکننده درخواست نمی‌تواند تأییدکننده همان درخواست باشد.",
                status_code=403,
            )

        approval = services.decide_step(
            step,
            body.validated_data["decision"],
            body.validated_data.get("comment", ""),
            actor_user_id=request.user.id,
            on_behalf_of_id=body.validated_data.get("on_behalf_of_id"),
        )
        return Response(ApprovalRequestSerializer(approval).data)


@extend_schema_view(list=extend_schema(tags=["Workflow"], summary="قالب‌های اعلان"))
class NotificationTemplateViewSet(BaseModelViewSet):
    queryset = NotificationTemplate.objects.all()
    serializer_class = NotificationTemplateSerializer
    filterset_fields = ("code", "channel", "locale", "is_active")
    permission_resource = "notification"


class NotificationFilter(filters.FilterSet):
    unread = filters.BooleanFilter(method="filter_unread", label="فقط خوانده‌نشده")

    class Meta:
        model = Notification
        fields = ("recipient_person", "channel", "status", "priority", "related_type")

    def filter_unread(self, queryset, name, value):
        return queryset.filter(read_at__isnull=value)


@extend_schema_view(
    list=extend_schema(
        tags=["Workflow"],
        summary="فهرست اعلان‌ها",
        description="صفحه‌بندی Cursor؛ برای مرکز اعلان و زنگوله هدر.",
    ),
    retrieve=extend_schema(tags=["Workflow"], summary="جزئیات اعلان"),
)
class NotificationViewSet(BaseModelViewSet):
    queryset = Notification.objects.select_related("recipient_person").prefetch_related(
        "attempts"
    )
    serializer_class = NotificationSerializer
    filterset_class = NotificationFilter
    pagination_class = TimelineCursorPagination
    permission_resource = "notification"
    permission_map = {"broadcast": "notification.broadcast", "mark_read": "notification.read"}

    @extend_schema(
        tags=["Workflow"],
        summary="اعلان‌های من",
        description="اعلان‌های کاربر جاری بر اساس شخصِ متصل به حساب کاربری.",
        responses={200: NotificationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="mine")
    def mine(self, request):
        queryset = self.filter_queryset(
            self.get_queryset().filter(recipient_person_id=request.user.person_id)
        )
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        tags=["Workflow"],
        summary="علامت‌گذاری به‌عنوان خوانده‌شده",
        request=None,
        responses={200: NotificationSerializer},
    )
    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.read_at = timezone.now()
        notification.status = NotificationStatus.READ
        notification.save(update_fields=["read_at", "status"])
        return Response(self.get_serializer(notification).data)

    @extend_schema(
        tags=["Workflow"],
        summary="ارسال گروهی اعلان",
        description=(
            "دو مرحله‌ای است (بخش ۱۱.۴): با `confirm=false` فقط تعداد گیرندگان "
            "و نمونه پیام برمی‌گردد؛ با `confirm=true` ارسال انجام می‌شود."
        ),
        request=BroadcastSerializer,
        responses={200: BroadcastPreviewSerializer, **ERRORS},
        examples=[
            OpenApiExample(
                "پیش‌نمایش",
                value={
                    "audience": "CLASS_GUARDIANS",
                    "target_id": "0a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
                    "channel": "SMS",
                    "body": "جلسه اولیا و مربیان روز چهارشنبه ساعت ۱۶ برگزار می‌شود.",
                    "confirm": False,
                },
                request_only=True,
            )
        ],
    )
    @action(detail=False, methods=["post"])
    def broadcast(self, request):
        body = BroadcastSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data

        recipients = self._resolve_audience(data["audience"], data.get("target_id"))

        if not data["confirm"]:
            return Response(
                {
                    "recipientCount": len(recipients),
                    "sampleMessage": data["body"],
                    "channel": data["channel"],
                    "sent": False,
                }
            )

        sent = 0
        for person in recipients:
            if services.queue_notification(
                recipient_person=person,
                channel=data["channel"],
                subject=data.get("subject", ""),
                body=data["body"],
                priority=data["priority"],
            ):
                sent += 1

        return Response(
            {
                "recipientCount": len(recipients),
                "sampleMessage": data["body"],
                "channel": data["channel"],
                "sent": True,
            }
        )

    @staticmethod
    def _resolve_audience(audience: str, target_id) -> list:
        from apps.hr.enums import EmployeeStatus
        from apps.identity.models import Person
        from apps.students.models import ClassMembership, StudentGuardian

        if audience == "CLASS_GUARDIANS":
            student_ids = ClassMembership.objects.filter(
                class_group_id=target_id, status="ACTIVE"
            ).values_list("enrollment__student_id", flat=True)
            return list(
                Person.objects.filter(
                    guardian_profile__student_links__student_id__in=student_ids,
                    guardian_profile__student_links__receives_reports=True,
                ).distinct()
            )
        if audience == "GRADE_GUARDIANS":
            student_ids = StudentGuardian.objects.filter(
                student__enrollments__grade_level_id=target_id
            ).values_list("student_id", flat=True)
            return list(
                Person.objects.filter(
                    guardian_profile__student_links__student_id__in=student_ids
                ).distinct()
            )
        if audience == "CLASS_STUDENTS":
            return list(
                Person.objects.filter(
                    student_profile__enrollments__class_memberships__class_group_id=target_id,
                    student_profile__enrollments__class_memberships__status="ACTIVE",
                ).distinct()
            )
        if audience == "ALL_STAFF":
            return list(
                Person.objects.filter(
                    employee_profile__status=EmployeeStatus.ACTIVE
                ).distinct()
            )
        return []


@extend_schema_view(
    list=extend_schema(tags=["Workflow"], summary="ترجیحات اعلان"),
)
class NotificationPreferenceViewSet(BaseModelViewSet):
    queryset = NotificationPreference.objects.select_related("person")
    serializer_class = NotificationPreferenceSerializer
    filterset_fields = ("person",)
    permission_resource = "notification"


@extend_schema_view(
    list=extend_schema(tags=["Workflow"], summary="پیوست‌ها"),
    create=extend_schema(
        tags=["Workflow"],
        summary="بارگذاری پیوست",
        description=(
            "فایل تا تکمیل اسکن بدافزار (`scanStatus = CLEAN`) در دسترس کاربر "
            "نهایی قرار نمی‌گیرد (بخش ۷.۱۱)."
        ),
    ),
)
class AttachmentViewSet(BaseModelViewSet):
    queryset = Attachment.objects.all()
    serializer_class = AttachmentSerializer
    filterset_fields = ("owner_type", "owner_id", "classification", "scan_status")
    permission_resource = "attachment"


@extend_schema_view(
    list=extend_schema(
        tags=["Workflow"],
        summary="رویدادهای Outbox",
        description="برای پایش عملیاتی انتشار رویدادها و Dead Letter (بخش ۱۳.۲).",
    )
)
class OutboxEventViewSet(BaseReadOnlyViewSet):
    # OutboxEvent فیلد created_at ندارد؛ صفحه‌بندی Cursor باید روی occurred_at
    # مرتب شود.
    queryset = OutboxEvent.objects.all()
    serializer_class = OutboxEventSerializer
    filterset_fields = ("aggregate_type", "aggregate_id", "event_type")
    pagination_class = AuditCursorPagination
    permission_resource = "report"


@extend_schema_view(
    list=extend_schema(tags=["Workflow"], summary="پیام‌های یکپارچه‌سازی")
)
class IntegrationMessageViewSet(BaseReadOnlyViewSet):
    queryset = IntegrationMessage.objects.all()
    serializer_class = IntegrationMessageSerializer
    filterset_fields = ("integration_code", "direction", "status")
    permission_resource = "report"


@extend_schema_view(
    list=extend_schema(tags=["Workflow"], summary="فهرست تیکت‌ها"),
    create=extend_schema(tags=["Workflow"], summary="ثبت تیکت جدید"),
)
class TicketViewSet(BaseModelViewSet):
    queryset = Ticket.objects.select_related("requester_person").prefetch_related(
        "messages"
    )
    serializer_class = TicketSerializer
    filterset_fields = ("category", "status", "priority", "assignee_user_id")
    search_fields = ("ticket_no", "subject")
    permission_resource = "approval"

    def perform_create(self, serializer):
        from apps.core.context import get_current_context

        ctx = get_current_context()
        serializer.save(
            tenant_id=ctx.tenant_id if ctx else None,
            ticket_no=services.generate_ticket_no(ctx.tenant_id if ctx else None),
        )

    @extend_schema(
        tags=["Workflow"],
        summary="بستن تیکت",
        request=None,
        responses={200: TicketSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        ticket = self.get_object()
        ticket.status = TicketStatus.RESOLVED
        ticket.resolved_at = timezone.now()
        ticket.resolution = request.data.get("resolution", "")
        ticket.save(update_fields=["status", "resolved_at", "resolution"])
        return Response(self.get_serializer(ticket).data)


@extend_schema_view(list=extend_schema(tags=["Workflow"], summary="پیام‌های تیکت"))
class TicketMessageViewSet(BaseModelViewSet):
    queryset = TicketMessage.objects.select_related("ticket")
    serializer_class = TicketMessageSerializer
    filterset_fields = ("ticket", "is_internal")
    permission_resource = "approval"

    def perform_create(self, serializer):
        from apps.core.context import get_current_context

        ctx = get_current_context()
        serializer.save(
            tenant_id=ctx.tenant_id if ctx else None,
            author_user_id=self.request.user.id,
        )


@extend_schema(
    tags=["Workflow"],
    summary="کارهای من (Inbox یکپارچه)",
    description=(
        "همه کارهای در انتظار کاربر جاری در یک فهرست: تأییدهای منتظر تصمیم، "
        "تیکت‌های ارجاع‌شده و جلسات با حضور ثبت‌نشده (بخش ۶.۲ سند فرانت)."
    ),
    responses={200: MyTaskSerializer(many=True)},
)
class MyTasksView(APIView):
    def get(self, request):
        user = request.user
        role_codes = {s["role__code"] for s in user.get_effective_scopes()}
        tasks: list[dict] = []

        pending_steps = (
            ApprovalStep.objects.filter(decision="PENDING")
            .filter(request__status=ApprovalStatus.PENDING)
            .select_related("request")
        )
        for step in pending_steps:
            is_mine = (
                step.approver_user_id == user.id
                or (step.approver_role_code and step.approver_role_code in role_codes)
            )
            if not is_mine:
                continue
            tasks.append(
                {
                    "type": "APPROVAL",
                    "id": step.id,
                    "title": f"تأیید: {step.request.subject_label or step.request.workflow_code}",
                    "subtitle": step.request.subject_type,
                    "dueAt": step.due_at,
                    "priority": "NORMAL",
                    "link": f"/app/tasks/approvals/{step.request_id}",
                }
            )

        tickets = Ticket.objects.filter(
            assignee_user_id=user.id,
            status__in=[TicketStatus.OPEN, TicketStatus.IN_PROGRESS],
        )
        for ticket in tickets:
            tasks.append(
                {
                    "type": "TICKET",
                    "id": ticket.id,
                    "title": ticket.subject,
                    "subtitle": ticket.category,
                    "dueAt": ticket.due_at,
                    "priority": ticket.priority,
                    "link": f"/app/tasks/tickets/{ticket.id}",
                }
            )

        if user.person_id:
            from apps.teaching.models import TeachingSession

            sessions = TeachingSession.objects.filter(
                teachers__teacher_profile__employee__person_id=user.person_id,
                attendance_finalized_at__isnull=True,
                starts_at__lte=timezone.now(),
            ).select_related("course_offering__course", "course_offering__class_group")[:50]
            for session in sessions:
                tasks.append(
                    {
                        "type": "ATTENDANCE_PENDING",
                        "id": session.id,
                        "title": (
                            f"ثبت حضور: {session.course_offering.class_group.code} — "
                            f"{session.course_offering.course.title}"
                        ),
                        "subtitle": timezone.localtime(session.starts_at).strftime(
                            "%Y-%m-%d %H:%M"
                        ),
                        "dueAt": session.ends_at,
                        "priority": "HIGH",
                        "link": f"/app/attendance/{session.id}",
                    }
                )

        return Response(tasks)
