"""
AppConfig پنل مدیریت.

عمداً از `apps/core/apps.py` جداست: جنگو هنگام حل `INSTALLED_APPS` هر ماژول
`apps.py` را دنبال یک AppConfig پیش‌فرض می‌گردد، و کنار هم قرارگرفتن
`CoreConfig` و این کلاس، خطای «more than one default AppConfig» می‌دهد.

`default_site` رشته است نه کلاس، تا `apps/core/admin_site.py` زودتر از
بارگذاری اپ‌ها import نشود.
"""

from django.contrib.admin.apps import AdminConfig


class SchoolAdminConfig(AdminConfig):
    """
    پنل مدیریت را به :class:`~apps.core.admin_site.SchoolAdminSite` می‌برد.

    در `INSTALLED_APPS` جای `django.contrib.admin` می‌نشیند؛ این روش مستند خود
    جنگو برای جایگزینی AdminSite پیش‌فرض است، پس `admin.site`، `admin.register`
    و مسیرهای `/admin/` همه بدون تغییر کار می‌کنند.
    """

    default_site = "apps.core.admin_site.SchoolAdminSite"
