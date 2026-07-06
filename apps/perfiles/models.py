"""Perfiles de filtrado: las búsquedas guardadas de cada usuario y sus reglas.

Capa de modelos. La semántica de matching (boundaries, frases, bypass) NO está aquí:
vive en `domain/matching.py`. Las reglas se administran desde el portal;
`importar_pivot` queda como herramienta opcional de migración desde el Excel
del proyecto original (ver decisiones.md, pivote de producto 2026-07-06).
"""

from django.conf import settings
from django.db import models


class PerfilFiltro(models.Model):
    """Una búsqueda guardada de un usuario: nombre + conjunto de reglas.

    Históricamente representaba un "equipo" (hoja del PIVOT); hoy es la unidad
    self-service del producto. El código identifica la búsqueda en URLs y API.
    """

    codigo = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, default="")
    activo = models.BooleanField(default=True)
    propietario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="busquedas",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "búsqueda guardada"
        verbose_name_plural = "búsquedas guardadas"
        ordering = ["codigo"]

    def __str__(self) -> str:
        return f"{self.codigo} ({self.nombre})"


class ReglaKeyword(models.Model):
    """Una palabra o frase clave de un perfil, con su tipo y campo objetivo.

    Réplica relacional de las columnas de la hoja de filtros del PIVOT: los grupos
    de inclusión/exclusión aplican sobre campos específicos de la licitación
    (mismo mapeo campo→grupo que la etapa 2 del proyecto original).
    """

    class Tipo(models.TextChoices):
        INCLUIR = "incluir", "Inclusión"
        EXCLUIR = "excluir", "Exclusión"
        BYPASS = "bypass", "Bypass (rescate)"
        EXCLUSION_DURA = "exclusion_dura", "Exclusión dura (no bypasseable)"

    class Campo(models.TextChoices):
        """Campo de la licitación sobre el que aplica la regla.

        Solo INCLUIR/EXCLUIR usan campo; BYPASS y EXCLUSION_DURA operan sobre
        conjuntos fijos de campos definidos por el motor (nombre+descripción y
        nivel1+nivel2 respectivamente), por eso admiten vacío.
        """

        NOMBRE = "nombre", "Nombre y descripción"
        NIVEL1 = "nivel1", "Taxonomía Nivel 1"
        NIVEL2 = "nivel2", "Taxonomía Nivel 2"
        NIVEL3 = "nivel3", "Taxonomía Nivel 3"
        GENERICO = "generico", "Genérico"
        ORGANISMO = "organismo", "Organismo"
        VALOR = "valor", "Tipo de adquisición"
        COMPONENTE = "componente", "Descripción del producto/servicio"

    perfil = models.ForeignKey(PerfilFiltro, on_delete=models.CASCADE, related_name="reglas")
    texto = models.CharField(max_length=200)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    campo = models.CharField(max_length=20, choices=Campo.choices, blank=True, default="")
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "regla de keyword"
        verbose_name_plural = "reglas de keyword"
        constraints = [
            models.UniqueConstraint(
                fields=["perfil", "tipo", "campo", "texto"],
                name="regla_unica_por_perfil",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.perfil.codigo}] {self.tipo}/{self.campo or '-'}: {self.texto}"


class PalabraIntencion(models.Model):
    """Invariante de negocio global (hoja 01-Intencion_Global del PIVOT).

    Compartida por todos los perfiles: 'vetada' descarta compras/insumos
    (no negociable, no bypasseable); 'requerida' marca confianza ALTA en que la
    licitación es un servicio profesional. Lo que no matchea ninguna queda en
    zona gris (REVISAR) y lo decide un humano.
    """

    class Tipo(models.TextChoices):
        REQUERIDA = "requerida", "Requerida (confianza alta)"
        VETADA = "vetada", "Vetada (descarte duro)"

    texto = models.CharField(max_length=200)
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "palabra de intención"
        verbose_name_plural = "palabras de intención"
        constraints = [
            models.UniqueConstraint(fields=["texto", "tipo"], name="intencion_unica"),
        ]

    def __str__(self) -> str:
        return f"{self.tipo}: {self.texto}"
