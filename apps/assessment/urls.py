"""مسیرهای بانک سؤال و آزمون."""

from rest_framework.routers import DefaultRouter

from apps.assessment.views import (
    AttemptAnswerViewSet,
    ExamAttemptViewSet,
    ExamQuestionViewSet,
    ExamRegistrationViewSet,
    ExamSectionViewSet,
    ExamSessionViewSet,
    ExamViewSet,
    GradeAppealViewSet,
    GradeReviewViewSet,
    ProctorEventViewSet,
    QuestionBankViewSet,
    QuestionOptionViewSet,
    QuestionTagViewSet,
    QuestionVersionViewSet,
    QuestionViewSet,
)

router = DefaultRouter()
router.register("question-banks", QuestionBankViewSet, basename="question-bank")
router.register("question-tags", QuestionTagViewSet, basename="question-tag")
router.register("questions", QuestionViewSet, basename="question")
router.register("question-versions", QuestionVersionViewSet, basename="question-version")
router.register("question-options", QuestionOptionViewSet, basename="question-option")
router.register("exams", ExamViewSet, basename="exam")
router.register("exam-sections", ExamSectionViewSet, basename="exam-section")
router.register("exam-questions", ExamQuestionViewSet, basename="exam-question")
router.register("exam-sessions", ExamSessionViewSet, basename="exam-session")
router.register("exam-registrations", ExamRegistrationViewSet, basename="exam-registration")
router.register("attempts", ExamAttemptViewSet, basename="exam-attempt")
router.register("attempt-answers", AttemptAnswerViewSet, basename="attempt-answer")
router.register("proctor-events", ProctorEventViewSet, basename="proctor-event")
router.register("grade-reviews", GradeReviewViewSet, basename="grade-review")
router.register("appeals", GradeAppealViewSet, basename="grade-appeal")

urlpatterns = router.urls
