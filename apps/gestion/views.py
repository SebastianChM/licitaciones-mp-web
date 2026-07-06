"""Vistas de gestión: CRUD del workflow humano por equipo."""

from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.serializers import BaseSerializer

from apps.gestion.models import GestionLicitacion
from apps.gestion.serializers import GestionLicitacionSerializer


class GestionLicitacionViewSet(viewsets.ModelViewSet):
    serializer_class = GestionLicitacionSerializer
    filterset_fields = ["perfil__codigo", "estado", "asignado_a__username"]
    ordering = ["-updated_at"]

    def get_queryset(self) -> QuerySet[GestionLicitacion]:
        return GestionLicitacion.objects.select_related(
            "licitacion", "perfil", "asignado_a", "actualizado_por"
        )

    def perform_create(self, serializer: BaseSerializer) -> None:
        serializer.save(actualizado_por=self.request.user)

    def perform_update(self, serializer: BaseSerializer) -> None:
        serializer.save(actualizado_por=self.request.user)
