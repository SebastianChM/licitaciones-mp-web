"""Gestión: el trabajo humano sobre las licitaciones. Territorio prohibido para la ingesta.

Capa de modelos. Esta app es la respuesta relacional al problema que la etapa 5 del
proyecto original resuelve preservando celdas de Excel: el estado de seguimiento,
las notas y la asignación son de las personas, y ningún proceso batch los toca (P4).
"""

from django.conf import settings
from django.db import models


class GestionLicitacion(models.Model):
    """Estado de trabajo de un equipo sobre una licitación concreta.

    Es por (licitación, perfil): dos equipos pueden gestionar la misma licitación
    en estados distintos sin pisarse, cosa que los archivos Excel por equipo del
    sistema original no podían expresar.
    """

    class Estado(models.TextChoices):
        NUEVA = "nueva", "Nueva"
        EN_REVISION = "en_revision", "En revisión"
        PREPARANDO_OFERTA = "preparando_oferta", "Preparando oferta"
        PRESENTADA = "presentada", "Oferta presentada"
        DESCARTADA = "descartada", "Descartada"

    licitacion = models.ForeignKey(
        "licitaciones.Licitacion", on_delete=models.CASCADE, related_name="gestiones"
    )
    perfil = models.ForeignKey(
        "perfiles.PerfilFiltro", on_delete=models.CASCADE, related_name="gestiones"
    )
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.NUEVA)
    notas = models.TextField(blank=True, default="")
    asignado_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="licitaciones_asignadas",
        null=True,
        blank=True,
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "gestión de licitación"
        verbose_name_plural = "gestiones de licitación"
        constraints = [
            models.UniqueConstraint(fields=["licitacion", "perfil"], name="una_gestion_por_equipo"),
        ]
        indexes = [
            models.Index(fields=["perfil", "estado"]),
        ]

    def __str__(self) -> str:
        return f"{self.licitacion.codigo_externo} x {self.perfil.codigo}: {self.estado}"
