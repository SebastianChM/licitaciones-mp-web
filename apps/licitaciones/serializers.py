"""Serializers de licitaciones: la representación pública de los HECHOS.

Capa de interfaz (P2): sin lógica de negocio. La API de licitaciones es de solo
lectura; los hechos entran únicamente por los comandos de ingesta.
"""

from rest_framework import serializers

from apps.licitaciones.models import EvaluacionFiltro, Licitacion


class EvaluacionFiltroSerializer(serializers.ModelSerializer):
    perfil = serializers.CharField(source="perfil.codigo", read_only=True)

    class Meta:
        model = EvaluacionFiltro
        fields = ["perfil", "resultado", "confianza", "trazabilidad", "evaluada_en"]


class LicitacionListSerializer(serializers.ModelSerializer):
    """Representación compacta para listados: sin descripciones largas ni payloads crudos."""

    organismo = serializers.CharField(source="organismo.nombre", default="", read_only=True)
    region = serializers.CharField(source="organismo.region", default="", read_only=True)

    class Meta:
        model = Licitacion
        fields = [
            "codigo_externo",
            "nombre",
            "organismo",
            "region",
            "moneda",
            "monto_estimado",
            "fecha_publicacion",
            "fecha_cierre",
            "estado_fuente",
            "url_ficha",
        ]


class LicitacionDetailSerializer(LicitacionListSerializer):
    """Detalle: agrega descripciones, taxonomía y las evaluaciones por equipo."""

    rubros = serializers.StringRelatedField(many=True, read_only=True)
    evaluaciones = EvaluacionFiltroSerializer(many=True, read_only=True)

    class Meta(LicitacionListSerializer.Meta):
        fields = [
            *LicitacionListSerializer.Meta.fields,
            "descripcion",
            "generico",
            "descripcion_producto",
            "tipo_adquisicion",
            "rubros",
            "evaluaciones",
            "enriquecida_en",
        ]
