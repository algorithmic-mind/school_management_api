"""مسیرهای گردش کار و ارتباطات."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.workflow.views import (
    ApprovalRequestViewSet,
    ApprovalStepViewSet,
    AttachmentViewSet,
    IntegrationMessageViewSet,
    MyTasksView,
    NotificationPreferenceViewSet,
    NotificationTemplateViewSet,
    NotificationViewSet,
    OutboxEventViewSet,
    TicketMessageViewSet,
    TicketViewSet,
    WorkflowDefinitionViewSet,
)

router = DefaultRouter()
router.register("workflow-definitions", WorkflowDefinitionViewSet, basename="workflow-definition")
router.register("approvals", ApprovalRequestViewSet, basename="approval-request")
router.register("approval-steps", ApprovalStepViewSet, basename="approval-step")
router.register("notification-templates", NotificationTemplateViewSet, basename="notification-template")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("notification-preferences", NotificationPreferenceViewSet, basename="notification-preference")
router.register("attachments", AttachmentViewSet, basename="attachment")
router.register("outbox-events", OutboxEventViewSet, basename="outbox-event")
router.register("integration-messages", IntegrationMessageViewSet, basename="integration-message")
router.register("tickets", TicketViewSet, basename="ticket")
router.register("ticket-messages", TicketMessageViewSet, basename="ticket-message")

urlpatterns = router.urls + [
    path("my-tasks/", MyTasksView.as_view(), name="my-tasks"),
]
