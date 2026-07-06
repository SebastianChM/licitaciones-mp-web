"""Vistas de licitaciones: solo lectura, delgadas (P2), sin N+1 (P9).

Los hechos entran por los comandos de ingesta; la API los consulta. La escritura
de workflow humano vive en apps.gestion.
"""

from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.licitaciones.filters import LicitacionFilter
from apps.licitaciones.models import Licitacion
from apps.licitaciones.serializers import LicitacionDetailSerializer, LicitacionListSerializer
from apps.ops.models import EjecucionPipeline


class LicitacionViewSet(viewsets.ReadOnlyModelViewSet):
    """Listado y detalle de licitaciones, con filtros por evaluación de equipo.

    Detalle por código externo del portal (URL estable y significativa):
    /api/licitaciones/1234-56-L126/
    """

    filterset_class = LicitacionFilter
    search_fields = ["codigo_externo", "nombre", "organismo__nombre"]
    ordering_fields = ["fecha_publicacion", "fecha_cierre", "monto_estimado"]
    ordering = ["-fecha_publicacion"]
    lookup_field = "codigo_externo"

    def get_queryset(self) -> QuerySet[Licitacion]:
        queryset = Licitacion.objects.select_related("organismo")
        if self.action != "list":
            # rubros/evaluaciones solo se serializan en el detalle
            queryset = queryset.prefetch_related("rubros", "evaluaciones__perfil")
        return queryset

    def get_serializer_class(self) -> type:
        if self.action == "list" or self.action == "nuevas":
            return LicitacionListSerializer
        return LicitacionDetailSerializer

    @action(detail=False, methods=["get"])
    def nuevas(self, request: Request) -> Response:
        """El incremental de la etapa 5 original, como consulta: licitaciones
        vistas por primera vez en la última ingesta exitosa."""
        ultima_ingesta = (
            EjecucionPipeline.objects.filter(
                tipo=EjecucionPipeline.Tipo.INGESTA,
                estado=EjecucionPipeline.Estado.EXITOSA,
            )
            .order_by("-iniciada_en")
            .first()
        )
        if ultima_ingesta is None:
            return Response({"detail": "Aún no hay ingestas exitosas.", "results": []})

        queryset = self.filter_queryset(self.get_queryset().filter(first_seen_run=ultima_ingesta))
        pagina = self.paginate_queryset(queryset)
        serializer = self.get_serializer(pagina if pagina is not None else queryset, many=True)
        if pagina is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
