# راهنمای استقرار

---

## دو مشکل روی `school.amirkho.ir`

### ۱. فایل‌های ثابت سرو نمی‌شوند — علت صفحه سفید Swagger و پنل بی‌استایل

هر نشانی زیر `‎/static/‎` را nginx با ۴۰۴ پاسخ می‌دهد و اصلاً به Django نمی‌رسد:

```
GET /static/admin/css/base.css                                    404  (nginx)
GET /static/drf_spectacular_sidecar/swagger-ui-dist/swagger-ui.css 404  (nginx)
GET /static/school_admin/css/admin-theme.css                      404  (nginx)
```

اما مسیرهای Django سالم‌اند:

```
GET /admin/login/   200
GET /api/docs/      200   ← خودِ HTML می‌آید
GET /api/schema/    200   ← قرارداد ۳٫۳ مگابایتی هم می‌آید
```

یعنی Django کار می‌کند؛ فقط CSS و JS نمی‌رسد. صفحه Swagger این چهار فایل را
صدا می‌زند و چون هیچ‌کدام نمی‌آید، صفحه سفید می‌ماند:

```
/static/drf_spectacular_sidecar/swagger-ui-dist/swagger-ui.css
/static/drf_spectacular_sidecar/swagger-ui-dist/swagger-ui-bundle.js
/static/drf_spectacular_sidecar/swagger-ui-dist/swagger-ui-standalone-preset.js
/static/drf_spectacular_sidecar/swagger-ui-dist/favicon-32x32.png
```

پنل مدیریت هم دقیقاً به همین دلیل بی‌استایل است.

**چرا مطمئنیم nginx مقصر است؟** بدنه ۴۰۴ مسیر `‎/static/‎` صفحه پیش‌فرض
nginx است (۱۵۳ بایت)، در حالی که یک مسیر ناموجود Django صفحه ۴۰۴ خود Django را
برمی‌گرداند (۳۲۴۳ بایت). پس nginx مسیر `‎/static/‎` را خودش برمی‌دارد.

**و علت اصلی‌اش:** nginx پوشه `public/` را با همان نام در نشانی سرو می‌کند:

```
GET /public/static/admin/css/base.96c479cedf7a.css    200  ✅
GET /static/admin/css/base.96c479cedf7a.css           404  ❌
```

اما Django نشانی‌ها را با پیشوند `‎/static/‎` تولید می‌کند. این ناهماهنگی، تنها
دلیل صفحه سفید است. راه‌حلش در گام ۴ آمده.

> بررسی شد که فقط `public/` از دیسک سرو می‌شود؛ `‎/.env`، `‎/database/db.sqlite3`،
> `‎/config/settings.py` و `‎/manage.py` همه ۴۰۴ می‌دهند و به Django پروکسی
> می‌شوند. یعنی نشتی فایل حساس وجود ندارد.

### ۲. `DEBUG=True` روی سرور عملیاتی — مشکل امنیتی

صفحه ۴۰۴ سایت، صفحه اشکال‌زدایی Django است («tried these URL patterns»). یعنی
`DJANGO_DEBUG` روی سرور `True` است.

با `DEBUG=True`، **هر خطای مدیریت‌نشده، صفحه‌ای برمی‌گرداند که کل تنظیمات شامل
`SECRET_KEY` و رمز پایگاه داده را نشان می‌دهد.** این باید همین حالا خاموش شود.

از آنجا که این حالت مدتی روی اینترنت باز بوده، `SECRET_KEY` را هم عوض کنید:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

> تغییر `SECRET_KEY` نشست‌های فعال و لینک‌های بازیابی گذرواژه را باطل می‌کند؛
> کاربران باید دوباره وارد شوند. توکن‌های JWT هم باطل می‌شوند.

---

## اصلاح سمت کد (انجام شد)

`whitenoise` اضافه شد تا خودِ Django بتواند فایل‌های ثابت را با `DEBUG=False`
سرو کند. با این تغییر، درست‌بودن پنل و Swagger دیگر به پیکربندی nginx وابسته
نیست: اگر nginx مسیر `‎/static/‎` را نگیرد، Django خودش جواب می‌دهد.

آزمایش‌شده با `DEBUG=False` روی هر دو حالت WSGI و ASGI (uvicorn):

```
/static/admin/css/base.css                              200   22 KB
/static/school_admin/css/admin-theme.css                200   10 KB
/static/school_admin/fonts/Vazirmatn-Variable.woff2     200  111 KB
/static/drf_spectacular_sidecar/.../swagger-ui-bundle.js 200  1.5 MB
```

ضمناً قرارداد OpenAPI کش شد. ساختش برای ۹۰۹ عملیات چند ثانیه طول می‌کشد و
بدون کش، هر بار بازکردن Swagger همان هزینه را دوباره می‌داد:

| | پیش از کش | پس از کش |
|---|---|---|
| `/api/schema/` | ۳٫۵۸ ثانیه | ۰٫۰۳ ثانیه |

مدتش با `SCHEMA_CACHE_SECONDS` قابل تنظیم است (پیش‌فرض ۹۰۰ ثانیه).

---

## کارهای سمت سرور

### ۱. به‌روزرسانی کد و وابستگی‌ها

```bash
git pull && pip install -r backend/requirements.txt
```

### ۲. تنظیم `.env`

```bash
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<کلید تازه‌ای که بالا ساختید>
DJANGO_ALLOWED_HOSTS=school.amirkho.ir
CSRF_TRUSTED_ORIGINS=https://school.amirkho.ir
CORS_ALLOWED_ORIGINS=https://school.amirkho.ir
USE_X_FORWARDED_PROTO=True
```

`USE_X_FORWARDED_PROTO=True` را حتماً بگذارید. nginx خودش TLS را تمام می‌کند و
بدون این تنظیم، `SECURE_SSL_REDIRECT` که با `DEBUG=False` روشن می‌شود، حلقه
بی‌پایان ریدایرکت می‌سازد.

### ۳. جمع‌آوری فایل‌های ثابت

**این مرحله حالا اجباری است.** با `DEBUG=False` فایل‌ها از `public/static/`
خوانده می‌شوند، نه از `assets/`:

```bash
cd backend && python manage.py collectstatic --noinput
```

بعد از هر تغییر در `assets/` دوباره اجرایش کنید.

### ۴. هماهنگ‌کردن نشانی فایل‌های ثابت با nginx

`STATIC_URL` یک **نشانی وب** است، نه مسیر روی دیسک. فایل‌ها همیشه در
`backend/public/static/` ذخیره می‌شوند؛ این متغیر فقط تعیین می‌کند مرورگر با
چه نشانی‌ای آن‌ها را بخواهد. اگر این نشانی با چیزی که nginx می‌شناسد یکی نباشد،
هر فایل ۴۰۴ می‌شود.

روی `school.amirkho.ir` وضعیت این است:

```
GET /public/static/admin/css/base.96c479cedf7a.css    200  ✅
GET /static/admin/css/base.96c479cedf7a.css           404  ❌
```

یعنی nginx پوشه `public/` را با همان نام در نشانی سرو می‌کند. پس:

```bash
STATIC_URL=public/static/
MEDIA_URL=public/media/
```

بعد از تغییر، سرویس را ری‌استارت کنید. `collectstatic` لازم نیست دوباره اجرا
شود — مسیر دیسک عوض نشده، فقط نشانی.

**اگر ترجیح می‌دهید نشانی‌ها `/static/` بماند** (قرارداد متعارف Django)، به‌جای
تغییر بالا این بلوک را به nginx اضافه کنید:

**گزینه الف — nginx فایل را مستقیم بدهد (سریع‌تر، پیشنهادی):**

```nginx
location /static/ {
    alias /مسیر/پروژه/backend/public/static/;
    access_log off;
    expires 30d;
    add_header Cache-Control "public, immutable";
}

location /media/ {
    alias /مسیر/پروژه/backend/public/media/;
    access_log off;
    expires 7d;
}
```

`alias` باید با `/` تمام شود و مسیرش دقیقاً پوشه‌ای باشد که `collectstatic`
در آن نوشته است. برای اطمینان:

```bash
cd backend && python manage.py findstatic admin/css/base.css
```

**گزینه ب — هیچ بلوکی برای `‎/static/‎` نگذارید.** آن‌وقت درخواست به Django
پروکسی می‌شود و WhiteNoise جواب می‌دهد. کمی کندتر است ولی هیچ‌وقت خراب نمی‌شود.

> هر سه راه درست‌اند؛ فقط یکی را انتخاب کنید. مهم این است که `STATIC_URL` و
> پیکربندی nginx یک چیز بگویند.

### ۵. بارگذاری مجدد

```bash
sudo nginx -t && sudo systemctl reload nginx
```

سرویس Django را هم ری‌استارت کنید تا `.env` تازه خوانده شود.

---

## بررسی پس از استقرار

```bash
cd backend && python manage.py check --deploy
```

سپس از بیرون سرور:

```bash
curl -sI https://school.amirkho.ir/public/static/admin/css/base.css | head -1
```

باید `200` بدهد. برای اطمینان از هماهنگی، ببینید صفحه Swagger چه نشانی‌ای صدا
می‌زند و همان را مستقیم باز کنید:

```bash
curl -s https://school.amirkho.ir/api/docs/ | grep -oE 'src="[^"]+"'
```

صفحه ۴۰۴ هم باید کوتاه و بدون جزئیات باشد؛ اگر هنوز «tried these URL patterns»
نشان می‌دهد یعنی `DEBUG` هنوز روشن است و سرویس ری‌استارت نشده.

| بررسی | انتظار |
|---|---|
| نشانی استاتیک (مطابق `STATIC_URL`) | ۲۰۰ |
| `/api/docs/` | صفحه Swagger با ظاهر کامل |
| `/api/redoc/` | صفحه ReDoc با ظاهر کامل |
| `/admin/` | پنل با پوسته نارنجی و فونت وزیرمتن |
| یک مسیر ناموجود | ۴۰۴ کوتاه، بدون جزئیات فنی |
| `http://` | ریدایرکت به `https://` بدون حلقه |
