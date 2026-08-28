"""
تنظیمات پروژه «سامانه مدیریت مدرسه».

مرجع: SCHOOL_MANAGEMENT_SYSTEM_ANALYSIS.md
- بخش ۶.۱ (Bounded Contextها) → نگاشت به اپ‌های Django
- بخش ۱۲.۴ (اصول API)
- بخش ۱۵.۱ (امنیت) و ۱۵.۲ (حریم خصوصی)
"""

from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# مسیرهای پروژه
#
#   database/        فایل SQLite — بیرون از درخت کد و بیرون از public
#   public/static/   خروجی collectstatic — چیزی که وب‌سرور سرو می‌کند
#   public/media/    فایل‌های آپلودی کاربران
#   assets/          فایل‌های ثابتِ منبع (پوسته و فونت پنل) — داخل مخزن
#
# `public/` تنها پوشه‌ای است که باید به وب‌سرور معرفی شود؛ نه کد در آن است و
# نه پایگاه داده، پس نشت فایل حساس از مسیر استاتیک ممکن نیست.
# ---------------------------------------------------------------------------
DATABASE_DIR = Path(config("DATABASE_DIR", default=BASE_DIR / "database"))
PUBLIC_DIR = Path(config("PUBLIC_DIR", default=BASE_DIR / "public"))
ASSETS_DIR = BASE_DIR / "assets"

for _directory in (DATABASE_DIR, PUBLIC_DIR):
    _directory.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# پایه
# ---------------------------------------------------------------------------
SECRET_KEY = config("DJANGO_SECRET_KEY", default="dev-insecure-key-change-me")
DEBUG = config("DJANGO_DEBUG", default=True, cast=bool)

#: دامنه‌های مجازی که Django به آن‌ها پاسخ می‌دهد.
#: در حالت عملیاتی حتماً فهرست صریح بدهید؛ `*` یعنی حمله Host Header باز است.
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

#: مبدأهایی که فرم و درخواست POST آن‌ها مورد اعتماد است (پنل پشت HTTPS).
#: باید با پروتکل نوشته شود: https://panel.example.school
#:
#: اگر خالی بماند از `DJANGO_ALLOWED_HOSTS` ساخته می‌شود. دلیلش یک خطای رایج
#: استقرار است: دامنه در ALLOWED_HOSTS هست ولی در CSRF_TRUSTED_ORIGINS نیست، و
#: ورود به پنل با «CSRF تأیید نشد» رد می‌شود. دامنه‌ای که به‌عنوان میزبان مجاز
#: اعلام شده، منطقاً مبدأ مورد اعتماد فرم‌های خودش هم هست.
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())


def _origins_from_hosts(hosts: list[str], *, include_http: bool) -> list[str]:
    """`ALLOWED_HOSTS` را به مبدأهای CSRF ترجمه می‌کند."""
    origins: list[str] = []
    for host in hosts:
        host = host.strip()
        if not host or host == "*":
            continue  # از «همه میزبان‌ها» نمی‌توان مبدأ مشخصی ساخت
        # `.example.com` در ALLOWED_HOSTS یعنی همه زیردامنه‌ها
        pattern = f"*{host}" if host.startswith(".") else host
        schemes = ("https", "http") if include_http else ("https",)
        for scheme in schemes:
            origin = f"{scheme}://{pattern}"
            if origin not in origins:
                origins.append(origin)
    return origins


if not CSRF_TRUSTED_ORIGINS:
    # در توسعه http هم لازم است؛ در عملیات فقط https اعتماد می‌شود.
    CSRF_TRUSTED_ORIGINS = _origins_from_hosts(ALLOWED_HOSTS, include_http=DEBUG)

#: مسیر پنل مدیریت. در عملیات تغییرش بدهید تا هدف اسکنرهای خودکار نباشد.
ADMIN_URL = config("ADMIN_URL", default="admin/").strip("/") + "/"

#: مدت نگهداری قرارداد OpenAPI در Cache (ثانیه). صفر یعنی خاموش.
SCHEMA_CACHE_SECONDS = config("SCHEMA_CACHE_SECONDS", default=900, cast=int)

#: سرورهایی که در قرارداد OpenAPI اعلام می‌شوند و در Swagger قابل انتخاب‌اند.
#:
#: پیش‌فرض عمداً خالی است. وقتی قرارداد هیچ `servers` اعلام نکند، Swagger و
#: ReDoc همان مبدأیی را صدا می‌زنند که خودشان از آن باز شده‌اند؛ یعنی روی
#: `localhost:8000` می‌شود localhost و روی دامنه عملیاتی می‌شود همان دامنه،
#: بدون هیچ تنظیمی. نشانی ثابت در این فهرست دقیقاً همان چیزی است که باعث
#: می‌شود دکمه Try it out روی سرور عملیاتی به `localhost` درخواست بزند.
#:
#: فقط اگر قرارداد را جای دیگری مصرف می‌کنید (تولید کلاینت، Postman) و به
#: نشانی مطلق نیاز دارید، پرش کنید. قالب هر مورد:
#:     https://school.amirkho.ir|محیط عملیاتی
API_SERVERS = [
    {"url": url, "description": description}
    for url, _, description in (
        item.partition("|") for item in config("API_SERVERS", default="", cast=Csv())
    )
    if url
]

# ---------------------------------------------------------------------------
# اپلیکیشن‌ها — هر اپ معادل یک Bounded Context در بخش ۶.۱ سند تحلیل است.
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "apps.core.admin_apps.SchoolAdminConfig",  # جای django.contrib.admin — AdminSite سفارشی
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "drf_spectacular_sidecar",
]

LOCAL_APPS = [
    "apps.core",          # زیرساخت مشترک، Tenant، ممیزی، خطا و صفحه‌بندی
    "apps.identity",      # هویت و دسترسی (IAM)
    "apps.organization",  # ساختار سازمانی و آموزشی
    "apps.students",      # پذیرش و امور دانش‌آموزان
    "apps.hr",            # منابع انسانی
    "apps.teaching",      # آموزش روزانه، حضور و تکلیف
    "apps.assessment",    # بانک سؤال و آزمون
    "apps.gradebook",     # دفتر نمره و کارنامه
    "apps.finance",       # شهریه، پرداخت و حسابداری
    "apps.inventory",     # خرید، انبار و اموال
    "apps.welfare",       # سلامت، مشاوره، کتابخانه، حمل‌ونقل
    "apps.workflow",      # گردش تأیید، اعلان، فایل، Outbox
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # فایل‌های ثابت را با DEBUG=False هم خود Django سرو می‌کند.
    # بدون این، اگر وب‌سرور مسیر /static/ را درست تنظیم نکرده باشد، پنل مدیریت
    # بی‌استایل و Swagger/ReDoc صفحه سفید می‌شوند.
    # جایش باید دقیقاً اینجا باشد: بعد از SecurityMiddleware و قبل از بقیه.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # میان‌افزارهای اختصاصی سامانه
    "apps.core.middleware.CorrelationIdMiddleware",
    "apps.core.middleware.RequestContextMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# پایگاه داده
# ---------------------------------------------------------------------------
DATABASE_URL = config("DATABASE_URL", default="")
if DATABASE_URL.startswith("postgres"):
    import urllib.parse as _urlparse

    _parsed = _urlparse.urlparse(DATABASE_URL)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _parsed.path.lstrip("/"),
            "USER": _parsed.username,
            "PASSWORD": _parsed.password,
            "HOST": _parsed.hostname,
            "PORT": _parsed.port or 5432,
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": DATABASE_DIR / config("SQLITE_NAME", default="db.sqlite3"),
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "identity.UserAccount"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# بین‌المللی‌سازی
# زمان در پایگاه داده UTC ذخیره می‌شود؛ تقویم جلالی وظیفه لایه نمایش است (بخش ۱).
# ---------------------------------------------------------------------------
LANGUAGE_CODE = config("DJANGO_LANGUAGE_CODE", default="fa")
TIME_ZONE = config("DJANGO_TIME_ZONE", default="Asia/Tehran")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# فایل‌های ثابت و آپلودی
# ---------------------------------------------------------------------------
STATIC_URL = config("STATIC_URL", default="public/static/")
STATIC_ROOT = PUBLIC_DIR / "static"

# پوسته و فونت پنل مدیریت (وزیرمتن، مجوز SIL OFL) اینجا میزبانی می‌شود
# تا پنل بدون دسترسی به اینترنت هم درست نمایش داده شود.
STATICFILES_DIRS = [ASSETS_DIR]

MEDIA_URL = config("MEDIA_URL", default="public/media/")
MEDIA_ROOT = PUBLIC_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        # فشرده‌سازی + نام هش‌دار برای Cache Busting.
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

#: فایلی که در Manifest نیست، به‌جای خطای ۵۰۰ با نام اصلی سرو می‌شود.
#: بعضی از CSSهای ثالث به فایل‌های ناموجود ارجاع می‌دهند و نباید کل صفحه را
#: از کار بیندازند.
WHITENOISE_MANIFEST_STRICT = False

#: در توسعه، WhiteNoise فایل‌ها را مستقیم از assets/ می‌خواند تا نیازی به
#: اجرای collectstatic بعد از هر تغییر پوسته نباشد.
WHITENOISE_USE_FINDERS = DEBUG
WHITENOISE_AUTOREFRESH = DEBUG

#: سقف حجم آپلود که در حافظه نگه داشته می‌شود (بایت)؛ بیشتر از آن روی دیسک.
DATA_UPLOAD_MAX_MEMORY_SIZE = config(
    "DATA_UPLOAD_MAX_MEMORY_SIZE", default=10 * 1024 * 1024, cast=int
)
FILE_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE

# ---------------------------------------------------------------------------
# Django REST Framework — بخش ۱۲.۴ اصول API
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("apps.core.permissions.ScopedRBACPermission",),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.DefaultPageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "apps.core.schema.PersianAutoSchema",
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ),
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.ScopedRateThrottle",),
    # نرخ‌های جداگانه برای ورود، آزمون، پرداخت و Export (بخش ۱۲.۴)
    "DEFAULT_THROTTLE_RATES": {
        "auth": "10/min",
        "password_reset": "5/hour",
        "exam_attempt": "120/min",
        "payment": "30/min",
        "export": "10/hour",
    },
    "ORDERING_PARAM": "ordering",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=config("JWT_ACCESS_MINUTES", default=30, cast=int)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=config("JWT_REFRESH_DAYS", default=7, cast=int)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ---------------------------------------------------------------------------
# drf-spectacular — OpenAPI 3 / Swagger UI / ReDoc
# ---------------------------------------------------------------------------
API_DESCRIPTION = """
وب‌سرویس یکپارچه مدیریت مدرسه: پذیرش، ثبت‌نام، آموزش، حضور و غیاب، آزمون،
دفتر نمره و کارنامه، منابع انسانی، مالی و حسابداری دوبل، خرید و انبار و اموال،
و خدمات دانش‌آموزی.

### احراز هویت
تمام مسیرها به‌جز `/api/v1/auth/token/` و `/api/v1/auth/token/refresh/`
نیازمند هدر زیر هستند:

    Authorization: Bearer <access_token>

### انتخاب Context کاری
اکثر منابع به مدرسه، شعبه و سال تحصیلی محدود می‌شوند. Context مؤثر با هدرهای
زیر ارسال می‌شود و در لایه Repository اعمال می‌گردد:

    X-School-Id: <uuid>
    X-Campus-Id: <uuid>
    X-Academic-Year-Id: <uuid>

### Idempotency
عملیات نوشتنی حساس (پرداخت، ثبت‌نام، تحویل آزمون) هدر `Idempotency-Key`
می‌پذیرند؛ ارسال مجدد با همان کلید، همان نتیجه را برمی‌گرداند.

### همزمانی خوش‌بینانه
پاسخ هر منبع دارای فیلد `version` است. برای جلوگیری از Lost Update،
هدر `If-Match: <version>` را در PUT/PATCH ارسال کنید.

### صفحه‌بندی
پیش‌فرض صفحه‌ای است (`?page=1&page_size=25`). برای فهرست‌های بزرگ و پرتغییر،
صفحه‌بندی مبتنی بر Cursor نیز در دسترس است (`?cursor=...`).

### قالب خطا (بخش ۱۲.۳ سند تحلیل)

    {
      "code": "CLASS_CAPACITY_EXCEEDED",
      "message": "ظرفیت کلاس تکمیل است.",
      "correlationId": "01J7ZS...",
      "fieldErrors": [{"field": "classGroupId", "reason": "capacity"}],
      "retryable": false
    }
"""

SPECTACULAR_SETTINGS = {
    "TITLE": "API سامانه مدیریت مدرسه",
    "DESCRIPTION": API_DESCRIPTION,
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    # خالی گذاشتنش عمدی است — توضیح کنار API_SERVERS در بالای همین فایل.
    "SERVERS": API_SERVERS,
    "TAGS": [
        {"name": "Auth", "description": "ورود، تازه‌سازی توکن، پروفایل و Context کاری"},
        {"name": "IAM", "description": "اشخاص، کاربران، نقش، مجوز و ممیزی دسترسی"},
        {
            "name": "Organization",
            "description": "مدرسه، شعبه، سال تحصیلی، پایه، درس، کلاس و برنامه هفتگی",
        },
        {
            "name": "Students",
            "description": "پذیرش، دانش‌آموز، اولیا، ثبت‌نام و رضایت‌نامه",
        },
        {"name": "HR", "description": "پرسنل، قرارداد، انتساب تدریس، مرخصی و حقوق"},
        {"name": "Teaching", "description": "جلسه، حضور و غیاب، تکلیف و منابع آموزشی"},
        {
            "name": "Assessment",
            "description": "بانک سؤال، آزمون، جلسه آزمون، تلاش و تصحیح",
        },
        {"name": "Gradebook", "description": "دفتر نمره، نتیجه درس و کارنامه"},
        {
            "name": "Finance",
            "description": "تعرفه، صورتحساب، پرداخت، استرداد و حسابداری دوبل",
        },
        {
            "name": "Inventory",
            "description": "تأمین‌کننده، خرید، انبار، حرکت موجودی و اموال",
        },
        {"name": "Welfare", "description": "سلامت، مشاوره، انضباط، کتابخانه و حمل‌ونقل"},
        {"name": "Workflow", "description": "گردش تأیید، اعلان، پیوست و Outbox"},
        {"name": "Reports", "description": "داشبورد و گزارش‌های تجمیعی"},
    ],
    # ترتیب مهم است: نخست Enumها به Schema مستقل تبدیل می‌شوند، سپس Hook فارسی
    # برچسب، نمونه و پاسخ‌های خطای استاندارد را روی همان خروجی می‌نشاند.
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "apps.core.schema.postprocess_persian_docs",
    ],
    # نام‌گذاری پایدار Enumها.
    # بدون این نگاشت، drf-spectacular برای فیلدهای هم‌نام (status, severity, …)
    # نام‌های هش‌دار مثل Status930Enum می‌سازد که در تولید تایپ TypeScript
    # ناخوانا و ناپایدار است.
    "ENUM_NAME_OVERRIDES": {
        # --- وضعیت‌ها ---
        "RecordStatusEnum": "apps.core.models.RecordStatus.choices",
        "PersonStatusEnum": "apps.identity.enums.PersonStatus.choices",
        "UserStatusEnum": "apps.identity.enums.UserStatus.choices",
        "RoleAssignmentStatusEnum": "apps.identity.enums.RoleAssignmentStatus.choices",
        "AccessReviewStatusEnum": "apps.identity.enums.AccessReviewStatus.choices",
        "AcademicYearStatusEnum": "apps.organization.enums.AcademicYearStatus.choices",
        "TermStatusEnum": "apps.organization.enums.TermStatus.choices",
        "ClassGroupStatusEnum": "apps.organization.enums.ClassGroupStatus.choices",
        "CourseOfferingStatusEnum": "apps.organization.enums.CourseOfferingStatus.choices",
        "ScheduleStatusEnum": "apps.organization.enums.ScheduleStatus.choices",
        "AdmissionStatusEnum": "apps.students.enums.AdmissionStatus.choices",
        "EnrollmentStatusEnum": "apps.students.enums.EnrollmentStatus.choices",
        "StudentStatusEnum": "apps.students.enums.StudentStatus.choices",
        "ClassMembershipStatusEnum": "apps.students.enums.ClassMembershipStatus.choices",
        "ConsentStatusEnum": "apps.students.enums.ConsentStatus.choices",
        "EmployeeStatusEnum": "apps.hr.enums.EmployeeStatus.choices",
        "ContractStatusEnum": "apps.hr.enums.ContractStatus.choices",
        "LeaveStatusEnum": "apps.hr.enums.LeaveStatus.choices",
        "PayrollStatusEnum": "apps.hr.enums.PayrollStatus.choices",
        "TeacherQualificationStatusEnum": "apps.hr.enums.QualificationStatus.choices",
        "SessionStatusEnum": "apps.teaching.enums.SessionStatus.choices",
        "AttendanceStatusEnum": "apps.teaching.enums.AttendanceStatus.choices",
        "FinalizationStatusEnum": "apps.teaching.enums.FinalizationStatus.choices",
        "AssignmentStatusEnum": "apps.teaching.enums.AssignmentStatus.choices",
        "SubmissionStatusEnum": "apps.teaching.enums.SubmissionStatus.choices",
        "LessonPlanStatusEnum": "apps.teaching.enums.LessonPlanStatus.choices",
        "QuestionLifecycleEnum": "apps.assessment.enums.QuestionLifecycle.choices",
        "QuestionReviewStatusEnum": "apps.assessment.enums.ReviewStatus.choices",
        "ExamStatusEnum": "apps.assessment.enums.ExamStatus.choices",
        "ExamSessionStatusEnum": "apps.assessment.enums.ExamSessionStatus.choices",
        "AttemptStatusEnum": "apps.assessment.enums.AttemptStatus.choices",
        "GradingStatusEnum": "apps.assessment.enums.GradingStatus.choices",
        "RegistrationStatusEnum": "apps.assessment.enums.RegistrationStatus.choices",
        "AppealStatusEnum": "apps.assessment.enums.AppealStatus.choices",
        "GradeItemStatusEnum": "apps.gradebook.enums.GradeItemStatus.choices",
        "ScoreStatusEnum": "apps.gradebook.enums.ScoreStatus.choices",
        "CourseResultStatusEnum": "apps.gradebook.enums.CourseResultStatus.choices",
        "ReportCardStatusEnum": "apps.gradebook.enums.ReportCardStatus.choices",
        "FiscalYearStatusEnum": "apps.finance.enums.FiscalYearStatus.choices",
        "AgreementStatusEnum": "apps.finance.enums.AgreementStatus.choices",
        "InvoiceStatusEnum": "apps.finance.enums.InvoiceStatus.choices",
        "PaymentStatusEnum": "apps.finance.enums.PaymentStatus.choices",
        "RefundStatusEnum": "apps.finance.enums.RefundStatus.choices",
        "JournalStatusEnum": "apps.finance.enums.JournalStatus.choices",
        "ReconciliationStatusEnum": "apps.finance.enums.ReconciliationStatus.choices",
        # این مجموعه مقادیر (PENDING/APPROVED/REJECTED) بین چند ماژول مشترک است.
        "PendingApprovalStateEnum": "apps.finance.enums.ApprovalState.choices",
        "VendorStatusEnum": "apps.inventory.enums.VendorStatus.choices",
        "StockDocumentStatusEnum": "apps.inventory.enums.StockDocumentStatus.choices",
        "PurchaseRequestStatusEnum": "apps.inventory.enums.PurchaseRequestStatus.choices",
        "PurchaseOrderStatusEnum": "apps.inventory.enums.PurchaseOrderStatus.choices",
        "ReceiptStatusEnum": "apps.inventory.enums.ReceiptStatus.choices",
        "QualityStatusEnum": "apps.inventory.enums.QualityStatus.choices",
        "AssetLifecycleStatusEnum": "apps.inventory.enums.AssetLifecycleStatus.choices",
        "AssetConditionEnum": "apps.inventory.enums.AssetCondition.choices",
        "MaintenanceStatusEnum": "apps.inventory.enums.MaintenanceStatus.choices",
        "HealthAlertStatusEnum": "apps.welfare.enums.HealthAlertStatus.choices",
        "CounselingCaseStatusEnum": "apps.welfare.enums.CounselingCaseStatus.choices",
        "BehaviorIncidentStatusEnum": "apps.welfare.enums.BehaviorIncidentStatus.choices",
        "CopyStatusEnum": "apps.welfare.enums.CopyStatus.choices",
        "LoanStatusEnum": "apps.welfare.enums.LoanStatus.choices",
        "RouteRunStatusEnum": "apps.welfare.enums.RouteRunStatus.choices",
        "WorkflowApprovalStatusEnum": "apps.workflow.enums.ApprovalStatus.choices",
        "NotificationStatusEnum": "apps.workflow.enums.NotificationStatus.choices",
        "TicketStatusEnum": "apps.workflow.enums.TicketStatus.choices",
        "IntegrationStatusEnum": "apps.workflow.enums.IntegrationStatus.choices",
        "ScanStatusEnum": "apps.workflow.enums.ScanStatus.choices",
        # --- سایر فیلدهای هم‌نام ---
        "AlertSeverityEnum": "apps.welfare.enums.AlertSeverity.choices",
        "BehaviorSeverityEnum": "apps.welfare.enums.BehaviorSeverity.choices",
        "ProctorEventSeverityEnum": "apps.assessment.enums.EventSeverity.choices",
        "NotificationChannelEnum": "apps.core.enums.NotificationChannel.choices",
        "NotificationPriorityEnum": "apps.workflow.enums.NotificationPriority.choices",
        # مقادیر اولویت بین تیکت و مشاوره مشترک است.
        "PriorityLevelEnum": "apps.workflow.enums.TicketPriority.choices",
        "RouteDirectionEnum": "apps.welfare.enums.RouteDirection.choices",
        "IntegrationDirectionEnum": "apps.workflow.enums.IntegrationDirection.choices",
        "DataClassificationEnum": "apps.core.enums.DataClassification.choices",
        "ApprovalDecisionEnum": "apps.core.enums.ApprovalDecision.choices",
    },
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
#: مبدأهای فرانت‌اند که اجازه فراخوانی API را دارند — با پروتکل و پورت.
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://localhost:5173",
    cast=Csv(),
)

#: اگر فرانت با کوکی (نه فقط توکن) کار می‌کند باید True باشد.
CORS_ALLOW_CREDENTIALS = config("CORS_ALLOW_CREDENTIALS", default=False, cast=bool)

#: فقط برای توسعه. با True هر مبدأیی مجاز می‌شود و CORS عملاً خاموش است.
CORS_ALLOW_ALL_ORIGINS = config("CORS_ALLOW_ALL_ORIGINS", default=False, cast=bool)
CORS_ALLOW_HEADERS = (
    "accept",
    "accept-language",
    "authorization",
    "content-type",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-school-id",
    "x-campus-id",
    "x-academic-year-id",
    "idempotency-key",
    "x-correlation-id",
    "if-match",
)
CORS_EXPOSE_HEADERS = ("x-correlation-id", "etag")

# ---------------------------------------------------------------------------
# امنیت در محیط عملیاتی (بخش ۱۵.۱)
#
# پیش‌فرض‌ها با `DEBUG=False` روشن می‌شوند، اما همه از `.env` قابل تنظیم‌اند:
# پشت یک Reverse Proxy که خودش TLS را تمام می‌کند، `SECURE_SSL_REDIRECT` بدون
# `SECURE_PROXY_SSL_HEADER` حلقه ریدایرکت می‌سازد.
# ---------------------------------------------------------------------------
_PRODUCTION = not DEBUG

SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=_PRODUCTION, cast=bool)
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=_PRODUCTION, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=_PRODUCTION, cast=bool)
SECURE_HSTS_SECONDS = config(
    "SECURE_HSTS_SECONDS", default=31536000 if _PRODUCTION else 0, cast=int
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=_PRODUCTION, cast=bool
)
SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", default=_PRODUCTION, cast=bool)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

#: پشت nginx/traefik این را روشن کنید تا Django پروتکل واقعی را بشناسد.
if config("USE_X_FORWARDED_PROTO", default=False, cast=bool):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} corr={correlation_id} {message}",
            "style": "{",
        },
    },
    "filters": {
        "correlation": {"()": "apps.core.logging_filters.CorrelationIdFilter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["correlation"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": config("LOG_LEVEL", default="INFO"),
    },
}
