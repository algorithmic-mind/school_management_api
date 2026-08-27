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
برمی‌گرداند (۳۲۴۳ بایت). پس nginx مسیر `‎/static/‎` را خودش برمی‌دارد و به
پوشه‌ای اشاره می‌کند که فایل‌ها آنجا نیستند.

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

### ۴. nginx

مسیر `‎/static/‎` را یا درست کنید یا کلاً بردارید تا Django جوابش را بدهد.

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

**گزینه ب — بلوک `‎/static/‎` را از nginx حذف کنید.** آن‌وقت درخواست به Django
پروکسی می‌شود و WhiteNoise جواب می‌دهد. کندتر است ولی هیچ‌وقت خراب نمی‌شود.

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
curl -sI https://school.amirkho.ir/static/admin/css/base.css | head -1
```

باید `200` بدهد. اگر `404` داد، `alias` هنوز به پوشه اشتباه اشاره می‌کند.

صفحه ۴۰۴ هم باید کوتاه و بدون جزئیات باشد؛ اگر هنوز «tried these URL patterns»
نشان می‌دهد یعنی `DEBUG` هنوز روشن است و سرویس ری‌استارت نشده.

| بررسی | انتظار |
|---|---|
| `/static/admin/css/base.css` | ۲۰۰ |
| `/api/docs/` | صفحه Swagger با ظاهر کامل |
| `/api/redoc/` | صفحه ReDoc با ظاهر کامل |
| `/admin/` | پنل با پوسته نارنجی و فونت وزیرمتن |
| یک مسیر ناموجود | ۴۰۴ کوتاه، بدون جزئیات فنی |
| `http://` | ریدایرکت به `https://` بدون حلقه |
