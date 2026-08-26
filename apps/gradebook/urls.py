"""مسیرهای دفتر نمره و کارنامه."""

from rest_framework.routers import DefaultRouter

from apps.gradebook.views import (
    AssessmentCategoryViewSet,
    CourseResultViewSet,
    GradebookView,
    GradeItemViewSet,
    ReportCardItemViewSet,
    ReportCardViewSet,
    StudentScoreViewSet,
)

router = DefaultRouter()
router.register("categories", AssessmentCategoryViewSet, basename="assessment-category")
router.register("grade-items", GradeItemViewSet, basename="grade-item")
router.register("scores", StudentScoreViewSet, basename="student-score")
router.register("gradebook", GradebookView, basename="gradebook")
router.register("course-results", CourseResultViewSet, basename="course-result")
router.register("report-cards", ReportCardViewSet, basename="report-card")
router.register("report-card-items", ReportCardItemViewSet, basename="report-card-item")

urlpatterns = router.urls
