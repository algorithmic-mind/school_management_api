"""Viewهای ماژول بانک سؤال و آزمون."""

from __future__ import annotations

import django_filters as filters
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.assessment import services
from apps.assessment.enums import (
    AppealStatus,
    AttemptStatus,
    ExamStatus,
    GradingStatus,
    QuestionLifecycle,
    ReviewStatus,
)
from apps.assessment.models import (
    AttemptAnswer,
    Exam,
    ExamAttempt,
    ExamQuestion,
    ExamRegistration,
    ExamSection,
    ExamSession,
    GradeAppeal,
    GradeReview,
    ProctorEvent,
    Question,
    QuestionBank,
    QuestionOption,
    QuestionTag,
    QuestionTagLink,
    QuestionVersion,
)
from apps.assessment.serializers import (
    AttemptAnswerSerializer,
    AttemptPaperSerializer,
    ExamAttemptSerializer,
    ExamDetailSerializer,
    ExamQuestionSerializer,
    ExamRegistrationSerializer,
    ExamSectionSerializer,
    ExamSerializer,
    ExamSessionSerializer,
    GradeAppealSerializer,
    GradeReviewSerializer,
    GradingQueueRowSerializer,
    ManualGradeSerializer,
    ProctorEventSerializer,
    QuestionAnalysisRowSerializer,
    QuestionBankSerializer,
    QuestionCreateSerializer,
    QuestionOptionPublicSerializer,
    QuestionOptionSerializer,
    QuestionSerializer,
    QuestionTagSerializer,
    QuestionVersionSerializer,
    ResolveAppealSerializer,
    SaveAnswerSerializer,
    StartAttemptSerializer,
)
from apps.core.exceptions import BusinessRuleViolation
from apps.core.serializers import (
    ErrorResponseSerializer,
    OperationResultSerializer,
    ReasonSerializer,
)
from apps.core.viewsets import BaseModelViewSet, BaseReadOnlyViewSet

ERRORS = {
    400: OpenApiResponse(ErrorResponseSerializer, description="داده ورودی معتبر نیست"),
    403: OpenApiResponse(ErrorResponseSerializer, description="بدون مجوز"),
    404: OpenApiResponse(ErrorResponseSerializer, description="یافت نشد"),
    409: OpenApiResponse(ErrorResponseSerializer, description="گذار وضعیت نامعتبر"),
    422: OpenApiResponse(ErrorResponseSerializer, description="نقض قاعده کسب‌وکار"),
}


@extend_schema_view(
    list=extend_schema(tags=["Assessment"], summary="فهرست بانک‌های سؤال"),
    create=extend_schema(tags=["Assessment"], summary="ایجاد بانک سؤال"),
)
class QuestionBankViewSet(BaseModelViewSet):
    queryset = QuestionBank.objects.select_related("school", "course")
    serializer_class = QuestionBankSerializer
    filterset_fields = ("school", "course", "visibility", "status")
    search_fields = ("title",)
    permission_resource = "question"


@extend_schema_view(list=extend_schema(tags=["Assessment"], summary="برچسب‌های سؤال"))
class QuestionTagViewSet(BaseModelViewSet):
    queryset = QuestionTag.objects.select_related("school")
    serializer_class = QuestionTagSerializer
    filterset_fields = ("school", "tag_type")
    search_fields = ("value",)
    permission_resource = "question"


class QuestionFilter(filters.FilterSet):
    tag = filters.UUIDFilter(
        field_name="versions__tag_links__tag_id", label="برچسب"
    )
    difficulty = filters.CharFilter(
        field_name="current_version__difficulty", label="سطح دشواری"
    )
    course = filters.UUIDFilter(field_name="bank__course_id", label="درس")
    grade_level = filters.UUIDFilter(
        field_name="current_version__grade_level_id", label="پایه"
    )

    class Meta:
        model = Question
        fields = ("bank", "question_type", "lifecycle_status")


@extend_schema_view(
    list=extend_schema(
        tags=["Assessment"],
        summary="فهرست سؤالات",
        description=(
            "فیلتر بر اساس بانک، نوع، دشواری، مبحث و پایه — برای صفحه «بانک "
            "سؤال» (بخش ۹.۱ سند فرانت)."
        ),
        parameters=[
            OpenApiParameter("tag", str, description="شناسه برچسب مبحث"),
            OpenApiParameter("difficulty", str, description="سطح دشواری نسخه جاری"),
        ],
    ),
    retrieve=extend_schema(tags=["Assessment"], summary="جزئیات سؤال با نسخه جاری"),
)
class QuestionViewSet(BaseModelViewSet):
    queryset = Question.objects.select_related(
        "bank", "current_version"
    ).prefetch_related("current_version__options")
    serializer_class = QuestionSerializer
    filterset_class = QuestionFilter
    search_fields = ("versions__body",)
    permission_resource = "question"
    permission_map = {
        "create_with_version": "question.create",
        "new_version": "question.update",
        "approve": "question.approve",
        "request_changes": "question.review",
        "retire": "question.retire",
    }

    @extend_schema(
        tags=["Assessment"],
        summary="ایجاد سؤال به‌همراه نسخه اول و گزینه‌ها",
        description=(
            "یک درخواست برای کل ویرایشگر سؤال. سؤال، نسخه ۱، گزینه‌ها و "
            "برچسب‌ها در یک تراکنش ساخته می‌شوند."
        ),
        request=QuestionCreateSerializer,
        responses={201: QuestionSerializer, **ERRORS},
        examples=[
            OpenApiExample(
                "سؤال چندگزینه‌ای",
                value={
                    "bank": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
                    "question_type": "SINGLE_CHOICE",
                    "body": "پایتخت ایران کدام شهر است؟",
                    "explanation": "تهران از سال ۱۱۶۵ خورشیدی پایتخت است.",
                    "default_score": 1,
                    "difficulty": "EASY",
                    "options": [
                        {"option_key": "A", "body": "اصفهان", "is_correct": False, "display_order": 1},
                        {"option_key": "B", "body": "تهران", "is_correct": True, "display_order": 2},
                        {"option_key": "C", "body": "شیراز", "is_correct": False, "display_order": 3},
                        {"option_key": "D", "body": "تبریز", "is_correct": False, "display_order": 4},
                    ],
                },
                request_only=True,
            ),
            OpenApiExample(
                "سؤال عددی با تلورانس",
                value={
                    "bank": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
                    "question_type": "NUMERIC",
                    "body": "مقدار تقریبی عدد پی را تا دو رقم اعشار بنویسید.",
                    "default_score": 2,
                    "correct_answer": {"value": 3.14, "tolerance": 0.01},
                },
                request_only=True,
            ),
        ],
    )
    @action(detail=False, methods=["post"], url_path="create-with-version")
    @transaction.atomic
    def create_with_version(self, request):
        from apps.core.context import get_current_context

        body = QuestionCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        ctx = get_current_context()
        tenant_id = ctx.tenant_id if ctx else None

        bank = get_object_or_404(QuestionBank, pk=data["bank"])
        question = Question.objects.create(
            tenant_id=tenant_id,
            bank=bank,
            question_type=data["question_type"],
            lifecycle_status=QuestionLifecycle.DRAFT,
        )
        version = QuestionVersion.objects.create(
            tenant_id=tenant_id,
            question=question,
            version_no=1,
            body=data["body"],
            explanation=data.get("explanation", ""),
            grading_rubric=data.get("grading_rubric", ""),
            default_score=data.get("default_score", 1),
            difficulty=data.get("difficulty", "MEDIUM"),
            grade_level_id=data.get("grade_level"),
            correct_answer=data.get("correct_answer") or {},
        )
        for option in data.get("options", []):
            QuestionOption.objects.create(
                tenant_id=tenant_id, question_version=version, **option
            )
        for tag_id in data.get("tag_ids", []):
            QuestionTagLink.objects.create(
                tenant_id=tenant_id, question_version=version, tag_id=tag_id
            )

        question.current_version = version
        question.save(update_fields=["current_version"])
        return Response(QuestionSerializer(question).data, status=201)

    @extend_schema(
        tags=["Assessment"],
        summary="تأیید نسخه جاری سؤال",
        description=(
            "چرخه سؤال: پیش‌نویس → بازبینی → تأیید → انتشار → بازنشستگی "
            "(بخش ۴.۴)."
        ),
        request=None,
        responses={200: QuestionSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        question = self.get_object()
        version = question.current_version
        if version is None:
            raise BusinessRuleViolation(
                code="NO_CURRENT_VERSION", message="این سؤال نسخه جاری ندارد."
            )
        version.review_status = ReviewStatus.APPROVED
        version.reviewed_by_id = request.user.id
        version.reviewed_at = timezone.now()
        version.save()
        question.lifecycle_status = QuestionLifecycle.APPROVED
        question.save(update_fields=["lifecycle_status"])
        return Response(self.get_serializer(question).data)

    @extend_schema(
        tags=["Assessment"],
        summary="بازنشستگی سؤال",
        description="سؤال بازنشسته در آزمون‌های جدید قابل استفاده نیست، اما آزمون‌های گذشته دست‌نخورده می‌مانند.",
        request=ReasonSerializer,
        responses={200: QuestionSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def retire(self, request, pk=None):
        question = self.get_object()
        question.lifecycle_status = QuestionLifecycle.RETIRED
        question.save(update_fields=["lifecycle_status"])
        return Response(self.get_serializer(question).data)


@extend_schema_view(
    list=extend_schema(tags=["Assessment"], summary="نسخه‌های سؤال"),
    create=extend_schema(
        tags=["Assessment"],
        summary="ایجاد نسخه جدید سؤال",
        description="نسخه‌های قبلی حفظ می‌شوند تا آزمون‌های گذشته تغییر نکنند (بخش ۷.۶).",
    ),
)
class QuestionVersionViewSet(BaseModelViewSet):
    queryset = QuestionVersion.objects.select_related("question").prefetch_related(
        "options"
    )
    serializer_class = QuestionVersionSerializer
    filterset_fields = ("question", "review_status", "difficulty", "grade_level")
    permission_resource = "question"

    def perform_create(self, serializer):
        question = serializer.validated_data["question"]
        last = question.versions.order_by("-version_no").first()
        instance = serializer.save(version_no=(last.version_no + 1) if last else 1)
        question.current_version = instance
        question.save(update_fields=["current_version"])


@extend_schema_view(list=extend_schema(tags=["Assessment"], summary="گزینه‌های سؤال"))
class QuestionOptionViewSet(BaseModelViewSet):
    queryset = QuestionOption.objects.select_related("question_version")
    serializer_class = QuestionOptionSerializer
    filterset_fields = ("question_version", "is_correct")
    permission_resource = "question"


class ExamFilter(filters.FilterSet):
    class_group = filters.UUIDFilter(
        field_name="course_offering__class_group_id", label="کلاس"
    )
    course = filters.UUIDFilter(
        field_name="course_offering__course_id", label="درس"
    )
    term = filters.UUIDFilter(field_name="course_offering__term_id", label="ترم")

    class Meta:
        model = Exam
        fields = ("course_offering", "mode", "purpose", "status")


@extend_schema_view(
    list=extend_schema(tags=["Assessment"], summary="فهرست آزمون‌ها"),
    retrieve=extend_schema(
        tags=["Assessment"],
        summary="جزئیات آزمون با بخش‌ها و جلسات",
        description="برای «سازنده آزمون» (بخش ۹.۳ سند فرانت).",
    ),
    create=extend_schema(tags=["Assessment"], summary="ایجاد آزمون"),
)
class ExamViewSet(BaseModelViewSet):
    queryset = Exam.objects.select_related(
        "course_offering__course", "course_offering__class_group"
    ).prefetch_related("sections__questions", "sessions")
    serializer_class = ExamSerializer
    filterset_class = ExamFilter
    search_fields = ("code", "title")
    permission_resource = "exam"
    permission_map = {
        "submit_for_review": "exam.update",
        "approve": "exam.publish",
        "publish": "exam.publish",
        "cancel": "exam.cancel",
        "close_submission": "exam.update",
        "start_grading": "exam.grade",
        "release_results": "exam.finalize",
        "analysis": "exam.read",
    }

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ExamDetailSerializer
        return ExamSerializer

    def _transition(self, action_name: str):
        exam = self.get_object()
        services.apply_exam_transition(exam, action_name)
        return exam

    @extend_schema(
        tags=["Assessment"],
        summary="ارسال آزمون برای بازبینی",
        request=None,
        responses={200: ExamSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="submit-for-review")
    def submit_for_review(self, request, pk=None):
        return Response(self.get_serializer(self._transition("submit_for_review")).data)

    @extend_schema(
        tags=["Assessment"],
        summary="تأیید آزمون",
        request=None,
        responses={200: ExamSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        exam = self._transition("approve")
        services.apply_exam_transition(exam, "schedule")
        return Response(self.get_serializer(exam).data)

    @extend_schema(
        tags=["Assessment"],
        summary="انتشار آزمون",
        description=(
            "پیش از انتشار بررسی می‌شود که مجموع بارم سؤالات با نمره کل آزمون "
            "برابر باشد و حداقل یک جلسه آزمون تعریف شده باشد (بخش ۷.۶)."
        ),
        request=None,
        responses={200: ExamSerializer, **ERRORS},
        examples=[
            OpenApiExample(
                "خطای ناسازگاری بارم",
                value={
                    "code": "EXAM_NOT_READY_FOR_PUBLISH",
                    "message": "آزمون برای انتشار آماده نیست.",
                    "correlationId": "8c4a1f2e",
                    "fieldErrors": [
                        {
                            "field": "maxScore",
                            "reason": "مجموع بارم سؤالات (18.00) با نمره کل آزمون (20.00) برابر نیست.",
                        }
                    ],
                    "retryable": False,
                },
                response_only=True,
                status_codes=["422"],
            )
        ],
    )
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        return Response(self.get_serializer(self._transition("publish")).data)

    @extend_schema(
        tags=["Assessment"],
        summary="لغو آزمون",
        request=ReasonSerializer,
        responses={200: ExamSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        body = ReasonSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        exam = self._transition("cancel")
        exam.cancel_reason = body.validated_data["reason"]
        exam.save(update_fields=["cancel_reason"])
        return Response(self.get_serializer(exam).data)

    @extend_schema(
        tags=["Assessment"],
        summary="بستن مهلت تحویل",
        request=None,
        responses={200: ExamSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="close-submission")
    def close_submission(self, request, pk=None):
        exam = self._transition("close_submission")
        services.auto_submit_expired_attempts()
        return Response(self.get_serializer(exam).data)

    @extend_schema(
        tags=["Assessment"],
        summary="شروع مرحله تصحیح",
        request=None,
        responses={200: ExamSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="start-grading")
    def start_grading(self, request, pk=None):
        return Response(self.get_serializer(self._transition("start_grading")).data)

    @extend_schema(
        tags=["Assessment"],
        summary="انتشار نتایج",
        description=(
            "پس از انتشار، پنجره اعتراض (پیش‌فرض ۷ روز) باز می‌شود و رویداد "
            "`ScoreFinalized` منتشر می‌گردد."
        ),
        request=None,
        responses={200: ExamSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="release-results")
    def release_results(self, request, pk=None):
        exam = self.get_object()
        services.apply_exam_transition(exam, "moderate")
        services.apply_exam_transition(exam, "approve_scores")
        services.apply_exam_transition(exam, "release_results")

        from apps.workflow.services import publish_event

        publish_event(
            aggregate_type="assessment.Exam",
            aggregate_id=exam.id,
            event_type="ScoreFinalized",
            payload={"examId": str(exam.id), "courseOfferingId": str(exam.course_offering_id)},
            tenant_id=exam.tenant_id,
        )
        return Response(self.get_serializer(exam).data)

    @extend_schema(
        tags=["Assessment"],
        summary="تحلیل سؤالات آزمون",
        description=(
            "درصد پاسخ صحیح، میانگین نمره و میانگین زمان پاسخ هر سؤال "
            "(بخش ۴.۴ — تحلیل کیفیت سؤال)."
        ),
        responses={200: QuestionAnalysisRowSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def analysis(self, request, pk=None):
        exam = self.get_object()
        return Response(services.question_analysis(exam))


@extend_schema_view(list=extend_schema(tags=["Assessment"], summary="بخش‌های آزمون"))
class ExamSectionViewSet(BaseModelViewSet):
    queryset = ExamSection.objects.select_related("exam").prefetch_related("questions")
    serializer_class = ExamSectionSerializer
    filterset_fields = ("exam",)
    permission_resource = "exam"


@extend_schema_view(
    list=extend_schema(tags=["Assessment"], summary="سؤالات آزمون"),
    create=extend_schema(
        tags=["Assessment"],
        summary="افزودن سؤال به آزمون",
        description="ارجاع به نسخه ثابت سؤال است، نه به خود سؤال (بخش ۷.۶).",
    ),
)
class ExamQuestionViewSet(BaseModelViewSet):
    queryset = ExamQuestion.objects.select_related(
        "section__exam", "question_version__question"
    )
    serializer_class = ExamQuestionSerializer
    filterset_fields = ("section", "question_version")
    permission_resource = "exam"


@extend_schema_view(
    list=extend_schema(tags=["Assessment"], summary="جلسات آزمون"),
    create=extend_schema(tags=["Assessment"], summary="تعریف جلسه آزمون"),
)
class ExamSessionViewSet(BaseModelViewSet):
    queryset = ExamSession.objects.select_related("exam", "room").prefetch_related(
        "registrations"
    )
    serializer_class = ExamSessionSerializer
    filterset_fields = ("exam", "room", "status")
    permission_resource = "exam"
    permission_map = {"open": "exam.update", "close": "exam.update", "enroll_class": "exam.update"}

    @extend_schema(
        tags=["Assessment"],
        summary="بازکردن جلسه آزمون",
        request=None,
        responses={200: ExamSessionSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def open(self, request, pk=None):
        session = self.get_object()
        session.status = "OPEN"
        session.save(update_fields=["status"])
        return Response(self.get_serializer(session).data)

    @extend_schema(
        tags=["Assessment"],
        summary="بستن جلسه آزمون",
        description="تلاش‌های باز به‌صورت خودکار تحویل می‌شوند.",
        request=None,
        responses={200: ExamSessionSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        session = self.get_object()
        session.status = "CLOSED"
        session.save(update_fields=["status"])
        services.auto_submit_expired_attempts()
        return Response(self.get_serializer(session).data)

    @extend_schema(
        tags=["Assessment"],
        summary="ثبت‌نام گروهی دانش‌آموزان یک کلاس",
        description="همه اعضای فعال کلاسِ ارائه درس آزمون را ثبت‌نام می‌کند.",
        request=None,
        responses={200: OperationResultSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="enroll-class")
    @transaction.atomic
    def enroll_class(self, request, pk=None):
        from apps.students.models import ClassMembership

        session = self.get_object()
        class_group = session.exam.course_offering.class_group
        memberships = ClassMembership.objects.filter(
            class_group=class_group, status="ACTIVE"
        ).select_related("enrollment")

        created = 0
        for membership in memberships:
            _, was_created = ExamRegistration.objects.get_or_create(
                exam_session=session,
                enrollment=membership.enrollment,
                defaults={"tenant_id": session.tenant_id},
            )
            created += int(was_created)
        return Response({"success": True, "affected": created})


@extend_schema_view(
    list=extend_schema(tags=["Assessment"], summary="ثبت‌نام‌های آزمون"),
    create=extend_schema(
        tags=["Assessment"],
        summary="ثبت‌نام دانش‌آموز در جلسه آزمون",
        description="`extraTimeMinutes` برای زمان اضافه فردی (دسترس‌پذیری) است.",
    ),
)
class ExamRegistrationViewSet(BaseModelViewSet):
    queryset = ExamRegistration.objects.select_related(
        "exam_session__exam", "enrollment__student__person"
    )
    serializer_class = ExamRegistrationSerializer
    filterset_fields = ("exam_session", "enrollment", "registration_status")
    permission_resource = "exam"


@extend_schema_view(
    list=extend_schema(tags=["Assessment"], summary="تلاش‌های آزمون"),
    retrieve=extend_schema(tags=["Assessment"], summary="جزئیات تلاش"),
)
class ExamAttemptViewSet(BaseReadOnlyViewSet):
    """
    تلاش‌های آزمون.

    تلاش با Endpoint صریح `start` ساخته می‌شود، نه با POST معمولی روی منبع
    (بخش ۱۲.۴: عملیات تغییر وضعیت از Endpoint صریح استفاده می‌کند).
    """

    queryset = ExamAttempt.objects.select_related(
        "registration__enrollment__student__person",
        "registration__exam_session__exam",
    )
    serializer_class = ExamAttemptSerializer
    filterset_fields = ("registration", "status")
    permission_resource = "attempt"
    throttle_scope = "exam_attempt"
    permission_map = {
        "start": "attempt.start",
        "paper": "attempt.read",
        "save_answer": "attempt.save",
        "submit": "attempt.submit",
        "grading_queue": "exam.grade",
    }

    @extend_schema(
        tags=["Assessment"],
        summary="شروع تلاش آزمون",
        description=(
            "**Idempotent است.** هدر `Idempotency-Key` را بفرستید؛ ارسال مجدد "
            "با همان کلید، همان تلاش را برمی‌گرداند و تلاش دوم نمی‌سازد.\n\n"
            "اگر تلاشی در وضعیت «در حال پاسخ‌دهی» یا «قطع اتصال» وجود داشته "
            "باشد، همان ادامه پیدا می‌کند (بخش ۹.۷ سند فرانت — بازیابی پس از "
            "قطع اتصال)."
        ),
        request=StartAttemptSerializer,
        responses={201: ExamAttemptSerializer, **ERRORS},
        parameters=[
            OpenApiParameter(
                "Idempotency-Key",
                str,
                location=OpenApiParameter.HEADER,
                description="کلید یکتای عملیات برای جلوگیری از تلاش تکراری",
            )
        ],
    )
    @action(detail=False, methods=["post"])
    def start(self, request):
        from apps.core.context import get_current_context

        body = StartAttemptSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        registration = get_object_or_404(
            ExamRegistration, pk=body.validated_data["registration"]
        )

        ctx = get_current_context()
        attempt = services.start_attempt(
            registration, idempotency_key=(ctx.idempotency_key if ctx else "")
        )
        return Response(ExamAttemptSerializer(attempt).data, status=201)

    @extend_schema(
        tags=["Assessment"],
        summary="برگه آزمون در حال اجرا",
        description=(
            "سؤالات آزمون به همراه پاسخ‌های ذخیره‌شده و زمان باقی‌مانده.\n\n"
            "**کلید پاسخ و پاسخ صحیح در این پاسخ برنمی‌گردد.**"
        ),
        responses={200: AttemptPaperSerializer, **ERRORS},
    )
    @action(detail=True, methods=["get"])
    def paper(self, request, pk=None):
        import random

        attempt = self.get_object()
        exam = attempt.registration.exam_session.exam

        exam_questions = list(
            ExamQuestion.objects.filter(section__exam=exam)
            .select_related("section", "question_version__question")
            .prefetch_related("question_version__options")
            .order_by("section__display_order", "display_order")
        )
        if exam.shuffle_questions:
            random.Random(str(attempt.id)).shuffle(exam_questions)

        saved = {
            answer.exam_question_id: answer.response_payload
            for answer in attempt.answers.all()
        }

        questions = []
        for exam_question in exam_questions:
            version = exam_question.question_version
            options = list(version.options.all())
            if exam.shuffle_options:
                random.Random(f"{attempt.id}{exam_question.id}").shuffle(options)
            questions.append(
                {
                    "examQuestionId": exam_question.id,
                    "sectionTitle": exam_question.section.title,
                    "questionType": version.question.question_type,
                    "body": version.body,
                    "score": exam_question.score,
                    "displayOrder": exam_question.display_order,
                    "isRequired": exam_question.is_required,
                    "options": QuestionOptionPublicSerializer(options, many=True).data,
                    "savedAnswer": saved.get(exam_question.id),
                }
            )

        remaining = None
        if attempt.expires_at:
            remaining = max(
                int((attempt.expires_at - timezone.now()).total_seconds()), 0
            )

        return Response(
            {
                "attemptId": attempt.id,
                "examTitle": exam.title,
                "instructions": exam.instructions,
                "maxScore": exam.max_score,
                "allowBacktrack": exam.allow_backtrack,
                "expiresAt": attempt.expires_at,
                "remainingSeconds": remaining,
                "questions": questions,
            }
        )

    @extend_schema(
        tags=["Assessment"],
        summary="ذخیره خودکار پاسخ",
        description=(
            "هر بار فراخوانی، شماره بازنگری پاسخ یک واحد جلو می‌رود و "
            "`lastSavedAt` تلاش به‌روز می‌شود. پس از پایان مهلت، خطای "
            "`ATTEMPT_TIME_EXPIRED` برمی‌گردد.\n\n"
            "قالب `responsePayload` بر اساس نوع سؤال در توضیح مدل آمده است."
        ),
        request=SaveAnswerSerializer,
        responses={200: AttemptAnswerSerializer, **ERRORS},
        examples=[
            OpenApiExample(
                "چندگزینه‌ای",
                value={
                    "exam_question": "9d8c7b6a-5f4e-3d2c-1b0a-9e8d7c6b5a4f",
                    "response_payload": {"selectedKeys": ["B"]},
                    "time_spent_seconds": 34,
                },
                request_only=True,
            ),
            OpenApiExample(
                "تشریحی",
                value={
                    "exam_question": "9d8c7b6a-5f4e-3d2c-1b0a-9e8d7c6b5a4f",
                    "response_payload": {"text": "پاسخ تشریحی دانش‌آموز…"},
                    "time_spent_seconds": 240,
                },
                request_only=True,
            ),
        ],
    )
    @action(detail=True, methods=["post"], url_path="answers")
    def save_answer(self, request, pk=None):
        attempt = self.get_object()
        body = SaveAnswerSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        answer = services.save_answer(
            attempt,
            body.validated_data["exam_question"],
            body.validated_data["response_payload"],
        )
        if body.validated_data.get("time_spent_seconds"):
            answer.time_spent_seconds = body.validated_data["time_spent_seconds"]
            answer.save(update_fields=["time_spent_seconds"])
        return Response(AttemptAnswerSerializer(answer).data)

    @extend_schema(
        tags=["Assessment"],
        summary="تحویل نهایی آزمون",
        description=(
            "عملیات اتمیک و تکرارپذیر است: ارسال مجدد پس از تحویل، همان نتیجه "
            "را برمی‌گرداند و خطا نمی‌دهد (بخش ۷.۶). تصحیح خودکار بلافاصله "
            "اجرا می‌شود."
        ),
        request=None,
        responses={200: ExamAttemptSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        attempt = self.get_object()
        services.submit_attempt(attempt)
        attempt.refresh_from_db()
        return Response(ExamAttemptSerializer(attempt).data)

    @extend_schema(
        tags=["Assessment"],
        summary="صف تصحیح تشریحی",
        description=(
            "پاسخ‌های نیازمند تصحیح انسانی. با `anonymous=true` نام دانش‌آموز "
            "با شناسه مستعار جایگزین می‌شود (ناشناس‌سازی مصحح — بخش ۴.۴)."
        ),
        parameters=[
            OpenApiParameter("exam", str, description="فیلتر بر اساس آزمون"),
            OpenApiParameter("anonymous", bool, description="ناشناس‌سازی هویت دانش‌آموز"),
        ],
        responses={200: GradingQueueRowSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="grading-queue")
    def grading_queue(self, request):
        exam_id = request.query_params.get("exam")
        anonymous = request.query_params.get("anonymous", "false").lower() == "true"

        answers = AttemptAnswer.objects.filter(
            grading_status=GradingStatus.PENDING
        ).select_related(
            "attempt__registration__enrollment__student__person",
            "attempt__registration__exam_session__exam",
            "exam_question__question_version",
        )
        if exam_id:
            answers = answers.filter(
                attempt__registration__exam_session__exam_id=exam_id
            )

        rows = []
        for answer in answers[:200]:
            student = answer.attempt.registration.enrollment.student
            rows.append(
                {
                    "attemptAnswerId": answer.id,
                    "attemptId": answer.attempt_id,
                    "examTitle": answer.attempt.registration.exam_session.exam.title,
                    "questionBody": answer.exam_question.question_version.body,
                    "responseText": (answer.response_payload or {}).get("text", ""),
                    "maxScore": answer.exam_question.score,
                    "gradingRubric": answer.exam_question.question_version.grading_rubric,
                    "studentLabel": (
                        f"داوطلب {str(answer.attempt_id)[:8]}"
                        if anonymous
                        else student.person.full_name
                    ),
                }
            )
        return Response(rows)


@extend_schema_view(
    list=extend_schema(tags=["Assessment"], summary="پاسخ‌های تلاش"),
)
class AttemptAnswerViewSet(BaseModelViewSet):
    queryset = AttemptAnswer.objects.select_related(
        "attempt", "exam_question__question_version"
    )
    serializer_class = AttemptAnswerSerializer
    filterset_fields = ("attempt", "exam_question", "grading_status")
    permission_resource = "exam"
    permission_map = {"manual_grade": "exam.grade"}
    http_method_names = ["get", "post", "head", "options"]

    @extend_schema(
        tags=["Assessment"],
        summary="ثبت نمره تصحیح دستی",
        description=(
            "نمره باید بین ۰ و بارم سؤال باشد. پس از ثبت، نمره تلاش مجدداً "
            "محاسبه و `calculationVersion` یک واحد جلو می‌رود (بخش ۱۱.۵)."
        ),
        request=ManualGradeSerializer,
        responses={200: GradeReviewSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"], url_path="grade")
    def manual_grade(self, request, pk=None):
        answer = self.get_object()
        body = ManualGradeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        review = services.apply_manual_grade(
            answer,
            body.validated_data["score"],
            body.validated_data.get("feedback", ""),
            request.user.id,
            body.validated_data.get("review_type", "FIRST_PASS"),
        )
        return Response(GradeReviewSerializer(review).data)


@extend_schema_view(
    list=extend_schema(
        tags=["Assessment"],
        summary="رخدادهای مراقبت",
        description=(
            "رخدادها فقط «شاهد» هستند و تصمیم تخلف را به‌صورت خودکار نمی‌گیرند "
            "(بخش ۷.۶)."
        ),
    ),
    create=extend_schema(tags=["Assessment"], summary="ثبت رخداد مراقبت"),
)
class ProctorEventViewSet(BaseModelViewSet):
    queryset = ProctorEvent.objects.select_related("attempt")
    serializer_class = ProctorEventSerializer
    filterset_fields = ("attempt", "event_type", "severity")
    permission_resource = "exam"


@extend_schema_view(list=extend_schema(tags=["Assessment"], summary="بازبینی‌های نمره"))
class GradeReviewViewSet(BaseReadOnlyViewSet):
    queryset = GradeReview.objects.select_related("attempt_answer")
    serializer_class = GradeReviewSerializer
    filterset_fields = ("attempt_answer", "review_type")
    permission_resource = "exam"


@extend_schema_view(
    list=extend_schema(tags=["Assessment"], summary="اعتراض‌های نمره"),
    create=extend_schema(
        tags=["Assessment"],
        summary="ثبت اعتراض به نمره",
        description="فقط تا پایان پنجره اعتراض آزمون امکان‌پذیر است.",
    ),
)
class GradeAppealViewSet(BaseModelViewSet):
    queryset = GradeAppeal.objects.select_related(
        "attempt__registration__enrollment__student__person"
    )
    serializer_class = GradeAppealSerializer
    filterset_fields = ("attempt", "status")
    permission_resource = "appeal"
    permission_map = {"resolve": "appeal.resolve"}

    def perform_create(self, serializer):
        attempt = serializer.validated_data["attempt"]
        exam = attempt.registration.exam_session.exam
        if exam.appeal_deadline and timezone.now() > exam.appeal_deadline:
            raise BusinessRuleViolation(
                code="APPEAL_WINDOW_CLOSED",
                message="پنجره اعتراض به نتایج این آزمون بسته شده است.",
            )
        super().perform_create(serializer)
        attempt.status = AttemptStatus.UNDER_APPEAL
        attempt.save(update_fields=["status"])

    @extend_schema(
        tags=["Assessment"],
        summary="رسیدگی به اعتراض",
        description=(
            "با پذیرش اعتراض، تلاش به مرحله بازتصحیح می‌رود و نمره قبل/بعد "
            "برای ممیزی نگهداری می‌شود."
        ),
        request=ResolveAppealSerializer,
        responses={200: GradeAppealSerializer, **ERRORS},
    )
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def resolve(self, request, pk=None):
        appeal = self.get_object()
        body = ResolveAppealSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        attempt = appeal.attempt
        appeal.score_before = attempt.final_score
        appeal.resolution = body.validated_data["resolution"]
        appeal.resolved_by_id = request.user.id
        appeal.resolved_at = timezone.now()

        if body.validated_data["accepted"]:
            appeal.status = AppealStatus.ACCEPTED
            attempt.status = AttemptStatus.REGRADED
        else:
            appeal.status = AppealStatus.REJECTED
            attempt.status = AttemptStatus.GRADED

        attempt.save(update_fields=["status"])
        appeal.score_after = attempt.final_score
        appeal.save()
        return Response(self.get_serializer(appeal).data)
