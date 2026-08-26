"""مسیرهای خدمات دانش‌آموزی."""

from rest_framework.routers import DefaultRouter

from apps.welfare.views import (
    BehaviorActionViewSet,
    BehaviorIncidentViewSet,
    CounselingCaseViewSet,
    CounselingSessionViewSet,
    HealthAlertViewSet,
    HealthIncidentViewSet,
    HealthProfileViewSet,
    LibraryCopyViewSet,
    LibraryLoanViewSet,
    LibraryTitleViewSet,
    RidershipEventViewSet,
    RouteRunViewSet,
    RouteStopViewSet,
    StudentRouteAssignmentViewSet,
    TransportRouteViewSet,
    VehicleViewSet,
)

router = DefaultRouter()
router.register("health-profiles", HealthProfileViewSet, basename="health-profile")
router.register("health-alerts", HealthAlertViewSet, basename="health-alert")
router.register("health-incidents", HealthIncidentViewSet, basename="health-incident")
router.register("counseling-cases", CounselingCaseViewSet, basename="counseling-case")
router.register("counseling-sessions", CounselingSessionViewSet, basename="counseling-session")
router.register("behavior-incidents", BehaviorIncidentViewSet, basename="behavior-incident")
router.register("behavior-actions", BehaviorActionViewSet, basename="behavior-action")
router.register("library-titles", LibraryTitleViewSet, basename="library-title")
router.register("library-copies", LibraryCopyViewSet, basename="library-copy")
router.register("library-loans", LibraryLoanViewSet, basename="library-loan")
router.register("vehicles", VehicleViewSet, basename="vehicle")
router.register("routes", TransportRouteViewSet, basename="transport-route")
router.register("route-stops", RouteStopViewSet, basename="route-stop")
router.register("route-assignments", StudentRouteAssignmentViewSet, basename="route-assignment")
router.register("route-runs", RouteRunViewSet, basename="route-run")
router.register("ridership-events", RidershipEventViewSet, basename="ridership-event")

urlpatterns = router.urls
