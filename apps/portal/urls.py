from django.urls import path

from apps.portal import views

app_name = "portal"

urlpatterns = [
    path("", views.ListaRelevantesView.as_view(), name="lista"),
    path("licitacion/<str:codigo_externo>/", views.DetalleLicitacionView.as_view(), name="detalle"),
    path(
        "licitacion/<str:codigo_externo>/gestion/",
        views.ActualizarGestionView.as_view(),
        name="actualizar-gestion",
    ),
]
