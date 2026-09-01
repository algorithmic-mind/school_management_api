"""
بازیابی رمز عبور با توکن یک‌بارمصرف.

بخش ۱۵.۱ سند تحلیل: «رمز عبور با الگوریتم تطبیقی امن، سیاست قفل هوشمند و
جلوگیری از افشای وجود حساب.»

طراحی:

- توکن با :class:`~django.contrib.auth.tokens.PasswordResetTokenGenerator`
  ساخته می‌شود: امضاشده با `SECRET_KEY`، بدون ذخیره در پایگاه داده، و
  خودبه‌خود با تغییر رمز یا زمان آخرین ورود باطل می‌شود.
- عمر توکن از `PASSWORD_RESET_TIMEOUT` می‌آید (پیش‌فرض ۲ ساعت).
- شناسه کاربر به‌صورت Base64 در `uid` می‌آید تا لینک، UUID خام را در URL نگذارد.
- پاسخ درخواست بازیابی همیشه یکسان است؛ وجود یا نبود حساب افشا نمی‌شود.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.identity.enums import UserStatus
from apps.identity.models import UserAccount

#: وضعیت‌هایی که بازیابی رمز برایشان معنا ندارد.
NON_RESETTABLE = {UserStatus.SUSPENDED, UserStatus.DISABLED}

token_generator = PasswordResetTokenGenerator()


def find_account(identifier: str) -> UserAccount | None:
    """
    حساب را با نام کاربری، ایمیل یا موبایل پیدا می‌کند.

    نتیجه `None` هرگز به کاربر گزارش نمی‌شود؛ فقط تعیین می‌کند که پیامی ارسال
    شود یا نه.
    """
    identifier = (identifier or "").strip()
    if not identifier:
        return None

    account = UserAccount.objects.filter(username__iexact=identifier).first()
    if account is None and "@" in identifier:
        account = UserAccount.objects.filter(email__iexact=identifier).first()
    if account is None:
        account = UserAccount.objects.filter(mobile=identifier).first()

    if account is None or account.status in NON_RESETTABLE:
        return None
    return account


def build_token(account: UserAccount) -> tuple[str, str]:
    """جفت (uid، token) برای لینک بازیابی."""
    return urlsafe_base64_encode(force_bytes(account.pk)), token_generator.make_token(
        account
    )


def build_reset_link(uid: str, token: str) -> str:
    """
    لینک کاملی که در پیام برای کاربر می‌رود.

    اگر `FRONTEND_BASE_URL` تنظیم نشده باشد، فقط مسیر نسبی برمی‌گردد — بهتر از
    ساختن لینکی است که به میزبان اشتباه اشاره کند.
    """
    path = f"/reset-password?uid={uid}&token={token}"
    base = getattr(settings, "FRONTEND_BASE_URL", "")
    return f"{base}{path}" if base else path


def resolve_token(uid: str, token: str) -> UserAccount | None:
    """
    کاربر را از جفت (uid، token) بازمی‌گرداند و توکن را اعتبارسنجی می‌کند.

    هر شکست — uid خراب، کاربر ناموجود، توکن منقضی یا مصرف‌شده — به `None`
    تبدیل می‌شود تا پاسخ خطا بین حالت‌ها تفاوتی نگذارد.
    """
    try:
        pk = force_str(urlsafe_base64_decode(uid))
        account = UserAccount.objects.get(pk=pk)
    except (TypeError, ValueError, OverflowError, UserAccount.DoesNotExist):
        return None

    if account.status in NON_RESETTABLE:
        return None
    if not token_generator.check_token(account, token):
        return None
    return account
