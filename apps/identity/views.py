"""Viewهای ماژول هویت، دسترسی و ممیزی."""

from __future__ import annotations

from django.contrib.auth import authenticate
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.core.exceptions import BusinessRuleViolation
from apps.core.permissions import ScopeType
from apps.core.pagination import AuditCursorPagination
from apps.core.serializers import ErrorResponseSerializer, OperationResultSerializer, ReasonSerializer
from apps.core.viewsets import BaseModelViewSet, BaseReadOnlyViewSet
from apps.identity.enums import (
    AccessReviewDecision,
    AccessReviewStatus,
    AuditAction,
    RoleAssignmentStatus,
    UserStatus,
)
from apps.identity import password_reset
from apps.identity.filters import (
    AuditLogFilter,
    PersonFilter,
    UserAccountFilter,
    UserRoleAssignmentFilter,
)
from apps.identity.models import (
    AccessReview,
    AccessReviewItem,
    Address,
    AuditLog,
    ContactPoint,
    Permission,
    Person,
    PersonAddress,
    PersonDocument,
    Role,
    UserAccount,
    UserRoleAssignment,
)
from apps.identity.serializers import (
    AccessReviewItemSerializer,
    AccessReviewSerializer,
    AddressSerializer,
    AuditLogSerializer,
    ContactPointSerializer,
    CurrentUserSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PermissionSerializer,
    PersonAddressSerializer,
    PersonDocumentSerializer,
    PersonListSerializer,
    PersonSerializer,
    RoleSerializer,
    TokenPairSerializer,
    UserAccountCreateSerializer,
    UserAccountSerializer,
    UserRoleAssignmentSerializer,
    VersionedTokenRefreshSerializer,
    WorkingContextSerializer,
)
from apps.identity.services import record_audit

ERROR_RESPONSES = {
    400: OpenApiResponse(ErrorResponseSerializer, description="داده ورودی معتبر نیست"),
    401: OpenApiResponse(ErrorResponseSerializer, description="نیازمند احراز هویت"),
    403: OpenApiResponse(ErrorResponseSerializer, description="بدون مجوز یا خارج از Scope"),
    404: OpenApiResponse(ErrorResponseSerializer, description="یافت نشد"),
    409: OpenApiResponse(ErrorResponseSerializer, description="تعارض وضعیت یا نسخه"),
    422: OpenApiResponse(ErrorResponseSerializer, description="نقض قاعده کسب‌وکار"),
}


def _request_ip(request) -> str | None:
    """نشانی واقعی کلاینت، با احترام به هدر Proxy."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


# ===========================================================================
# احراز هویت
# ===========================================================================
@extend_schema(
    tags=["Auth"],
    summary="ورود و دریافت توکن",
    description=(
        "با نام کاربری و رمز عبور، جفت توکن `access`/`refresh` صادر می‌شود.\n\n"
        "**نکته امنیتی (بخش ۱۵.۱ سند تحلیل):** پیام خطای ورود ناموفق عمومی است "
        "و وجود یا نبود حساب را افشا نمی‌کند.\n\n"
        "پس از ورود، برای تعیین محیط کاری، `/api/v1/auth/me/` را صدا بزنید و از "
        "فهرست `contexts` یکی را انتخاب کرده و در درخواست‌های بعدی هدرهای "
        "`X-School-Id` / `X-Campus-Id` / `X-Academic-Year-Id` را بفرستید."
    ),
    request=LoginSerializer,
    responses={
        200: OpenApiResponse(TokenPairSerializer, description="ورود موفق"),
        401: OpenApiResponse(ErrorResponseSerializer, description="نام کاربری یا رمز عبور نادرست"),
        429: OpenApiResponse(ErrorResponseSerializer, description="تعداد تلاش بیش از حد مجاز"),
    },
    examples=[
        OpenApiExample(
            "درخواست",
            value={"username": "vp.academic", "password": "SecurePass!2026"},
            request_only=True,
        ),
        OpenApiExample(
            "پاسخ موفق",
            value={
                "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "expiresIn": 1800,
                "mustChangePassword": False,
                "mfaRequired": False,
            },
            response_only=True,
        ),
        OpenApiExample(
            "پاسخ ناموفق",
            value={
                "code": "AUTHENTICATION_FAILED",
                "message": "نام کاربری یا رمز عبور درست نیست.",
                "correlationId": "9f2c1a4b8e7d",
                "fieldErrors": [],
                "retryable": False,
            },
            response_only=True,
            status_codes=["401"],
        ),
    ],
)
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "auth"
    serializer_class = LoginSerializer

    #: خطای ورود ناموفق همیشه یکسان است تا وجود یا نبود حساب افشا نشود
    #: (بخش ۱۵.۱). قفل‌بودن حساب هم با همین پیام برنمی‌گردد، چون خودش نشانه
    #: وجود حساب است؛ فقط کد پاسخ فرق می‌کند.
    GENERIC_FAILURE = "نام کاربری یا رمز عبور درست نیست."

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]

        account = UserAccount.objects.filter(username=username).first()

        # قفل موقت پیش از بررسی رمز کنترل می‌شود؛ وگرنه مهاجم می‌تواند در طول
        # مدت قفل هم به آزمودن رمزها ادامه دهد.
        if account is not None and account.is_locked_out:
            record_audit(
                action=AuditAction.LOGIN_FAILED,
                entity_type="identity.UserAccount",
                entity_id=account.id,
                entity_label=username,
                reason="تلاش ورود روی حساب قفل‌شده",
                actor_username=username,
            )
            raise BusinessRuleViolation(
                code="ACCOUNT_LOCKED",
                message=(
                    "این حساب به‌دلیل تلاش‌های ناموفق موقتاً قفل شده است؛ "
                    "کمی بعد دوباره تلاش کنید."
                ),
                # قفل موقت است، پس فرانت می‌تواند «بعداً دوباره تلاش کنید» را
                # نشان دهد، نه «با پشتیبانی تماس بگیرید».
                retryable=True,
                status_code=status.HTTP_423_LOCKED,
            )

        user = authenticate(request, username=username, password=password)

        if user is None:
            locked = account.register_failed_login() if account else False
            record_audit(
                action=AuditAction.LOGIN_FAILED,
                entity_type="identity.UserAccount",
                entity_id=account.id if account else None,
                entity_label=username,
                reason="قفل حساب پس از تلاش‌های ناموفق" if locked else "",
                actor_username=username,
            )
            raise BusinessRuleViolation(
                code="AUTHENTICATION_FAILED",
                message=self.GENERIC_FAILURE,
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        if user.status in {UserStatus.LOCKED, UserStatus.SUSPENDED, UserStatus.DISABLED}:
            raise BusinessRuleViolation(
                code="ACCOUNT_NOT_ACTIVE",
                message="این حساب کاربری فعال نیست. با مدیر سامانه تماس بگیرید.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        from apps.identity.serializers import ContextTokenObtainPairSerializer

        refresh = ContextTokenObtainPairSerializer.get_token(user)
        user.register_successful_login(_request_ip(request))

        record_audit(
            action=AuditAction.LOGIN,
            entity_type="identity.UserAccount",
            entity_id=user.id,
            entity_label=user.username,
            actor_username=user.username,
        )

        from django.conf import settings

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "expiresIn": int(
                    settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()
                ),
                "mustChangePassword": user.must_change_password,
                "mfaRequired": user.mfa_enabled,
            }
        )


@extend_schema(
    tags=["Auth"],
    summary="تازه‌سازی توکن دسترسی",
    description=(
        "با ارسال `refresh` معتبر، توکن `access` تازه دریافت می‌شود.\n\n"
        "اگر نشست باطل شده باشد (خروج، تغییر رمز، ابطال توسط مدیر)، پاسخ ۴۰۱ "
        "با کد `token_revoked` است؛ فرانت باید کاربر را به صفحه ورود ببرد و "
        "دوباره تلاش نکند."
    ),
    responses={
        200: OpenApiResponse(description="توکن دسترسی تازه"),
        401: OpenApiResponse(
            ErrorResponseSerializer, description="Refresh نامعتبر، منقضی یا باطل‌شده"
        ),
    },
)
class RefreshTokenView(TokenRefreshView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "auth"
    serializer_class = VersionedTokenRefreshSerializer


@extend_schema(
    tags=["Auth"],
    summary="خروج از سامانه",
    description=(
        "همه توکن‌های در گردش کاربر — هم `access` و هم `refresh`، روی همه "
        "دستگاه‌ها — بلافاصله باطل می‌شوند و رخداد خروج ممیزی می‌گردد.\n\n"
        "ابطال با جلوبردن نسخه توکن انجام می‌شود، پس نیازی به ارسال بدنه یا "
        "نگهداری فهرست سیاه نیست. فرانت باید توکن‌های ذخیره‌شده را پاک کند."
    ),
    request=None,
    responses={200: OperationResultSerializer, 401: ErrorResponseSerializer},
)
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.user.revoke_tokens()
        record_audit(
            action=AuditAction.LOGOUT,
            entity_type="identity.UserAccount",
            entity_id=request.user.id,
            entity_label=request.user.username,
            actor_username=request.user.username,
        )
        return Response(
            {"success": True, "message": "خروج انجام شد و نشست‌های فعال باطل شدند."}
        )


@extend_schema(
    tags=["Auth"],
    summary="پروفایل کاربر جاری، مجوزها و محیط‌های کاری",
    description=(
        "همه‌چیزی که فرانت برای ساخت منو، کنترل نمایش دکمه‌ها و صفحه "
        "«انتخاب محیط کاری» لازم دارد:\n\n"
        "- `permissions`: فهرست کدهای مجوز مؤثر (مثلاً `student.read`). "
        "فرانت باید نمایش هر عمل را با این فهرست کنترل کند.\n"
        "- `contexts`: محیط‌های کاری مجاز (نقش + دامنه). اگر فقط یک مورد باشد، "
        "صفحه انتخاب محیط Skip می‌شود (بخش ۵.۲ سند فرانت)."
    ),
    responses={200: CurrentUserSerializer, 401: ErrorResponseSerializer},
    examples=[
        OpenApiExample(
            "نمونه پاسخ",
            value={
                "id": "0f8f9b2c-7d3e-4a1b-9c5d-2e6f7a8b9c0d",
                "username": "vp.academic",
                "displayName": "زهرا محمدی",
                "email": "vp@example.school",
                "mobile": "09120000000",
                "personId": "6b1d2f3a-4c5e-4d7f-8a9b-0c1d2e3f4a5b",
                "tenantId": "11111111-2222-3333-4444-555555555555",
                "status": "ACTIVE",
                "mfaEnabled": False,
                "mustChangePassword": False,
                "isSuperuser": False,
                "roles": ["ACADEMIC_VP"],
                "permissions": [
                    "attendance.read",
                    "attendance.finalize",
                    "class_group.read",
                    "grade.publish",
                ],
                "contexts": [
                    {
                        "roleCode": "ACADEMIC_VP",
                        "roleTitle": "معاون آموزشی",
                        "scopeType": "CAMPUS",
                        "scopeId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    }
                ],
            },
            response_only=True,
        )
    ],
)
class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        scopes = user.get_effective_scopes()
        permissions = sorted(user.get_effective_permission_codes())
        payload = {
            "id": user.id,
            "username": user.username,
            "displayName": user.display_name,
            "email": user.email,
            "mobile": user.mobile,
            "personId": user.person_id,
            "tenantId": user.tenant_id,
            "status": user.status,
            "mfaEnabled": user.mfa_enabled,
            "mustChangePassword": user.must_change_password,
            "isSuperuser": user.is_superuser,
            "roles": sorted({s["role__code"] for s in scopes}),
            "permissions": permissions,
            "contexts": [
                {
                    "roleCode": s["role__code"],
                    "roleTitle": s["role__title"],
                    "scopeType": s["scope_type"],
                    "scopeId": s["scope_id"],
                }
                for s in scopes
            ],
        }
        return Response(CurrentUserSerializer(payload).data)


@extend_schema(
    tags=["Auth"],
    summary="تغییر رمز عبور",
    description=(
        "تغییر رمز عبور کاربرِ واردشده. رمز فعلی برای تأیید هویت الزامی است.\n\n"
        "- رمز جدید با اعتبارسنج‌های رمز جنگو بررسی می‌شود (طول، سادگی، شباهت "
        "به نام کاربری).\n"
        "- پس از موفقیت، `mustChangePassword` صفر می‌شود و رخداد در ممیزی ثبت "
        "می‌گردد.\n"
        "- همه توکن‌های صادرشده پیش از تغییر رمز بلافاصله باطل می‌شوند "
        "(بخش ۱۵.۱)، پس کاربر باید با رمز جدید دوباره وارد شود."
    ),
    request=PasswordChangeSerializer,
    responses={200: OperationResultSerializer, 400: ErrorResponseSerializer},
    examples=[
        OpenApiExample(
            "تغییر رمز",
            value={
                "current_password": "P@ssw0rd!2025",
                "new_password": "P@ssw0rd!2026",
            },
            request_only=True,
        ),
        OpenApiExample(
            "پاسخ موفق",
            value={"success": True, "message": "رمز عبور با موفقیت تغییر کرد."},
            response_only=True,
        ),
    ],
)
class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.password_changed_at = timezone.now()
        user.save(
            update_fields=["password", "must_change_password", "password_changed_at"]
        )
        # بخش ۱۵.۱: تغییر رمز، نشست‌های پیشین را باطل می‌کند — وگرنه کسی که با
        # رمز قدیمی توکن گرفته، تا نیم‌ساعت بعد هنوز داخل سامانه است.
        user.revoke_tokens()
        record_audit(
            action=AuditAction.UPDATE,
            entity_type="identity.UserAccount",
            entity_id=user.id,
            entity_label=user.username,
            reason="تغییر رمز عبور توسط کاربر",
            actor_username=user.username,
        )
        return Response(
            {
                "success": True,
                "message": "رمز عبور تغییر کرد؛ برای ادامه دوباره وارد شوید.",
            }
        )


@extend_schema(
    tags=["Auth"],
    summary="درخواست بازیابی رمز عبور",
    description=(
        "پاسخ همیشه یکسان است تا وجود یا نبود حساب افشا نشود (بخش ۱۵.۱). "
        "در صورت وجود حساب، لینک/کد بازیابی از کانال ترجیحی ارسال می‌شود."
    ),
    request=PasswordResetRequestSerializer,
    responses={200: OperationResultSerializer},
)
class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        account = password_reset.find_account(serializer.validated_data["identifier"])
        if account is not None:
            uid, token = password_reset.build_token(account)
            _deliver_reset_link(account, uid, token)
            record_audit(
                action=AuditAction.UPDATE,
                entity_type="identity.UserAccount",
                entity_id=account.id,
                entity_label=account.username,
                reason="درخواست بازیابی رمز عبور",
                actor_username=account.username,
            )

        return Response(
            {
                "success": True,
                "message": "اگر حسابی با این مشخصات وجود داشته باشد، راهنمای بازیابی ارسال می‌شود.",
            }
        )


def _deliver_reset_link(account, uid: str, token: str) -> None:
    """
    لینک بازیابی را از کانال ترجیحی کاربر می‌فرستد.

    خطای ارسال نباید پاسخ را تغییر دهد؛ وگرنه تفاوت زمان یا نتیجه پاسخ، خودش
    وجود حساب را لو می‌دهد (بخش ۱۵.۱).
    """
    import logging

    link = password_reset.build_reset_link(uid, token)
    if account.person_id is None:
        logging.getLogger(__name__).warning(
            "بازیابی رمز برای حساب بدون شخص مرتبط؛ پیام ارسال نشد: %s",
            account.username,
        )
        return

    try:
        from apps.core.enums import NotificationChannel
        from apps.workflow.enums import NotificationPriority
        from apps.workflow.services import queue_notification

        channel = (
            NotificationChannel.SMS if account.mobile else NotificationChannel.EMAIL
        )
        queue_notification(
            recipient_person=account.person,
            channel=channel,
            subject="بازیابی رمز عبور",
            body=(
                f"برای تعیین رمز تازه این نشانی را باز کنید: {link}\n"
                "اگر شما درخواست نداده‌اید، این پیام را نادیده بگیرید."
            ),
            priority=NotificationPriority.TRANSACTIONAL,
            deep_link=link,
            related_type="identity.UserAccount",
            related_id=account.id,
            tenant_id=account.tenant_id,
        )
    except Exception:  # pragma: no cover - ارسال نباید مسیر اصلی را بشکند
        logging.getLogger(__name__).exception("ارسال پیام بازیابی رمز ناموفق بود.")


@extend_schema(
    tags=["Auth"],
    summary="تعیین رمز تازه با توکن بازیابی",
    description=(
        "`uid` و `token` را از پارامترهای لینک بازیابی بردارید و همراه رمز "
        "تازه بفرستید.\n\n"
        "- توکن یک‌بارمصرف است و با نخستین استفاده موفق باطل می‌شود.\n"
        "- عمر توکن از `PASSWORD_RESET_TIMEOUT` می‌آید (پیش‌فرض ۲ ساعت).\n"
        "- پس از موفقیت، همه نشست‌های فعال کاربر باطل می‌شوند.\n"
        "- خطای توکن نامعتبر و منقضی یکسان است تا اطلاعاتی درباره حساب فاش نشود."
    ),
    request=PasswordResetConfirmSerializer,
    responses={
        200: OperationResultSerializer,
        400: OpenApiResponse(
            ErrorResponseSerializer, description="توکن نامعتبر یا رمز ضعیف"
        ),
    },
)
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "password_reset"

    def post(self, request):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        account = password_reset.resolve_token(data["uid"], data["token"])
        if account is None:
            raise BusinessRuleViolation(
                code="INVALID_RESET_TOKEN",
                message="لینک بازیابی نامعتبر یا منقضی شده است؛ دوباره درخواست دهید.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(data["new_password"], account)
        except DjangoValidationError as error:
            raise BusinessRuleViolation(
                code="WEAK_PASSWORD",
                message=" ".join(error.messages),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        account.set_password(data["new_password"])
        account.must_change_password = False
        account.password_changed_at = timezone.now()
        account.failed_login_count = 0
        account.locked_until = None
        if account.status == UserStatus.LOCKED:
            account.status = UserStatus.ACTIVE
        account.save(
            update_fields=[
                "password",
                "must_change_password",
                "password_changed_at",
                "failed_login_count",
                "locked_until",
                "status",
            ]
        )
        account.revoke_tokens()

        record_audit(
            action=AuditAction.UPDATE,
            entity_type="identity.UserAccount",
            entity_id=account.id,
            entity_label=account.username,
            reason="بازیابی رمز عبور با توکن",
            actor_username=account.username,
        )
        return Response(
            {"success": True, "message": "رمز عبور تعیین شد؛ اکنون وارد شوید."}
        )


@extend_schema(
    tags=["Auth"],
    summary="ابطال همه نشست‌های من",
    description=(
        "همه توکن‌های در گردش کاربر روی همه دستگاه‌ها باطل می‌شوند — همان "
        "دکمه «خروج از همه دستگاه‌ها» (بخش ۱۵.۱).\n\n"
        "توکن خودِ همین درخواست هم باطل می‌شود، پس فرانت باید بلافاصله کاربر "
        "را به صفحه ورود ببرد."
    ),
    request=None,
    responses={200: OperationResultSerializer, 401: ErrorResponseSerializer},
)
class RevokeSessionsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.user.revoke_tokens()
        record_audit(
            action=AuditAction.LOGOUT,
            entity_type="identity.UserAccount",
            entity_id=request.user.id,
            entity_label=request.user.username,
            reason="ابطال دستی همه نشست‌ها",
            actor_username=request.user.username,
        )
        return Response(
            {"success": True, "message": "همه نشست‌های فعال شما باطل شدند."}
        )


@extend_schema(
    tags=["Auth"],
    summary="محیط‌های کاری من",
    description=(
        "داده کامل صفحه «انتخاب مدرسه، شعبه و سال» (بخش ۵.۲ سند فرانت).\n\n"
        "برخلاف `contexts` در `/auth/me/` که فقط شناسه دامنه را می‌دهد، اینجا "
        "نام خواندنی هر دامنه و هدرهایی که باید فرستاده شوند هم می‌آید:\n\n"
        "- `contexts[].scopeTitle`: نام مدرسه/شعبه/سال برای نمایش در فهرست.\n"
        "- `contexts[].schoolId` و `campusId` و `academicYearId`: دقیقاً همان "
        "مقادیری که باید در هدرهای Context برود.\n"
        "- `defaultContext`: اگر فقط یک محیط کاری وجود داشته باشد، فرانت صفحه "
        "انتخاب را Skip می‌کند و همین را به کار می‌برد.\n"
        "- `schools`: فهرست مدارس در دسترس، برای Dropdown بالای صفحه."
    ),
    responses={200: WorkingContextSerializer, 401: ErrorResponseSerializer},
)
class WorkingContextView(APIView):
    permission_classes = [IsAuthenticated]

    #: نگاشت نوع دامنه به هدری که فرانت باید بفرستد.
    SCOPE_HEADERS = {
        ScopeType.SCHOOL: "schoolId",
        ScopeType.CAMPUS: "campusId",
        ScopeType.ACADEMIC_YEAR: "academicYearId",
    }

    def get(self, request):
        from apps.organization.models import AcademicYear, Campus, School

        user = request.user
        assignments = user.get_effective_scopes()

        # نام دامنه‌ها یک‌جا خوانده می‌شود تا در حلقه Query تکراری نزنیم.
        ids_by_type: dict[str, set] = {}
        for assignment in assignments:
            if assignment["scope_id"]:
                ids_by_type.setdefault(assignment["scope_type"], set()).add(
                    assignment["scope_id"]
                )

        titles: dict[str, dict] = {}
        for scope_type, model, field in (
            (ScopeType.SCHOOL, School, "name"),
            (ScopeType.CAMPUS, Campus, "name"),
            (ScopeType.ACADEMIC_YEAR, AcademicYear, "title"),
        ):
            wanted = ids_by_type.get(scope_type)
            if not wanted:
                continue
            titles[scope_type] = {
                str(item.pk): item for item in model.objects.filter(pk__in=wanted)
            }

        scope_labels = dict(ScopeType.CHOICES)
        contexts = []
        for assignment in assignments:
            scope_type = assignment["scope_type"]
            scope_id = assignment["scope_id"]
            target = titles.get(scope_type, {}).get(str(scope_id)) if scope_id else None

            entry = {
                "roleCode": assignment["role__code"],
                "roleTitle": assignment["role__title"],
                "scopeType": scope_type,
                "scopeTypeDisplay": scope_labels.get(scope_type, scope_type),
                "scopeId": scope_id,
                "scopeTitle": str(target) if target else "",
                "schoolId": None,
                "campusId": None,
                "academicYearId": None,
            }
            header_field = self.SCOPE_HEADERS.get(scope_type)
            if header_field and scope_id:
                entry[header_field] = scope_id
            # شعبه و سال تحصیلی، مدرسه خودشان را هم تعیین می‌کنند؛ فرانت لازم
            # نیست برای پرکردن هدر X-School-Id درخواست جداگانه بزند.
            if target is not None and scope_type in {
                ScopeType.CAMPUS,
                ScopeType.ACADEMIC_YEAR,
            }:
                entry["schoolId"] = target.school_id
            contexts.append(entry)

        schools = self._accessible_schools(request, School)

        return Response(
            WorkingContextSerializer(
                {
                    "defaultContext": contexts[0] if len(contexts) == 1 else None,
                    "contexts": contexts,
                    "schools": schools,
                    "headers": {
                        "school": "X-School-Id",
                        "campus": "X-Campus-Id",
                        "academicYear": "X-Academic-Year-Id",
                    },
                }
            ).data
        )

    @staticmethod
    def _accessible_schools(request, School) -> list[dict]:
        """مدارسی که کاربر با نقش‌های فعلی‌اش به آن‌ها دسترسی دارد."""
        from apps.core.context import get_current_context

        queryset = School.objects.all()
        ctx = get_current_context()
        if ctx and ctx.tenant_id:
            queryset = queryset.filter(tenant_id=ctx.tenant_id)

        scope = getattr(ctx, "effective_scope", None) if ctx else None
        if scope is not None and not scope.is_unrestricted:
            allowed = scope.dimension("schools")
            if allowed is not None:
                if not allowed:
                    return []
                queryset = queryset.filter(pk__in=allowed)

        return [
            {"id": str(school.pk), "name": school.name, "code": school.code}
            for school in queryset.order_by("name")
        ]


# ===========================================================================
# منابع IAM
# ===========================================================================
@extend_schema_view(
    list=extend_schema(
        tags=["IAM"],
        summary="فهرست اشخاص",
        description=(
            "جست‌وجو در اشخاص با نام، نام خانوادگی یا شماره ملی. "
            "این فهرست پایه انتخاب دانش‌آموز، ولی و کارمند است."
        ),
        parameters=[
            OpenApiParameter(
                "search",
                str,
                description="جست‌وجوی متنی در نام، نام خانوادگی و شماره ملی",
            )
        ],
        responses={200: PersonListSerializer, **ERROR_RESPONSES},
    ),
    retrieve=extend_schema(tags=["IAM"], summary="جزئیات شخص"),
    create=extend_schema(tags=["IAM"], summary="ایجاد شخص"),
    update=extend_schema(tags=["IAM"], summary="ویرایش کامل شخص"),
    partial_update=extend_schema(tags=["IAM"], summary="ویرایش جزئی شخص"),
    destroy=extend_schema(tags=["IAM"], summary="حذف نرم شخص"),
)
class PersonViewSet(BaseModelViewSet):
    """
    اشخاص — هویت پایه مستقل از نقش.

    بخش ۵ سند تحلیل: «Person هویت پایه فرد؛ مستقل از نقش دانش‌آموز، ولی یا کارمند.»
    """

    queryset = Person.objects.select_related("tenant").prefetch_related(
        "contact_points", "person_addresses__address"
    )
    serializer_class = PersonSerializer
    filterset_class = PersonFilter
    search_fields = ("first_name", "last_name", "national_id", "passport_no")
    ordering_fields = ("last_name", "first_name", "created_at", "birth_date")
    permission_resource = "person"

    def get_serializer_class(self):
        if self.action == "list":
            return PersonListSerializer
        return PersonSerializer

    @extend_schema(
        tags=["IAM"],
        summary="مدارک شخص",
        responses={200: PersonDocumentSerializer(many=True)},
    )
    @action(detail=True, methods=["get"], url_path="documents")
    def documents(self, request, pk=None):
        person = self.get_object()
        queryset = PersonDocument.objects.filter(person=person)
        return Response(PersonDocumentSerializer(queryset, many=True).data)


@extend_schema_view(
    list=extend_schema(tags=["IAM"], summary="فهرست راه‌های تماس"),
    create=extend_schema(tags=["IAM"], summary="افزودن راه تماس"),
)
class ContactPointViewSet(BaseModelViewSet):
    queryset = ContactPoint.objects.select_related("person")
    serializer_class = ContactPointSerializer
    filterset_fields = ("person", "contact_type", "is_primary", "is_verified")
    permission_resource = "person"


@extend_schema_view(list=extend_schema(tags=["IAM"], summary="فهرست نشانی‌ها"))
class AddressViewSet(BaseModelViewSet):
    queryset = Address.objects.all()
    serializer_class = AddressSerializer
    filterset_fields = ("city", "province", "postal_code")
    search_fields = ("line", "city", "postal_code")
    permission_resource = "person"


@extend_schema_view(list=extend_schema(tags=["IAM"], summary="نشانی‌های اشخاص"))
class PersonAddressViewSet(BaseModelViewSet):
    queryset = PersonAddress.objects.select_related("person", "address")
    serializer_class = PersonAddressSerializer
    filterset_fields = ("person", "address_type")
    permission_resource = "person"


@extend_schema_view(
    list=extend_schema(tags=["IAM"], summary="مدارک اشخاص"),
    create=extend_schema(tags=["IAM"], summary="بارگذاری مدرک"),
)
class PersonDocumentViewSet(BaseModelViewSet):
    queryset = PersonDocument.objects.select_related("person")
    serializer_class = PersonDocumentSerializer
    filterset_fields = ("person", "document_type", "verification_status")
    permission_resource = "person"

    @extend_schema(
        tags=["IAM"],
        summary="تأیید مدرک",
        request=None,
        responses={200: PersonDocumentSerializer},
    )
    @action(detail=True, methods=["post"], url_path="verify")
    def verify(self, request, pk=None):
        document = self.get_object()
        document.verification_status = "VERIFIED"
        document.verified_at = timezone.now()
        document.verified_by_id = request.user.id
        document.save()
        return Response(self.get_serializer(document).data)


@extend_schema_view(
    list=extend_schema(
        tags=["IAM"],
        summary="فهرست مجوزهای سامانه",
        description=(
            "کاتالوگ کامل مجوزهای اتمی به شکل `resource.action`. "
            "فرانت می‌تواند از این فهرست برای ساخت صفحه «تعریف نقش» استفاده کند."
        ),
    ),
    retrieve=extend_schema(tags=["IAM"], summary="جزئیات مجوز"),
)
class PermissionViewSet(BaseReadOnlyViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    filterset_fields = ("module", "resource", "action", "is_sensitive")
    search_fields = ("code", "title", "resource")
    ordering_fields = ("module", "resource", "code")
    permission_resource = "role"
    tenant_field = None
    pagination_class = None


@extend_schema_view(
    list=extend_schema(tags=["IAM"], summary="فهرست نقش‌ها"),
    retrieve=extend_schema(tags=["IAM"], summary="جزئیات نقش"),
    create=extend_schema(tags=["IAM"], summary="ایجاد نقش سفارشی"),
    update=extend_schema(tags=["IAM"], summary="ویرایش نقش"),
    destroy=extend_schema(
        tags=["IAM"],
        summary="حذف نقش",
        description="نقش سیستمی قابل حذف نیست (بخش ۷.۳).",
    ),
)
class RoleViewSet(BaseModelViewSet):
    queryset = Role.objects.prefetch_related("permissions")
    serializer_class = RoleSerializer
    filterset_fields = ("is_system", "requires_mfa")
    search_fields = ("code", "title")
    permission_resource = "role"

    def perform_destroy(self, instance):
        if instance.is_system:
            raise BusinessRuleViolation(
                code="SYSTEM_ROLE_IMMUTABLE",
                message="نقش سیستمی قابل حذف نیست.",
            )
        super().perform_destroy(instance)


@extend_schema_view(
    list=extend_schema(tags=["IAM"], summary="فهرست حساب‌های کاربری"),
    retrieve=extend_schema(tags=["IAM"], summary="جزئیات حساب کاربری"),
    create=extend_schema(
        tags=["IAM"],
        summary="ایجاد حساب کاربری",
        description=(
            "اگر `password` ارسال نشود، حساب بدون رمز قابل استفاده ساخته می‌شود "
            "و کاربر باید از مسیر بازیابی رمز، رمز خود را تعیین کند."
        ),
    ),
)
class UserAccountViewSet(BaseModelViewSet):
    queryset = UserAccount.objects.select_related("person").prefetch_related(
        "role_assignments__role"
    )
    serializer_class = UserAccountSerializer
    filterset_class = UserAccountFilter
    search_fields = ("username", "email", "mobile", "person__first_name", "person__last_name")
    permission_resource = "user"
    permission_map = {
        "unlock": "user.disable",
        "revoke_sessions": "user.disable",
    }

    def get_serializer_class(self):
        if self.action == "create":
            return UserAccountCreateSerializer
        return UserAccountSerializer

    @extend_schema(
        tags=["IAM"],
        summary="غیرفعال‌سازی حساب",
        request=ReasonSerializer,
        responses={200: UserAccountSerializer, **ERROR_RESPONSES},
    )
    @action(detail=True, methods=["post"], url_path="disable")
    def disable(self, request, pk=None):
        user = self.get_object()
        body = ReasonSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        user.status = UserStatus.DISABLED
        user.is_active = False
        user.save(update_fields=["status", "is_active"])
        # بدون ابطال، توکن معتبرِ همین کاربر تا نیم‌ساعت بعد هنوز کار می‌کند.
        user.revoke_tokens()
        record_audit(
            action=AuditAction.PERMISSION_CHANGE,
            entity_type="identity.UserAccount",
            entity_id=user.id,
            entity_label=user.username,
            reason=body.validated_data["reason"],
        )
        return Response(UserAccountSerializer(user).data)

    @extend_schema(
        tags=["IAM"],
        summary="فعال‌سازی مجدد حساب",
        description="وضعیت به «فعال» برمی‌گردد و قفل و شمارنده تلاش ناموفق پاک می‌شود.",
        request=ReasonSerializer,
        responses={200: UserAccountSerializer, **ERROR_RESPONSES},
    )
    @action(detail=True, methods=["post"], url_path="enable")
    def enable(self, request, pk=None):
        user = self.get_object()
        body = ReasonSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        user.status = UserStatus.ACTIVE
        user.is_active = True
        user.locked_until = None
        user.failed_login_count = 0
        user.save(
            update_fields=["status", "is_active", "locked_until", "failed_login_count"]
        )
        record_audit(
            action=AuditAction.PERMISSION_CHANGE,
            entity_type="identity.UserAccount",
            entity_id=user.id,
            entity_label=user.username,
            reason=body.validated_data["reason"],
        )
        return Response(UserAccountSerializer(user).data)

    @extend_schema(
        tags=["IAM"],
        summary="بازکردن قفل حساب",
        description=(
            "قفل موقتِ ناشی از تلاش‌های ناموفق ورود را برمی‌دارد، بدون آنکه "
            "وضعیت حساب را تغییر دهد. حسابی که مدیر عمداً غیرفعال کرده با این "
            "Endpoint فعال نمی‌شود؛ برای آن `enable/` را صدا بزنید."
        ),
        request=ReasonSerializer,
        responses={200: UserAccountSerializer, **ERROR_RESPONSES},
    )
    @action(detail=True, methods=["post"], url_path="unlock")
    def unlock(self, request, pk=None):
        user = self.get_object()
        body = ReasonSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        user.locked_until = None
        user.failed_login_count = 0
        if user.status == UserStatus.LOCKED:
            user.status = UserStatus.ACTIVE
        user.save(update_fields=["locked_until", "failed_login_count", "status"])
        record_audit(
            action=AuditAction.PERMISSION_CHANGE,
            entity_type="identity.UserAccount",
            entity_id=user.id,
            entity_label=user.username,
            reason=body.validated_data["reason"],
        )
        return Response(UserAccountSerializer(user).data)

    @extend_schema(
        tags=["IAM"],
        summary="ابطال نشست‌های کاربر",
        description=(
            "همه توکن‌های در گردش کاربر باطل می‌شوند — برای وقتی که دستگاهی "
            "گم شده یا دسترسی مشکوکی دیده شده است (بخش ۱۵.۱)."
        ),
        request=ReasonSerializer,
        responses={200: OperationResultSerializer, **ERROR_RESPONSES},
    )
    @action(detail=True, methods=["post"], url_path="revoke-sessions")
    def revoke_sessions(self, request, pk=None):
        user = self.get_object()
        body = ReasonSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        user.revoke_tokens()
        record_audit(
            action=AuditAction.PERMISSION_CHANGE,
            entity_type="identity.UserAccount",
            entity_id=user.id,
            entity_label=user.username,
            reason=body.validated_data["reason"],
        )
        return Response(
            {"success": True, "message": "همه نشست‌های این کاربر باطل شدند."}
        )


@extend_schema_view(
    list=extend_schema(tags=["IAM"], summary="فهرست انتساب‌های نقش"),
    create=extend_schema(
        tags=["IAM"],
        summary="انتساب نقش به کاربر",
        description=(
            "`scopeType` و `scopeId` دامنه اعمال نقش را تعیین می‌کنند "
            "(بخش ۳.۲). ترکیب باید با `allowedScopeTypes` نقش سازگار باشد."
        ),
    ),
)
class UserRoleAssignmentViewSet(BaseModelViewSet):
    queryset = UserRoleAssignment.objects.select_related("user", "role")
    serializer_class = UserRoleAssignmentSerializer
    filterset_class = UserRoleAssignmentFilter
    permission_resource = "role"

    def perform_create(self, serializer):
        super().perform_create(serializer)
        record_audit(
            action=AuditAction.PERMISSION_CHANGE,
            entity_type="identity.UserRoleAssignment",
            entity_id=serializer.instance.id,
            entity_label=str(serializer.instance),
            changes={"granted": True},
        )

    @extend_schema(
        tags=["IAM"],
        summary="لغو انتساب نقش",
        request=ReasonSerializer,
        responses={200: UserRoleAssignmentSerializer},
    )
    @action(detail=True, methods=["post"], url_path="revoke")
    def revoke(self, request, pk=None):
        assignment = self.get_object()
        body = ReasonSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        assignment.status = RoleAssignmentStatus.REVOKED
        assignment.revoked_at = timezone.now()
        assignment.revoke_reason = body.validated_data["reason"]
        assignment.save()
        record_audit(
            action=AuditAction.PERMISSION_CHANGE,
            entity_type="identity.UserRoleAssignment",
            entity_id=assignment.id,
            entity_label=str(assignment),
            reason=assignment.revoke_reason,
            changes={"revoked": True},
        )
        return Response(self.get_serializer(assignment).data)


@extend_schema_view(
    list=extend_schema(tags=["IAM"], summary="دوره‌های بازبینی دسترسی"),
    create=extend_schema(tags=["IAM"], summary="ایجاد دوره بازبینی"),
)
class AccessReviewViewSet(BaseModelViewSet):
    queryset = AccessReview.objects.prefetch_related("items")
    serializer_class = AccessReviewSerializer
    filterset_fields = ("status",)
    permission_resource = "role"

    @extend_schema(
        tags=["IAM"],
        summary="تولید اقلام بازبینی برای همه انتساب‌های نقش حساس",
        request=None,
        responses={200: OperationResultSerializer},
    )
    @action(detail=True, methods=["post"], url_path="populate")
    @transaction.atomic
    def populate(self, request, pk=None):
        review = self.get_object()
        assignments = UserRoleAssignment.objects.filter(
            tenant_id=review.tenant_id, status=RoleAssignmentStatus.ACTIVE
        )
        created = 0
        for assignment in assignments:
            _, was_created = AccessReviewItem.objects.get_or_create(
                review=review,
                assignment=assignment,
                defaults={
                    "tenant_id": review.tenant_id,
                    "decision": AccessReviewDecision.PENDING,
                },
            )
            created += int(was_created)
        review.status = AccessReviewStatus.IN_PROGRESS
        review.save(update_fields=["status"])
        return Response({"success": True, "affected": created})

    @extend_schema(
        tags=["IAM"],
        summary="بستن دوره بازبینی",
        request=None,
        responses={200: AccessReviewSerializer},
    )
    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        review = self.get_object()
        pending = review.items.filter(decision=AccessReviewDecision.PENDING).count()
        if pending:
            raise BusinessRuleViolation(
                code="REVIEW_HAS_PENDING_ITEMS",
                message=f"{pending} قلم بازبینی هنوز تصمیم‌گیری نشده است.",
            )
        review.status = AccessReviewStatus.CLOSED
        review.closed_at = timezone.now()
        review.save(update_fields=["status", "closed_at"])
        return Response(self.get_serializer(review).data)


@extend_schema_view(list=extend_schema(tags=["IAM"], summary="اقلام بازبینی دسترسی"))
class AccessReviewItemViewSet(BaseModelViewSet):
    queryset = AccessReviewItem.objects.select_related("review", "assignment__role")
    serializer_class = AccessReviewItemSerializer
    filterset_fields = ("review", "decision")
    permission_resource = "role"

    def perform_update(self, serializer):
        serializer.save(
            reviewed_by_id=self.request.user.id, reviewed_at=timezone.now()
        )


@extend_schema_view(
    list=extend_schema(
        tags=["IAM"],
        summary="گزارش ممیزی",
        description=(
            "رکوردهای ممیزی فقط‌خواندنی و Append-only هستند (بخش ۷.۳). "
            "صفحه‌بندی این فهرست از نوع Cursor است."
        ),
    ),
    retrieve=extend_schema(tags=["IAM"], summary="جزئیات رکورد ممیزی"),
)
class AuditLogViewSet(BaseReadOnlyViewSet):
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    filterset_class = AuditLogFilter
    pagination_class = AuditCursorPagination
    search_fields = ("entity_label", "actor_username", "correlation_id")
    permission_resource = "audit"
