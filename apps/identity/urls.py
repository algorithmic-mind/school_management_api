"""مسیرهای IAM."""

from rest_framework.routers import DefaultRouter

from apps.identity.views import (
    AccessReviewItemViewSet,
    AccessReviewViewSet,
    AddressViewSet,
    AuditLogViewSet,
    ContactPointViewSet,
    PermissionViewSet,
    PersonAddressViewSet,
    PersonDocumentViewSet,
    PersonViewSet,
    RoleViewSet,
    UserAccountViewSet,
    UserRoleAssignmentViewSet,
)

router = DefaultRouter()
router.register("persons", PersonViewSet, basename="person")
router.register("contact-points", ContactPointViewSet, basename="contact-point")
router.register("addresses", AddressViewSet, basename="address")
router.register("person-addresses", PersonAddressViewSet, basename="person-address")
router.register("person-documents", PersonDocumentViewSet, basename="person-document")
router.register("permissions", PermissionViewSet, basename="permission")
router.register("roles", RoleViewSet, basename="role")
router.register("users", UserAccountViewSet, basename="user")
router.register("role-assignments", UserRoleAssignmentViewSet, basename="role-assignment")
router.register("access-reviews", AccessReviewViewSet, basename="access-review")
router.register("access-review-items", AccessReviewItemViewSet, basename="access-review-item")
router.register("audit-logs", AuditLogViewSet, basename="audit-log")

urlpatterns = router.urls
