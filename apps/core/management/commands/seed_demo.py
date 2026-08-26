"""
ساخت داده نمونه برای توسعه فرانت‌اند.

این دستور یک سازمان، مدرسه، شعبه، سال تحصیلی، پایه‌ها، دروس، کلاس، معلم،
دانش‌آموزان، تعرفه شهریه و کاربران نمونه می‌سازد تا توسعه‌دهنده فرانت بتواند
بلافاصله با داده واقعی کار کند.

هشدار (بخش ۱۵.۲): این داده مصنوعی است و نباید در محیط عملیاتی اجرا شود.
"""

from __future__ import annotations

import random
from datetime import date, time, timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.enums import ContactType, Gender
from apps.core.models import Tenant
from apps.core.permissions import ScopeType
from apps.finance.enums import AccountType, FeeType
from apps.finance.models import Account, FeePlan, FeePlanItem, FiscalYear
from apps.hr.enums import ContractStatus, ContractType, EmployeeStatus, PositionType
from apps.hr.models import (
    Employee,
    EmployeeAssignment,
    EmploymentContract,
    OrgUnit,
    Position,
    TeacherProfile,
    TeacherQualification,
    TeachingAssignment,
)
from apps.identity.models import ContactPoint, Person, Role, UserAccount, UserRoleAssignment
from apps.organization.enums import AcademicYearStatus, ClassGroupStatus, SchoolType
from apps.organization.models import (
    AcademicYear,
    Campus,
    ClassGroup,
    Course,
    CourseOffering,
    GradeLevel,
    ProgramCourse,
    Room,
    ScheduleEntry,
    School,
    StudyProgram,
    Term,
)
from apps.students.enums import EnrollmentStatus, RelationshipType, StudentStatus
from apps.students.models import (
    ClassMembership,
    Enrollment,
    Guardian,
    Student,
    StudentGuardian,
)

FIRST_NAMES_M = ["امیرعلی", "محمد", "آرش", "سینا", "پارسا", "رضا", "کیان", "بردیا"]
FIRST_NAMES_F = ["زهرا", "نیلوفر", "ستایش", "مریم", "آیدا", "هستی", "الناز", "پریسا"]
LAST_NAMES = [
    "محمدی", "احمدی", "رضایی", "حسینی", "کریمی", "موسوی",
    "جعفری", "نوری", "صادقی", "قاسمی",
]

DEMO_PASSWORD = "Demo!Pass2026"


class Command(BaseCommand):
    help = "ساخت داده نمونه برای محیط توسعه (در محیط عملیاتی اجرا نکنید)."

    def add_arguments(self, parser):
        parser.add_argument("--students", type=int, default=24, help="تعداد دانش‌آموز")
        parser.add_argument(
            "--reset", action="store_true", help="حذف سازمان نمونه قبلی و ساخت مجدد"
        )

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(1404)

        # تاریخ‌ها نسبت به «امروز» ساخته می‌شوند تا داده نمونه همیشه جاری بماند:
        # سال تحصیلی از ۶۰ روز پیش شروع شده و تا ۲۴۰ روز آینده ادامه دارد.
        today = timezone.localdate()
        self.year_start = today - timedelta(days=60)
        self.year_end = today + timedelta(days=240)
        self.term1_end = today + timedelta(days=60)
        self.term2_start = today + timedelta(days=61)

        if options["reset"]:
            Tenant.objects.filter(code="demo-school").delete()
            self.stdout.write(self.style.WARNING("سازمان نمونه قبلی حذف شد."))

        tenant, _ = Tenant.objects.get_or_create(
            code="demo-school",
            defaults={"name": "مجتمع آموزشی نمونه", "default_currency": "IRR"},
        )
        self.tenant = tenant

        # نقش‌های سیستمی باید پیش از ساخت کاربران وجود داشته باشند.
        call_command("sync_permissions", tenant_code=tenant.code, verbosity=0)

        school = self._create_school(tenant)
        campus = self._create_campus(tenant, school)
        year, terms = self._create_academic_year(tenant, school)
        grades = self._create_grade_levels(tenant, school)
        program = self._create_program(tenant, school)
        courses = self._create_courses(tenant, school)
        self._map_program_courses(tenant, program, grades, courses)
        rooms = self._create_rooms(tenant, campus)
        class_group = self._create_class_group(
            tenant, campus, year, grades[0], program, rooms[0]
        )
        offerings = self._create_offerings(tenant, class_group, terms[0], courses)
        teacher = self._create_teacher(tenant, campus, courses)
        self._assign_teaching(tenant, offerings, teacher)
        self._create_schedule(tenant, offerings, rooms, teacher)
        self._create_finance(tenant, school, year, grades[0])
        students = self._create_students(
            tenant, campus, year, grades[0], program, class_group, options["students"]
        )
        self._create_users(tenant, teacher, students)

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 62))
        self.stdout.write(self.style.SUCCESS("داده نمونه با موفقیت ساخته شد."))
        self.stdout.write(self.style.SUCCESS("=" * 62))
        self.stdout.write(f"سازمان        : {tenant.name} ({tenant.code})")
        self.stdout.write(f"مدرسه         : {school.name} — شناسه {school.id}")
        self.stdout.write(f"شعبه          : {campus.name} — شناسه {campus.id}")
        self.stdout.write(f"سال تحصیلی    : {year.title} — شناسه {year.id}")
        self.stdout.write(f"کلاس نمونه    : {class_group.code} — شناسه {class_group.id}")
        self.stdout.write(f"تعداد دانش‌آموز: {len(students)}")
        self.stdout.write("\nکاربران نمونه (رمز عبور همه: " + DEMO_PASSWORD + ")")
        self.stdout.write("  admin        — مدیر سامانه (superuser)")
        self.stdout.write("  principal    — مدیر مدرسه")
        self.stdout.write("  vp.academic  — معاون آموزشی")
        self.stdout.write("  registrar    — مسئول ثبت‌نام")
        self.stdout.write("  teacher1     — معلم")
        self.stdout.write("  accountant   — حسابدار")
        self.stdout.write("  guardian1    — ولی")
        self.stdout.write("  student1     — دانش‌آموز")
        self.stdout.write(
            "\nهدرهای Context برای فرانت:\n"
            f"  X-School-Id: {school.id}\n"
            f"  X-Campus-Id: {campus.id}\n"
            f"  X-Academic-Year-Id: {year.id}\n"
        )

    # ------------------------------------------------------------------
    def _create_school(self, tenant) -> School:
        school, _ = School.objects.get_or_create(
            tenant=tenant,
            code="SCH01",
            defaults={
                "name": "دبیرستان نمونه دانش",
                "school_type": SchoolType.LOWER_SECONDARY,
                "currency": "IRR",
            },
        )
        return school

    def _create_campus(self, tenant, school) -> Campus:
        campus, _ = Campus.objects.get_or_create(
            school=school,
            code="C01",
            defaults={
                "tenant": tenant,
                "name": "شعبه مرکزی",
                "address_line": "تهران، خیابان نمونه، پلاک ۱",
                "phone": "02100000000",
            },
        )
        return campus

    def _create_academic_year(self, tenant, school):
        year, _ = AcademicYear.objects.get_or_create(
            school=school,
            title="۱۴۰۵–۱۴۰۶",
            defaults={
                "tenant": tenant,
                "starts_on": self.year_start,
                "ends_on": self.year_end,
                "status": AcademicYearStatus.ACTIVE,
                "is_default": True,
            },
        )
        terms = []
        for index, (title, start, end) in enumerate(
            [
                ("نوبت اول", self.year_start, self.term1_end),
                ("نوبت دوم", self.term2_start, self.year_end),
            ],
            start=1,
        ):
            term, _ = Term.objects.get_or_create(
                academic_year=year,
                sequence_no=index,
                defaults={
                    "tenant": tenant,
                    "title": title,
                    "starts_on": start,
                    "ends_on": end,
                    "status": "ACTIVE" if index == 1 else "PLANNED",
                },
            )
            terms.append(term)
        return year, terms

    def _create_grade_levels(self, tenant, school) -> list[GradeLevel]:
        grades = []
        for index, title in enumerate(["پایه هفتم", "پایه هشتم", "پایه نهم"], start=7):
            grade, _ = GradeLevel.objects.get_or_create(
                school=school,
                code=f"G{index}",
                defaults={
                    "tenant": tenant,
                    "title": title,
                    "sequence_no": index,
                    "stage": "متوسطه اول",
                },
            )
            grades.append(grade)
        return grades

    def _create_program(self, tenant, school) -> StudyProgram:
        program, _ = StudyProgram.objects.get_or_create(
            school=school,
            code="GEN",
            defaults={"tenant": tenant, "title": "دوره عمومی متوسطه اول"},
        )
        return program

    def _create_courses(self, tenant, school) -> list[Course]:
        catalog = [
            ("MATH", "ریاضی", 4),
            ("SCI", "علوم تجربی", 3),
            ("LIT", "ادبیات فارسی", 4),
            ("ARB", "عربی", 2),
            ("ENG", "زبان انگلیسی", 3),
            ("SOC", "مطالعات اجتماعی", 2),
        ]
        courses = []
        for code, title, credit in catalog:
            course, _ = Course.objects.get_or_create(
                school=school,
                code=code,
                defaults={
                    "tenant": tenant,
                    "title": title,
                    "credit": credit,
                    "max_score": 20,
                },
            )
            courses.append(course)
        return courses

    def _map_program_courses(self, tenant, program, grades, courses):
        for course in courses:
            ProgramCourse.objects.get_or_create(
                program=program,
                grade_level=grades[0],
                course=course,
                defaults={
                    "tenant": tenant,
                    "weekly_minutes": int(course.credit) * 45,
                    "is_required": True,
                },
            )

    def _create_rooms(self, tenant, campus) -> list[Room]:
        rooms = []
        for index in range(1, 5):
            room, _ = Room.objects.get_or_create(
                campus=campus,
                code=f"R10{index}",
                defaults={
                    "tenant": tenant,
                    "title": f"کلاس {index}",
                    "capacity": 30,
                    "building": "ساختمان اصلی",
                    "floor": "۱",
                },
            )
            rooms.append(room)
        return rooms

    def _create_class_group(self, tenant, campus, year, grade, program, room):
        class_group, _ = ClassGroup.objects.get_or_create(
            campus=campus,
            academic_year=year,
            code="701",
            defaults={
                "tenant": tenant,
                "grade_level": grade,
                "program": program,
                "home_room": room,
                "title": "هفتم / ۱",
                "capacity": 28,
                "status": ClassGroupStatus.ACTIVE,
            },
        )
        return class_group

    def _create_offerings(self, tenant, class_group, term, courses):
        offerings = []
        for course in courses:
            offering, _ = CourseOffering.objects.get_or_create(
                class_group=class_group,
                term=term,
                course=course,
                defaults={
                    "tenant": tenant,
                    "weekly_minutes": int(course.credit) * 45,
                    "status": "ACTIVE",
                },
            )
            offerings.append(offering)
        return offerings

    def _create_teacher(self, tenant, campus, courses) -> TeacherProfile:
        person, _ = Person.objects.get_or_create(
            tenant=tenant,
            national_id="0012345678",
            defaults={
                "first_name": "سارا",
                "last_name": "کریمی",
                "gender": Gender.FEMALE,
                "birth_date": date(1988, 4, 12),
            },
        )
        ContactPoint.objects.get_or_create(
            person=person,
            contact_type=ContactType.MOBILE,
            value="09120000001",
            defaults={"tenant": tenant, "is_primary": True},
        )

        employee, _ = Employee.objects.get_or_create(
            person=person,
            defaults={
                "tenant": tenant,
                "employee_no": "E1001",
                "hired_on": date(2020, 9, 1),
                "status": EmployeeStatus.ACTIVE,
            },
        )
        EmploymentContract.objects.get_or_create(
            employee=employee,
            contract_no="CT-1001",
            defaults={
                "tenant": tenant,
                "contract_type": ContractType.PERMANENT,
                "starts_on": date(2020, 9, 1),
                "base_salary_amount": 180_000_000,
                "status": ContractStatus.ACTIVE,
            },
        )

        org_unit, _ = OrgUnit.objects.get_or_create(
            campus=campus, code="EDU", defaults={"tenant": tenant, "title": "واحد آموزش"}
        )
        position, _ = Position.objects.get_or_create(
            org_unit=org_unit,
            code="TCH",
            defaults={
                "tenant": tenant,
                "title": "دبیر",
                "position_type": PositionType.TEACHING,
                "headcount": 20,
            },
        )
        EmployeeAssignment.objects.get_or_create(
            employee=employee,
            position=position,
            campus=campus,
            effective_from=date(2020, 9, 1),
            defaults={"tenant": tenant, "allocation_percent": 100, "is_primary": True},
        )

        profile, _ = TeacherProfile.objects.get_or_create(
            employee=employee,
            defaults={
                "tenant": tenant,
                "required_weekly_hours": 18,
                "qualification_status": "APPROVED",
                "specialization": "ریاضی و علوم",
            },
        )
        for course in courses:
            TeacherQualification.objects.get_or_create(
                teacher_profile=profile,
                course=course,
                grade_level=None,
                defaults={"tenant": tenant, "status": "APPROVED"},
            )
        return profile

    def _assign_teaching(self, tenant, offerings, teacher):
        for offering in offerings:
            TeachingAssignment.objects.get_or_create(
                course_offering=offering,
                teacher_profile=teacher,
                effective_from=self.year_start,
                defaults={
                    "tenant": tenant,
                    "responsibility": "PRIMARY",
                    "share_percent": 100,
                },
            )

    def _create_schedule(self, tenant, offerings, rooms, teacher):
        slots = [
            (0, time(8, 0), time(8, 45)),
            (0, time(8, 55), time(9, 40)),
            (1, time(8, 0), time(8, 45)),
            (1, time(8, 55), time(9, 40)),
            (2, time(8, 0), time(8, 45)),
            (2, time(8, 55), time(9, 40)),
        ]
        for offering, (weekday, starts, ends) in zip(offerings, slots):
            ScheduleEntry.objects.get_or_create(
                course_offering=offering,
                weekday=weekday,
                starts_at=starts,
                defaults={
                    "tenant": tenant,
                    "room": rooms[0],
                    "teacher_profile_id": teacher.id,
                    "ends_at": ends,
                    "effective_from": self.year_start,
                    "status": "PUBLISHED",
                },
            )

    def _create_finance(self, tenant, school, year, grade):
        FiscalYear.objects.get_or_create(
            school=school,
            title="سال مالی ۱۴۰۵",
            defaults={
                "tenant": tenant,
                "starts_on": self.year_start - timedelta(days=120),
                "ends_on": self.year_end + timedelta(days=60),
                "status": "OPEN",
            },
        )

        accounts = [
            ("1101", "صندوق", AccountType.ASSET),
            ("1102", "بانک", AccountType.ASSET),
            ("1131", "حساب دریافتنی دانش‌آموزان", AccountType.ASSET),
            ("2131", "پیش‌دریافت شهریه", AccountType.LIABILITY),
            ("4101", "درآمد شهریه", AccountType.REVENUE),
            ("6101", "هزینه اداری", AccountType.EXPENSE),
        ]
        for code, title, account_type in accounts:
            Account.objects.get_or_create(
                school=school,
                code=code,
                defaults={
                    "tenant": tenant,
                    "title": title,
                    "account_type": account_type,
                    "allows_posting": True,
                },
            )

        fee_plan, _ = FeePlan.objects.get_or_create(
            academic_year=year,
            grade_level=grade,
            title="تعرفه پایه هفتم — ۱۴۰۵",
            defaults={"tenant": tenant, "currency": "IRR"},
        )
        revenue = Account.objects.filter(school=school, code="4101").first()
        items = [
            (FeeType.REGISTRATION, "هزینه ثبت‌نام", 15_000_000),
            (FeeType.TUITION, "شهریه سالانه", 180_000_000),
            (FeeType.BOOK, "کتاب و لوازم", 12_000_000),
        ]
        for fee_type, title, amount in items:
            FeePlanItem.objects.get_or_create(
                fee_plan=fee_plan,
                fee_type=fee_type,
                defaults={
                    "tenant": tenant,
                    "title": title,
                    "amount": amount,
                    "revenue_account": revenue,
                },
            )

    def _create_students(
        self, tenant, campus, year, grade, program, class_group, count
    ) -> list[Student]:
        students = []
        for index in range(1, count + 1):
            is_female = index % 2 == 0
            first_name = random.choice(
                FIRST_NAMES_F if is_female else FIRST_NAMES_M
            )
            last_name = random.choice(LAST_NAMES)

            person, _ = Person.objects.get_or_create(
                tenant=tenant,
                national_id=f"10{index:08d}",
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "gender": Gender.FEMALE if is_female else Gender.MALE,
                    "birth_date": date(2013, ((index % 12) + 1), ((index % 28) + 1)),
                },
            )
            student, _ = Student.objects.get_or_create(
                person=person,
                defaults={
                    "tenant": tenant,
                    "student_no": f"14{index:05d}",
                    "joined_on": self.year_start,
                    "status": StudentStatus.ACTIVE,
                },
            )

            # ولی
            guardian_person, _ = Person.objects.get_or_create(
                tenant=tenant,
                national_id=f"20{index:08d}",
                defaults={
                    "first_name": random.choice(FIRST_NAMES_M),
                    "last_name": last_name,
                    "gender": Gender.MALE,
                },
            )
            ContactPoint.objects.get_or_create(
                person=guardian_person,
                contact_type=ContactType.MOBILE,
                value=f"0912{index:07d}",
                defaults={"tenant": tenant, "is_primary": True},
            )
            guardian, _ = Guardian.objects.get_or_create(
                person=guardian_person,
                defaults={"tenant": tenant, "occupation": "آزاد"},
            )
            StudentGuardian.objects.get_or_create(
                student=student,
                guardian=guardian,
                effective_from=self.year_start,
                defaults={
                    "tenant": tenant,
                    "relationship_type": RelationshipType.FATHER,
                    "has_custody": True,
                    "can_pickup": True,
                    "receives_reports": True,
                    "financially_responsible": True,
                    "contact_priority": 1,
                },
            )

            enrollment, _ = Enrollment.objects.get_or_create(
                student=student,
                academic_year=year,
                defaults={
                    "tenant": tenant,
                    "campus": campus,
                    "grade_level": grade,
                    "program": program,
                    "enrollment_no": f"ENR-1405-{index:05d}",
                    "enrolled_on": self.year_start,
                    "status": EnrollmentStatus.ACTIVE,
                },
            )
            ClassMembership.objects.get_or_create(
                enrollment=enrollment,
                class_group=class_group,
                defaults={
                    "tenant": tenant,
                    "effective_from": self.year_start,
                    "is_primary": True,
                    "status": "ACTIVE",
                },
            )
            students.append(student)

        return students

    def _create_users(self, tenant, teacher, students):
        """کاربران نمونه با نقش‌های سیستمی."""
        roles = {role.code: role for role in Role.objects.filter(tenant=tenant)}
        if not roles:
            self.stdout.write(
                self.style.WARNING(
                    "نقش‌های سیستمی یافت نشد. ابتدا `sync_permissions` را اجرا کنید."
                )
            )
            return

        def make_user(username, person=None, role_code=None, scope_type=None,
                      superuser=False):
            user, created = UserAccount.objects.get_or_create(
                username=username,
                defaults={
                    "tenant": tenant,
                    "person": person,
                    "status": "ACTIVE",
                    "is_staff": superuser,
                    "is_superuser": superuser,
                },
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            if role_code and role_code in roles:
                UserRoleAssignment.objects.get_or_create(
                    user=user,
                    role=roles[role_code],
                    scope_type=scope_type or ScopeType.SCHOOL,
                    defaults={
                        "tenant": tenant,
                        "effective_from": self.year_start,
                        "status": "ACTIVE",
                    },
                )
            return user

        staff_specs = [
            ("principal", "مریم", "شریفی", "PRINCIPAL", ScopeType.SCHOOL),
            ("vp.academic", "زهرا", "محمدی", "ACADEMIC_VP", ScopeType.CAMPUS),
            ("registrar", "علی", "نوری", "REGISTRAR", ScopeType.CAMPUS),
            ("accountant", "حسین", "قاسمی", "ACCOUNTANT", ScopeType.SCHOOL),
            ("librarian", "فاطمه", "جعفری", "LIBRARIAN", ScopeType.CAMPUS),
            ("warehouse", "مجید", "صادقی", "WAREHOUSE_KEEPER", ScopeType.CAMPUS),
        ]
        for index, (username, first, last, role_code, scope) in enumerate(
            staff_specs, start=1
        ):
            person, _ = Person.objects.get_or_create(
                tenant=tenant,
                national_id=f"30{index:08d}",
                defaults={"first_name": first, "last_name": last},
            )
            make_user(username, person, role_code, scope)

        make_user("admin", None, "SYS_ADMIN", ScopeType.TENANT, superuser=True)
        make_user("teacher1", teacher.employee.person, "TEACHER", ScopeType.CAMPUS)

        if students:
            first_student = students[0]
            make_user("student1", first_student.person, "STUDENT", ScopeType.SELF)
            link = first_student.guardian_links.first()
            if link:
                make_user(
                    "guardian1", link.guardian.person, "GUARDIAN", ScopeType.SELF
                )
