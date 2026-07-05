"""Perfiles de filtrado: las reglas por equipo que hoy viven en PIVOT_MAESTRO.xlsx.

Capa de modelos. La semántica de matching (boundaries, frases, bypass) NO está aquí:
vive en `domain/matching.py`. Estos modelos solo persisten las reglas que el Admin
edita y que `importar_pivot` puebla desde el Excel maestro del proyecto original.
"""

from django.db import models


class PerfilFiltro(models.Model):
    """Perfil de un equipo (ej: TELECOM, ARQ, ELEC), equivalente a una hoja del PIVOT."""

    codigo = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, default="")
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "perfil de filtro"
        verbose_name_plural = "perfiles de filtro"
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
