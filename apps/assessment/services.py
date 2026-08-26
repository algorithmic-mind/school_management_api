"""
قواعد کسب‌وکار آزمون.

مرجع: بخش ۷.۶ (قیدها)، ۹.۴ (اجرای آزمون آنلاین)، ۱۰.۳ و ۱۰.۴ (ماشین حالت).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.assessment.enums import (
    AUTO_GRADED_TYPES,
    AttemptStatus,
    ExamStatus,
    GradingStatus,
    QuestionType,
)
from apps.assessment.models import (
    AttemptAnswer,
    Exam,
    ExamAttempt,
    ExamQuestion,
    ExamRegistration,
)
from apps.core.exceptions import BusinessRuleViolation, InvalidStateTransition

# ---------------------------------------------------------------------------
# ماشین حالت آزمون — بخش ۱۰.۳
# ---------------------------------------------------------------------------
EXAM_TRANSITIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "submit_for_review": ((ExamStatus.DRAFT,), ExamStatus.UNDER_REVIEW),
    "request_changes": ((ExamStatus.UNDER_REVIEW,), ExamStatus.DRAFT),
    "approve": ((ExamStatus.UNDER_REVIEW,), ExamStatus.APPROVED),
    "schedule": ((ExamStatus.APPROVED,), ExamStatus.SCHEDULED),
    "publish": ((ExamStatus.SCHEDULED,), ExamStatus.PUBLISHED),
    "cancel": (
        (ExamStatus.DRAFT, ExamStatus.APPROVED, ExamStatus.SCHEDULED, ExamStatus.PUBLISHED),
        ExamStatus.CANCELLED,
    ),
    "close_submission": (
        (ExamStatus.PUBLISHED, ExamStatus.IN_PROGRESS),
        ExamStatus.SUBMISSION_CLOSED,
    ),
    "start_grading": (
        (ExamStatus.SUBMISSION_CLOSED, ExamStatus.PUBLISHED_RESULTS),
        ExamStatus.GRADING,
    ),
    "moderate": ((ExamStatus.GRADING,), ExamStatus.MODERATION),
    "approve_scores": ((ExamStatus.MODERATION,), ExamStatus.RESULTS_READY),
    "release_results": ((ExamStatus.RESULTS_READY,), ExamStatus.PUBLISHED_RESULTS),
    "archive": ((ExamStatus.PUBLISHED_RESULTS,), ExamStatus.ARCHIVED),
}


def validate_exam_for_publish(exam: Exam) -> None:
    """
    کنترل سازگاری بارم پیش از انتشار.

    بخش ۷.۶: «max_score باید با مجموع بارم سؤال‌ها یا قاعده نرمال‌سازی سازگار
    باشد.»
    """
    errors: list[dict[str, str]] = []

    if not exam.sections.exists():
        errors.append({"field": "sections", "reason": "آزمون هیچ بخشی ندارد."})

    total = Decimal(str(exam.total_question_score))
    if total <= 0:
        errors.append({"field": "questions", "reason": "آزمون هیچ سؤالی ندارد."})
    elif total != exam.max_score:
        errors.append(
            {
                "field": "maxScore",
                "reason": (
                    f"مجموع بارم سؤالات ({total}) با نمره کل آزمون "
                    f"({exam.max_score}) برابر نیست."
                ),
            }
        )

    if not exam.sessions.exists():
        errors.append(
            {"field": "sessions", "reason": "حداقل یک جلسه آزمون باید تعریف شود."}
        )

    if errors:
        raise BusinessRuleViolation(
            code="EXAM_NOT_READY_FOR_PUBLISH",
            message="آزمون برای انتشار آماده نیست.",
            field_errors=errors,
        )


def apply_exam_transition(exam: Exam, action_name: str) -> Exam:
    from apps.identity.enums import AuditAction
    from apps.identity.services import record_audit

    allowed_from, target = EXAM_TRANSITIONS[action_name]
    if exam.status not in allowed_from:
        raise InvalidStateTransition(
            entity="آزمون", current=exam.status, action=action_name
        )

    if action_name == "publish":
        validate_exam_for_publish(exam)

    previous = exam.status
    exam.status = target
    if action_name == "publish":
        exam.published_at = timezone.now()
    if action_name == "release_results":
        exam.results_published_at = timezone.now()
        if not exam.appeal_deadline:
            exam.appeal_deadline = timezone.now() + timedelta(days=7)
    exam.save()

    record_audit(
        action=AuditAction.STATE_TRANSITION,
        entity_type="assessment.Exam",
        entity_id=exam.id,
        entity_label=str(exam),
        changes={"action": action_name, "from": previous, "to": target},
    )
    return exam


# ---------------------------------------------------------------------------
# اجرای آزمون آنلاین — بخش ۹.۴ و ۱۰.۴
# ---------------------------------------------------------------------------
@transaction.atomic
def start_attempt(
    registration: ExamRegistration, idempotency_key: str = ""
) -> ExamAttempt:
    """
    شروع تلاش آزمون.

    بخش ۷.۶: «شروع تلاش با Token کوتاه‌عمر و ثبت Idempotent انجام می‌شود؛
    تلاش هم‌زمان غیرمجاز قفل یا طبق سیاست ادغام می‌شود.»
    """
    session = registration.exam_session
    now = timezone.now()

    # ارسال مجدد با همان Idempotency-Key، همان تلاش را برمی‌گرداند
    if idempotency_key:
        existing = ExamAttempt.objects.filter(
            registration=registration, idempotency_key=idempotency_key
        ).first()
        if existing:
            return existing

    if session.status != "OPEN":
        raise BusinessRuleViolation(
            code="EXAM_SESSION_NOT_OPEN",
            message="این جلسه آزمون در حال حاضر باز نیست.",
        )
    if now < session.opens_at:
        raise BusinessRuleViolation(
            code="EXAM_NOT_STARTED",
            message=f"آزمون از {timezone.localtime(session.opens_at):%H:%M} آغاز می‌شود.",
        )
    if now > session.closes_at:
        raise BusinessRuleViolation(
            code="EXAM_WINDOW_CLOSED",
            message="پنجره زمانی این آزمون بسته شده است.",
        )
    if registration.registration_status == "DISQUALIFIED":
        raise BusinessRuleViolation(
            code="REGISTRATION_DISQUALIFIED",
            message="امکان شرکت در این آزمون برای شما وجود ندارد.",
            status_code=403,
        )

    # تلاش باز موجود را ادامه بده (پس از قطع اتصال)
    open_attempt = (
        ExamAttempt.objects.select_for_update()
        .filter(
            registration=registration,
            status__in=[AttemptStatus.IN_PROGRESS, AttemptStatus.INTERRUPTED],
        )
        .first()
    )
    if open_attempt:
        open_attempt.status = AttemptStatus.IN_PROGRESS
        open_attempt.save(update_fields=["status"])
        return open_attempt

    used = ExamAttempt.objects.filter(registration=registration).count()
    if used >= session.attempt_limit:
        raise BusinessRuleViolation(
            code="ATTEMPT_LIMIT_REACHED",
            message=f"حداکثر تعداد مجاز تلاش ({session.attempt_limit}) استفاده شده است.",
        )

    duration = session.duration_minutes + registration.extra_time_minutes
    expires_at = min(now + timedelta(minutes=duration), session.closes_at)

    attempt = ExamAttempt.objects.create(
        tenant_id=registration.tenant_id,
        registration=registration,
        attempt_no=used + 1,
        started_at=now,
        last_saved_at=now,
        expires_at=expires_at,
        status=AttemptStatus.IN_PROGRESS,
        idempotency_key=idempotency_key or uuid.uuid4().hex,
    )

    exam = session.exam
    if exam.status == ExamStatus.PUBLISHED:
        exam.status = ExamStatus.IN_PROGRESS
        exam.save(update_fields=["status"])

    return attempt


def assert_attempt_active(attempt: ExamAttempt) -> None:
    """کنترل اینکه تلاش هنوز باز و در مهلت است."""
    if attempt.status not in {AttemptStatus.IN_PROGRESS, AttemptStatus.INTERRUPTED}:
        raise InvalidStateTransition(
            entity="تلاش آزمون", current=attempt.status, action="save_answer"
        )
    if attempt.expires_at and timezone.now() > attempt.expires_at:
        raise BusinessRuleViolation(
            code="ATTEMPT_TIME_EXPIRED",
            message="زمان آزمون شما به پایان رسیده است.",
            status_code=409,
        )


@transaction.atomic
def save_answer(
    attempt: ExamAttempt, exam_question_id, response_payload: dict
) -> AttemptAnswer:
    """ذخیره خودکار پاسخ با شماره بازنگری افزایشی (بخش ۷.۶)."""
    assert_attempt_active(attempt)

    valid = ExamQuestion.objects.filter(
        id=exam_question_id, section__exam_id=attempt.registration.exam_session.exam_id
    ).exists()
    if not valid:
        raise BusinessRuleViolation(
            code="QUESTION_NOT_IN_EXAM",
            message="این سؤال متعلق به آزمون جاری نیست.",
            status_code=400,
        )

    now = timezone.now()
    answer, _ = AttemptAnswer.objects.get_or_create(
        attempt=attempt,
        exam_question_id=exam_question_id,
        defaults={"tenant_id": attempt.tenant_id},
    )
    answer.response_payload = response_payload
    answer.saved_at = now
    answer.save_revision += 1
    answer.save()

    attempt.last_saved_at = now
    attempt.save(update_fields=["last_saved_at"])
    return answer


def grade_answer_automatically(answer: AttemptAnswer) -> Decimal | None:
    """
    تصحیح خودکار یک پاسخ.

    برای سؤالات تشریحی و کوتاه‌پاسخ، نمره‌دهی به تصحیح انسانی سپرده می‌شود.
    """
    exam_question = answer.exam_question
    version = exam_question.question_version
    question_type = version.question.question_type
    max_score = Decimal(str(exam_question.score))

    if question_type not in AUTO_GRADED_TYPES:
        answer.grading_status = GradingStatus.PENDING
        answer.save(update_fields=["grading_status"])
        return None

    payload = answer.response_payload or {}
    score = Decimal("0")

    if question_type in {QuestionType.SINGLE_CHOICE, QuestionType.TRUE_FALSE}:
        selected = payload.get("selectedKeys") or []
        correct_keys = set(
            version.options.filter(is_correct=True).values_list("option_key", flat=True)
        )
        if len(selected) == 1 and set(selected) == correct_keys:
            score = max_score

    elif question_type == QuestionType.MULTIPLE_CHOICE:
        selected = set(payload.get("selectedKeys") or [])
        correct_keys = set(
            version.options.filter(is_correct=True).values_list("option_key", flat=True)
        )
        wrong = selected - correct_keys
        if selected == correct_keys:
            score = max_score
        elif selected and not wrong:
            # نمره جزئی متناسب با تعداد گزینه‌های درست انتخاب‌شده
            score = max_score * Decimal(len(selected)) / Decimal(len(correct_keys))

    elif question_type == QuestionType.NUMERIC:
        expected = version.correct_answer.get("value")
        tolerance = Decimal(str(version.correct_answer.get("tolerance", 0)))
        given = payload.get("value")
        if expected is not None and given is not None:
            try:
                if abs(Decimal(str(given)) - Decimal(str(expected))) <= tolerance:
                    score = max_score
            except (TypeError, ValueError):
                score = Decimal("0")

    elif question_type in {QuestionType.MATCHING, QuestionType.ORDERING}:
        expected = version.correct_answer.get("pairs") or version.correct_answer.get(
            "order"
        )
        given = payload.get("pairs") or payload.get("order")
        if expected and given == expected:
            score = max_score

    answer.awarded_score = score.quantize(Decimal("0.01"))
    answer.grading_status = GradingStatus.AUTO_GRADED
    answer.save(update_fields=["awarded_score", "grading_status"])
    return answer.awarded_score


@transaction.atomic
def submit_attempt(attempt: ExamAttempt, auto: bool = False) -> ExamAttempt:
    """
    تحویل تلاش — عملیات اتمیک و تکرارپذیر (بخش ۷.۶).

    ارسال مجدد پس از تحویل، همان نتیجه را برمی‌گرداند و خطا نمی‌دهد.
    """
    if attempt.status in {
        AttemptStatus.SUBMITTED,
        AttemptStatus.AUTO_SUBMITTED,
        AttemptStatus.GRADING,
        AttemptStatus.GRADED,
        AttemptStatus.FINALIZED,
    }:
        return attempt

    if attempt.status not in {AttemptStatus.IN_PROGRESS, AttemptStatus.INTERRUPTED}:
        raise InvalidStateTransition(
            entity="تلاش آزمون", current=attempt.status, action="submit"
        )

    attempt.submitted_at = timezone.now()
    attempt.status = (
        AttemptStatus.AUTO_SUBMITTED if auto else AttemptStatus.SUBMITTED
    )
    attempt.save(update_fields=["submitted_at", "status"])

    grade_attempt(attempt)

    from apps.workflow.services import publish_event

    publish_event(
        aggregate_type="assessment.ExamAttempt",
        aggregate_id=attempt.id,
        event_type="ExamSubmitted",
        payload={
            "attemptId": str(attempt.id),
            "examId": str(attempt.registration.exam_session.exam_id),
            "autoSubmitted": auto,
        },
        tenant_id=attempt.tenant_id,
    )
    return attempt


@transaction.atomic
def grade_attempt(attempt: ExamAttempt) -> ExamAttempt:
    """تصحیح خودکار همه پاسخ‌ها و محاسبه نمره تجمیعی."""
    attempt.status = AttemptStatus.GRADING
    attempt.save(update_fields=["status"])

    auto_total = Decimal("0")
    pending_manual = False

    answers = attempt.answers.select_related(
        "exam_question__question_version__question"
    )
    for answer in answers:
        result = grade_answer_automatically(answer)
        if result is None:
            pending_manual = True
        else:
            auto_total += result

    attempt.auto_score = auto_total
    manual_total = sum(
        (a.awarded_score or Decimal("0"))
        for a in attempt.answers.filter(grading_status=GradingStatus.MANUAL_GRADED)
    )
    attempt.manual_score = Decimal(str(manual_total))
    attempt.final_score = auto_total + Decimal(str(manual_total))
    attempt.status = (
        AttemptStatus.GRADING if pending_manual else AttemptStatus.GRADED
    )
    attempt.save(update_fields=["auto_score", "manual_score", "final_score", "status"])
    return attempt


@transaction.atomic
def apply_manual_grade(
    answer: AttemptAnswer, score: Decimal, feedback: str, reviewer_id, review_type: str
):
    """ثبت نمره تصحیح دستی و به‌روزرسانی نمره تلاش."""
    from apps.assessment.models import GradeReview

    max_score = Decimal(str(answer.exam_question.score))
    if score < 0 or score > max_score:
        raise BusinessRuleViolation(
            code="SCORE_OUT_OF_RANGE",
            message=f"نمره باید بین ۰ و {max_score} باشد.",
            field_errors=[{"field": "score", "reason": "out_of_range"}],
        )

    review = GradeReview.objects.create(
        tenant_id=answer.tenant_id,
        attempt_answer=answer,
        reviewer_id=reviewer_id,
        awarded_score=score,
        feedback=feedback,
        review_type=review_type,
        reviewed_at=timezone.now(),
    )
    answer.awarded_score = score
    answer.grading_status = GradingStatus.MANUAL_GRADED
    answer.save(update_fields=["awarded_score", "grading_status"])

    recalculate_attempt_score(answer.attempt)
    return review


def recalculate_attempt_score(attempt: ExamAttempt) -> ExamAttempt:
    """محاسبه مجدد نمره تلاش از روی پاسخ‌ها."""
    from django.db.models import Sum

    aggregate = attempt.answers.aggregate(total=Sum("awarded_score"))
    total = aggregate["total"] or Decimal("0")
    attempt.final_score = total
    attempt.calculation_version += 1

    still_pending = attempt.answers.filter(
        grading_status=GradingStatus.PENDING
    ).exists()
    if not still_pending and attempt.status == AttemptStatus.GRADING:
        attempt.status = AttemptStatus.GRADED

    attempt.save(update_fields=["final_score", "calculation_version", "status"])
    return attempt


def auto_submit_expired_attempts() -> int:
    """
    تحویل خودکار تلاش‌هایی که مهلتشان تمام شده است.

    برای اجرا از طریق Job زمان‌بندی‌شده (بخش ۱۵.۴).
    """
    expired = ExamAttempt.objects.filter(
        status__in=[AttemptStatus.IN_PROGRESS, AttemptStatus.INTERRUPTED],
        expires_at__lt=timezone.now(),
    )
    count = 0
    for attempt in expired:
        submit_attempt(attempt, auto=True)
        count += 1
    return count


def question_analysis(exam: Exam) -> list[dict]:
    """
    تحلیل سؤال: درصد پاسخ صحیح، میانگین نمره و زمان پاسخ (بخش ۴.۴).
    """
    from django.db.models import Avg, Count, Q

    rows = []
    exam_questions = ExamQuestion.objects.filter(
        section__exam=exam
    ).select_related("question_version__question", "section")

    for exam_question in exam_questions:
        answers = AttemptAnswer.objects.filter(exam_question=exam_question)
        stats = answers.aggregate(
            total=Count("id"),
            average=Avg("awarded_score"),
            average_time=Avg("time_spent_seconds"),
            full_credit=Count("id", filter=Q(awarded_score=exam_question.score)),
        )
        total = stats["total"] or 0
        rows.append(
            {
                "examQuestionId": str(exam_question.id),
                "sectionTitle": exam_question.section.title,
                "questionBody": exam_question.question_version.body[:120],
                "questionType": exam_question.question_version.question.question_type,
                "maxScore": float(exam_question.score),
                "responseCount": total,
                "correctPercent": (
                    round((stats["full_credit"] or 0) * 100 / total, 1) if total else None
                ),
                "averageScore": (
                    float(stats["average"]) if stats["average"] is not None else None
                ),
                "averageTimeSeconds": (
                    int(stats["average_time"]) if stats["average_time"] else 0
                ),
            }
        )
    return rows
