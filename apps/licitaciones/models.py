"""Licitaciones: los HECHOS que vienen de la fuente, y su evaluación por perfil.

Capa de modelos. Regla de oro (PLAN.md R4): esta app contiene datos que la ingesta
puede refrescar sin riesgo. El estado de trabajo humano NO vive aquí sino en
`apps.gestion`, que la ingesta tiene prohibido tocar (P4 de CLAUDE.md).
"""

from django.db import models
from django.utils import timezone


class Licitacion(models.Model):
    """Una licitación pública tal como la reporta la fuente (bulk del portal + API).

    `raw_bulk` conserva la fila original del Excel masivo y `raw_api` la respuesta
    de la API de detalle: auditables y re-procesables sin volver a descargar.
    """

    class Moneda(models.TextChoices):
        CLP = "CLP", "Peso chileno"
        UTM = "UTM", "Unidad Tributaria Mensual"
        USD = "USD", "Dólar estadounidense"
        EUR = "EUR", "Euro"

    codigo_externo = models.CharField(max_length=60, unique=True)
    nombre = models.CharField(max_length=500)
    descripcion = models.TextField(blank=True, default="")
    organismo = models.ForeignKey(
        "catalogo.Organismo",
        on_delete=models.PROTECT,
        related_name="licitaciones",
        null=True,
        blank=True,
    )
    rubros = models.ManyToManyField("catalogo.Rubro", related_name="licitaciones", blank=True)
    # Campos que el motor de matching necesita además de nombre/descripción/taxonomía
    # (mismo mapeo campo→regla que la etapa 2 del proyecto original)
    generico = models.TextField(blank=True, default="")
    descripcion_producto = models.TextField(blank=True, default="")
    tipo_adquisicion = models.CharField(max_length=120, blank=True, default="")

    estado_fuente = models.CharField(max_length=60, blank=True, default="")
    monto_estimado = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    moneda = models.CharField(max_length=3, choices=Moneda.choices, blank=True, default="")
    monto_clp_calculado = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True
    )
    fecha_publicacion = models.DateField(null=True, blank=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    url_ficha = models.URLField(max_length=300, blank=True, default="")

    raw_bulk = models.JSONField(default=dict, blank=True)
    raw_api = models.JSONField(null=True, blank=True)
    enriquecida_en = models.DateTimeField(null=True, blank=True)

    first_seen_run = models.ForeignKey(
        "ops.EjecucionPipeline",
        on_delete=models.SET_NULL,
        related_name="licitaciones_nuevas",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "licitación"
        verbose_name_plural = "licitaciones"
        ordering = ["-fecha_publicacion", "codigo_externo"]
        indexes = [
            models.Index(fields=["fecha_cierre"]),
            models.Index(fields=["estado_fuente"]),
        ]

    def __str__(self) -> str:
        return f"{self.codigo_externo}: {self.nombre[:80]}"


class EvaluacionFiltro(models.Model):
    """Resultado de evaluar UNA licitación contra UN perfil de equipo.

    Relación explícita licitacion x perfil (PLAN.md R3): una misma licitación puede
    ser relevante para Telecom e irrelevante para Arquitectura simultáneamente.
    Re-ejecutable: si cambian las reglas, se re-evalúa sin re-ingestar.
    """

    class Resultado(models.TextChoices):
        INCLUIDA = "incluida", "Incluida"
        BYPASS = "bypass", "Incluida por bypass"
        SIN_MATCH = "sin_match", "Sin match de inclusión"
        EXCLUIDA = "excluida", "Excluida"
        EXCLUSION_DURA = "exclusion_dura", "Exclusión dura"
        VETADA = "vetada", "Vetada por intención"

    class Confianza(models.TextChoices):
        ALTA = "alta", "Alta (servicio profesional)"
        REVISAR = "revisar", "Revisar (zona gris)"
        NO_APLICA = "na", "No aplica"

    licitacion = models.ForeignKey(
        Licitacion, on_delete=models.CASCADE, related_name="evaluaciones"
    )
    perfil = models.ForeignKey(
        "perfiles.PerfilFiltro", on_delete=models.CASCADE, related_name="evaluaciones"
    )
    resultado = models.CharField(max_length=20, choices=Resultado.choices)
    confianza = models.CharField(
        max_length=10, choices=Confianza.choices, default=Confianza.NO_APLICA
    )
    # Qué keywords matchearon y en qué campo: {"inclusion": [...], "exclusion": [...], ...}
    trazabilidad = models.JSONField(default=dict, blank=True)
    # default (callable) y no auto_now: el upsert masivo de `evaluar` usa bulk_create,
    # que no pasa por save() y por lo tanto auto_now nunca se aplicaría.
    evaluada_en = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "evaluación de filtro"
        verbose_name_plural = "evaluaciones de filtro"
        constraints = [
            models.UniqueConstraint(
                fields=["licitacion", "perfil"], name="una_evaluacion_por_perfil"
            ),
        ]
        indexes = [
            models.Index(fields=["perfil", "resultado"]),
        ]

    def __str__(self) -> str:
        return f"{self.licitacion.codigo_externo} x {self.perfil.codigo}: {self.resultado}"

    @property
    def es_relevante(self) -> bool:
        """True si la licitación pasó el filtro para este perfil (incluida o rescatada)."""
        return self.resultado in {self.Resultado.INCLUIDA, self.Resultado.BYPASS}
