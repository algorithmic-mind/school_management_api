"""مسیرهای امور دانش‌آموزان."""

from rest_framework.routers import DefaultRouter

from apps.students.views import (
    AdmissionApplicationViewSet,
    ClassMembershipViewSet,
    ConsentViewSet,
    EnrollmentViewSet,
    GuardianViewSet,
    PromotionBatchViewSet,
    PromotionDecisionRecordViewSet,
    StudentGuardianViewSet,
    StudentTransferViewSet,
    StudentViewSet,
)

router = DefaultRouter()
router.register("students", StudentViewSet, basename="student")
router.register("guardians", GuardianViewSet, basename="guardian")
router.register("student-guardians", StudentGuardianViewSet, basename="student-guardian")
router.register("admissions", AdmissionApplicationViewSet, basename="admission")
router.register("enrollments", EnrollmentViewSet, basename="enrollment")
router.register("class-memberships", ClassMembershipViewSet, basename="class-membership")
router.register("consents", ConsentViewSet, basename="consent")
router.register("transfers", StudentTransferViewSet, basename="student-transfer")
router.register("promotion-batches", PromotionBatchViewSet, basename="promotion-batch")
router.register(
    "promotion-decisions", PromotionDecisionRecordViewSet, basename="promotion-decision"
)

urlpatterns = router.urls
