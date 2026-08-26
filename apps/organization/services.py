"""
قواعد کسب‌وکار ساختار آموزشی.

مرجع: بخش ۷.۱ (قیدها)، ۹.۳ (ساخت برنامه هفتگی) و ۱۱.۱ (مرز سال تحصیلی).
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Q

from apps.core.exceptions import BusinessRuleViolation
from apps.organization.enums import AcademicYearStatus, ScheduleStatus
from apps.organization.models import (
    AcademicYear,
    ClassGroup,
    ScheduleEntry,
    Term,
)


def detect_schedule_conflicts(entry: ScheduleEntry) -> list[dict]:
    """
    تداخل برنامه را برای معلم، اتاق و کلاس تشخیص می‌دهد.

    خروجی: فهرست تداخل‌ها با نوع و شناسه قلم متعارض.
    """
    conflicts: list[dict] = []

    overlapping = ScheduleEntry.objects.filter(
        weekday=entry.weekday,
        starts_at__lt=entry.ends_at,
        ends_at__gt=entry.starts_at,
    ).exclude(pk=entry.pk)

    # هم‌پوشانی بازه اعتبار
    overlapping = overlapping.filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=entry.effective_from)
    )
    if entry.effective_to:
        overlapping = overlapping.filter(effective_from__lte=entry.effective_to)

    if entry.room_id:
        for other in overlapping.filter(room_id=entry.room_id):
            conflicts.append(
                {
                    "type": "ROOM_CONFLICT",
                    "message": f"اتاق در این بازه به «{other.course_offering}» اختصاص دارد.",
                    "conflictingEntryId": str(other.id),
                }
            )

    if entry.teacher_profile_id:
        for other in overlapping.filter(teacher_profile_id=entry.teacher_profile_id):
            conflicts.append(
                {
                    "type": "TEACHER_CONFLICT",
                    "message": f"معلم در این بازه در «{other.course_offering}» کلاس دارد.",
                    "conflictingEntryId": str(other.id),
                }
            )

    class_group_id = entry.course_offering.class_group_id
    for other in overlapping.filter(
        course_offering__class_group_id=class_group_id
    ):
        conflicts.append(
            {
                "type": "CLASS_CONFLICT",
                "message": f"کلاس در این بازه درس «{other.course_offering.course.title}» دارد.",
                "conflictingEntryId": str(other.id),
            }
        )

    return conflicts


def validate_schedule_entry(entry: ScheduleEntry) -> None:
    """در صورت تداخل، خطای قابل فهم برای فرانت تولید می‌کند."""
    conflicts = detect_schedule_conflicts(entry)
    if conflicts:
        raise BusinessRuleViolation(
            code="SCHEDULE_CONFLICT",
            message="این قلم برنامه با برنامه معلم، اتاق یا کلاس تداخل دارد.",
            field_errors=[
                {"field": conflict["type"], "reason": conflict["message"]}
                for conflict in conflicts
            ],
        )


def assert_year_editable(year: AcademicYear) -> None:
    """سال بسته فقط‌خواندنی است (بخش ۷.۱ و ۱۱.۱)."""
    if not year.is_editable:
        raise BusinessRuleViolation(
            code="ACADEMIC_YEAR_CLOSED",
            message=f"سال تحصیلی «{year.title}» بسته است و تغییر در آن مجاز نیست.",
        )


def activate_academic_year(year: AcademicYear) -> AcademicYear:
    """
    فعال‌سازی سال تحصیلی با Checklist بخش ۱۱.۱.

    شرط‌ها: وجود حداقل یک ترم، پوشش کامل بازه سال توسط ترم‌ها، وجود پایه‌ها.
    """
    errors: list[dict[str, str]] = []

    terms = list(year.terms.order_by("sequence_no"))
    if not terms:
        errors.append({"field": "terms", "reason": "حداقل یک ترم باید تعریف شود."})
    else:
        if terms[0].starts_on < year.starts_on or terms[-1].ends_on > year.ends_on:
            errors.append(
                {
                    "field": "terms",
                    "reason": "بازه ترم‌ها باید داخل بازه سال تحصیلی باشد.",
                }
            )

    if not year.school.grade_levels.exists():
        errors.append(
            {"field": "gradeLevels", "reason": "هیچ پایه تحصیلی تعریف نشده است."}
        )

    if errors:
        raise BusinessRuleViolation(
            code="ACADEMIC_YEAR_NOT_READY",
            message="پیش‌نیازهای فعال‌سازی سال تحصیلی کامل نیست.",
            field_errors=errors,
        )

    with transaction.atomic():
        # فقط یک سال پیش‌فرض برای هر مدرسه (بخش ۱۱.۱)
        AcademicYear.objects.filter(school=year.school, is_default=True).exclude(
            pk=year.pk
        ).update(is_default=False)
        year.status = AcademicYearStatus.ACTIVE
        year.is_default = True
        year.save(update_fields=["status", "is_default"])
    return year


def close_academic_year(year: AcademicYear, note: str = "") -> AcademicYear:
    """
    بستن سال تحصیلی.

    بخش ۱۱.۱: بستن پس از کنترل نمرات، کارنامه، وضعیت ثبت‌نام‌ها و اسناد مالی.
    """
    from django.utils import timezone

    from apps.students.models import Enrollment

    pending_enrollments = Enrollment.objects.filter(
        academic_year=year,
        status__in=["PENDING_DOCUMENTS", "PENDING_FINANCE", "PENDING_PLACEMENT"],
    ).count()

    if pending_enrollments:
        raise BusinessRuleViolation(
            code="ACADEMIC_YEAR_HAS_PENDING_ENROLLMENTS",
            message=(
                f"{pending_enrollments} ثبت‌نام هنوز در وضعیت میانی است؛ "
                "پیش از بستن سال باید تعیین تکلیف شوند."
            ),
        )

    year.status = AcademicYearStatus.CLOSED
    year.is_default = False
    year.closed_at = timezone.now()
    year.close_note = note
    year.save(update_fields=["status", "is_default", "closed_at", "close_note"])
    return year


def check_class_capacity(class_group: ClassGroup, additional: int = 1) -> None:
    """
    کنترل ظرفیت کلاس (بخش ۱۱.۳).

    ظرفیت در سه سطح: ظرفیت مصوب کلاس، ظرفیت اتاق و ظرفیت خدمت جانبی.
    """
    if class_group.capacity <= 0:
        return

    occupied = class_group.occupied_seats
    if occupied + additional > class_group.capacity:
        raise BusinessRuleViolation(
            code="CLASS_CAPACITY_EXCEEDED",
            message="ظرفیت کلاس تکمیل است.",
            field_errors=[{"field": "classGroupId", "reason": "capacity"}],
        )

    room = class_group.home_room
    if room and room.capacity and occupied + additional > room.capacity:
        raise BusinessRuleViolation(
            code="ROOM_CAPACITY_EXCEEDED",
            message=f"ظرفیت فیزیکی اتاق «{room.code}» کمتر از تعداد درخواستی است.",
            field_errors=[{"field": "homeRoomId", "reason": "capacity"}],
        )


def publish_schedule(course_offering_id) -> int:
    """انتشار برنامه هفتگی یک ارائه درس؛ خروجی تعداد اقلام منتشرشده."""
    entries = ScheduleEntry.objects.filter(
        course_offering_id=course_offering_id, status=ScheduleStatus.DRAFT
    )
    for entry in entries:
        validate_schedule_entry(entry)
    return entries.update(status=ScheduleStatus.PUBLISHED)


def clone_year_structure(source: AcademicYear, target: AcademicYear) -> dict:
    """
    ایجاد سال جدید از روی Template سال قبل.

    بخش ۱۱.۱: «دانش‌آموز، بدهی، نمره یا حضور کورکورانه کپی نمی‌شود.»
    فقط ساختار (کلاس‌ها و ارائه‌های درس) کپی می‌شود.
    """
    created_classes = 0
    with transaction.atomic():
        for source_class in source.class_groups.all():
            _, was_created = ClassGroup.objects.get_or_create(
                campus=source_class.campus,
                academic_year=target,
                code=source_class.code,
                defaults={
                    "tenant_id": target.tenant_id,
                    "grade_level": source_class.grade_level,
                    "program": source_class.program,
                    "home_room": source_class.home_room,
                    "capacity": source_class.capacity,
                    "title": source_class.title,
                },
            )
            created_classes += int(was_created)
    return {"createdClassGroups": created_classes}
