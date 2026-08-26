"""
قواعد کسب‌وکار امور دانش‌آموزان.

مرجع: بخش ۹.۱ (پذیرش تا فعال‌شدن)، ۹.۲ (ثبت‌نام و تعهد مالی)،
۹.۱۰ (انتقال بین کلاس)، ۱۰.۱ و ۱۰.۲ (ماشین حالت)، ۱۱.۲ (ارتقای پایه).
"""

from __future__ import annotations

from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleViolation, InvalidStateTransition
from apps.identity.enums import AuditAction
from apps.identity.services import record_audit
from apps.organization.services import check_class_capacity
from apps.students.enums import (
    AdmissionStatus,
    ClassMembershipStatus,
    EnrollmentStatus,
    StudentStatus,
    TransferType,
)
from apps.students.models import (
    AdmissionApplication,
    ClassMembership,
    Enrollment,
    Student,
    StudentStatusHistory,
    StudentTransfer,
)

# ---------------------------------------------------------------------------
# ماشین حالت پذیرش — بخش ۱۰.۱
# ---------------------------------------------------------------------------
ADMISSION_TRANSITIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "submit": ((AdmissionStatus.DRAFT, AdmissionStatus.INCOMPLETE), AdmissionStatus.SUBMITTED),
    "mark_incomplete": ((AdmissionStatus.SUBMITTED,), AdmissionStatus.INCOMPLETE),
    "assign_reviewer": ((AdmissionStatus.SUBMITTED,), AdmissionStatus.UNDER_REVIEW),
    "waitlist": ((AdmissionStatus.UNDER_REVIEW,), AdmissionStatus.WAITLISTED),
    "resume_review": ((AdmissionStatus.WAITLISTED,), AdmissionStatus.UNDER_REVIEW),
    "accept_conditionally": (
        (AdmissionStatus.UNDER_REVIEW,),
        AdmissionStatus.CONDITIONALLY_ACCEPTED,
    ),
    "accept": (
        (AdmissionStatus.UNDER_REVIEW, AdmissionStatus.CONDITIONALLY_ACCEPTED),
        AdmissionStatus.ACCEPTED,
    ),
    "reject": (
        (AdmissionStatus.UNDER_REVIEW, AdmissionStatus.CONDITIONALLY_ACCEPTED),
        AdmissionStatus.REJECTED,
    ),
    "withdraw": (
        (
            AdmissionStatus.DRAFT,
            AdmissionStatus.SUBMITTED,
            AdmissionStatus.WAITLISTED,
            AdmissionStatus.UNDER_REVIEW,
        ),
        AdmissionStatus.WITHDRAWN,
    ),
}

# ---------------------------------------------------------------------------
# ماشین حالت ثبت‌نام — بخش ۱۰.۲
# ---------------------------------------------------------------------------
ENROLLMENT_TRANSITIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "approve_documents": (
        (EnrollmentStatus.PENDING_DOCUMENTS,),
        EnrollmentStatus.PENDING_FINANCE,
    ),
    "confirm_finance": (
        (EnrollmentStatus.PENDING_FINANCE,),
        EnrollmentStatus.PENDING_PLACEMENT,
    ),
    "activate": ((EnrollmentStatus.PENDING_PLACEMENT,), EnrollmentStatus.ACTIVE),
    "suspend": ((EnrollmentStatus.ACTIVE,), EnrollmentStatus.SUSPENDED),
    "reinstate": ((EnrollmentStatus.SUSPENDED,), EnrollmentStatus.ACTIVE),
    "transfer_out": ((EnrollmentStatus.ACTIVE,), EnrollmentStatus.TRANSFERRED),
    "withdraw": ((EnrollmentStatus.ACTIVE,), EnrollmentStatus.WITHDRAWN),
    "complete": ((EnrollmentStatus.ACTIVE,), EnrollmentStatus.COMPLETED),
    "graduate": ((EnrollmentStatus.COMPLETED,), EnrollmentStatus.GRADUATED),
    "cancel": (
        (
            EnrollmentStatus.PENDING_DOCUMENTS,
            EnrollmentStatus.PENDING_FINANCE,
            EnrollmentStatus.PENDING_PLACEMENT,
        ),
        EnrollmentStatus.CANCELLED,
    ),
}


def apply_transition(instance, table: dict, action_name: str, entity_label: str):
    """اجرای امن یک گذار وضعیت با ثبت ممیزی."""
    allowed_from, target = table[action_name]
    current = instance.status
    if current not in allowed_from:
        raise InvalidStateTransition(
            entity=entity_label, current=current, action=action_name
        )
    instance.status = target
    instance.save(update_fields=["status", "updated_at", "version"])
    record_audit(
        action=AuditAction.STATE_TRANSITION,
        entity_type=instance._meta.label,
        entity_id=instance.id,
        entity_label=str(instance),
        changes={"action": action_name, "from": current, "to": target},
    )
    return instance


def generate_student_no(tenant_id, joined_on: date | None = None) -> str:
    """
    تولید شماره دانش‌آموزی.

    قالب: <سال><شماره ترتیبی ۵ رقمی>. در محیط عملیاتی، دنباله باید از یک
    Sequence اتمیک پایگاه داده تأمین شود تا در بار همزمان تکراری نشود.
    """
    joined_on = joined_on or timezone.localdate()
    year_prefix = str(joined_on.year)[-2:]
    last = (
        Student.objects.filter(
            tenant_id=tenant_id, student_no__startswith=year_prefix
        )
        .order_by("-student_no")
        .values_list("student_no", flat=True)
        .first()
    )
    sequence = int(last[2:]) + 1 if last and last[2:].isdigit() else 1
    return f"{year_prefix}{sequence:05d}"


def generate_enrollment_no(tenant_id, academic_year) -> str:
    count = Enrollment.objects.filter(
        tenant_id=tenant_id, academic_year=academic_year
    ).count()
    return f"ENR-{academic_year.title.replace('–', '-')}-{count + 1:05d}"


@transaction.atomic
def convert_admission_to_enrollment(
    application: AdmissionApplication, enrolled_on: date | None = None
) -> Enrollment:
    """
    تبدیل درخواست پذیرفته‌شده به ثبت‌نام (بخش ۹.۱ و ۹.۲).

    - پرونده دانش‌آموز در صورت نبود ساخته می‌شود.
    - ثبت‌نام در وضعیت اولیه «در انتظار مدارک» ایجاد می‌شود.
    - تعهد مالی توسط ماژول مالی و در پاسخ به رویداد ایجاد می‌گردد.
    """
    if application.status != AdmissionStatus.ACCEPTED:
        raise InvalidStateTransition(
            entity="درخواست پذیرش",
            current=application.status,
            action="convert_to_enrollment",
        )

    student = Student.objects.filter(person=application.person).first()
    if student is None:
        student = Student.objects.create(
            tenant_id=application.tenant_id,
            person=application.person,
            student_no=generate_student_no(application.tenant_id),
            joined_on=enrolled_on or timezone.localdate(),
            status=StudentStatus.PROSPECTIVE,
        )

    existing = Enrollment.objects.filter(
        student=student,
        academic_year=application.academic_year,
    ).exclude(status=EnrollmentStatus.CANCELLED).first()
    if existing:
        raise BusinessRuleViolation(
            code="ENROLLMENT_ALREADY_EXISTS",
            message="برای این دانش‌آموز در این سال تحصیلی ثبت‌نام وجود دارد.",
            field_errors=[{"field": "studentId", "reason": "duplicate_enrollment"}],
        )

    enrollment = Enrollment.objects.create(
        tenant_id=application.tenant_id,
        student=student,
        academic_year=application.academic_year,
        campus=application.preferred_campus,
        grade_level=application.preferred_grade_level,
        program=application.preferred_program,
        admission_application=application,
        enrollment_no=generate_enrollment_no(
            application.tenant_id, application.academic_year
        ),
        enrolled_on=enrolled_on or timezone.localdate(),
        status=EnrollmentStatus.PENDING_DOCUMENTS,
    )

    application.status = AdmissionStatus.CONVERTED
    application.save(update_fields=["status", "updated_at", "version"])

    record_audit(
        action=AuditAction.STATE_TRANSITION,
        entity_type="students.AdmissionApplication",
        entity_id=application.id,
        entity_label=str(application),
        changes={"action": "convert", "enrollmentId": str(enrollment.id)},
    )
    return enrollment


@transaction.atomic
def place_in_class(
    enrollment: Enrollment, class_group, effective_from: date | None = None
) -> ClassMembership:
    """
    تخصیص کلاس با کنترل ظرفیت و بستن عضویت فعال قبلی.

    بخش ۷.۲: «فقط یک CLASS_MEMBERSHIP اصلی فعال در یک لحظه.»
    """
    effective_from = effective_from or timezone.localdate()

    if class_group.academic_year_id != enrollment.academic_year_id:
        raise BusinessRuleViolation(
            code="CLASS_YEAR_MISMATCH",
            message="کلاس انتخابی متعلق به سال تحصیلی این ثبت‌نام نیست.",
            field_errors=[{"field": "classGroupId", "reason": "academic_year_mismatch"}],
        )

    if class_group.grade_level_id != enrollment.grade_level_id:
        raise BusinessRuleViolation(
            code="CLASS_GRADE_MISMATCH",
            message="پایه کلاس با پایه ثبت‌نام دانش‌آموز یکسان نیست.",
            field_errors=[{"field": "classGroupId", "reason": "grade_mismatch"}],
        )

    check_class_capacity(class_group, additional=1)

    current = enrollment.class_memberships.filter(
        status=ClassMembershipStatus.ACTIVE, is_primary=True
    ).first()
    if current:
        if current.class_group_id == class_group.id:
            return current
        current.status = ClassMembershipStatus.TRANSFERRED
        current.effective_to = effective_from
        current.save(update_fields=["status", "effective_to", "updated_at", "version"])

    membership = ClassMembership.objects.create(
        tenant_id=enrollment.tenant_id,
        enrollment=enrollment,
        class_group=class_group,
        effective_from=effective_from,
        is_primary=True,
        status=ClassMembershipStatus.ACTIVE,
    )

    if enrollment.status == EnrollmentStatus.PENDING_PLACEMENT:
        enrollment.status = EnrollmentStatus.ACTIVE
        enrollment.save(update_fields=["status", "updated_at", "version"])
        set_student_status(enrollment.student, StudentStatus.ACTIVE, "تخصیص کلاس")

    return membership


@transaction.atomic
def transfer_class(
    enrollment: Enrollment, target_class_group, reason: str, effective_on: date | None = None
) -> StudentTransfer:
    """انتقال دانش‌آموز بین کلاس‌ها با ثبت سابقه (بخش ۹.۱۰)."""
    effective_on = effective_on or timezone.localdate()
    source = enrollment.current_class_group

    if source and source.id == target_class_group.id:
        raise BusinessRuleViolation(
            code="SAME_CLASS_TRANSFER",
            message="کلاس مبدأ و مقصد یکسان است.",
        )

    place_in_class(enrollment, target_class_group, effective_from=effective_on)

    transfer = StudentTransfer.objects.create(
        tenant_id=enrollment.tenant_id,
        student=enrollment.student,
        enrollment=enrollment,
        transfer_type=(
            TransferType.INTERNAL_CAMPUS
            if source and source.campus_id != target_class_group.campus_id
            else TransferType.INTERNAL_CLASS
        ),
        from_class_group=source,
        to_class_group=target_class_group,
        effective_on=effective_on,
        reason=reason,
    )
    record_audit(
        action=AuditAction.UPDATE,
        entity_type="students.Enrollment",
        entity_id=enrollment.id,
        entity_label=str(enrollment),
        reason=reason,
        changes={
            "from": str(source.code) if source else None,
            "to": target_class_group.code,
        },
    )
    return transfer


def set_student_status(student: Student, new_status: str, reason: str = "") -> Student:
    """تغییر وضعیت دانش‌آموز با ثبت تاریخچه (بخش ۷.۲)."""
    previous = student.status
    if previous == new_status:
        return student
    student.status = new_status
    student.save(update_fields=["status", "updated_at", "version"])
    StudentStatusHistory.objects.create(
        tenant_id=student.tenant_id,
        student=student,
        from_status=previous,
        to_status=new_status,
        reason=reason,
    )
    return student


@transaction.atomic
def withdraw_student(enrollment: Enrollment, reason: str, exit_date: date | None = None):
    """ترک تحصیل: بستن عضویت کلاس و به‌روزرسانی وضعیت دانش‌آموز."""
    exit_date = exit_date or timezone.localdate()
    apply_transition(enrollment, ENROLLMENT_TRANSITIONS, "withdraw", "ثبت‌نام")
    enrollment.exit_date = exit_date
    enrollment.exit_reason = reason
    enrollment.save(update_fields=["exit_date", "exit_reason", "updated_at", "version"])

    enrollment.class_memberships.filter(status=ClassMembershipStatus.ACTIVE).update(
        status=ClassMembershipStatus.ENDED, effective_to=exit_date, exit_reason=reason
    )
    set_student_status(enrollment.student, StudentStatus.WITHDRAWN, reason)
    return enrollment


def preview_promotion(batch) -> list[dict]:
    """
    پیش‌نمایش ارتقای پایه (بخش ۱۱.۲ و ۱۱.۶).

    تصمیم پیشنهادی بر اساس ترتیب پایه محاسبه می‌شود؛ ثبت نهایی جداگانه است.
    """
    from apps.organization.models import GradeLevel
    from apps.students.enums import PromotionDecision

    rows = []
    enrollments = Enrollment.objects.filter(
        academic_year=batch.source_year,
        status__in=[EnrollmentStatus.ACTIVE, EnrollmentStatus.COMPLETED],
    ).select_related("student__person", "grade_level")

    for enrollment in enrollments:
        next_grade = (
            GradeLevel.objects.filter(
                school=enrollment.grade_level.school,
                sequence_no=enrollment.grade_level.sequence_no + 1,
            ).first()
        )
        decision = (
            PromotionDecision.PROMOTED if next_grade else PromotionDecision.GRADUATED
        )
        rows.append(
            {
                "enrollmentId": str(enrollment.id),
                "studentNo": enrollment.student.student_no,
                "studentName": enrollment.student.full_name,
                "currentGrade": enrollment.grade_level.title,
                "suggestedDecision": decision,
                "targetGradeLevelId": str(next_grade.id) if next_grade else None,
                "targetGrade": next_grade.title if next_grade else None,
                "errors": [],
            }
        )
    return rows
