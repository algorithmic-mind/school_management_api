"""
قواعد کسب‌وکار دفتر نمره و کارنامه.

مرجع: بخش ۷.۷، ۹.۹ (نهایی‌سازی نمره و کارنامه) و ۱۱.۵ (داده‌های محاسباتی).
"""

from __future__ import annotations

import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.exceptions import BusinessRuleViolation
from apps.gradebook.enums import (
    CourseResultStatus,
    DropPolicy,
    GradeItemStatus,
    ReportCardStatus,
    ScoreStatus,
)
from apps.gradebook.models import (
    AssessmentCategory,
    CourseResult,
    GradeItem,
    ReportCard,
    ReportCardItem,
    StudentScore,
)

#: وضعیت‌هایی که در محاسبه معدل وارد نمی‌شوند (بخش ۷.۷)
EXCLUDED_FROM_AVERAGE = {
    ScoreStatus.NOT_RECORDED,
    ScoreStatus.EXEMPT,
    ScoreStatus.EXCUSED,
}

#: نمره قبولی پیش‌فرض از ۲۰ — قابل انتقال به تنظیمات مدرسه
PASSING_SCORE = Decimal("10")


def validate_category_weights(course_offering_id) -> None:
    """
    بخش ۷.۷: «مجموع وزن دسته‌های فعال هر درس باید ۱۰۰٪ باشد.»
    """
    total = AssessmentCategory.objects.filter(
        course_offering_id=course_offering_id, is_active=True
    ).aggregate(total=Sum("weight_percent"))["total"] or Decimal("0")

    if total != Decimal("100"):
        raise BusinessRuleViolation(
            code="CATEGORY_WEIGHT_MISMATCH",
            message=f"مجموع وزن دسته‌های ارزشیابی {total}٪ است و باید دقیقاً ۱۰۰٪ باشد.",
            field_errors=[{"field": "weightPercent", "reason": "sum_not_100"}],
        )


def normalize_score(raw_score: Decimal | None, max_score: Decimal) -> Decimal | None:
    """نمره نرمال‌شده بر مبنای ۱۰۰ (بخش ۷.۷: نمره خام نگهداری می‌شود)."""
    if raw_score is None or not max_score:
        return None
    return (Decimal(str(raw_score)) / Decimal(str(max_score)) * 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


@transaction.atomic
def record_score(
    grade_item: GradeItem,
    enrollment_id,
    raw_score: Decimal | None,
    status: str,
    *,
    comment: str = "",
    actor_id=None,
    reason: str = "",
) -> StudentScore:
    """
    ثبت یا اصلاح نمره با ثبت تاریخچه تغییر.

    اگر قلم نمره قفل باشد، تغییر نیازمند علت و مجوز `grade.unlock` است.
    """
    from apps.gradebook.models import ScoreChange

    if grade_item.status == GradeItemStatus.LOCKED and not reason:
        raise BusinessRuleViolation(
            code="GRADE_ITEM_LOCKED",
            message="این قلم نمره قفل است؛ تغییر آن نیازمند ثبت علت است.",
            field_errors=[{"field": "reason", "reason": "required"}],
            status_code=409,
        )

    score, created = StudentScore.objects.get_or_create(
        grade_item=grade_item,
        enrollment_id=enrollment_id,
        defaults={"tenant_id": grade_item.tenant_id},
    )

    old_score = score.raw_score
    old_status = score.status

    score.raw_score = raw_score
    score.normalized_score = normalize_score(raw_score, grade_item.max_score)
    score.status = status
    score.comment = comment
    score.recorded_by_id = actor_id
    score.recorded_at = timezone.now()
    score.save()

    if not created and (old_score != raw_score or old_status != status):
        ScoreChange.objects.create(
            tenant_id=grade_item.tenant_id,
            student_score=score,
            old_score=old_score,
            new_score=raw_score,
            old_status=old_status,
            new_status=status,
            reason=reason or "ثبت اولیه/اصلاح نمره",
            changed_by_id=actor_id,
        )

    return score


def _category_average(category: AssessmentCategory, enrollment_id) -> Decimal | None:
    """میانگین وزنی نمرات یک دسته با اعمال سیاست حذف پایین‌ترین نمره."""
    scores = list(
        StudentScore.objects.filter(
            grade_item__category=category, enrollment_id=enrollment_id
        )
        .exclude(status__in=EXCLUDED_FROM_AVERAGE)
        .select_related("grade_item")
    )
    if not scores:
        return None

    normalized = [
        (
            s.normalized_score
            if s.normalized_score is not None
            else Decimal("0"),
            Decimal(str(s.grade_item.weight or 1)),
        )
        for s in scores
    ]

    if category.drop_policy == DropPolicy.DROP_LOWEST and len(normalized) > 1:
        normalized.sort(key=lambda pair: pair[0])
        normalized = normalized[1:]
    elif category.drop_policy == DropPolicy.DROP_LOWEST_TWO and len(normalized) > 2:
        normalized.sort(key=lambda pair: pair[0])
        normalized = normalized[2:]

    weight_sum = sum(weight for _, weight in normalized)
    if not weight_sum:
        return None
    weighted = sum(value * weight for value, weight in normalized)
    return (weighted / weight_sum).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@transaction.atomic
def calculate_course_result(course_offering, enrollment) -> CourseResult:
    """
    محاسبه نتیجه یک درس برای یک دانش‌آموز.

    بخش ۱۱.۵: «هر محاسبه مهم calculation_version و Snapshot ورودی‌های ضروری
    دارد.»
    """
    categories = AssessmentCategory.objects.filter(
        course_offering=course_offering, is_active=True
    )
    validate_category_weights(course_offering.id)

    inputs: dict[str, object] = {"categories": []}
    total_percent = Decimal("0")

    for category in categories:
        average = _category_average(category, enrollment.id)
        inputs["categories"].append(
            {
                "categoryId": str(category.id),
                "title": category.title,
                "weightPercent": float(category.weight_percent),
                "average": float(average) if average is not None else None,
            }
        )
        if average is not None:
            total_percent += average * Decimal(str(category.weight_percent)) / 100

    max_course_score = Decimal(str(course_offering.course.max_score or 20))
    final_score = (total_percent * max_course_score / 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    result, _ = CourseResult.objects.get_or_create(
        course_offering=course_offering,
        enrollment=enrollment,
        defaults={"tenant_id": course_offering.tenant_id},
    )
    result.final_score = final_score
    result.result_status = (
        CourseResultStatus.PASSED
        if final_score >= PASSING_SCORE
        else CourseResultStatus.FAILED
    )
    result.calculation_version += 1
    result.calculated_at = timezone.now()
    result.calculation_inputs = inputs
    result.save()
    return result


@transaction.atomic
def lock_grade_item(grade_item: GradeItem, actor_id) -> GradeItem:
    """قفل قلم نمره در پایان بازه ثبت (بخش ۷.۷)."""
    grade_item.status = GradeItemStatus.LOCKED
    grade_item.locked_at = timezone.now()
    grade_item.locked_by_id = actor_id
    grade_item.save(update_fields=["status", "locked_at", "locked_by_id"])
    return grade_item


@transaction.atomic
def unlock_grade_item(grade_item: GradeItem, reason: str, actor_id) -> GradeItem:
    """
    بازگشایی قفل نمره.

    بخش ۷.۷: «بازگشایی نیازمند علت و تأیید معاون آموزشی است.»
    """
    from apps.identity.enums import AuditAction
    from apps.identity.services import record_audit

    if grade_item.status != GradeItemStatus.LOCKED:
        raise BusinessRuleViolation(
            code="GRADE_ITEM_NOT_LOCKED",
            message="این قلم نمره قفل نیست.",
        )
    grade_item.status = GradeItemStatus.OPEN
    grade_item.locked_at = None
    grade_item.save(update_fields=["status", "locked_at"])

    record_audit(
        action=AuditAction.STATE_TRANSITION,
        entity_type="gradebook.GradeItem",
        entity_id=grade_item.id,
        entity_label=str(grade_item),
        reason=reason,
        changes={"action": "unlock"},
    )
    return grade_item


@transaction.atomic
def generate_report_card(enrollment, term) -> ReportCard:
    """
    تولید نسخه جدید کارنامه با Snapshot نتایج دروس.

    نسخه قبلی به `SUPERSEDED` می‌رود و حذف نمی‌شود (بخش ۷.۷).
    """
    previous = (
        ReportCard.objects.filter(enrollment=enrollment, term=term)
        .order_by("-version_no")
        .first()
    )
    version_no = (previous.version_no + 1) if previous else 1

    if previous and previous.status == ReportCardStatus.PUBLISHED:
        previous.status = ReportCardStatus.SUPERSEDED
        previous.save(update_fields=["status"])

    report_card = ReportCard.objects.create(
        tenant_id=enrollment.tenant_id,
        enrollment=enrollment,
        term=term,
        version_no=version_no,
        generated_at=timezone.now(),
        status=ReportCardStatus.GENERATED,
        verification_code=uuid.uuid4().hex[:16].upper(),
    )

    results = CourseResult.objects.filter(
        enrollment=enrollment, course_offering__term=term
    ).select_related("course_offering__course")

    total_weighted = Decimal("0")
    total_credit = Decimal("0")

    for index, result in enumerate(results, start=1):
        course = result.course_offering.course
        ReportCardItem.objects.create(
            tenant_id=enrollment.tenant_id,
            report_card=report_card,
            course_result=result,
            course_title=course.title,
            displayed_score=result.final_score,
            displayed_level=result.qualitative_level,
            credit=course.credit,
            teacher_comment=result.teacher_comment,
            display_order=index,
        )
        if result.final_score is not None and course.credit:
            total_weighted += Decimal(str(result.final_score)) * Decimal(
                str(course.credit)
            )
            total_credit += Decimal(str(course.credit))

    if total_credit:
        report_card.average_score = (total_weighted / total_credit).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    report_card.attendance_summary = _attendance_snapshot(enrollment, term)
    report_card.save(update_fields=["average_score", "attendance_summary"])
    return report_card


def _attendance_snapshot(enrollment, term) -> dict:
    from django.db.models import Count

    from apps.teaching.models import AttendanceRecord

    rows = (
        AttendanceRecord.objects.filter(
            enrollment=enrollment, session__course_offering__term=term
        )
        .values("attendance_status")
        .annotate(count=Count("id"))
    )
    counts = {row["attendance_status"]: row["count"] for row in rows}
    total = sum(counts.values())
    present = counts.get("PRESENT", 0) + counts.get("LATE", 0)
    return {
        "totalSessions": total,
        "byStatus": counts,
        "presentPercent": (
            float(round(present * 100 / total, 1)) if total else None
        ),
    }


@transaction.atomic
def publish_report_card(report_card: ReportCard, actor_id) -> ReportCard:
    """انتشار کارنامه و انتشار رویداد `ReportCardPublished` (بخش ۱۳.۱)."""
    from apps.workflow.services import publish_event

    if report_card.status not in {
        ReportCardStatus.GENERATED,
        ReportCardStatus.UNDER_REVIEW,
    }:
        raise BusinessRuleViolation(
            code="REPORT_CARD_NOT_PUBLISHABLE",
            message="فقط کارنامه تولیدشده یا در حال بازبینی قابل انتشار است.",
            status_code=409,
        )

    report_card.status = ReportCardStatus.PUBLISHED
    report_card.published_at = timezone.now()
    report_card.published_by_id = actor_id
    report_card.save(update_fields=["status", "published_at", "published_by_id"])

    publish_event(
        aggregate_type="gradebook.ReportCard",
        aggregate_id=report_card.id,
        event_type="ReportCardPublished",
        payload={
            "reportCardId": str(report_card.id),
            "enrollmentId": str(report_card.enrollment_id),
            "termId": str(report_card.term_id),
            "versionNo": report_card.version_no,
        },
        tenant_id=report_card.tenant_id,
    )
    return report_card


def compute_class_ranks(term, class_group) -> int:
    """
    محاسبه رتبه در کلاس برای کارنامه‌های منتشرشده یک ترم.

    بخش ۴.۳: «رتبه در صورت مجاز بودن». این تابع فقط در صورت درخواست صریح
    فراخوانی می‌شود.
    """
    cards = list(
        ReportCard.objects.filter(
            term=term,
            enrollment__class_memberships__class_group=class_group,
            status=ReportCardStatus.PUBLISHED,
            average_score__isnull=False,
        ).order_by("-average_score")
    )
    for index, card in enumerate(cards, start=1):
        card.rank_in_class = index
        card.save(update_fields=["rank_in_class"])
    return len(cards)
