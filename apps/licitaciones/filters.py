"""Filtros declarativos del endpoint de licitaciones.

Nota de diseño: equipo/resultado/confianza/relevantes filtran sobre la MISMA
fila de EvaluacionFiltro (un solo .filter() encadena las condiciones sobre la
misma relación), de modo que "equipo=TELECOM&resultado=incluida" signifique
"incluida PARA TELECOM" y no "evaluada por TELECOM y ademas incluida para
cualquier otro equipo".
"""

import django_filters
from django.db.models import QuerySet

from apps.licitaciones.models import EvaluacionFiltro, Licitacion

RESULTADOS_RELEVANTES = (
    EvaluacionFiltro.Resultado.INCLUIDA,
    EvaluacionFiltro.Resultado.BYPASS,
)


class LicitacionFilter(django_filters.FilterSet):
    perfil = django_filters.CharFilter(method="filtrar_por_evaluacion")
    # Alias legado del pivote de producto (decisiones.md 2026-07-06): "equipo"
    # sigue funcionando para clientes existentes; "perfil" es el nombre actual.
    equipo = django_filters.CharFilter(method="filtrar_por_evaluacion")
    resultado = django_filters.CharFilter(method="filtrar_por_evaluacion")
    confianza = django_filters.CharFilter(method="filtrar_por_evaluacion")
    relevantes = django_filters.BooleanFilter(method="filtrar_por_evaluacion")
    region = django_filters.CharFilter(field_name="organismo__region", lookup_expr="icontains")
    organismo = django_filters.CharFilter(field_name="organismo__nombre", lookup_expr="icontains")
    monto_min = django_filters.NumberFilter(field_name="monto_estimado", lookup_expr="gte")
    monto_max = django_filters.NumberFilter(field_name="monto_estimado", lookup_expr="lte")
    publicada_desde = django_filters.DateFilter(field_name="fecha_publicacion", lookup_expr="gte")
    publicada_hasta = django_filters.DateFilter(field_name="fecha_publicacion", lookup_expr="lte")
    cierra_desde = django_filters.DateTimeFilter(field_name="fecha_cierre", lookup_expr="gte")
    cierra_hasta = django_filters.DateTimeFilter(field_name="fecha_cierre", lookup_expr="lte")

    class Meta:
        model = Licitacion
        fields = ["moneda", "estado_fuente"]

    def filtrar_por_evaluacion(
        self, queryset: QuerySet[Licitacion], name: str, value: object
    ) -> QuerySet[Licitacion]:
        """Acumula los parámetros de evaluación y los aplica en UN solo filter().

        django-filter llama a este método una vez por parámetro; el trabajo real
        ocurre en la última llamada, cuando ya se conocen todos (ver docstring
        del módulo para el porqué).
        """
        condiciones: dict[str, object] = {}
        datos = self.data
        codigo_perfil = datos.get("perfil") or datos.get("equipo")
        if codigo_perfil:
            condiciones["evaluaciones__perfil__codigo"] = str(codigo_perfil).upper()
        if datos.get("resultado"):
            condiciones["evaluaciones__resultado"] = datos["resultado"]
        if datos.get("confianza"):
            condiciones["evaluaciones__confianza"] = datos["confianza"]
        if str(datos.get("relevantes", "")).lower() in ("true", "1"):
            condiciones["evaluaciones__resultado__in"] = RESULTADOS_RELEVANTES

        # Aplicar solo en la última pasada evita repetir el JOIN por cada parámetro.
        parametros_evaluacion = [
            p for p in ("perfil", "equipo", "resultado", "confianza", "relevantes") if datos.get(p)
        ]
        if not parametros_evaluacion or name != parametros_evaluacion[-1]:
            return queryset
        return queryset.filter(**condiciones).distinct()
