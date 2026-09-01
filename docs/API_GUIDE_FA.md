# راهنمای وب‌سرویس سامانه مدیریت مدرسه

> مخاطب: توسعه‌دهنده فرانت‌اند
> نسخه API: `v1` — پیشوند همه مسیرها: `/api/v1/`
> مرجع دامنه: [تحلیل جامع سامانه](../../SCHOOL_MANAGEMENT_SYSTEM_ANALYSIS.md) و [راهنمای وایرفریم RTL](../../FRONTEND_RTL_WIREFRAME_GUIDE.md)

---

## فهرست

| بخش | موضوع |
|---:|---|
| ۱ | شروع سریع و راه‌اندازی |
| ۲ | مستندات تعاملی (Swagger / ReDoc) |
| ۳ | احراز هویت و Context کاری |
| ۴ | مدل دسترسی و کنترل نمایش در UI |
| ۵ | قراردادهای عمومی: صفحه‌بندی، فیلتر، مرتب‌سازی، حذف |
| ۶ | قالب خطا و کدهای معنایی |
| ۷ | Idempotency و کنترل هم‌زمانی |
| ۸ | کاتالوگ Enumها و برچسب‌های فارسی |
| ۹ | نقشه ماژول‌ها و منابع |
| ۱۰ | سناریوهای کامل با نمونه درخواست/پاسخ |
| ۱۱ | تولید تایپ TypeScript |
| ۱۲ | نکات پیاده‌سازی فرانت |

---

## ۱. شروع سریع

### پیش‌نیاز

- Python 3.11+
- (اختیاری) PostgreSQL — پیش‌فرض SQLite است

### راه‌اندازی

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
```

```bash
cd backend && python manage.py migrate
```

```bash
cd backend && python manage.py seed_demo
```

```bash
cd backend && python manage.py runserver
```

سرویس روی `http://localhost:8000` بالا می‌آید.

### کاربران نمونه

دستور `seed_demo` یک مدرسه کامل با ۲۴ دانش‌آموز، معلم، کلاس، برنامه هفتگی و
تعرفه شهریه می‌سازد. رمز عبور همه کاربران نمونه: **`Demo!Pass2026`**

| نام کاربری | نقش | کاربرد در تست فرانت |
|---|---|---|
| `admin` | مدیر سامانه (superuser) | دسترسی کامل، تست همه صفحات |
| `principal` | مدیر مدرسه | داشبورد مدیریتی، تأییدها |
| `vp.academic` | معاون آموزشی | کلاس، برنامه، حضور، نمره، آزمون |
| `registrar` | مسئول ثبت‌نام | پذیرش، پرونده دانش‌آموز، ثبت‌نام |
| `teacher1` | معلم | «امروز من»، ثبت حضور، تکلیف، دفتر نمره |
| `accountant` | حسابدار | صورتحساب، دریافت، اسناد حسابداری |
| `librarian` | کتابدار | کتابخانه و امانت |
| `warehouse` | انباردار | کالا، رسید، حواله، کاردکس |
| `guardian1` | ولی | پرتال ولی: حضور، نمره، مالی فرزند |
| `student1` | دانش‌آموز | برنامه، تکلیف، آزمون، کارنامه |

> خروجی `seed_demo` شناسه‌های مدرسه، شعبه، سال تحصیلی و کلاس نمونه را چاپ
> می‌کند؛ همان‌ها را در هدرهای Context بگذارید.

---

## ۲. مستندات تعاملی

| آدرس | توضیح |
|---|---|
| `/api/docs/` | **Swagger UI** — تست زنده همه Endpointها |
| `/api/redoc/` | **ReDoc** — مطالعه ساختاریافته |
| `/api/schema/` | فایل خام OpenAPI 3 (YAML) |
| `backend/docs/openapi.yaml` | نسخه تولیدشده و ذخیره‌شده (YAML) |
| `backend/docs/openapi.json` | نسخه JSON برای ابزارهای Codegen |

آمار فعلی قرارداد: **۴۴۴ مسیر**، **۹۲۷ عملیات**، **۷۸۸ Schema**، بدون هیچ هشدار.

### آنچه در قرارداد تضمین شده است

هر عملیات — بدون استثنا — این چهار مورد را دارد، بنابراین برای پیاده‌سازی فرانت
نیازی به خواندن کد بک‌اند نیست:

| مورد | توضیح |
|---|---|
| **عنوان فارسی** | `summary` هر عملیات؛ همان چیزی که در فهرست Swagger و ReDoc دیده می‌شود |
| **راهنمای فارسی** | `description` شامل قواعد همان عملیات: صفحه‌بندی، فیلترها، کنترل هم‌زمانی، دامنه دسترسی و **کد مجوز لازم** |
| **نمونه ورودی و خروجی** | هر Schema یک `example` کامل دارد؛ در Swagger زیر تب *Example Value* و در ReDoc کنار هر مدل دیده می‌شود |
| **پاسخ‌های خطا** | ۴۰۰، ۴۰۱، ۴۰۳، ۴۰۴، ۴۰۹ و ۴۲۲ با نمونه واقعی، مطابق [قالب خطا](#۶-قالب-خطا) |

همچنین برچسب فارسی همه فیلدها (`title`) در Schema موجود است؛ فرم‌ساز فرانت
می‌تواند مستقیماً از قرارداد، Label بگیرد.

> این متن‌ها دستی نوشته نشده‌اند: `apps/core/schema.py` آن‌ها را هنگام تولید
> Schema از `verbose_name` مدل و پیکربندی خود View می‌سازد. پس با افزوده‌شدن
> منبع تازه، مستندسازی‌اش هم خودکار کامل می‌شود.

### استفاده از Swagger UI

1. ابتدا `POST /api/v1/auth/token/` را با یکی از کاربران بالا اجرا کنید.
2. مقدار `access` را کپی کنید.
3. دکمه **Authorize** بالای صفحه → مقدار را وارد کنید.
4. حالا همه Endpointها قابل تست‌اند.

---

## ۳. احراز هویت و Context کاری

### ۳.۱ ورود

```
POST /api/v1/auth/token/
Content-Type: application/json
```

```json
{
  "username": "vp.academic",
  "password": "Demo!Pass2026"
}
```

**پاسخ ۲۰۰:**

```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expiresIn": 1800,
  "mustChangePassword": false,
  "mfaRequired": false
}
```

**پاسخ ۴۰۱ (نام کاربری یا رمز نادرست):**

```json
{
  "code": "AUTHENTICATION_FAILED",
  "message": "نام کاربری یا رمز عبور درست نیست.",
  "correlationId": "0fd0eac5ac8142958950d299d5395a4e",
  "fieldErrors": [],
  "retryable": false
}
```

> **نکته امنیتی (بخش ۱۵.۱ سند تحلیل):** پیام خطا عمداً عمومی است و وجود یا
> نبود حساب را افشا نمی‌کند. فرانت نباید پیام متفاوتی برای «کاربر یافت نشد»
> نشان دهد.

### ۳.۲ ارسال توکن

همه درخواست‌های بعدی:

```
Authorization: Bearer <access>
```

### ۳.۳ تازه‌سازی توکن

```
POST /api/v1/auth/token/refresh/
```

```json
{ "refresh": "<refresh token>" }
```

### ۳.۴ پروفایل و محیط‌های کاری

```
GET /api/v1/auth/me/
```

```json
{
  "id": "554dc400-bc55-478b-a045-f3b2313c29ec",
  "username": "vp.academic",
  "displayName": "زهرا محمدی",
  "email": "",
  "mobile": "",
  "personId": "68d1c161-17b8-4a7c-a923-e8816b817174",
  "tenantId": "1f82120f-7554-48a1-845e-4dcc754ed0a1",
  "status": "ACTIVE",
  "mfaEnabled": false,
  "mustChangePassword": false,
  "isSuperuser": false,
  "roles": ["ACADEMIC_VP"],
  "permissions": [
    "attendance.create",
    "attendance.finalize",
    "attendance.read",
    "attendance.update",
    "class_group.create",
    "grade.publish"
  ],
  "contexts": [
    {
      "roleCode": "ACADEMIC_VP",
      "roleTitle": "معاون آموزشی",
      "scopeType": "CAMPUS",
      "scopeId": "6708ba93-0683-45fe-84e6-6b6911421357"
    }
  ]
}
```

این پاسخ سه کار را برای فرانت انجام می‌دهد:

1. **ساخت منو** بر اساس `roles`
2. **کنترل نمایش دکمه‌ها** بر اساس `permissions`
3. **صفحه «انتخاب محیط کاری»** بر اساس `contexts` — اگر فقط یک مورد باشد،
   این صفحه Skip می‌شود (بخش ۵.۲ سند فرانت).

### ۳.۵ هدرهای Context

پس از انتخاب محیط کاری، این هدرها را در همه درخواست‌ها بفرستید:

```
X-School-Id: d0d4c729-26af-47b9-bf81-359f37f2f6d8
X-Campus-Id: 6708ba93-0683-45fe-84e6-6b6911421357
X-Academic-Year-Id: 8f1fe8d2-afdc-418e-bdb1-6e3f84965fe9
```

سرور این Contextها را **در لایه دسترسی داده** اعمال می‌کند و با پارامتر Query
قابل دور زدن نیست (بخش ۱۲.۴ سند تحلیل). یعنی اگر `X-Academic-Year-Id` بفرستید،
فهرست کلاس‌ها خودبه‌خود فقط کلاس‌های همان سال را برمی‌گرداند.

> **مهم:** با تعویض Context، **Query Cache فرانت باید بر اساس Scope جدا شود**
> وگرنه داده سال قبل در سال جدید نشان داده می‌شود.

### ۳.۶ سایر مسیرهای احراز هویت

| متد | مسیر | توضیح |
|---|---|---|
| `GET` | `/auth/contexts/` | محیط‌های کاری با **نام** دامنه و هدرهای لازم |
| `POST` | `/auth/logout/` | خروج — همه نشست‌های فعال باطل می‌شوند |
| `POST` | `/auth/sessions/revoke/` | «خروج از همه دستگاه‌ها» |
| `POST` | `/auth/password/change/` | تغییر رمز (نیازمند رمز فعلی) |
| `POST` | `/auth/password/reset/` | درخواست بازیابی — پاسخ همیشه یکسان |
| `POST` | `/auth/password/reset/confirm/` | تعیین رمز تازه با `uid` و `token` لینک |

### ۳.۷ ابطال نشست

توکن‌ها **نسخه** دارند. با خروج، تغییر رمز، بازیابی رمز، غیرفعال‌شدن حساب یا
ابطال توسط مدیر، نسخه یک واحد جلو می‌رود و همه توکن‌های پیشین — هم `access` و
هم `refresh`، روی همه دستگاه‌ها — بلافاصله بی‌اعتبار می‌شوند.

آنچه فرانت باید انجام دهد:

- پاسخ **۴۰۱ با کد `token_revoked`** روی `/auth/token/refresh/` یعنی نشست باطل
  شده است: توکن‌های ذخیره‌شده را پاک کنید و به صفحه ورود بروید. **دوباره تلاش
  نکنید** — این خطا با انقضای عادی توکن فرق دارد.
- پس از `POST /auth/password/change/` کاربر باید دوباره وارد شود.

### ۳.۸ قفل حساب

پس از چند تلاش ناموفق پیاپی (پیش‌فرض ۵)، حساب برای مدتی کوتاه (پیش‌فرض ۱۵
دقیقه) قفل می‌شود. پاسخ در این حالت:

```json
{
  "code": "ACCOUNT_LOCKED",
  "message": "این حساب به‌دلیل تلاش‌های ناموفق موقتاً قفل شده است؛ کمی بعد دوباره تلاش کنید.",
  "correlationId": "112f12270ba4437b9b4cfea2d3044ca1",
  "fieldErrors": [],
  "retryable": true
}
```

کد وضعیت `423` است و `retryable: true` یعنی قفل موقتی است — پیام باید
«کمی بعد دوباره تلاش کنید» باشد، نه «با پشتیبانی تماس بگیرید». مدیر می‌تواند
با `POST /iam/users/{id}/unlock/` قفل را زودتر بردارد.

### ۳.۹ محیط‌های کاری با نام

`contexts` در `/auth/me/` فقط شناسه دامنه را می‌دهد. برای صفحه
«انتخاب مدرسه، شعبه و سال» از این استفاده کنید:

```
GET /api/v1/auth/contexts/
```

```json
{
  "defaultContext": null,
  "contexts": [
    {
      "roleCode": "ACADEMIC_VP",
      "roleTitle": "معاون آموزشی",
      "scopeType": "CAMPUS",
      "scopeTypeDisplay": "شعبه",
      "scopeId": "6708ba93-0683-45fe-84e6-6b6911421357",
      "scopeTitle": "شعبه مرکزی",
      "schoolId": "d0d4c729-26af-47b9-bf81-359f37f2f6d8",
      "campusId": "6708ba93-0683-45fe-84e6-6b6911421357",
      "academicYearId": null
    }
  ],
  "schools": [
    { "id": "d0d4c729-26af-47b9-bf81-359f37f2f6d8", "name": "دبیرستان نمونه دانش", "code": "SCH01" }
  ],
  "headers": {
    "school": "X-School-Id",
    "campus": "X-Campus-Id",
    "academicYear": "X-Academic-Year-Id"
  }
}
```

- `scopeTitle` نام خواندنی برای نمایش در فهرست است.
- `schoolId` / `campusId` / `academicYearId` دقیقاً همان مقادیری‌اند که باید در
  هدرهای Context بروند؛ نگاشت نوع دامنه به نام هدر در `headers` آمده است.
- `defaultContext` اگر پر باشد یعنی کاربر تنها یک محیط کاری دارد و صفحه انتخاب
  باید Skip شود.

> هدر Context فقط می‌تواند دسترسی را **باریک‌تر** کند. فرستادن شناسه‌ای بیرون
> از محدوده مجاز، خطا نمی‌دهد؛ نادیده گرفته می‌شود و نتیجه همان محدوده مجاز
> کاربر می‌ماند. پس فهرست خالی را «بدون دسترسی» تفسیر کنید، نه «خطا».

---

## ۴. مدل دسترسی

### ۴.۱ ساختار

مدل ترکیبی **RBAC + Scope** است (بخش ۳.۲ سند تحلیل):

- **Permission** — عمل اتمی روی منبع: `student.read`، `grade.publish`، `payment.refund`
- **Role** — مجموعه‌ای از مجوزها: «معلم»، «حسابدار»
- **Scope** — دامنه اعمال نقش: `TENANT` / `SCHOOL` / `CAMPUS` / `ACADEMIC_YEAR` / `CLASS_GROUP` / `COURSE_OFFERING` / `SELF`

سامانه **۲۰۹ مجوز** و **۱۷ نقش سیستمی** از پیش تعریف‌شده دارد.

### ۴.۲ کنترل نمایش در فرانت

```ts
const can = (code: string) =>
  me.isSuperuser || me.permissions.includes(code);

// نمونه
{can('grade.publish') && <PublishReportCardButton />}
{can('payment.create') && <NewPaymentButton />}
```

> فرانت **نباید** تصمیم امنیتی بگیرد؛ فقط UI را تمیز نگه می‌دارد. سرور در هر
> درخواست مجوز و Scope را دوباره بررسی می‌کند (جلوگیری از IDOR — بخش ۱۵.۱).

### ۴.۳ فهرست مجوزها برای صفحه «تعریف نقش»

```
GET /api/v1/iam/permissions/
```

پاسخ بدون صفحه‌بندی و شامل `module`، `resource`، `action`، `title` فارسی و
`isSensitive` است.

### ۴.۴ نقش‌های سیستمی

| کد | عنوان | Scope پیش‌فرض |
|---|---|---|
| `PRINCIPAL` | مدیر مدرسه | SCHOOL / CAMPUS |
| `ACADEMIC_VP` | معاون آموزشی | CAMPUS / ACADEMIC_YEAR |
| `REGISTRAR` | معاون اجرایی و ثبت‌نام | CAMPUS |
| `TEACHER` | معلم | COURSE_OFFERING / CLASS_GROUP |
| `ACCOUNTANT` | حسابدار | SCHOOL |
| `CASHIER` | صندوق‌دار | CAMPUS |
| `HR_MANAGER` | مسئول منابع انسانی | SCHOOL |
| `WAREHOUSE_KEEPER` | انباردار | CAMPUS |
| `PROCUREMENT` | مسئول تدارکات | SCHOOL |
| `COUNSELOR` | مشاور | CAMPUS |
| `HEALTH_OFFICER` | مربی بهداشت | CAMPUS |
| `LIBRARIAN` | کتابدار | CAMPUS |
| `TRANSPORT_MANAGER` | مسئول حمل‌ونقل | CAMPUS |
| `GUARDIAN` | ولی/سرپرست | SELF |
| `STUDENT` | دانش‌آموز | SELF |
| `AUDITOR` | ناظر/بازرس | SCHOOL |
| `SYS_ADMIN` | مدیر سامانه | TENANT |

---

## ۵. قراردادهای عمومی

### ۵.۱ صفحه‌بندی

**پیش‌فرض (شماره‌ای):**

```
GET /api/v1/students/students/?page=2&page_size=25
```

```json
{
  "count": 137,
  "pageCount": 6,
  "page": 2,
  "pageSize": 25,
  "next": "http://localhost:8000/api/v1/students/students/?page=3",
  "previous": "http://localhost:8000/api/v1/students/students/?page=1",
  "results": [ ... ]
}
```

**Cursor** (برای ممیزی، اعلان، حرکات موجودی، Outbox):

```
GET /api/v1/iam/audit-logs/?cursor=cD0yMDI2LTA4LTI2
```

```json
{
  "next": "...?cursor=cD0yMDI2LTA4LTI1",
  "previous": null,
  "pageSize": 50,
  "results": [ ... ]
}
```

حداکثر `page_size` برابر ۲۰۰ است.

### ۵.۲ فیلتر، جست‌وجو و مرتب‌سازی

```
GET /api/v1/students/students/
      ?academic_year=<uuid>
      &grade_level=<uuid>
      &class_group=<uuid>
      &status=ACTIVE
      &search=رضایی
      &ordering=-created_at
```

- `search` — جست‌وجوی متنی روی فیلدهای تعریف‌شده هر منبع
- `ordering` — با `-` برای نزولی
- فیلترهای اختصاصی هر منبع در Swagger زیر همان Endpoint فهرست شده‌اند

### ۵.۳ عملیات تغییر وضعیت

طبق بخش ۱۲.۴ سند تحلیل، تغییر وضعیت **هرگز** با `PATCH status` انجام نمی‌شود؛
هر گذار Endpoint صریح خودش را دارد:

```
POST /api/v1/students/enrollments/{id}/activate/
POST /api/v1/students/enrollments/{id}/withdraw/
POST /api/v1/finance/invoices/{id}/issue/
POST /api/v1/assessment/exams/{id}/publish/
POST /api/v1/gradebook/report-cards/{id}/publish/
```

فیلد `status` در بدنه PUT/PATCH فقط‌خواندنی است.

### ۵.۴ حذف

`DELETE` روی منابع عملیاتی **حذف نرم** است: رکورد از فهرست‌ها و جست‌وجوها خارج
می‌شود ولی با `deleted_at` در پایگاه داده می‌ماند و در ممیزی قابل ردیابی است.

```
DELETE /api/v1/students/enrollments/{id}/?reason=ثبت%20اشتباه
```

| نکته | توضیح |
|---|---|
| `reason` | پارامتر Query اختیاری؛ روی رکورد و در ممیزی ثبت می‌شود. حتماً بفرستید. |
| پاسخ موفق | `204` بدون بدنه |
| اسناد قطعی | سند مالی و انبار قطعی‌شده اصلاً حذف نمی‌شود؛ اصلاح فقط با **سند معکوس** |

---

## ۶. قالب خطا

همه خطاها — بدون استثنا — این ساختار را دارند (بخش ۱۲.۳ سند تحلیل):

```json
{
  "code": "CLASS_CAPACITY_EXCEEDED",
  "message": "ظرفیت کلاس تکمیل است.",
  "correlationId": "3a7f2b9c8d1e4f5a",
  "fieldErrors": [
    { "field": "classGroupId", "reason": "capacity" }
  ],
  "retryable": false
}
```

| فیلد | کاربرد در فرانت |
|---|---|
| `code` | **منطق روی این تصمیم بگیرد**، نه روی متن پیام |
| `message` | مستقیماً به کاربر نشان داده شود (فارسی و آماده) |
| `correlationId` | در گزارش خطا به پشتیبانی نمایش داده شود |
| `fieldErrors` | نگاشت به فیلدهای فرم برای نمایش خطای زیر هر ورودی |
| `retryable` | اگر `true` بود، دکمه «تلاش مجدد» نشان داده شود |

### ۶.۱ کدهای وضعیت HTTP

| کد | معنی | نمونه |
|---:|---|---|
| ۴۰۰ | داده ورودی نامعتبر | `VALIDATION_ERROR` |
| ۴۰۱ | نیازمند احراز هویت | `AUTHENTICATION_REQUIRED` |
| ۴۰۳ | بدون مجوز / خارج از Scope | `PERMISSION_DENIED`, `SCOPE_FORBIDDEN`, `SEGREGATION_OF_DUTIES` |
| ۴۰۴ | یافت نشد | `RESOURCE_NOT_FOUND` |
| ۴۰۹ | تعارض وضعیت یا نسخه | `INVALID_STATE_TRANSITION`, `VERSION_CONFLICT`, `PERIOD_CLOSED` |
| ۴۲۲ | نقض قاعده کسب‌وکار | `CLASS_CAPACITY_EXCEEDED`, `JOURNAL_NOT_BALANCED` |
| ۴۲۹ | عبور از حد نرخ | `RATE_LIMIT_EXCEEDED` (هدر `Retry-After`) |
| ۵۰۰ | خطای داخلی | `INTERNAL_ERROR` (بدون افشای جزئیات) |

### ۶.۲ کدهای معنایی پرکاربرد

| کد | ماژول | معنی |
|---|---|---|
| `INVALID_STATE_TRANSITION` | همه | گذار وضعیت در ماشین حالت مجاز نیست |
| `VERSION_CONFLICT` | همه | رکورد توسط کاربر دیگری تغییر کرده |
| `SEGREGATION_OF_DUTIES` | مالی، خرید، HR | ایجادکننده نمی‌تواند تأییدکننده باشد |
| `SCOPE_FORBIDDEN` | همه | رکورد خارج از دامنه دسترسی |
| `CLASS_CAPACITY_EXCEEDED` | ثبت‌نام | ظرفیت کلاس پر است |
| `ROOM_CAPACITY_EXCEEDED` | ثبت‌نام | ظرفیت فیزیکی اتاق کمتر است |
| `CLASS_YEAR_MISMATCH` | ثبت‌نام | کلاس متعلق به سال تحصیلی دیگری است |
| `CLASS_GRADE_MISMATCH` | ثبت‌نام | پایه کلاس با پایه ثبت‌نام یکی نیست |
| `SCHEDULE_CONFLICT` | برنامه | تداخل معلم/اتاق/کلاس |
| `ACADEMIC_YEAR_NOT_READY` | سال تحصیلی | پیش‌نیاز فعال‌سازی کامل نیست |
| `ACADEMIC_YEAR_CLOSED` | سال تحصیلی | سال بسته، فقط‌خواندنی |
| `ATTENDANCE_ALREADY_FINALIZED` | حضور | حضور نهایی شده و مجوز اصلاح ندارید |
| `AMENDMENT_REASON_REQUIRED` | حضور | اصلاح پس از نهایی‌سازی نیازمند علت است |
| `TEACHER_NOT_QUALIFIED` | HR | صلاحیت تدریس این درس ثبت نشده |
| `TEACHER_NO_ACTIVE_CONTRACT` | HR | معلم قرارداد فعال ندارد |
| `EXAM_NOT_READY_FOR_PUBLISH` | آزمون | بارم سؤالات با نمره کل نمی‌خواند |
| `ATTEMPT_TIME_EXPIRED` | آزمون | مهلت آزمون تمام شده |
| `ATTEMPT_LIMIT_REACHED` | آزمون | سقف تعداد تلاش پر شده |
| `APPEAL_WINDOW_CLOSED` | آزمون | پنجره اعتراض بسته است |
| `CATEGORY_WEIGHT_MISMATCH` | دفتر نمره | مجموع وزن دسته‌ها ۱۰۰٪ نیست |
| `GRADE_ITEM_LOCKED` | دفتر نمره | قلم نمره قفل است |
| `ALLOCATION_EXCEEDS_PAYMENT` | مالی | تخصیص از مبلغ دریافت بیشتر است |
| `ALLOCATION_EXCEEDS_INVOICE_BALANCE` | مالی | تخصیص از مانده صورتحساب بیشتر است |
| `JOURNAL_NOT_BALANCED` | حسابداری | سند متوازن نیست |
| `ACCOUNT_NOT_POSTABLE` | حسابداری | حساب گروه است، ثبت مستقیم ممنوع |
| `PERIOD_CLOSED` | حسابداری | دوره مالی بسته است |
| `INSUFFICIENT_STOCK` | انبار | موجودی قابل‌دسترس کافی نیست |
| `SERIAL_REQUIRED` / `LOT_REQUIRED` | انبار | کالای سریال‌دار/بچ‌دار نیازمند شناسه |
| `RECEIPT_EXCEEDS_ORDER` | خرید | دریافت بیش از باقیمانده سفارش |
| `ROUTE_CAPACITY_EXCEEDED` | سرویس | ظرفیت خودرو تکمیل است |
| `VEHICLE_DOCUMENTS_EXPIRED` | سرویس | معاینه فنی/بیمه معتبر نیست |
| `COPY_NOT_AVAILABLE` | کتابخانه | نسخه موجود نیست |

---

## ۷. Idempotency و کنترل هم‌زمانی

### ۷.۱ Idempotency

عملیات نوشتنی حساس هدر `Idempotency-Key` می‌پذیرند. ارسال مجدد با همان کلید،
**همان نتیجه** را برمی‌گرداند و رکورد دوم نمی‌سازد:

```
POST /api/v1/finance/payments/
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
```

مسیرهای پشتیبانی‌شده:

| مسیر | چرا مهم است |
|---|---|
| `POST /finance/payments/` | Callback تکراری درگاه، دریافت دوم نسازد |
| `POST /assessment/attempts/start/` | Refresh صفحه آزمون، تلاش دوم نسازد |

> فرانت باید یک UUID تولید کند و **تا موفقیت قطعی، همان را در Retry بفرستد**.

### ۷.۲ کنترل هم‌زمانی خوش‌بینانه

هر منبع فیلد `version` دارد. برای جلوگیری از Lost Update:

```
PATCH /api/v1/students/students/{id}/
If-Match: 3
```

اگر نسخه نخواند:

```json
{
  "code": "VERSION_CONFLICT",
  "message": "این رکورد توسط کاربر دیگری تغییر کرده است. نسخه ارسالی 3 و نسخه فعلی 5 است.",
  "correlationId": "...",
  "fieldErrors": [],
  "retryable": true
}
```

پاسخ‌ها هدر `ETag` هم دارند.

### ۷.۳ محدودیت نرخ

| Scope | حد |
|---|---|
| ورود و بازیابی رمز | ۱۰ در دقیقه / ۵ در ساعت |
| ذخیره پاسخ آزمون | ۱۲۰ در دقیقه |
| پرداخت | ۳۰ در دقیقه |
| خروجی‌گیری | ۱۰ در ساعت |

---

## ۸. کاتالوگ Enumها

**مهم‌ترین Endpoint برای فرانت.** همه فهرست‌های مقادیر مجاز با برچسب فارسی:

```
GET /api/v1/meta/enums/
```

```json
{
  "students.EnrollmentStatus": [
    { "value": "PENDING_DOCUMENTS", "label": "در انتظار مدارک" },
    { "value": "PENDING_FINANCE",   "label": "در انتظار تسویه مالی" },
    { "value": "PENDING_PLACEMENT", "label": "در انتظار تخصیص کلاس" },
    { "value": "ACTIVE",            "label": "فعال" },
    { "value": "SUSPENDED",         "label": "تعلیق" },
    { "value": "GRADUATED",         "label": "فارغ‌التحصیل" }
  ],
  "teaching.AttendanceStatus": [
    { "value": "PRESENT", "label": "حاضر" },
    { "value": "ABSENT",  "label": "غایب" },
    { "value": "LATE",    "label": "تأخیر" },
    { "value": "EXCUSED", "label": "غیبت موجه" }
  ]
}
```

**۱۳۵ Enum** در پاسخ هست. یک‌بار در بوت اپلیکیشن بگیرید و Cache کنید:

```ts
const enums = await api.get('/meta/enums/');
const label = (group: string, value: string) =>
  enums[group].find(i => i.value === value)?.label ?? value;
```

> علاوه بر این، اکثر منابع فیلد `*_display` هم دارند (مثلاً `status_display`)
> که برچسب فارسی همان رکورد را مستقیم برمی‌گرداند و نیاز به نگاشت دستی ندارد.

### نقشه ماژول‌ها

```
GET /api/v1/meta/modules/
```

فهرست ماژول‌ها، پیشوند مسیر و تعداد موجودیت‌های هر کدام.

---

## ۹. نقشه ماژول‌ها و منابع

| ماژول | پیشوند | موجودیت | نمونه منابع |
|---|---|---:|---|
| هویت و دسترسی | `/api/v1/iam/` | ۱۳ | `persons`, `users`, `roles`, `permissions`, `audit-logs` |
| ساختار آموزشی | `/api/v1/org/` | ۱۳ | `schools`, `campuses`, `academic-years`, `class-groups`, `schedule-entries` |
| امور دانش‌آموزان | `/api/v1/students/` | ۱۱ | `students`, `guardians`, `admissions`, `enrollments`, `consents` |
| منابع انسانی | `/api/v1/hr/` | ۱۴ | `employees`, `contracts`, `teachers`, `leaves`, `payroll-runs` |
| آموزش و حضور | `/api/v1/teaching/` | ۹ | `sessions`, `attendance`, `assignments`, `submissions` |
| آزمون | `/api/v1/assessment/` | ۱۶ | `question-banks`, `questions`, `exams`, `attempts`, `appeals` |
| دفتر نمره | `/api/v1/gradebook/` | ۷ | `gradebook`, `grade-items`, `scores`, `report-cards` |
| مالی و حسابداری | `/api/v1/finance/` | ۱۶ | `invoices`, `payments`, `refunds`, `journal-entries` |
| خرید و انبار | `/api/v1/inventory/` | ۱۷ | `items`, `balances`, `purchase-orders`, `assets` |
| خدمات دانش‌آموزی | `/api/v1/welfare/` | ۱۶ | `health-profiles`, `counseling-cases`, `library-loans`, `routes` |
| گردش کار | `/api/v1/workflow/` | ۱۲ | `approvals`, `notifications`, `tickets`, `my-tasks` |

---

## ۱۰. سناریوهای کامل

سناریوهای گام‌به‌گام با نمونه درخواست و پاسخ واقعی در فایل جداگانه آمده است:

**[سناریوهای کاربردی API](./API_RECIPES_FA.md)**

شامل:

1. ورود و راه‌اندازی Context
2. فهرست دانش‌آموزان و پرونده ۳۶۰ درجه
3. پذیرش تا ثبت‌نام و تخصیص کلاس
4. ثبت حضور و غیاب کلاس
5. ساخت آزمون و اجرای آنلاین
6. دفتر نمره و انتشار کارنامه
7. شهریه، صورتحساب، پرداخت و حسابداری دوبل
8. خرید تا رسید کالا و کاردکس
9. گردش تأیید و «کارهای من»

---

## ۱۱. تولید تایپ TypeScript

```bash
npx openapi-typescript backend/docs/openapi.yaml -o src/api/schema.d.ts
```

یا با کلاینت کامل:

```bash
npx @hey-api/openapi-ts -i backend/docs/openapi.yaml -o src/api
```

نام Enumها **پایدار و معنادار** است (`EnrollmentStatusEnum`، `AttendanceStatusEnum`،
`InvoiceStatusEnum` و …) نه هش‌های تصادفی؛ پس Regenerate کردن باعث تغییر
نام تایپ‌ها نمی‌شود.

---

## ۱۲. نکات پیاده‌سازی فرانت

### ۱۲.۱ تاریخ

- سرور تاریخ را **میلادی/ISO** و زمان را **UTC-aware** می‌فرستد.
- تبدیل به **تقویم جلالی** وظیفه لایه نمایش فرانت است (بخش ۱ سند تحلیل).
- تاریخ‌های ورودی هم باید ISO باشند: `"2026-09-01"` و `"2026-08-26T10:00:00+03:30"`.

### ۱۲.۲ مبالغ

همه مبالغ **عدد صحیح به ریال** هستند — هرگز اعشاری شناور نیستند:

```ts
const format = (rial: number) => rial.toLocaleString('fa-IR') + ' ریال';
// 69000000 → "۶۹٬۰۰۰٬۰۰۰ ریال"
```

برای نمایش تومان بر ۱۰ تقسیم کنید، اما **در ارسال به سرور همیشه ریال بفرستید**.

### ۱۲.۳ داده‌های مشتق‌شده

بسیاری از منابع فیلدهای محاسبه‌شده دارند تا فرانت درخواست اضافی نزند:

| منبع | فیلدهای آماده |
|---|---|
| `class-groups` | `occupied_seats`, `available_seats` |
| `invoices` | `balance` |
| `payments` | `allocated_amount`, `unallocated_amount` |
| `agreements` | `total_invoiced`, `total_paid`, `balance` |
| `sessions` | `attendance_summary` |
| `assignments` | `submission_stats` |
| `attempts` | `remaining_seconds` |
| `balances` (انبار) | `available_qty`, `below_reorder_point` |
| `assets` | `book_value`, `current_assignee` |
| `journal-entries` | `total_debit`, `total_credit`, `is_balanced` |

### ۱۲.۴ نماهای تجمیعی (یک درخواست، یک صفحه)

| Endpoint | صفحه فرانت |
|---|---|
| `GET /students/students/{id}/profile-360/` | پرونده ۳۶۰ درجه (بخش ۷.۲ سند فرانت) |
| `GET /org/class-groups/{id}/timetable/` | برنامه هفتگی کلاس (۸.۳) |
| `GET /teaching/sessions/{id}/roster/` | فرم ثبت حضور (۸.۴) |
| `GET /teaching/attendance/monitor/` | پایش حضور مدرسه (۸.۵) |
| `GET /gradebook/gradebook/?course_offering=` | دفتر نمره (۱۰.۱) |
| `GET /assessment/attempts/{id}/paper/` | پوسته آزمون دانش‌آموز (۹.۶) |
| `GET /assessment/attempts/grading-queue/` | صف تصحیح تشریحی (۹.۸) |
| `GET /finance/family-balance/?guardian=` | مانده خانواده (۱۲.۲) |
| `GET /finance/invoices/aging/` | گزارش سنی مطالبات (۱۲.۱) |
| `GET /finance/general-ledger/` | اسناد و دفتر کل (۱۲.۶) |
| `GET /inventory/items/{id}/kardex/` | کاردکس کالا (۱۳.۵) |
| `GET /welfare/route-runs/{id}/manifest/` | فهرست مسافران سرویس (۱۴.۵) |
| `GET /workflow/my-tasks/` | کارهای من (۶.۲) |
| `GET /reports/dashboard/` | داشبورد نقش‌محور (۶.۱) |
| `GET /auth/contexts/` | انتخاب مدرسه، شعبه و سال (۵.۲) |

### ۱۲.۵ گزارش‌های حسابداری

صفحه «اسناد و دفتر کل» (`/app/accounting/journals`) از این مسیرها تغذیه می‌شود:

| Endpoint | گزارش |
|---|---|
| `GET /finance/general-ledger/` | دفتر کل — ریز گردش هر حساب با مانده ابتدا و پایان |
| `GET /finance/trial-balance/` | تراز آزمایشی شش‌ستونی |
| `GET /finance/income-statement/` | صورت سود و زیان دوره |
| `GET /finance/balance-sheet/` | صورت وضعیت مالی در یک تاریخ |
| `GET /finance/daybook/` | دفتر روزنامه |
| `GET /finance/reports/cost-centers/` | درآمد و هزینه مراکز هزینه |
| `GET /finance/reports/` | کاتالوگ گزارش‌ها با مسیر و پارامتر هرکدام |
| `GET /finance/accounts/{id}/ledger/` | گردش یک حساب |

پارامترهای مشترک: `school`، `fiscal_year`، `date_from`، `date_to`
(و `as_of` برای صورت وضعیت مالی).

قواعد خواندن پاسخ:

- فقط سند **قطعی** (`POSTED`) در گزارش می‌آید؛ پیش‌نویس اثری ندارد.
- مبالغ عدد صحیح ریال‌اند. `balance` منفی یعنی مانده بستانکار؛ برای نمایش
  دو ستونی، `closingDebit` و `closingCredit` آماده‌اند.
- `totals.isBalanced` باید همیشه `true` باشد؛ `false` یعنی دفتر مشکل دارد و
  باید به کاربر هشدار داده شود.
- بدون `date_from`، مقدار `openingBalance` صفر است چون دوره‌ای تعریف نشده.
- `rowsTruncated` روی یک حساب یعنی ریز ردیف‌ها به `max_rows` بریده شده‌اند و
  باید بازه را باریک‌تر کرد.
- هر گزارش فقط مدارسی را می‌بیند که کاربر به آن‌ها دسترسی دارد؛ ارسال
  `school` خارج از دسترسی، نتیجه را تهی می‌کند، نه خطا.

### ۱۲.۶ داده حساس

طبق بخش ۱۵.۲ سند تحلیل، برخی فیلدها بسته به مجوز کاربر **خالی برمی‌گردند**،
نه اینکه خطا بدهند:

- `profile-360` → بخش‌های بدون مجوز `null` هستند
- `counseling-sessions.protected_note` → برای غیرمجاز رشته خالی
- `health-alerts/for-class/` → فقط `safeSummary`، بدون جزئیات پزشکی

فرانت باید این حالت را به‌عنوان «بدون دسترسی» رندر کند، نه «داده وجود ندارد».

### ۱۲.۷ اعتبارسنجی زنده

برای فرم برنامه هفتگی، پیش از ذخیره می‌توانید تداخل را بررسی کنید:

```
POST /api/v1/org/schedule-entries/check-conflicts/
```

بدنه همان قلم برنامه است؛ پاسخ فهرست تداخل‌ها بدون ذخیره چیزی.

---

## پیوست: ساختار پروژه

```
backend/
├── manage.py
├── requirements.txt
├── .env.example
├── config/                 تنظیمات، مسیرها، WSGI/ASGI
├── docs/
│   ├── openapi.yaml        قرارداد OpenAPI (YAML)
│   ├── openapi.json        قرارداد OpenAPI (JSON)
│   ├── API_GUIDE_FA.md     همین سند
│   └── API_RECIPES_FA.md   سناریوهای کامل
└── apps/
    ├── core/          زیرساخت: Tenant، خطا، صفحه‌بندی، مجوز، ViewSet پایه
    ├── identity/      شخص، کاربر، نقش، مجوز، ممیزی
    ├── organization/  مدرسه، شعبه، سال، پایه، درس، کلاس، برنامه
    ├── students/      پذیرش، دانش‌آموز، ولی، ثبت‌نام، رضایت‌نامه
    ├── hr/            پرسنل، قرارداد، تدریس، مرخصی، حقوق
    ├── teaching/      جلسه، حضور، تکلیف، منابع
    ├── assessment/    بانک سؤال، آزمون، تلاش، تصحیح، اعتراض
    ├── gradebook/     دسته ارزشیابی، نمره، نتیجه درس، کارنامه
    ├── finance/       تعرفه، صورتحساب، پرداخت، استرداد، حسابداری دوبل
    ├── inventory/     تأمین‌کننده، کالا، انبار، خرید، اموال
    ├── welfare/       سلامت، مشاوره، انضباط، کتابخانه، حمل‌ونقل
    └── workflow/      تأیید، اعلان، پیوست، Outbox، تیکت
```

هر اپ معادل یک **Bounded Context** در بخش ۶.۱ سند تحلیل است و ساختار یکسانی
دارد: `models.py`، `enums.py`، `serializers.py`، `services.py` (قواعد کسب‌وکار)،
`views.py`، `urls.py`، `admin.py`.
