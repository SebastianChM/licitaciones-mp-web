"""Operación y observabilidad: registro de ejecuciones batch y tasas de cambio.

Capa de modelos. Cada comando de ingesta/evaluación/enriquecimiento registra aquí
su ejecución (O5 de CLAUDE.md: sin observabilidad no hay operación).
"""

from django.db import models


class EjecucionPipeline(models.Model):
    """Una corrida de un proceso batch, con sus métricas y hallazgos."""

    class Tipo(models.TextChoices):
        INGESTA = "ingesta", "Ingesta bulk"
        EVALUACION = "evaluacion", "Evaluación de filtros"
        ENRIQUECIMIENTO = "enriquecimiento", "Enriquecimiento API"
        SINCRONIZACION = "sincronizacion", "Sincronización de estados"
        IMPORTACION_PIVOT = "importacion_pivot", "Importación de PIVOT"

    class Estado(models.TextChoices):
        EN_CURSO = "en_curso", "En curso"
        EXITOSA = "exitosa", "Exitosa"
        FALLIDA = "fallida", "Fallida"

    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.EN_CURSO)
    iniciada_en = models.DateTimeField(auto_now_add=True)
    terminada_en = models.DateTimeField(null=True, blank=True)
    # Totales por fase, exclusiones toxicas, valores de taxonomía nuevos, errores por registro
    metricas = models.JSONField(default=dict, blank=True)
    log_resumen = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "ejecución de pipeline"
        verbose_name_plural = "ejecuciones de pipeline"
        ordering = ["-iniciada_en"]

    def __str__(self) -> str:
        return f"{self.tipo} {self.iniciada_en:%Y-%m-%d %H:%M} ({self.estado})"


class TipoCambio(models.Model):
    """Tasa de conversión a CLP de un día, cacheada en BD.

    Reemplaza los valores hardcodeados del proyecto original (UTM=65000, USD=900)
    por tasas con fecha y fuente auditables. Si no hay tasa para el día, la
    conversión queda pendiente en vez de usar un número inventado.
    """

    class Moneda(models.TextChoices):
        UTM = "UTM", "Unidad Tributaria Mensual"
        USD = "USD", "Dólar estadounidense"
        EUR = "EUR", "Euro"

    fecha = models.DateField()
    moneda = models.CharField(max_length=3, choices=Moneda.choices)
    tasa_clp = models.DecimalField(max_digits=12, decimal_places=2)
    fuente = models.CharField(max_length=100)

    class Meta:
        verbose_name = "tipo de cambio"
        verbose_name_plural = "tipos de cambio"
        constraints = [
            models.UniqueConstraint(fields=["fecha", "moneda"], name="tasa_unica_por_dia"),
        ]
        ordering = ["-fecha", "moneda"]

    def __str__(self) -> str:
        return f"{self.moneda} {self.fecha}: ${self.tasa_clp} CLP"
