"""Catálogo: entidades de referencia compartidas (organismos compradores y taxonomía).

Capa de modelos. No contiene lógica de negocio: el matching contra estos datos
vive en `domain/` y la orquestación en los services de cada app.
"""

from django.db import models


class Organismo(models.Model):
    """Organismo público comprador (ej: 'Ministerio de Obras Públicas')."""

    nombre = models.CharField(max_length=300, unique=True)
    # El Excel masivo del portal no trae código de organismo; la API de detalle sí.
    # Se completa durante el enriquecimiento, por eso admite vacío.
    codigo = models.CharField(max_length=50, blank=True, default="")
    region = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        verbose_name = "organismo"
        verbose_name_plural = "organismos"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre


class Rubro(models.Model):
    """Categoría de la taxonomía UNSPSC del portal (columnas Nivel 1/2/3 del bulk)."""

    class Nivel(models.IntegerChoices):
        NIVEL_1 = 1, "Nivel 1"
        NIVEL_2 = 2, "Nivel 2"
        NIVEL_3 = 3, "Nivel 3"

    nivel = models.PositiveSmallIntegerField(choices=Nivel.choices)
    nombre = models.CharField(max_length=300)

    class Meta:
        verbose_name = "rubro"
        verbose_name_plural = "rubros"
        constraints = [
            models.UniqueConstraint(fields=["nivel", "nombre"], name="rubro_unico_por_nivel"),
        ]
        ordering = ["nivel", "nombre"]

    def __str__(self) -> str:
        return f"N{self.nivel}: {self.nombre}"
