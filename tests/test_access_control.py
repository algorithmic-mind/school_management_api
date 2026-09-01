"""
آزمون محدوده دسترسی (بخش ۳.۲ و ۱۵.۱ سند تحلیل).

این آزمون‌ها روی رفتاری تمرکز دارند که با «۲۰۰ گرفتن» قابل تشخیص نیست:
اینکه پاسخ **چه چیزهایی را نشان نمی‌دهد**. هر مورد یک راه فرار مشخص را
می‌بندد.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.permissions import ScopeType
from apps.identity.scopes import build_effective_scope
from tests import factories


def authenticate(user) -> APIClient:
    """کلاینت با توکن همان کاربر؛ بدون عبور از محدودیت نرخ ورود."""
    from apps.identity.serializers import ContextTokenObtainPairSerializer

    client = APIClient()
    token = ContextTokenObtainPairSerializer.get_token(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


class EffectiveScopeTests(TestCase):
    """منطق ترکیب انتساب‌های نقش، مستقل از HTTP."""

    def test_tenant_scope_is_unrestricted(self):
        scope = build_effective_scope([{"scope_type": ScopeType.TENANT, "scope_id": None}])
        self.assertTrue(scope.is_unrestricted)

    def test_assignment_without_scope_id_means_whole_tenant(self):
        scope = build_effective_scope(
            [{"scope_type": ScopeType.SCHOOL, "scope_id": None}]
        )
        self.assertTrue(scope.is_unrestricted)

    def test_no_active_role_sees_nothing(self):
        scope = build_effective_scope([])
        self.assertFalse(scope.is_unrestricted)
        self.assertEqual(scope.clauses, [])

    def test_self_scope_alone_is_self_only(self):
        scope = build_effective_scope([{"scope_type": ScopeType.SELF, "scope_id": None}])
        self.assertTrue(scope.self_only)

    def test_self_plus_organizational_role_is_not_self_only(self):
        """نقش سازمانی نباید با داشتن یک انتساب SELF محدود شود."""
        tenant = factories.make_tenant()
        school = factories.make_school(tenant, "S1", "مدرسه")
        scope = build_effective_scope(
            [
                {"scope_type": ScopeType.SELF, "scope_id": None},
                {"scope_type": ScopeType.SCHOOL, "scope_id": school.id},
            ]
        )
        self.assertFalse(scope.self_only)
        self.assertEqual(scope.dimension("schools"), {school.id})

    def test_campus_scope_implies_its_school(self):
        """منبعی که شعبه ندارد باید با مدرسهٔ ضمنی همان شعبه محدود شود."""
        tenant = factories.make_tenant()
        school = factories.make_school(tenant, "S1", "مدرسه")
        campus = factories.make_campus(tenant, school)
        scope = build_effective_scope(
            [{"scope_type": ScopeType.CAMPUS, "scope_id": campus.id}]
        )
        self.assertEqual(scope.dimension("campuses"), {campus.id})
        self.assertEqual(scope.dimension("schools"), {school.id})


class QuerysetScopeTests(TestCase):
    """محدوده روی داده واقعی، از مسیر HTTP."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = factories.make_tenant()
        factories.sync_roles(cls.tenant)

        cls.school_a = factories.make_school(cls.tenant, "SCH01", "مدرسه الف")
        cls.school_b = factories.make_school(cls.tenant, "SCH02", "مدرسه ب")
        cls.campus_a = factories.make_campus(cls.tenant, cls.school_a, "CMP-A")
        cls.campus_b = factories.make_campus(cls.tenant, cls.school_b, "CMP-B")
        cls.year_a = factories.make_academic_year(cls.tenant, cls.school_a)
        cls.year_b = factories.make_academic_year(cls.tenant, cls.school_b)
        cls.grade_a = factories.make_grade_level(cls.tenant, cls.school_a)
        cls.grade_b = factories.make_grade_level(cls.tenant, cls.school_b)

        factories.make_chart_of_accounts(cls.tenant, cls.school_a)
        factories.make_chart_of_accounts(cls.tenant, cls.school_b, prefix="9")

        cls.students_a = [
            factories.make_student(
                cls.tenant, cls.campus_a, cls.year_a, cls.grade_a, index=index
            )
            for index in range(1, 4)
        ]
        cls.students_b = [
            factories.make_student(
                cls.tenant, cls.campus_b, cls.year_b, cls.grade_b, index=index
            )
            for index in range(10, 12)
        ]

        cls.accountant_a = factories.make_user(
            cls.tenant,
            "acc.a",
            role_code="ACCOUNTANT",
            scope_type=ScopeType.SCHOOL,
            scope_id=cls.school_a.id,
        )
        cls.admin = factories.make_user(cls.tenant, "root", superuser=True)

        student = cls.students_a[0]
        cls.student_user = factories.make_user(
            cls.tenant,
            "std1",
            role_code="STUDENT",
            scope_type=ScopeType.SELF,
            person=student.person,
        )
        guardian_person = factories.make_person(cls.tenant, "ولی", "نمونه", "5000000001")
        factories.link_guardian(cls.tenant, student, guardian_person)
        cls.guardian_user = factories.make_user(
            cls.tenant,
            "grd1",
            role_code="GUARDIAN",
            scope_type=ScopeType.SELF,
            person=guardian_person,
        )

    # -- جداسازی بین مدارس ------------------------------------------------
    def test_school_scoped_user_sees_only_own_school(self):
        response = authenticate(self.accountant_a).get(
            "/api/v1/finance/accounts/", {"page_size": 50}
        )
        self.assertEqual(response.status_code, 200)
        codes = {row["code"] for row in response.data["results"]}
        self.assertTrue(all(not code.startswith("9") for code in codes))
        self.assertEqual(len(codes), 7)

    def test_superuser_sees_every_school(self):
        response = authenticate(self.admin).get(
            "/api/v1/finance/accounts/", {"page_size": 50}
        )
        self.assertEqual(response.data["count"], 14)

    def test_context_header_cannot_widen_scope(self):
        """
        هدر Context فقط باریک‌تر می‌کند.

        فرستادن شناسه مدرسه‌ای که کاربر به آن دسترسی ندارد باید بی‌اثر باشد —
        نه اینکه پنجره‌ای به آن مدرسه باز کند.
        """
        client = authenticate(self.accountant_a)
        response = client.get(
            "/api/v1/finance/accounts/",
            {"page_size": 50},
            HTTP_X_SCHOOL_ID=str(self.school_b.id),
        )
        self.assertEqual(response.status_code, 200)
        codes = {row["code"] for row in response.data["results"]}
        self.assertEqual(len(codes), 7)
        self.assertTrue(all(not code.startswith("9") for code in codes))

    def test_query_parameter_cannot_bypass_scope(self):
        """فیلتر Query روی محدوده اعمال می‌شود، نه به‌جای آن."""
        response = authenticate(self.accountant_a).get(
            "/api/v1/finance/accounts/",
            {"school": str(self.school_b.id), "page_size": 50},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)

    def test_reports_respect_school_scope(self):
        """گزارش‌ها از ScopedQuerysetMixin رد نمی‌شوند و باید خودشان محدود کنند."""
        response = authenticate(self.accountant_a).get("/api/v1/finance/general-ledger/")
        self.assertEqual(response.status_code, 200)
        codes = {row["accountCode"] for row in response.data["accounts"]}
        self.assertTrue(all(not code.startswith("9") for code in codes))

    # -- قاعده SELF -------------------------------------------------------
    def test_student_lists_only_own_record(self):
        response = authenticate(self.student_user).get("/api/v1/students/students/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["id"], str(self.students_a[0].id)
        )

    def test_student_cannot_read_another_student_by_id(self):
        """
        جلوگیری از IDOR.

        نقش «دانش‌آموز» خودش مجوز `student.read` دارد، پس مجوز به‌تنهایی نباید
        مبنای تصمیم باشد؛ وگرنه هر دانش‌آموز با داشتن شناسه، پرونده دیگری را
        می‌خواند.
        """
        other = self.students_a[1]
        response = authenticate(self.student_user).get(
            f"/api/v1/students/students/{other.id}/"
        )
        self.assertEqual(response.status_code, 404)

    def test_student_can_read_own_record_by_id(self):
        own = self.students_a[0]
        response = authenticate(self.student_user).get(
            f"/api/v1/students/students/{own.id}/"
        )
        self.assertEqual(response.status_code, 200)

    def test_guardian_sees_only_own_child(self):
        response = authenticate(self.guardian_user).get("/api/v1/students/students/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["id"], str(self.students_a[0].id)
        )

    def test_self_scoped_user_gets_no_aggregate_dashboard(self):
        """داشبورد سازمانی برای دانش‌آموز، افشای تجمیعی است."""
        response = authenticate(self.student_user).get("/api/v1/reports/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["selfServiceOnly"])
        self.assertEqual(response.data["widgetCount"], 0)

    # -- داشبورد و محیط کاری ---------------------------------------------
    def test_dashboard_omits_widgets_without_permission(self):
        """ویجت بدون مجوز نباید با مقدار صفر برگردد؛ باید اصلاً نباشد."""
        response = authenticate(self.accountant_a).get("/api/v1/reports/dashboard/")
        keys = {widget["key"] for widget in response.data["widgets"]}
        self.assertIn("tuitionCollection", keys)
        self.assertNotIn("attendanceToday", keys)

    def test_dashboard_counts_respect_scope(self):
        response = authenticate(self.accountant_a).get(
            "/api/v1/reports/dashboard/", {"widgets": "activeStudents"}
        )
        widget = response.data["widgets"][0]
        self.assertEqual(widget["key"], "activeStudents")
        self.assertEqual(widget["value"], len(self.students_a))

    def test_working_contexts_list_only_accessible_schools(self):
        response = authenticate(self.accountant_a).get("/api/v1/auth/contexts/")
        self.assertEqual(response.status_code, 200)
        codes = {school["code"] for school in response.data["schools"]}
        self.assertEqual(codes, {"SCH01"})
        self.assertEqual(response.data["defaultContext"]["scopeTitle"], "مدرسه الف")
