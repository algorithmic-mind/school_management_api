"""نقشه مسیرهای سراسری پروژه."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.decorators.cache import cache_page
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

#: قرارداد OpenAPI ۹۲۷ عملیات دارد و ساختش چند ثانیه طول می‌کشد؛ بدون Cache،
#: هر بار بازکردن Swagger همان هزینه را دوباره می‌دهد.
_schema_view = cache_page(settings.SCHEMA_CACHE_SECONDS)(
    SpectacularAPIView.as_view()
)

api_v1_patterns = [
    path("auth/", include("apps.identity.urls_auth")),
    path("iam/", include("apps.identity.urls")),
    path("org/", include("apps.organization.urls")),
    path("students/", include("apps.students.urls")),
    path("hr/", include("apps.hr.urls")),
    path("teaching/", include("apps.teaching.urls")),
    path("assessment/", include("apps.assessment.urls")),
    path("gradebook/", include("apps.gradebook.urls")),
    path("finance/", include("apps.finance.urls")),
    path("inventory/", include("apps.inventory.urls")),
    path("welfare/", include("apps.welfare.urls")),
    path("workflow/", include("apps.workflow.urls")),
    path("", include("apps.core.urls")),
]

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/v1/", include((api_v1_patterns, "v1"), namespace="v1")),
    # ---- مستندات OpenAPI ----
    path("api/schema/", _schema_view, name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]

if settings.DEBUG:
    # در عملیات، وب‌سرور پوشه public/ را مستقیم سرو می‌کند و این‌ها لازم نیست.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
