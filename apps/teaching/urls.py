"""مسیرهای آموزش روزانه، حضور و تکلیف."""

from rest_framework.routers import DefaultRouter

from apps.teaching.views import (
    AbsenceJustificationViewSet,
    AssignmentSubmissionViewSet,
    AssignmentViewSet,
    AttendanceRecordViewSet,
    LearningResourceViewSet,
    LessonPlanViewSet,
    SessionTeacherViewSet,
    SubmissionFeedbackViewSet,
    TeachingSessionViewSet,
)

router = DefaultRouter()
router.register("sessions", TeachingSessionViewSet, basename="teaching-session")
router.register("session-teachers", SessionTeacherViewSet, basename="session-teacher")
router.register("attendance", AttendanceRecordViewSet, basename="attendance-record")
router.register("justifications", AbsenceJustificationViewSet, basename="absence-justification")
router.register("lesson-plans", LessonPlanViewSet, basename="lesson-plan")
router.register("assignments", AssignmentViewSet, basename="assignment")
router.register("submissions", AssignmentSubmissionViewSet, basename="assignment-submission")
router.register("feedbacks", SubmissionFeedbackViewSet, basename="submission-feedback")
router.register("resources", LearningResourceViewSet, basename="learning-resource")

urlpatterns = router.urls
