# سناریوهای کاربردی API

> مکمل [راهنمای وب‌سرویس](./API_GUIDE_FA.md)
> همه نمونه‌ها **از اجرای واقعی سرویس** روی داده `seed_demo` گرفته شده‌اند.

در همه نمونه‌ها فرض بر این است که این هدرها ارسال می‌شوند:

```
Authorization: Bearer <access>
Content-Type: application/json
X-School-Id: <uuid>
X-Campus-Id: <uuid>
X-Academic-Year-Id: <uuid>
```

---

## فهرست سناریوها

| # | سناریو | ماژول |
|---:|---|---|
| ۱ | ورود و راه‌اندازی Context | Auth |
| ۲ | فهرست دانش‌آموزان و پرونده ۳۶۰ درجه | Students |
| ۳ | پذیرش → ثبت‌نام → تخصیص کلاس | Students |
| ۴ | برنامه هفتگی و کنترل تداخل | Organization |
| ۵ | ثبت حضور و غیاب کلاس | Teaching |
| ۶ | ساخت آزمون و اجرای آنلاین | Assessment |
| ۷ | دفتر نمره و انتشار کارنامه | Gradebook |
| ۸ | شهریه → صورتحساب → پرداخت → سند حسابداری | Finance |
| ۹ | درخواست خرید → سفارش → رسید → کاردکس | Inventory |
| ۱۰ | گردش تأیید و کارهای من | Workflow |

---

## ۱. ورود و راه‌اندازی Context

### گام ۱ — ورود

```http
POST /api/v1/auth/token/
```

```json
{ "username": "vp.academic", "password": "Demo!Pass2026" }
```

```json
{
  "access": "eyJhbGciOiJIUzI1NiJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiJ9...",
  "expiresIn": 1800,
  "mustChangePassword": false,
  "mfaRequired": false
}
```

### گام ۲ — پروفایل و محیط‌های کاری

```http
GET /api/v1/auth/me/
```

```json
{
  "username": "vp.academic",
  "displayName": "زهرا محمدی",
  "roles": ["ACADEMIC_VP"],
  "permissions": ["attendance.finalize", "class_group.create", "grade.publish", "..."],
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

### گام ۳ — گرفتن سال تحصیلی فعال

```http
GET /api/v1/org/academic-years/?is_default=true
```

```json
{
  "count": 1,
  "results": [
    {
      "id": "8f1fe8d2-afdc-418e-bdb1-6e3f84965fe9",
      "title": "۱۴۰۵–۱۴۰۶",
      "starts_on": "2026-06-27",
      "ends_on": "2027-04-23",
      "status": "ACTIVE",
      "status_display": "فعال",
      "is_default": true,
      "is_editable": true,
      "terms": [
        { "title": "نوبت اول", "sequence_no": 1, "status": "ACTIVE" },
        { "title": "نوبت دوم", "sequence_no": 2, "status": "PLANNED" }
      ]
    }
  ]
}
```

از این پس `X-Academic-Year-Id` را با این شناسه بفرستید.

---

## ۲. فهرست دانش‌آموزان و پرونده ۳۶۰ درجه

### فهرست با فیلتر

```http
GET /api/v1/students/students/?grade_level=<uuid>&status=ACTIVE&page_size=3
```

```json
{
  "count": 24,
  "pageCount": 8,
  "page": 1,
  "pageSize": 3,
  "next": "http://localhost:8000/api/v1/students/students/?page=2&page_size=3",
  "previous": null,
  "results": [
    {
      "id": "6b4c2900-2d05-4e1d-aa9b-e3c264e82734",
      "student_no": "1400001",
      "full_name": "محمد رضایی",
      "national_id": "1000000001",
      "gender": "MALE",
      "status": "ACTIVE",
      "status_display": "در حال تحصیل",
      "current_class": "701",
      "current_grade": "پایه هفتم",
      "joined_on": "2026-06-27"
    }
  ]
}
```

> `current_class` و `current_grade` از پیش محاسبه شده‌اند — نیازی به درخواست
> اضافی برای هر ردیف نیست.

### پرونده ۳۶۰ درجه — یک درخواست برای کل صفحه

```http
GET /api/v1/students/students/{id}/profile-360/
```

```json
{
  "student": {
    "student_no": "1400001",
    "full_name": "محمد رضایی",
    "status_display": "در حال تحصیل",
    "current_class": "701",
    "current_grade": "پایه هفتم"
  },
  "person": {
    "national_id": "1000000001",
    "first_name": "محمد",
    "last_name": "رضایی",
    "birth_date": "2013-02-02",
    "gender": "MALE",
    "contact_points": [],
    "addresses": []
  },
  "guardians": [
    {
      "guardian_name": "محمد رضایی",
      "relationship_display": "پدر",
      "guardian_mobile": "09120000001",
      "has_custody": true,
      "can_pickup": true,
      "receives_reports": true,
      "financially_responsible": true,
      "contact_priority": 1
    }
  ],
  "enrollments": [
    {
      "enrollment_no": "ENR-1405-00001",
      "academic_year_title": "۱۴۰۵–۱۴۰۶",
      "grade_level_title": "پایه هفتم",
      "status": "ACTIVE",
      "status_display": "فعال",
      "current_class_code": "701"
    }
  ],
  "consents": [],
  "attendanceSummary": {
    "totalSessions": 24,
    "byStatus": { "PRESENT": 22, "LATE": 1, "ABSENT": 1 },
    "presentPercent": 95.8
  },
  "financialSummary": {
    "totalInvoiced": 69000000,
    "totalPaid": 40000000,
    "balance": 29000000,
    "currency": "IRR"
  },
  "academicSummary": { "averageScore": null },
  "healthSummary": { "hasProfile": false, "activeAlerts": 0 }
}
```

> **کنترل دسترسی:** هر بخشی که کاربر مجوزش را ندارد `null` برمی‌گردد، نه خطا.
> مثلاً معلم بدون `invoice.read` مقدار `financialSummary` را `null` می‌بیند.
> فرانت باید آن Tab را «بدون دسترسی» رندر کند.

---

## ۳. پذیرش → ثبت‌نام → تخصیص کلاس

جریان کامل بخش ۹.۱ و ۹.۲ سند تحلیل.

### گام ۱ — ثبت درخواست پذیرش

```http
POST /api/v1/students/admissions/
```

```json
{
  "person": "<uuid شخص متقاضی>",
  "academic_year": "<uuid>",
  "preferred_campus": "<uuid>",
  "preferred_grade_level": "<uuid>",
  "application_no": "ADM-1405-0042"
}
```

### گام ۲ — گذارهای وضعیت (بخش ۱۰.۱)

```http
POST /api/v1/students/admissions/{id}/submit/
POST /api/v1/students/admissions/{id}/assign-reviewer/
POST /api/v1/students/admissions/{id}/accept/
```

بدنه `accept`:

```json
{ "reason": "پذیرش بر اساس نتیجه آزمون ورودی", "final_score": 18.5 }
```

اگر گذار مجاز نباشد:

```json
{
  "code": "INVALID_STATE_TRANSITION",
  "message": "در وضعیت «DRAFT» امکان اجرای «accept» روی درخواست پذیرش وجود ندارد.",
  "correlationId": "9ebe4c86",
  "fieldErrors": [],
  "retryable": false
}
```
**HTTP 409**

### گام ۳ — تبدیل به ثبت‌نام

```http
POST /api/v1/students/admissions/{id}/convert/
```

```json
{ "enrolled_on": "2026-06-27" }
```

پاسخ **۲۰۱** یک ثبت‌نام در وضعیت `PENDING_DOCUMENTS` است. پرونده دانش‌آموز و
شماره دانش‌آموزی خودکار ساخته می‌شوند.

### گام ۴ — پیشبرد ثبت‌نام (بخش ۱۰.۲)

```http
POST /api/v1/students/enrollments/{id}/approve-documents/   → PENDING_FINANCE
POST /api/v1/students/enrollments/{id}/confirm-finance/     → PENDING_PLACEMENT
```

### گام ۵ — تخصیص کلاس و فعال‌سازی

```http
POST /api/v1/students/enrollments/{id}/place-in-class/
```

```json
{ "class_group": "9f1e4154-25fb-4a43-9804-2afeae6a9b34" }
```

**موفق:** ثبت‌نام به `ACTIVE` می‌رود و عضویت کلاس ساخته می‌شود.

**خطای ظرفیت:**

```json
{
  "code": "CLASS_CAPACITY_EXCEEDED",
  "message": "ظرفیت کلاس تکمیل است.",
  "correlationId": "3a7f2b9c",
  "fieldErrors": [{ "field": "classGroupId", "reason": "capacity" }],
  "retryable": false
}
```
**HTTP 422**

**خطای ناسازگاری پایه:**

```json
{
  "code": "CLASS_GRADE_MISMATCH",
  "message": "پایه کلاس با پایه ثبت‌نام دانش‌آموز یکسان نیست.",
  "fieldErrors": [{ "field": "classGroupId", "reason": "grade_mismatch" }],
  "retryable": false
}
```

### گام ۶ — انتقال بین کلاس

```http
POST /api/v1/students/enrollments/{id}/transfer/
```

```json
{
  "target_class_group": "<uuid>",
  "reason": "درخواست ولی به دلیل تغییر شیفت",
  "effective_on": "2026-10-01"
}
```

عضویت قبلی بسته و سابقه انتقال ثبت می‌شود.

### گام ۷ — ترک تحصیل

```http
POST /api/v1/students/enrollments/{id}/withdraw/
```

```json
{ "reason": "انتقال به شهر دیگر", "exit_date": "2026-11-15" }
```

اگر `reason` نفرستید:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "داده ورودی معتبر نیست.",
  "fieldErrors": [{ "field": "reason", "reason": "این مقدار لازم است." }],
  "retryable": false
}
```

---

## ۴. برنامه هفتگی و کنترل تداخل

### مشاهده برنامه کلاس

```http
GET /api/v1/org/class-groups/{id}/timetable/
```

```json
{
  "classGroupId": "9f1e4154-25fb-4a43-9804-2afeae6a9b34",
  "classGroupCode": "701",
  "entries": [
    {
      "weekday": 0,
      "weekday_display": "شنبه",
      "starts_at": "08:00:00",
      "ends_at": "08:45:00",
      "course_title": "ریاضی",
      "room_code": "R101",
      "status": "PUBLISHED"
    },
    {
      "weekday": 0,
      "weekday_display": "شنبه",
      "starts_at": "08:55:00",
      "ends_at": "09:40:00",
      "course_title": "علوم تجربی",
      "room_code": "R101",
      "status": "PUBLISHED"
    }
  ]
}
```

> روز هفته از **شنبه = ۰** شروع می‌شود تا با تقویم ایران بخواند.

### بررسی تداخل پیش از ذخیره (اعتبارسنجی زنده فرم)

```http
POST /api/v1/org/schedule-entries/check-conflicts/
```

```json
{
  "course_offering": "<uuid>",
  "room": "<uuid>",
  "teacher_profile_id": "<uuid>",
  "weekday": 0,
  "starts_at": "08:00:00",
  "ends_at": "08:45:00",
  "effective_from": "2026-06-27"
}
```

```json
[
  {
    "type": "ROOM_CONFLICT",
    "message": "اتاق در این بازه به «701 / ریاضی» اختصاص دارد.",
    "conflictingEntryId": "..."
  },
  {
    "type": "TEACHER_CONFLICT",
    "message": "معلم در این بازه در «701 / ریاضی» کلاس دارد.",
    "conflictingEntryId": "..."
  }
]
```

آرایه خالی یعنی بدون تداخل. هنگام `POST` واقعی، اگر تداخل باشد خطای
`SCHEDULE_CONFLICT` با همین جزئیات در `fieldErrors` برمی‌گردد.

---

## ۵. ثبت حضور و غیاب

جریان بخش ۸.۴ سند فرانت و ۷.۵ سند تحلیل.

### گام ۱ — جلسات امروزِ معلم

```http
GET /api/v1/teaching/sessions/?date=2026-08-26&attendance_pending=true
```

### گام ۲ — گرفتن فهرست حضور

```http
GET /api/v1/teaching/sessions/{id}/roster/
```

```json
{
  "sessionId": "7e8bb324-7cac-4d3a-a45d-ceea8c21c9c1",
  "classGroupCode": "701",
  "courseTitle": "ادبیات فارسی",
  "startsAt": "2026-08-26T08:00:00+03:30",
  "finalizationStatus": "DRAFT",
  "rows": [
    {
      "enrollmentId": "3f1c8a2b-9d4e-4f7a-8b1c-2d3e4f5a6b7c",
      "studentNo": "1400001",
      "studentName": "محمد رضایی",
      "attendanceStatus": "PRESENT",
      "lateMinutes": 0,
      "earlyLeaveMinutes": 0,
      "reasonCode": "",
      "note": ""
    }
  ]
}
```

> **دو نکته مهم:**
> ۱. فقط دانش‌آموزانی برمی‌گردند که **در تاریخ آن جلسه** عضو فعال کلاس بوده‌اند.
> ۲. وضعیت پیش‌فرض `PRESENT` است تا معلم فقط استثناها را تغییر دهد.

### گام ۳ — ثبت گروهی + نهایی‌سازی

```http
POST /api/v1/teaching/sessions/{id}/attendance/
```

```json
{
  "rows": [
    { "enrollmentId": "3f1c8a2b-...", "attendanceStatus": "PRESENT" },
    { "enrollmentId": "4a2d9b3c-...", "attendanceStatus": "LATE", "lateMinutes": 12, "note": "تأخیر سرویس" },
    { "enrollmentId": "5b3e0c4d-...", "attendanceStatus": "ABSENT", "reasonCode": "UNKNOWN" }
  ],
  "finalize": true
}
```

```json
{ "success": true, "message": "حضور ثبت شد.", "affected": 24 }
```

پس از نهایی‌سازی، جلسه به `HELD` می‌رود و رویداد `AttendanceFinalized` منتشر
می‌شود:

```json
{
  "status_display": "برگزارشده",
  "attendance_finalized_at": "2026-08-26T13:14:58Z",
  "attendance_summary": { "PRESENT": 22, "LATE": 1, "ABSENT": 1 }
}
```

### گام ۴ — اصلاح پس از نهایی‌سازی

طبق بخش ۷.۵، اصلاح **هم مجوز می‌خواهد هم علت**. بدون علت:

```json
{
  "code": "AMENDMENT_REASON_REQUIRED",
  "message": "حضور این جلسه نهایی شده است؛ برای اصلاح، ثبت علت الزامی است.",
  "fieldErrors": [{ "field": "reason", "reason": "required" }],
  "retryable": false
}
```
**HTTP 409**

با علت:

```json
{
  "rows": [ ... ],
  "reason": "اصلاح پس از ارائه گواهی پزشکی توسط ولی"
}
```

```json
{ "success": true, "message": "حضور اصلاح شد.", "affected": 24 }
```

رکوردها به `finalization_status = AMENDED` می‌روند و تغییر در ممیزی ثبت می‌شود.

### گام ۵ — توجیه غیبت توسط ولی

```http
POST /api/v1/teaching/justifications/
```

```json
{ "attendance": "<uuid رکورد حضور>", "reason": "بیماری و مراجعه به پزشک" }
```

```http
POST /api/v1/teaching/justifications/{id}/approve/
```

با پذیرش، وضعیت حضور خودکار به `EXCUSED` تغییر می‌کند.

### گام ۶ — خلاصه حضور و هشدار نصاب

```http
GET /api/v1/teaching/attendance/student-summary/?enrollment=<uuid>
```

```json
{
  "enrollmentId": "...",
  "studentName": "محمد رضایی",
  "totalSessions": 120,
  "byStatus": { "PRESENT": 100, "LATE": 5, "ABSENT": 15 },
  "presentPercent": 87.5,
  "consecutiveAbsences": 3,
  "belowThreshold": false
}
```

### گام ۷ — پایش حضور مدرسه

```http
GET /api/v1/teaching/attendance/monitor/?date=2026-08-26
```

```json
[
  {
    "classGroupId": "...",
    "classGroupCode": "701",
    "gradeLevel": "پایه هفتم",
    "totalSessions": 6,
    "finalizedSessions": 4,
    "pendingSessions": 2,
    "absentToday": 3
  }
]
```

---

## ۶. آزمون: ساخت تا اجرای آنلاین

### گام ۱ — ساخت سؤال با گزینه‌ها (یک درخواست)

```http
POST /api/v1/assessment/questions/create-with-version/
```

```json
{
  "bank": "<uuid بانک سؤال>",
  "question_type": "SINGLE_CHOICE",
  "body": "پایتخت ایران کدام شهر است؟",
  "explanation": "تهران از سال ۱۱۶۵ خورشیدی پایتخت است.",
  "default_score": 1,
  "difficulty": "EASY",
  "options": [
    { "option_key": "A", "body": "اصفهان", "is_correct": false, "display_order": 1 },
    { "option_key": "B", "body": "تهران",  "is_correct": true,  "display_order": 2 },
    { "option_key": "C", "body": "شیراز",  "is_correct": false, "display_order": 3 },
    { "option_key": "D", "body": "تبریز",  "is_correct": false, "display_order": 4 }
  ]
}
```

سؤال عددی با تلورانس:

```json
{
  "bank": "<uuid>",
  "question_type": "NUMERIC",
  "body": "مقدار تقریبی عدد پی را تا دو رقم اعشار بنویسید.",
  "default_score": 2,
  "correct_answer": { "value": 3.14, "tolerance": 0.01 }
}
```

### گام ۲ — ساخت آزمون، بخش و سؤال

```http
POST /api/v1/assessment/exams/
POST /api/v1/assessment/exam-sections/
POST /api/v1/assessment/exam-questions/
```

### گام ۳ — جلسه آزمون و ثبت‌نام گروهی

```http
POST /api/v1/assessment/exam-sessions/
```

```json
{
  "exam": "<uuid>",
  "opens_at": "2026-09-10T08:00:00+03:30",
  "closes_at": "2026-09-10T10:00:00+03:30",
  "duration_minutes": 60,
  "attempt_limit": 1
}
```

```http
POST /api/v1/assessment/exam-sessions/{id}/enroll-class/
```

همه اعضای فعال کلاس ثبت‌نام می‌شوند.

### گام ۴ — انتشار آزمون

```http
POST /api/v1/assessment/exams/{id}/publish/
```

اگر بارم نخواند:

```json
{
  "code": "EXAM_NOT_READY_FOR_PUBLISH",
  "message": "آزمون برای انتشار آماده نیست.",
  "fieldErrors": [
    { "field": "maxScore", "reason": "مجموع بارم سؤالات (18.00) با نمره کل آزمون (20.00) برابر نیست." }
  ],
  "retryable": false
}
```
**HTTP 422**

### گام ۵ — شروع تلاش (Idempotent)

```http
POST /api/v1/assessment/attempts/start/
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
```

```json
{ "registration": "<uuid>" }
```

```json
{
  "id": "...",
  "attempt_no": 1,
  "started_at": "2026-09-10T08:03:00Z",
  "expires_at": "2026-09-10T09:03:00Z",
  "remaining_seconds": 3600,
  "status": "IN_PROGRESS",
  "status_display": "در حال پاسخ‌دهی"
}
```

> اگر تلاشی در وضعیت `IN_PROGRESS` یا `INTERRUPTED` باشد، **همان ادامه پیدا
> می‌کند** — سناریوی بازیابی پس از قطع اتصال (بخش ۹.۷ سند فرانت).

### گام ۶ — گرفتن برگه آزمون

```http
GET /api/v1/assessment/attempts/{id}/paper/
```

```json
{
  "attemptId": "...",
  "examTitle": "آزمون میان‌ترم ریاضی",
  "instructions": "به همه سؤالات پاسخ دهید.",
  "maxScore": 20,
  "allowBacktrack": true,
  "expiresAt": "2026-09-10T09:03:00Z",
  "remainingSeconds": 3540,
  "questions": [
    {
      "examQuestionId": "...",
      "sectionTitle": "بخش اول",
      "questionType": "SINGLE_CHOICE",
      "body": "پایتخت ایران کدام شهر است؟",
      "score": 1,
      "displayOrder": 1,
      "isRequired": true,
      "options": [
        { "id": "...", "option_key": "A", "body": "اصفهان", "display_order": 1 },
        { "id": "...", "option_key": "B", "body": "تهران",  "display_order": 2 }
      ],
      "savedAnswer": null
    }
  ]
}
```

> **کلید پاسخ هرگز در این پاسخ نمی‌آید.** `is_correct` از گزینه‌ها حذف شده است.

### گام ۷ — ذخیره خودکار پاسخ

```http
POST /api/v1/assessment/attempts/{id}/answers/
```

قالب `response_payload` بر اساس نوع سؤال:

| نوع سؤال | قالب |
|---|---|
| چندگزینه‌ای | `{"selectedKeys": ["B"]}` |
| چندپاسخی | `{"selectedKeys": ["A", "C"]}` |
| عددی | `{"value": 3.14}` |
| کوتاه‌پاسخ / تشریحی | `{"text": "..."}` |
| تطبیقی | `{"pairs": {"1": "ب", "2": "الف"}}` |
| ترتیبی | `{"order": ["c", "a", "b"]}` |

```json
{
  "exam_question": "9d8c7b6a-...",
  "response_payload": { "selectedKeys": ["B"] },
  "time_spent_seconds": 34
}
```

پس از پایان مهلت:

```json
{
  "code": "ATTEMPT_TIME_EXPIRED",
  "message": "زمان آزمون شما به پایان رسیده است.",
  "retryable": false
}
```
**HTTP 409**

### گام ۸ — تحویل نهایی

```http
POST /api/v1/assessment/attempts/{id}/submit/
```

عملیات **اتمیک و تکرارپذیر** است: ارسال مجدد همان نتیجه را برمی‌گرداند و خطا
نمی‌دهد. تصحیح خودکار بلافاصله اجرا می‌شود:

```json
{
  "status": "GRADED",
  "auto_score": 14.00,
  "manual_score": 0.00,
  "final_score": 14.00
}
```

### گام ۹ — صف تصحیح تشریحی

```http
GET /api/v1/assessment/attempts/grading-queue/?exam=<uuid>&anonymous=true
```

```json
[
  {
    "attemptAnswerId": "...",
    "attemptId": "...",
    "examTitle": "آزمون میان‌ترم ریاضی",
    "questionBody": "روش حل معادله درجه دو را توضیح دهید.",
    "responseText": "با استفاده از فرمول دلتا …",
    "maxScore": 5,
    "gradingRubric": "۲ نمره فرمول، ۲ نمره محاسبه، ۱ نمره نتیجه",
    "studentLabel": "داوطلب 3f1c8a2b"
  }
]
```

> با `anonymous=true` نام دانش‌آموز با شناسه مستعار جایگزین می‌شود
> (ناشناس‌سازی مصحح — بخش ۴.۴).

### گام ۱۰ — ثبت نمره دستی

```http
POST /api/v1/assessment/attempt-answers/{id}/grade/
```

```json
{ "score": 4.5, "feedback": "روش درست، محاسبه ناقص", "review_type": "FIRST_PASS" }
```

نمره تلاش خودکار بازمحاسبه و `calculation_version` یک واحد جلو می‌رود.

### گام ۱۱ — انتشار نتایج و اعتراض

```http
POST /api/v1/assessment/exams/{id}/release-results/
```

پنجره اعتراض (پیش‌فرض ۷ روز) باز می‌شود و رویداد `ScoreFinalized` منتشر می‌گردد.

```http
POST /api/v1/assessment/appeals/
POST /api/v1/assessment/appeals/{id}/resolve/
```

```json
{ "accepted": true, "resolution": "بازتصحیح انجام شد و نمره اصلاح گردید." }
```

### گام ۱۲ — تحلیل سؤالات

```http
GET /api/v1/assessment/exams/{id}/analysis/
```

```json
[
  {
    "examQuestionId": "...",
    "sectionTitle": "بخش اول",
    "questionBody": "پایتخت ایران کدام شهر است؟",
    "questionType": "SINGLE_CHOICE",
    "maxScore": 1.0,
    "responseCount": 24,
    "correctPercent": 91.7,
    "averageScore": 0.92,
    "averageTimeSeconds": 28
  }
]
```

---

## ۷. دفتر نمره و کارنامه

### گام ۱ — تعریف دسته‌های ارزشیابی

```http
POST /api/v1/gradebook/categories/
```

```json
{ "course_offering": "<uuid>", "title": "مستمر", "weight_percent": 40, "display_order": 1 }
```

```json
{ "course_offering": "<uuid>", "title": "پایانی", "weight_percent": 60, "display_order": 2 }
```

اعتبارسنجی مجموع وزن:

```http
GET /api/v1/gradebook/categories/validate-weights/?course_offering=<uuid>
```

```json
{
  "code": "CATEGORY_WEIGHT_MISMATCH",
  "message": "مجموع وزن دسته‌های ارزشیابی 90٪ است و باید دقیقاً ۱۰۰٪ باشد.",
  "fieldErrors": [{ "field": "weightPercent", "reason": "sum_not_100" }],
  "retryable": false
}
```

### گام ۲ — نمای کامل دفتر نمره

```http
GET /api/v1/gradebook/gradebook/?course_offering=<uuid>
```

```json
{
  "courseOfferingId": "...",
  "courseTitle": "ریاضی",
  "classGroupCode": "701",
  "termTitle": "نوبت اول",
  "weightsValid": true,
  "categories": [
    { "id": "...", "title": "مستمر", "weight_percent": "40.00", "item_count": 3 },
    { "id": "...", "title": "پایانی", "weight_percent": "60.00", "item_count": 1 }
  ],
  "columns": [
    {
      "gradeItemId": "...",
      "title": "آزمون فصل ۱",
      "categoryId": "...",
      "categoryTitle": "مستمر",
      "maxScore": "20.00",
      "weight": "1.00",
      "status": "OPEN",
      "isLocked": false
    }
  ],
  "rows": [
    {
      "enrollmentId": "...",
      "studentNo": "1400001",
      "studentName": "محمد رضایی",
      "scores": {
        "<gradeItemId>": { "rawScore": 18.5, "status": "RECORDED", "comment": "" }
      },
      "finalScore": 17.8
    }
  ]
}
```

> ساختار `columns` + `rows` مستقیماً برای رندر جدول دفتر نمره طراحی شده است.
> اگر `weightsValid = false` بود، فرانت باید هشدار بدهد و اجازه نهایی‌سازی ندهد.

### گام ۳ — ثبت گروهی نمرات

```http
POST /api/v1/gradebook/grade-items/{id}/scores/
```

```json
{
  "rows": [
    { "enrollment": "11111111-...", "raw_score": 18.5, "status": "RECORDED" },
    { "enrollment": "22222222-...", "status": "ABSENT" },
    { "enrollment": "33333333-...", "raw_score": 0, "status": "RECORDED", "comment": "پاسخ‌برگ سفید" }
  ]
}
```

> **چهار حالت متفاوت** (بخش ۷.۷): `ABSENT` (غایب)، `EXEMPT` (معاف)،
> `NOT_RECORDED` (ثبت‌نشده) و `RECORDED` با نمره صفر — اینها **یکی نیستند** و
> در معدل رفتار متفاوتی دارند. هرگز غیبت را با نمره صفر ثبت نکنید.

### گام ۴ — قفل و بازگشایی

```http
POST /api/v1/gradebook/grade-items/{id}/lock/
POST /api/v1/gradebook/grade-items/{id}/unlock/
```

بازگشایی نیازمند علت است:

```json
{ "reason": "اصلاح خطای ورود نمره پس از بازبینی برگه" }
```

### گام ۵ — محاسبه نتیجه درس

```http
POST /api/v1/gradebook/course-results/calculate/
```

```json
{ "course_offering": "<uuid>" }
```

```json
{ "success": true, "message": "محاسبه انجام شد.", "affected": 24 }
```

هر نتیجه `calculation_inputs` (Snapshot ورودی‌های محاسبه) و
`calculation_version` دارد — بخش ۱۱.۵.

### گام ۶ — تولید و انتشار کارنامه

```http
POST /api/v1/gradebook/report-cards/bulk-generate/
```

```json
{ "class_group": "<uuid>", "term": "<uuid>" }
```

```http
POST /api/v1/gradebook/report-cards/{id}/publish/
```

```json
{
  "version_no": 2,
  "status": "PUBLISHED",
  "status_display": "منتشرشده",
  "average_score": 17.42,
  "verification_code": "A3F91B2C7D4E5601",
  "attendance_summary": {
    "totalSessions": 120,
    "byStatus": { "PRESENT": 112, "ABSENT": 8 },
    "presentPercent": 93.3
  },
  "items": [
    { "course_title": "ریاضی", "displayed_score": 18.0, "credit": "4.00" }
  ]
}
```

> **نسخه‌بندی:** انتشار مجدد نسخه جدید می‌سازد و نسخه قبلی به `SUPERSEDED`
> می‌رود و حذف نمی‌شود (بخش ۷.۷). `verification_code` برای اعتبارسنجی کارنامه
> چاپی است.

---

## ۸. مالی: شهریه تا سند حسابداری

**این سناریو کامل روی سرویس اجرا و خروجی‌ها واقعی است.**

### گام ۱ — مشاهده تعرفه

```http
GET /api/v1/finance/fee-plans/
```

```json
{
  "results": [
    {
      "title": "تعرفه پایه هفتم — ۱۴۰۵",
      "currency": "IRR",
      "total_amount": 207000000,
      "items": [
        { "fee_type": "REGISTRATION", "title": "هزینه ثبت‌نام", "amount": 15000000 },
        { "fee_type": "TUITION",      "title": "شهریه سالانه",  "amount": 180000000 },
        { "fee_type": "BOOK",         "title": "کتاب و لوازم",  "amount": 12000000 }
      ]
    }
  ]
}
```

### گام ۲ — ایجاد قرارداد مالی

```http
POST /api/v1/finance/agreements/
```

```json
{
  "enrollment": "<uuid>",
  "fee_plan": "<uuid>",
  "responsible_guardian": "<uuid>",
  "installment_count": 3,
  "status": "ACTIVE"
}
```

```json
{
  "id": "c31da428-cf01-4b3c-ae3b-95b010af8e64",
  "agreed_amount": 207000000,
  "total_invoiced": 0,
  "total_paid": 0,
  "balance": 0
}
```

### گام ۳ — تولید اقساط

```http
POST /api/v1/finance/agreements/{id}/generate-installments/
```

```json
{ "first_due_date": "2026-09-01", "interval_days": 30 }
```

```json
[
  { "invoice_no": "INV-202608-000001", "installment_no": 1, "due_date": "2026-09-01", "total_amount": 69000000, "status": "DRAFT" },
  { "invoice_no": "INV-202608-000002", "installment_no": 2, "due_date": "2026-10-01", "total_amount": 69000000, "status": "DRAFT" },
  { "invoice_no": "INV-202608-000003", "installment_no": 3, "due_date": "2026-10-31", "total_amount": 69000000, "status": "DRAFT" }
]
```

> باقیمانده تقسیم به **قسط آخر** اضافه می‌شود تا جمع اقساط دقیقاً برابر مبلغ
> توافق‌شده بماند (بدون خطای گِرد کردن).

### گام ۴ — صدور صورتحساب

```http
POST /api/v1/finance/invoices/{id}/issue/
```

```json
{
  "invoice_no": "INV-202608-000001",
  "status": "ISSUED",
  "status_display": "صادرشده",
  "total_amount": 69000000,
  "paid_amount": 0,
  "balance": 69000000
}
```

سند تعهدی خودکار ثبت می‌شود و رویداد `InvoiceIssued` منتشر می‌گردد.

### گام ۵ — ثبت دریافت (Idempotent)

```http
POST /api/v1/finance/payments/
Idempotency-Key: demo-key-0001
```

```json
{
  "payer_person": "<uuid ولی>",
  "method": "ONLINE_GATEWAY",
  "amount": 40000000,
  "currency": "IRR",
  "received_at": "2026-08-26T10:00:00+03:30",
  "gateway_reference": "GW-778812"
}
```

> ارسال مجدد با همان `Idempotency-Key` **همان رکورد** را برمی‌گرداند —
> Callback تکراری درگاه دریافت دوم نمی‌سازد.

### گام ۶ — قطعی‌کردن دریافت

```http
POST /api/v1/finance/payments/{id}/post/
```

```json
{
  "payment_no": "PAY-202608-000001",
  "status": "SUCCEEDED",
  "status_display": "موفق",
  "amount": 40000000,
  "allocated_amount": 0,
  "unallocated_amount": 40000000
}
```

### گام ۷ — تخصیص به صورتحساب

```http
POST /api/v1/finance/payments/{id}/allocate/
```

```json
{ "allocations": [ { "invoice": "<uuid>", "amount": 40000000 } ] }
```

**خطای تجاوز از مبلغ:**

```json
{
  "code": "ALLOCATION_EXCEEDS_PAYMENT",
  "message": "مجموع تخصیص (90,000,000) از مبلغ تخصیص‌نیافته (40,000,000) بیشتر است.",
  "correlationId": "18e3742d",
  "fieldErrors": [{ "field": "allocations", "reason": "exceeds_payment" }],
  "retryable": false
}
```
**HTTP 422**

**موفق — وضعیت صورتحساب خودکار به‌روز می‌شود:**

```json
{
  "invoice_no": "INV-202608-000001",
  "status": "PARTIALLY_PAID",
  "status_display": "پرداخت جزئی",
  "total_amount": 69000000,
  "paid_amount": 40000000,
  "balance": 29000000
}
```

### گام ۸ — دفتر روزنامه (حسابداری دوبل خودکار)

```http
GET /api/v1/finance/journal-entries/
```

سه سند متوازن به‌صورت خودکار ساخته شده‌اند:

```
JV-202608-000001  [قطعی]  صدور صورتحساب INV-202608-000001
    1131 حساب دریافتنی دانش‌آموزان   بدهکار   69,000,000
    4101 درآمد شهریه                 بستانکار 69,000,000
    ⇒ متوازن: true

JV-202608-000002  [قطعی]  دریافت PAY-202608-000001
    1102 بانک                        بدهکار   40,000,000
    2131 پیش‌دریافت شهریه            بستانکار 40,000,000
    ⇒ متوازن: true

JV-202608-000003  [قطعی]  تخصیص دریافت PAY-202608-000001 به صورتحساب INV-202608-000001
    2131 پیش‌دریافت شهریه            بدهکار   40,000,000
    1131 حساب دریافتنی دانش‌آموزان   بستانکار 40,000,000
    ⇒ متوازن: true
```

> **منطق حسابداری (بخش ۷.۸):** وجه دریافتی تا پیش از تخصیص «پیش‌دریافت»
> (بدهی) است و پس از تخصیص به حساب دریافتنی منتقل می‌شود. مانده حساب دریافتنی
> = ۶۹ − ۴۰ = **۲۹ میلیون** که دقیقاً با مانده صورتحساب می‌خواند.

### گام ۹ — سند دستی

```http
POST /api/v1/finance/journal-entries/create-entry/
```

```json
{
  "fiscal_year": "<uuid>",
  "entry_date": "2026-08-26",
  "description": "بابت هزینه نوشت‌افزار اداری",
  "lines": [
    { "account": "<uuid 6101>", "debit": 12000000, "credit": 0, "description": "هزینه اداری" },
    { "account": "<uuid 1101>", "debit": 0, "credit": 12000000, "description": "پرداخت از صندوق" }
  ],
  "post_immediately": true
}
```

**خطای عدم توازن:**

```json
{
  "code": "JOURNAL_NOT_BALANCED",
  "message": "سند متوازن نیست: جمع بدهکار 12,000,000 و جمع بستانکار 10,000,000 است.",
  "fieldErrors": [{ "field": "lines", "reason": "not_balanced" }],
  "retryable": false
}
```

**خطای حساب گروه:**

```json
{
  "code": "ACCOUNT_NOT_POSTABLE",
  "message": "حساب «11 — دارایی‌های جاری» گروه است و ثبت مستقیم روی آن مجاز نیست.",
  "fieldErrors": [{ "field": "lines[1].account", "reason": "group_account" }]
}
```

### گام ۱۰ — برگشت سند

سند قطعی **هرگز ویرایش یا حذف نمی‌شود**؛ فقط سند معکوس ساخته می‌شود:

```http
POST /api/v1/finance/journal-entries/{id}/reverse/
```

```json
{ "reason": "ثبت اشتباه مرکز هزینه" }
```

### گام ۱۱ — استرداد با تفکیک وظایف

```http
POST /api/v1/finance/refunds/
POST /api/v1/finance/refunds/{id}/approve/
```

اگر تأییدکننده همان درخواست‌دهنده باشد:

```json
{
  "code": "SEGREGATION_OF_DUTIES",
  "message": "درخواست‌دهنده استرداد نمی‌تواند تأییدکننده همان استرداد باشد.",
  "retryable": false
}
```
**HTTP 403**

### گام ۱۲ — نماهای گزارشی

```http
GET /api/v1/finance/family-balance/?guardian=<uuid>
```

```json
{
  "guardianId": "...",
  "guardianName": "محمد رضایی",
  "currency": "IRR",
  "totalInvoiced": 69000000,
  "totalPaid": 40000000,
  "totalBalance": 29000000,
  "unallocatedCredit": 0,
  "students": [
    { "studentNo": "1400001", "studentName": "محمد رضایی", "agreedAmount": 207000000, "balance": 29000000 }
  ]
}
```

```http
GET /api/v1/finance/invoices/aging/
GET /api/v1/finance/accounts/{id}/ledger/?date_from=2026-06-01&date_to=2026-08-31
```

---

## ۹. خرید تا رسید کالا

### گام ۱ — درخواست خرید

```http
POST /api/v1/inventory/purchase-requests/
POST /api/v1/inventory/purchase-request-lines/
POST /api/v1/inventory/purchase-requests/{id}/submit/
```

هر قلم درخواست، **موجودی فعلی** را هم برمی‌گرداند تا کاربر ببیند واقعاً نیاز
به خرید هست یا نه (بخش ۱۳.۲ سند فرانت):

```json
{ "item_title": "کاغذ A4", "quantity": "100.000", "available_stock": 12.0 }
```

### گام ۲ — تأیید (با تفکیک وظایف)

```http
POST /api/v1/inventory/purchase-requests/{id}/approve/
```

درخواست‌دهنده نمی‌تواند تأییدکننده باشد → `SEGREGATION_OF_DUTIES` / HTTP 403.

### گام ۳ — سفارش خرید

```http
POST /api/v1/inventory/purchase-orders/
POST /api/v1/inventory/purchase-order-lines/
POST /api/v1/inventory/purchase-orders/{id}/issue/
```

### گام ۴ — رسید کالا

```http
POST /api/v1/inventory/purchase-orders/{id}/receive/
```

```json
{
  "warehouse": "<uuid>",
  "vendor_invoice_no": "F-140501-882",
  "vendor_invoice_amount": 48000000,
  "lines": [
    { "order_line": "<uuid>", "quantity": 100, "unit_cost": 480000 }
  ]
}
```

سند انبار ساخته و قطعی می‌شود، موجودی به‌روز می‌گردد و رویداد `GoodsReceived`
منتشر می‌شود.

**خطای دریافت بیش از سفارش:**

```json
{
  "code": "RECEIPT_EXCEEDS_ORDER",
  "message": "مقدار دریافتی (150) از باقیمانده سفارش برای «کاغذ A4» (100) بیشتر است.",
  "fieldErrors": [{ "field": "lines[1].quantity", "reason": "exceeds_order" }]
}
```

### گام ۵ — تطبیق سه‌طرفه

```http
POST /api/v1/inventory/goods-receipts/{id}/three-way-match/?tolerance_percent=2
```

```json
{
  "orderNo": "PO-202608-00001",
  "receiptNo": "GR-202608-00001",
  "orderAmount": 48000000,
  "receivedValue": 48000000,
  "invoiceAmount": 48000000,
  "difference": 0,
  "tolerance": 960000,
  "matched": true
}
```

### گام ۶ — حواله مصرف

```http
POST /api/v1/inventory/stock-documents/
POST /api/v1/inventory/stock-document-lines/
POST /api/v1/inventory/stock-documents/{id}/confirm/
```

**خطای کمبود موجودی:**

```json
{
  "code": "INSUFFICIENT_STOCK",
  "message": "موجودی قابل‌دسترس «کاغذ A4» در انبار W01 برابر 12 است و کمتر از 50 درخواستی است.",
  "fieldErrors": [{ "field": "quantity", "reason": "insufficient_stock" }],
  "retryable": false
}
```

کالای سریال‌دار/بچ‌دار → `SERIAL_REQUIRED` / `LOT_REQUIRED`.

### گام ۷ — کاردکس کالا

```http
GET /api/v1/inventory/items/{id}/kardex/?warehouse=<uuid>
```

```json
{
  "itemId": "...",
  "sku": "PPR-A4",
  "title": "کاغذ A4",
  "closingBalance": 62.0,
  "rows": [
    {
      "occurredAt": "2026-08-26T10:00:00Z",
      "documentNo": "STK-202608-00001",
      "documentType": "RECEIPT",
      "warehouse": "W01",
      "quantity": 100.0,
      "unitCost": 480000,
      "balance": 112.0
    },
    {
      "occurredAt": "2026-08-27T09:00:00Z",
      "documentNo": "STK-202608-00002",
      "documentType": "ISSUE",
      "warehouse": "W01",
      "quantity": -50.0,
      "unitCost": 0,
      "balance": 62.0
    }
  ]
}
```

### گام ۸ — اموال

```http
POST /api/v1/inventory/assets/{id}/accept/     → IN_STOCK
POST /api/v1/inventory/assets/{id}/assign/     → ASSIGNED
POST /api/v1/inventory/assets/{id}/return/     → IN_STOCK
POST /api/v1/inventory/assets/{id}/retire/     → RETIRED
```

بدنه `assign`:

```json
{
  "assignee_type": "EMPLOYEE",
  "assignee_id": "<uuid>",
  "location_room": "<uuid>",
  "condition_on_assign": "GOOD"
}
```

---

## ۱۰. گردش تأیید و کارهای من

### تعریف گردش

```http
POST /api/v1/workflow/workflow-definitions/
```

```json
{
  "code": "REFUND_APPROVAL",
  "title": "تأیید استرداد شهریه",
  "subject_type": "finance.Refund",
  "steps_definition": [
    { "sequence": 1, "roleCode": "ACCOUNTANT" },
    { "sequence": 2, "roleCode": "PRINCIPAL" }
  ]
}
```

### شروع گردش

```http
POST /api/v1/workflow/approvals/start/
```

```json
{
  "subject_type": "finance.Refund",
  "subject_id": "<uuid>",
  "workflow_code": "REFUND_APPROVAL",
  "subject_label": "استرداد REF-202608-000001"
}
```

نسخه تعریف گردش **Snapshot** می‌شود؛ تغییر بعدی تنظیمات، درخواست در جریان را
تغییر نمی‌دهد (بخش ۷.۱۱).

### تصمیم گام

```http
POST /api/v1/workflow/approval-steps/{id}/decide/
```

```json
{ "decision": "APPROVED", "comment": "مدارک کامل است." }
```

گام‌ها **به ترتیب** تصمیم‌گیری می‌شوند؛ در غیر این صورت:

```json
{ "code": "PREVIOUS_STEP_PENDING", "message": "گام‌های قبلی این گردش هنوز تصمیم‌گیری نشده‌اند." }
```

### کارهای من (Inbox یکپارچه)

```http
GET /api/v1/workflow/my-tasks/
```

```json
[
  {
    "type": "APPROVAL",
    "id": "...",
    "title": "تأیید: استرداد REF-202608-000001",
    "subtitle": "finance.Refund",
    "dueAt": null,
    "priority": "NORMAL",
    "link": "/app/tasks/approvals/..."
  },
  {
    "type": "ATTENDANCE_PENDING",
    "id": "...",
    "title": "ثبت حضور: 701 — ریاضی",
    "subtitle": "2026-08-26 08:00",
    "dueAt": "2026-08-26T08:45:00Z",
    "priority": "HIGH",
    "link": "/app/attendance/..."
  }
]
```

سه نوع کار در یک فهرست: `APPROVAL`، `TICKET`، `ATTENDANCE_PENDING`. فیلد `link`
مسیر پیشنهادی فرانت است.

### ارسال گروهی اعلان (دو مرحله‌ای)

**مرحله ۱ — پیش‌نمایش:**

```http
POST /api/v1/workflow/notifications/broadcast/
```

```json
{
  "audience": "CLASS_GUARDIANS",
  "target_id": "<uuid کلاس>",
  "channel": "SMS",
  "body": "جلسه اولیا و مربیان روز چهارشنبه ساعت ۱۶ برگزار می‌شود.",
  "confirm": false
}
```

```json
{
  "recipientCount": 24,
  "sampleMessage": "جلسه اولیا و مربیان روز چهارشنبه ساعت ۱۶ برگزار می‌شود.",
  "channel": "SMS",
  "sent": false
}
```

**مرحله ۲ — ارسال:** همان بدنه با `"confirm": true`.

> طبق بخش ۱۱.۴، ارسال انبوه باید پیش‌نمایش تعداد گیرندگان و تأیید داشته باشد.
> گیرندگان از **رابطه فعال ولی با مجوز دریافت گزارش** استخراج می‌شوند، نه از
> یک شماره تلفن ثابت روی پرونده.

### رویدادهای دامنه‌ای (Outbox)

```http
GET /api/v1/workflow/outbox-events/
```

```json
{
  "results": [
    { "event_type": "PaymentPosted",  "aggregate_type": "finance.Payment", "occurred_at": "2026-08-26T13:14:58Z" },
    { "event_type": "InvoiceIssued",  "aggregate_type": "finance.Invoice", "occurred_at": "2026-08-26T13:14:58Z" }
  ]
}
```

رویدادهای پیاده‌سازی‌شده: `AttendanceFinalized`، `ExamSubmitted`،
`ScoreFinalized`، `ReportCardPublished`، `InvoiceIssued`، `PaymentPosted`،
`RefundCompleted`، `GoodsReceived`، `StockBelowReorderPoint`، `AssetAssigned`،
`ApprovalCompleted`.
