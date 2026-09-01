"""
احراز هویت JWT با امکان ابطال سمت سرور.

بخش ۱۵.۱ سند تحلیل: «Sessionها قابل مشاهده و ابطال؛ تغییر رمز یا نقش حساس،
Sessionهای پرریسک را باطل می‌کند.»

JWT ذاتاً بی‌حالت است: توکن صادرشده تا لحظه انقضا معتبر می‌ماند و صرفِ
تغییر رمز، آن را از کار نمی‌اندازد. راه‌حل اینجا یک Claim نسخه است:

- هر توکن، `token_version` کاربر را در لحظه صدور با خود حمل می‌کند.
- هر درخواست، این عدد را با مقدار فعلی رکورد کاربر مقایسه می‌کند.
- `UserAccount.revoke_tokens()` عدد را جلو می‌برد، پس همه توکن‌های پیشین
  در نخستین درخواست بعدی رد می‌شوند.

هزینه‌اش یک مقایسه عدد روی همان Query کاربر است که SimpleJWT به‌هرحال انجام
می‌دهد؛ نه Query اضافه دارد و نه به فهرست سیاه نیاز.

توکن‌های صادرشده پیش از افزودن این Claim، `token_version` ندارند. آن‌ها
معتبر شمرده می‌شوند تا ارتقای نسخه، کاربران واردشده را یک‌باره بیرون نیندازد؛
نخستین `revoke_tokens` یا ورود مجدد، همه را به مسیر نسخه‌دار می‌آورد.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from drf_spectacular.authentication import SessionScheme
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

from apps.identity.enums import UserStatus

#: نام Claim نسخه توکن. در `ContextTokenObtainPairSerializer` نوشته می‌شود.
TOKEN_VERSION_CLAIM = "token_version"

#: وضعیت‌هایی که حساب با آن‌ها اجازه استفاده از توکن ندارد.
BLOCKED_STATUSES = {UserStatus.LOCKED, UserStatus.SUSPENDED, UserStatus.DISABLED}


class ContextHydrationMixin:
    """
    پس از احراز هویت موفق، Context درخواست را کامل می‌کند.

    اگر این کار فقط در `ScopedRBACPermission` انجام شود، هر Viewی که
    `permission_classes` خودش را اعلام کند (مثلاً `[IsAuthenticated]`) با
    Contextِ خالی اجرا می‌شود: بدون `tenant_id` و بدون محدوده مؤثر. نتیجه‌اش
    یا نتیجه تهی است یا — بدتر — نبودِ فیلتر سازمان. لایه احراز هویت تنها
    جایی است که همه مسیرها از آن رد می‌شوند.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            from apps.core.permissions import hydrate_context_from_user

            user, _token = result
            # `request` اینجا Requestِ DRF است و هنوز `request.user` ندارد.
            request.user = user
            hydrate_context_from_user(request)
        return result


class VersionedJWTAuthentication(ContextHydrationMixin, JWTAuthentication):
    """JWTAuthentication استاندارد، به‌علاوه کنترل نسخه توکن و وضعیت حساب."""

    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        if user.status in BLOCKED_STATUSES:
            raise AuthenticationFailed(
                _("این حساب کاربری فعال نیست."), code="account_not_active"
            )

        if getattr(user, "is_locked_out", False):
            raise AuthenticationFailed(
                _("این حساب کاربری موقتاً قفل شده است."), code="account_locked"
            )

        claimed = validated_token.get(TOKEN_VERSION_CLAIM)
        if claimed is not None and int(claimed) != int(user.token_version or 1):
            raise AuthenticationFailed(
                _("این نشست باطل شده است؛ دوباره وارد شوید."),
                code="token_revoked",
            )

        return user


class ContextSessionAuthentication(ContextHydrationMixin, SessionAuthentication):
    """
    احراز هویت مبتنی بر Session (پنل مدیریت و Browsable API) با همان Context.

    بدون این، ورود با کوکی به همان مشکل Contextِ خالی می‌خورد که ورود با توکن.
    """


class ContextSessionScheme(SessionScheme):
    """
    معرفی نسخه سفارشی SessionAuthentication به drf-spectacular.

    رفتار قرارداد با نسخه استاندارد فرقی ندارد؛ فقط باید نام کلاس تازه را
    بشناسد وگرنه برای هر View یک هشدار می‌دهد و Security Scheme کوکی از
    قرارداد می‌افتد.
    """

    target_class = "apps.identity.authentication.ContextSessionAuthentication"


class VersionedJWTScheme(OpenApiAuthenticationExtension):
    """
    معرفی این کلاس احراز هویت به drf-spectacular.

    بدون آن، قرارداد OpenAPI هیچ Security Schemeای اعلام نمی‌کند و دکمه
    Authorize در Swagger کار نمی‌کند — چون drf-spectacular فقط کلاس‌های
    شناخته‌شده را می‌شناسد و برای هر Viewی یک هشدار می‌دهد.
    """

    target_class = "apps.identity.authentication.VersionedJWTAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "توکن دریافتی از `/api/v1/auth/token/` را به‌صورت "
                "`Authorization: Bearer <access>` بفرستید."
            ),
        }
