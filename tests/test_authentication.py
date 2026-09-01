"""
آزمون احراز هویت و چرخه نشست (بخش ۱۵.۱ سند تحلیل).
"""

from __future__ import annotations

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.permissions import ScopeType
from apps.identity.enums import UserStatus
from apps.identity.models import UserAccount
from tests import factories


class AuthTestCase(TestCase):
    """
    پایه آزمون‌های احراز هویت.

    `APIView.throttle_classes` هنگام import مقدار می‌گیرد، پس
    `override_settings` روی `REST_FRAMEWORK` محدودیت نرخ را خاموش نمی‌کند.
    راه درست، پاک‌کردن شمارنده‌های نرخ پیش از هر آزمون است: هدف این پرونده
    سنجش منطق احراز هویت است، و بدون این کار آزمون‌ها بودجه نرخ یکدیگر را
    مصرف می‌کنند و به‌شکل کاذب می‌شکنند.
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()


class LoginTests(AuthTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = factories.make_tenant()
        factories.sync_roles(cls.tenant)
        cls.school = factories.make_school(cls.tenant, "SCH01", "مدرسه")
        cls.user = factories.make_user(
            cls.tenant,
            "someone",
            role_code="ACCOUNTANT",
            scope_id=cls.school.id,
        )

    def login(self, username="someone", password=factories.PASSWORD):
        return self.client.post(
            "/api/v1/auth/token/",
            {"username": username, "password": password},
            format="json",
        )

    def test_successful_login_returns_token_pair(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_unknown_and_wrong_password_look_identical(self):
        """بخش ۱۵.۱: پاسخ نباید وجود یا نبود حساب را افشا کند."""
        wrong = self.login(password="TotallyWrong!9")
        missing = self.login(username="ghost", password="TotallyWrong!9")
        self.assertEqual(wrong.status_code, missing.status_code)
        self.assertEqual(wrong.data["code"], missing.data["code"])
        self.assertEqual(wrong.data["message"], missing.data["message"])

    @override_settings(AUTH_MAX_FAILED_LOGINS=3, AUTH_LOCKOUT_MINUTES=15)
    def test_account_locks_after_repeated_failures(self):
        for _ in range(3):
            self.assertEqual(self.login(password="Nope!123456").status_code, 401)

        # حتی با رمز درست، تا پایان مهلت قفل باز نمی‌شود.
        response = self.login()
        self.assertEqual(response.status_code, 423)
        self.assertEqual(response.data["code"], "ACCOUNT_LOCKED")
        self.assertTrue(response.data["retryable"])

    @override_settings(AUTH_MAX_FAILED_LOGINS=3, AUTH_LOCKOUT_MINUTES=15)
    def test_lock_expires_on_its_own(self):
        for _ in range(3):
            self.login(password="Nope!123456")

        user = UserAccount.objects.get(pk=self.user.pk)
        user.locked_until = timezone.now() - timedelta(minutes=1)
        user.save(update_fields=["locked_until"])

        response = self.login()
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.failed_login_count, 0)
        self.assertIsNone(user.locked_until)

    @override_settings(AUTH_MAX_FAILED_LOGINS=3)
    def test_successful_login_clears_the_counter(self):
        self.login(password="Nope!123456")
        self.login(password="Nope!123456")
        self.assertEqual(self.login().status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_count, 0)

    def test_disabled_account_cannot_log_in(self):
        self.user.status = UserStatus.DISABLED
        self.user.save(update_fields=["status"])
        response = self.login()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "ACCOUNT_NOT_ACTIVE")


class SessionRevocationTests(AuthTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = factories.make_tenant()
        factories.sync_roles(cls.tenant)
        cls.school = factories.make_school(cls.tenant, "SCH01", "مدرسه")
        cls.user = factories.make_user(
            cls.tenant, "someone", role_code="ACCOUNTANT", scope_id=cls.school.id
        )

    def setUp(self):
        super().setUp()
        response = self.client.post(
            "/api/v1/auth/token/",
            {"username": "someone", "password": factories.PASSWORD},
            format="json",
        )
        self.access = response.data["access"]
        self.refresh = response.data["refresh"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")

    def test_token_works_before_revocation(self):
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)

    def test_logout_invalidates_the_access_token_immediately(self):
        """
        JWT ذاتاً بی‌حالت است؛ بدون کنترل نسخه، توکن تا نیم‌ساعت بعد از خروج
        هنوز کار می‌کرد.
        """
        self.assertEqual(self.client.post("/api/v1/auth/logout/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)

    def test_logout_invalidates_the_refresh_token_too(self):
        self.client.post("/api/v1/auth/logout/")
        response = APIClient().post(
            "/api/v1/auth/token/refresh/", {"refresh": self.refresh}, format="json"
        )
        self.assertEqual(response.status_code, 401)

    def test_refresh_works_while_the_session_is_valid(self):
        response = APIClient().post(
            "/api/v1/auth/token/refresh/", {"refresh": self.refresh}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_password_change_revokes_existing_sessions(self):
        response = self.client.post(
            "/api/v1/auth/password/change/",
            {
                "current_password": factories.PASSWORD,
                "new_password": "AnotherPass!2027",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)

    def test_revoke_all_sessions_endpoint(self):
        self.assertEqual(
            self.client.post("/api/v1/auth/sessions/revoke/").status_code, 200
        )
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)

    def test_disabling_an_account_kills_its_live_token(self):
        self.user.status = UserStatus.DISABLED
        self.user.save(update_fields=["status"])
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)


class PasswordResetTests(AuthTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = factories.make_tenant()
        factories.sync_roles(cls.tenant)
        cls.school = factories.make_school(cls.tenant, "SCH01", "مدرسه")
        cls.person = factories.make_person(cls.tenant, "کاربر", "نمونه", "4000000001")
        cls.user = factories.make_user(
            cls.tenant,
            "someone",
            role_code="ACCOUNTANT",
            scope_id=cls.school.id,
            person=cls.person,
        )

    def request_reset(self, identifier):
        return self.client.post(
            "/api/v1/auth/password/reset/", {"identifier": identifier}, format="json"
        )

    def test_response_is_identical_for_known_and_unknown_accounts(self):
        known = self.request_reset("someone")
        unknown = self.request_reset("nobody-at-all")
        self.assertEqual(known.status_code, 200)
        self.assertEqual(known.data, unknown.data)

    def test_reset_queues_a_notification_only_for_a_real_account(self):
        from apps.workflow.models import Notification

        self.request_reset("nobody-at-all")
        self.assertEqual(Notification.objects.count(), 0)

        self.request_reset("someone")
        self.assertEqual(Notification.objects.count(), 1)
        self.assertIn("reset-password", Notification.objects.get().body)

    def test_confirm_sets_the_new_password_and_revokes_sessions(self):
        from apps.identity import password_reset

        uid, token = password_reset.build_token(self.user)
        response = self.client.post(
            "/api/v1/auth/password/reset/confirm/",
            {"uid": uid, "token": token, "new_password": "BrandNew!2027"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            self.client.post(
                "/api/v1/auth/token/",
                {"username": "someone", "password": "BrandNew!2027"},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/token/",
                {"username": "someone", "password": factories.PASSWORD},
                format="json",
            ).status_code,
            401,
        )

    def test_reset_token_is_single_use(self):
        from apps.identity import password_reset

        uid, token = password_reset.build_token(self.user)
        body = {"uid": uid, "token": token, "new_password": "BrandNew!2027"}
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/password/reset/confirm/", body, format="json"
            ).status_code,
            200,
        )
        second = self.client.post(
            "/api/v1/auth/password/reset/confirm/", body, format="json"
        )
        self.assertEqual(second.status_code, 400)
        self.assertEqual(second.data["code"], "INVALID_RESET_TOKEN")

    def test_tampered_token_is_rejected_the_same_way(self):
        from apps.identity import password_reset

        uid, _token = password_reset.build_token(self.user)
        response = self.client.post(
            "/api/v1/auth/password/reset/confirm/",
            {"uid": uid, "token": "aaaaaa-bbbbbbbbbbbb", "new_password": "BrandNew!2027"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "INVALID_RESET_TOKEN")

    def test_weak_password_is_rejected(self):
        from apps.identity import password_reset

        uid, token = password_reset.build_token(self.user)
        response = self.client.post(
            "/api/v1/auth/password/reset/confirm/",
            {"uid": uid, "token": token, "new_password": "1234567890"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "WEAK_PASSWORD")

    def test_reset_unlocks_a_locked_account(self):
        from apps.identity import password_reset

        self.user.locked_until = timezone.now() + timedelta(minutes=15)
        self.user.failed_login_count = 9
        self.user.save(update_fields=["locked_until", "failed_login_count"])

        uid, token = password_reset.build_token(self.user)
        self.client.post(
            "/api/v1/auth/password/reset/confirm/",
            {"uid": uid, "token": token, "new_password": "BrandNew!2027"},
            format="json",
        )
        self.user.refresh_from_db()
        self.assertIsNone(self.user.locked_until)
        self.assertEqual(self.user.failed_login_count, 0)


class AdminAccountActionsTests(AuthTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = factories.make_tenant()
        factories.sync_roles(cls.tenant)
        cls.school = factories.make_school(cls.tenant, "SCH01", "مدرسه")
        cls.admin = factories.make_user(
            cls.tenant, "sysadmin", role_code="SYS_ADMIN", scope_type=ScopeType.TENANT
        )
        cls.target = factories.make_user(cls.tenant, "target")

    def setUp(self):
        from apps.identity.serializers import ContextTokenObtainPairSerializer

        super().setUp()
        token = ContextTokenObtainPairSerializer.get_token(self.admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_unlock_clears_the_lock_without_touching_status(self):
        self.target.locked_until = timezone.now() + timedelta(minutes=30)
        self.target.failed_login_count = 5
        self.target.status = UserStatus.DISABLED
        self.target.save(
            update_fields=["locked_until", "failed_login_count", "status"]
        )

        response = self.client.post(
            f"/api/v1/iam/users/{self.target.id}/unlock/",
            {"reason": "تماس کاربر با پشتیبانی"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.target.refresh_from_db()
        self.assertIsNone(self.target.locked_until)
        self.assertEqual(self.target.failed_login_count, 0)
        # غیرفعال‌سازی عمدی مدیر نباید با «باز کردن قفل» خنثی شود.
        self.assertEqual(self.target.status, UserStatus.DISABLED)

    def test_revoke_sessions_bumps_the_token_version(self):
        before = self.target.token_version
        response = self.client.post(
            f"/api/v1/iam/users/{self.target.id}/revoke-sessions/",
            {"reason": "گم‌شدن دستگاه"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual(self.target.token_version, before + 1)
