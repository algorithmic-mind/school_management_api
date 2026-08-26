"""مسیرهای زیرساختی."""

from django.urls import path

from apps.core.views import EnumCatalogView, HealthCheckView, ModuleMapView

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health"),
    path("meta/enums/", EnumCatalogView.as_view(), name="enum-catalog"),
    path("meta/modules/", ModuleMapView.as_view(), name="module-map"),
]
