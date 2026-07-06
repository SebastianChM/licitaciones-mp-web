from django.urls import path

from apps.portal import views

app_name = "portal"

urlpatterns = [
    path("", views.ListaRelevantesView.as_view(), name="lista"),
    path("busquedas/nueva/", views.BusquedaCrearView.as_view(), name="busqueda-nueva"),
    path("busquedas/<str:codigo>/reglas/", views.ReglasView.as_view(), name="reglas"),
    path(
        "busquedas/<str:codigo>/reglas/<int:regla_id>/eliminar/",
        views.ReglaEliminarView.as_view(),
        name="regla-eliminar",
    ),
    path("busquedas/<str:codigo>/evaluar/", views.EvaluarAhoraView.as_view(), name="evaluar-ahora"),
    path(
        "busquedas/<str:codigo>/eliminar/",
        views.BusquedaEliminarView.as_view(),
        name="busqueda-eliminar",
    ),
    path("licitacion/<str:codigo_externo>/", views.DetalleLicitacionView.as_view(), name="detalle"),
    path(
        "licitacion/<str:codigo_externo>/gestion/",
        views.ActualizarGestionView.as_view(),
        name="actualizar-gestion",
    ),
]
