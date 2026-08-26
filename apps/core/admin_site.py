"""
چیدمان صفحه اصلی پنل مدیریت بر اساس اولویت استفاده.

جنگو ماژول‌ها و موجودیت‌ها را الفبایی مرتب می‌کند. نتیجه‌اش این است که
«اقلام فیش» بالاتر از «پرسنل» می‌نشیند و «اقلام بازبینی دسترسی» پیش از
«اشخاص» — یعنی جدول‌های جزئیات و لاگ، جای موجودیت‌های اصلی را می‌گیرند.

اینجا دو فهرست ترتیب صریح تعریف شده است: :data:`APP_ORDER` برای ماژول‌ها و
:data:`MODEL_ORDER` برای موجودیت‌های هر ماژول. هرچه در فهرست نیامده باشد، پس از
موارد فهرست‌شده و به‌ترتیب الفبا می‌آید — پس افزودن مدل تازه چیزی را نمی‌شکند،
فقط تا وقتی به فهرست اضافه نشده در انتهای ماژولش دیده می‌شود.

**برای تغییر ترتیب فقط همین دو فهرست را جابه‌جا کنید؛ جای دیگری وابسته نیست.**
"""

from __future__ import annotations

from django.contrib.admin import AdminSite

#: ترتیب ماژول‌ها در صفحه اصلی و نوار کناری.
#:
#: منطق چیدمان: امور اداری و پرسنل، سپس پیکربندی سازمانی و آموزشی، سپس
#: جریان روزمره کلاس (حضور، تکلیف، نمره، آزمون)، بعد مالی و پشتیبانی، و در
#: انتها زیرساخت که به‌ندرت باز می‌شود.
APP_ORDER: tuple[str, ...] = (
    "hr",            # پرسنل، معلمان، قرارداد، مرخصی، حقوق
    "identity",      # اشخاص، کاربر، نقش و دسترسی
    "organization",  # مدرسه، سال تحصیلی، کلاس، درس، برنامه هفتگی
    "students",      # پذیرش، دانش‌آموز، ولی، ثبت‌نام
    "teaching",      # جلسه، حضور و غیاب، تکلیف
    "gradebook",     # دفتر نمره و کارنامه
    "assessment",    # بانک سؤال و آزمون
    "finance",       # شهریه، دریافت، حسابداری
    "welfare",       # سلامت، مشاوره، انضباط، کتابخانه، سرویس
    "inventory",     # کالا، انبار، خرید، اموال
    "workflow",      # گردش تأیید، اعلان، تیکت
    "core",          # سازمان — تنظیمات بنیادی
    "auth",          # گروه‌های داخلی جنگو
)

#: ترتیب موجودیت‌ها درون هر ماژول.
#:
#: قاعده کلی: موجودیت اصلی اول، سپس وابسته‌های پرکاربرد، و در انتها جدول‌های
#: سطر/قلم و لاگ که مستقیم کم باز می‌شوند.
MODEL_ORDER: dict[str, tuple[str, ...]] = {
    "hr": (
        "Employee",
        "TeacherProfile",
        "TeachingAssignment",
        "EmploymentContract",
        "EmployeeAssignment",
        "Position",
        "OrgUnit",
        "WorkShift",
        "EmployeeAttendance",
        "LeaveRequest",
        "TeacherQualification",
        "PayrollRun",
        "Payslip",
        "PayslipItem",
    ),
    "identity": (
        "Person",
        "UserAccount",
        "Role",
        "Permission",
        "UserRoleAssignment",
        "RolePermission",
        "ContactPoint",
        "Address",
        "PersonAddress",
        "PersonDocument",
        "AccessReview",
        "AccessReviewItem",
        "AuditLog",
    ),
    "organization": (
        "School",
        "Campus",
        "AcademicYear",
        "Term",
        "GradeLevel",
        "StudyProgram",
        "Course",
        "ProgramCourse",
        "ClassGroup",
        "CourseOffering",
        "ScheduleEntry",
        "Room",
        "CalendarEvent",
    ),
    "students": (
        "Student",
        "Enrollment",
        "Guardian",
        "StudentGuardian",
        "ClassMembership",
        "AdmissionApplication",
        "StudentTransfer",
        "StudentStatusHistory",
        "Consent",
        "PromotionBatch",
        "PromotionDecisionRecord",
    ),
    "teaching": (
        "TeachingSession",
        "AttendanceRecord",
        "AbsenceJustification",
        "Assignment",
        "AssignmentSubmission",
        "SubmissionFeedback",
        "LessonPlan",
        "LearningResource",
        "SessionTeacher",
    ),
    "gradebook": (
        "GradeItem",
        "StudentScore",
        "AssessmentCategory",
        "CourseResult",
        "ReportCard",
        "ReportCardItem",
        "ScoreChange",
    ),
    "assessment": (
        "Exam",
        "ExamSession",
        "ExamRegistration",
        "ExamAttempt",
        "AttemptAnswer",
        "QuestionBank",
        "Question",
        "QuestionVersion",
        "QuestionOption",
        "ExamSection",
        "ExamQuestion",
        "QuestionTag",
        "QuestionTagLink",
        "ProctorEvent",
        "GradeReview",
        "GradeAppeal",
    ),
    "finance": (
        "Invoice",
        "Payment",
        "StudentFinancialAgreement",
        "FeePlan",
        "FeePlanItem",
        "DiscountAward",
        "Refund",
        "InvoiceLine",
        "PaymentAllocation",
        "Account",
        "JournalEntry",
        "JournalLine",
        "FiscalYear",
        "CostCenter",
        "BankAccount",
        "BankReconciliation",
    ),
    "welfare": (
        "HealthProfile",
        "HealthIncident",
        "HealthAlert",
        "CounselingCase",
        "CounselingSession",
        "BehaviorIncident",
        "BehaviorAction",
        "LibraryTitle",
        "LibraryCopy",
        "LibraryLoan",
        "TransportRoute",
        "RouteStop",
        "StudentRouteAssignment",
        "Vehicle",
        "RouteRun",
        "RidershipEvent",
    ),
    "inventory": (
        "Item",
        "ItemCategory",
        "StockBalance",
        "StockDocument",
        "StockDocumentLine",
        "StockMovement",
        "Warehouse",
        "Vendor",
        "PurchaseRequest",
        "PurchaseRequestLine",
        "PurchaseOrder",
        "PurchaseOrderLine",
        "GoodsReceipt",
        "Asset",
        "AssetAssignment",
        "MaintenanceOrder",
        "UnitOfMeasure",
    ),
    "workflow": (
        "ApprovalRequest",
        "ApprovalStep",
        "WorkflowDefinition",
        "Notification",
        "NotificationTemplate",
        "NotificationPreference",
        "DeliveryAttempt",
        "Ticket",
        "TicketMessage",
        "Attachment",
        "IntegrationMessage",
        "OutboxEvent",
    ),
    "core": ("Tenant",),
}

#: ماژول یا موجودیتی که در فهرست نیامده، بعد از همه فهرست‌شده‌ها می‌آید.
_UNRANKED = 10_000


class SchoolAdminSite(AdminSite):
    """پنل مدیریت با چیدمان اولویت‌محور و عنوان‌های فارسی."""

    site_header = "سامانه مدیریت مدرسه"
    site_title = "پنل مدیریت"
    index_title = "ماژول‌های سامانه"
    empty_value_display = "—"

    def get_app_list(self, request, app_label=None):
        """
        همان فهرست جنگو، اما مرتب‌شده بر اساس اولویت استفاده.

        نوار کناری هم از همین متد تغذیه می‌شود، پس ترتیب هر دو یکی می‌ماند.
        """
        app_list = super().get_app_list(request, app_label)

        app_list.sort(key=lambda app: self._app_rank(app["app_label"]))
        for app in app_list:
            order = MODEL_ORDER.get(app["app_label"], ())
            app["models"].sort(key=lambda model: self._model_rank(order, model))
        return app_list

    @staticmethod
    def _app_rank(app_label: str) -> int:
        try:
            return APP_ORDER.index(app_label)
        except ValueError:
            return _UNRANKED

    @staticmethod
    def _model_rank(order: tuple[str, ...], model: dict) -> tuple[int, str]:
        """رتبه موجودیت؛ نام فارسی، هم‌رتبه‌های فهرست‌نشده را الفبایی می‌کند."""
        name = model.get("object_name", "")
        try:
            rank = order.index(name)
        except ValueError:
            rank = _UNRANKED
        return rank, str(model.get("name", ""))
