"""Enrutamiento raíz: Admin para operar, API para consumir (PLAN.md 2.1)."""

from django.contrib import admin
from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from apps.gestion.views import GestionLicitacionViewSet
from apps.licitaciones.views import LicitacionViewSet

router = DefaultRouter()
router.register("licitaciones", LicitacionViewSet, basename="licitacion")
router.register("gestiones", GestionLicitacionViewSet, basename="gestion")

urlpatterns = [
    path("", include("apps.portal.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/token/", obtain_auth_token, name="api-token"),
]
