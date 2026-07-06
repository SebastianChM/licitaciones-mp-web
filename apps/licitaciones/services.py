"""Servicios de licitaciones: orquestación entre adaptadores de ingesta y modelos.

Capa de servicios (P2): aquí vive la lógica de upsert. NUNCA escribe en
apps.gestion (P4): los hechos se refrescan, el trabajo humano no se toca.
"""

import datetime
import logging
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db.models import QuerySet
from django.utils import timezone

from apps.catalogo.models import Organismo, Rubro
from apps.licitaciones.api_mp import ClienteDetalleMP
from apps.licitaciones.ingesta import FilaBulk
from apps.licitaciones.models import EvaluacionFiltro, Licitacion
from apps.ops.models import EjecucionPipeline
from apps.perfiles.models import PalabraIntencion, PerfilFiltro, ReglaKeyword
from domain import matching

logger = logging.getLogger(__name__)

MONEDAS_CONOCIDAS = frozenset(Licitacion.Moneda.values)

# Una keyword de exclusión que por sí sola mata más de este % del subconjunto
# post-inclusión es demasiado genérica (mismo umbral que el proyecto original).
UMBRAL_EXCLUSION_TOXICA_PCT = 10.0
# Tamaño de lote para el upsert masivo de evaluaciones.
BATCH_EVALUACIONES = 500


@dataclass
class ResultadoIngesta:
    """Métricas de una corrida de ingesta, para EjecucionPipeline (O5)."""

    total_filas: int = 0
    creadas: int = 0
    actualizadas: int = 0
    advertencias: list[str] = field(default_factory=list)

    def como_dict(self) -> dict[str, object]:
        return {
            "total_filas": self.total_filas,
            "creadas": self.creadas,
            "actualizadas": self.actualizadas,
            "advertencias": self.advertencias,
        }


def _parsear_fecha(valor: object) -> datetime.date | None:
    """El bulk entrega fechas como datetime, date o string ISO; unificamos a date."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, str):
        try:
            return datetime.datetime.fromisoformat(valor).date()
        except ValueError:
            return None
    if isinstance(valor, datetime.datetime):
        return valor.date()
    if isinstance(valor, datetime.date):
        return valor
    return None


def _parsear_fecha_hora(valor: object) -> datetime.datetime | None:
    """Fecha de cierre con hora; el bulk la trae naive en hora de Chile (USE_TZ=True)."""
    if valor is None or valor == "":
        return None
    resultado: datetime.datetime | None = None
    if isinstance(valor, str):
        try:
            resultado = datetime.datetime.fromisoformat(valor)
        except ValueError:
            return None
    elif isinstance(valor, datetime.datetime):
        resultado = valor
    if resultado is None:
        return None
    if resultado.tzinfo is None:
        from django.utils import timezone

        resultado = timezone.make_aware(resultado)
    return resultado


def _parsear_monto(valor: object) -> Decimal | None:
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None


def ingestar_filas(filas: list[FilaBulk], ejecucion: EjecucionPipeline) -> ResultadoIngesta:
    """Upsert de filas del bulk en la BD. Idempotente por codigo_externo (O4).

    El llamador (command) es dueño de la transacción (O3). `first_seen_run` solo
    se asigna al crear: es la base del análisis incremental (reemplaza la etapa 5
    del proyecto original con una consulta).
    """
    resultado = ResultadoIngesta(total_filas=len(filas))

    for fila in filas:
        datos = fila.datos

        organismo = None
        nombre_organismo = str(datos.get("organismo") or "").strip()
        if nombre_organismo:
            organismo, _ = Organismo.objects.get_or_create(
                nombre=nombre_organismo,
                defaults={"region": str(datos.get("region") or "").strip()},
            )

        moneda = str(datos.get("moneda") or "").strip().upper()
        if moneda and moneda not in MONEDAS_CONOCIDAS:
            resultado.advertencias.append(
                f"{fila.codigo_externo}: moneda desconocida '{moneda}', se guarda vacía."
            )
            moneda = ""

        licitacion, creada = Licitacion.objects.update_or_create(
            codigo_externo=fila.codigo_externo,
            defaults={
                "nombre": str(datos.get("nombre") or "")[:500],
                "descripcion": str(datos.get("descripcion") or ""),
                "organismo": organismo,
                "generico": str(datos.get("generico") or ""),
                "descripcion_producto": str(datos.get("descripcion_producto") or ""),
                "tipo_adquisicion": str(datos.get("tipo_adquisicion") or "")[:120],
                "estado_fuente": str(datos.get("estado_fuente") or "")[:60],
                "moneda": moneda,
                "monto_estimado": _parsear_monto(datos.get("monto_estimado")),
                "fecha_publicacion": _parsear_fecha(datos.get("fecha_publicacion")),
                "fecha_cierre": _parsear_fecha_hora(datos.get("fecha_cierre")),
                "raw_bulk": fila.cruda,
            },
        )
        if creada:
            licitacion.first_seen_run = ejecucion
            licitacion.save(update_fields=["first_seen_run"])
            resultado.creadas += 1
        else:
            resultado.actualizadas += 1

        # add(), no set(): el bulk trae una fila POR ITEM de la licitacion, y la
        # taxonomía de todos los ítems se acumula (hallazgo de la primera ingesta
        # real: 17.812 filas → 4.174 licitaciones; ver docs/decisiones.md).
        rubros = [
            Rubro.objects.get_or_create(nivel=nivel, nombre=nombre_rubro)[0]
            for nivel, clave in ((1, "nivel1"), (2, "nivel2"), (3, "nivel3"))
            if (nombre_rubro := str(datos.get(clave) or "").strip())
        ]
        if rubros:
            licitacion.rubros.add(*rubros)

    return resultado


@dataclass
class ResultadoEvaluacion:
    """Métricas de una corrida de evaluación por perfil (O5)."""

    perfil: str = ""
    total: int = 0
    por_resultado: dict[str, int] = field(default_factory=dict)
    confianza_alta: int = 0
    confianza_revisar: int = 0
    top_keywords_exclusion: list[tuple[str, int]] = field(default_factory=list)
    exclusiones_toxicas: list[tuple[str, int, float]] = field(default_factory=list)

    def como_dict(self) -> dict[str, object]:
        return {
            "perfil": self.perfil,
            "total": self.total,
            "por_resultado": self.por_resultado,
            "confianza_alta": self.confianza_alta,
            "confianza_revisar": self.confianza_revisar,
            "top_keywords_exclusion": self.top_keywords_exclusion,
            "exclusiones_toxicas": self.exclusiones_toxicas,
        }


def construir_reglas(perfil: PerfilFiltro) -> matching.ReglasEquipo:
    """Traduce las reglas persistidas de un perfil al dominio puro."""
    incluir: dict[str, list[str]] = {}
    excluir: dict[str, list[str]] = {}
    bypass: list[str] = []
    dura: list[str] = []
    for regla in perfil.reglas.filter(activa=True):
        if regla.tipo == ReglaKeyword.Tipo.INCLUIR:
            incluir.setdefault(regla.campo, []).append(regla.texto)
        elif regla.tipo == ReglaKeyword.Tipo.EXCLUIR:
            excluir.setdefault(regla.campo, []).append(regla.texto)
        elif regla.tipo == ReglaKeyword.Tipo.BYPASS:
            bypass.append(regla.texto)
        elif regla.tipo == ReglaKeyword.Tipo.EXCLUSION_DURA:
            dura.append(regla.texto)

    intencion = PalabraIntencion.objects.filter(activa=True)
    return matching.ReglasEquipo(
        incluir={campo: tuple(textos) for campo, textos in incluir.items()},
        excluir={campo: tuple(textos) for campo, textos in excluir.items()},
        bypass=tuple(bypass),
        exclusion_dura=tuple(dura),
        intencion_requerida=tuple(
            intencion.filter(tipo=PalabraIntencion.Tipo.REQUERIDA).values_list("texto", flat=True)
        ),
        intencion_vetada=tuple(
            intencion.filter(tipo=PalabraIntencion.Tipo.VETADA).values_list("texto", flat=True)
        ),
    )


def _campos_de(licitacion: Licitacion) -> matching.CamposLicitacion:
    niveles = {rubro.nivel: rubro.nombre for rubro in licitacion.rubros.all()}
    return matching.CamposLicitacion(
        nombre=licitacion.nombre,
        descripcion=licitacion.descripcion,
        nivel1=niveles.get(1, ""),
        nivel2=niveles.get(2, ""),
        nivel3=niveles.get(3, ""),
        generico=licitacion.generico,
        organismo=licitacion.organismo.nombre if licitacion.organismo else "",
        tipo_adquisicion=licitacion.tipo_adquisicion,
        descripcion_producto=licitacion.descripcion_producto,
    )


def _detectar_toxicas(
    conteo_exclusion: Counter, universo_post_inclusion: int
) -> list[tuple[str, int, float]]:
    """Port de _registrar_top_keywords: keywords que solas matan >umbral% del universo."""
    if universo_post_inclusion == 0:
        return []
    limite = (UMBRAL_EXCLUSION_TOXICA_PCT / 100.0) * universo_post_inclusion
    toxicas = [
        (kw, n, round(n / universo_post_inclusion * 100.0, 2))
        for kw, n in conteo_exclusion.items()
        if n >= limite
    ]
    toxicas.sort(key=lambda t: t[1], reverse=True)
    return toxicas


def evaluar_perfil(perfil: PerfilFiltro) -> ResultadoEvaluacion:
    """Evalúa TODAS las licitaciones contra un perfil y persiste EvaluacionFiltro.

    Upsert masivo por (licitacion, perfil): re-ejecutar tras cambiar reglas
    re-evalúa sin duplicar (R3). El llamador es dueño de la transacción (O3).
    """
    reglas = construir_reglas(perfil)
    resultado = ResultadoEvaluacion(perfil=perfil.codigo)
    conteo_resultados: Counter = Counter()
    conteo_exclusion: Counter = Counter()
    ahora = timezone.now()
    lote: list[EvaluacionFiltro] = []

    queryset = Licitacion.objects.select_related("organismo").prefetch_related("rubros")
    for licitacion in queryset.iterator(chunk_size=BATCH_EVALUACIONES):
        evaluacion = matching.evaluar(_campos_de(licitacion), reglas)
        conteo_resultados[evaluacion.resultado] += 1
        if evaluacion.confianza == matching.CONFIANZA_ALTA:
            resultado.confianza_alta += 1
        elif evaluacion.confianza == matching.CONFIANZA_REVISAR:
            resultado.confianza_revisar += 1
        for entrada in evaluacion.trazabilidad.get("exclusion", []):
            keyword = entrada.rsplit(" (", 1)[0]
            conteo_exclusion[keyword] += 1

        lote.append(
            EvaluacionFiltro(
                licitacion=licitacion,
                perfil=perfil,
                resultado=evaluacion.resultado,
                confianza=evaluacion.confianza,
                trazabilidad=evaluacion.trazabilidad,
                evaluada_en=ahora,
            )
        )
        resultado.total += 1
        if len(lote) >= BATCH_EVALUACIONES:
            _guardar_lote(lote)
            lote = []
    if lote:
        _guardar_lote(lote)

    universo_post_inclusion = resultado.total - conteo_resultados[matching.RESULTADO_SIN_MATCH]
    resultado.por_resultado = dict(conteo_resultados)
    resultado.top_keywords_exclusion = conteo_exclusion.most_common(10)
    resultado.exclusiones_toxicas = _detectar_toxicas(conteo_exclusion, universo_post_inclusion)
    return resultado


def _guardar_lote(lote: list[EvaluacionFiltro]) -> None:
    """Upsert por la constraint (licitacion, perfil): crea o actualiza en un viaje."""
    EvaluacionFiltro.objects.bulk_create(
        lote,
        update_conflicts=True,
        unique_fields=["licitacion", "perfil"],
        update_fields=["resultado", "confianza", "trazabilidad", "evaluada_en"],
    )


# Fallos de RED consecutivos que activan la pausa del circuit breaker (port etapa3).
CB_UMBRAL_FALLOS = 5
CB_PAUSA_SEGUNDOS = 60


@dataclass
class ResultadoEnriquecimiento:
    """Métricas de una corrida de enriquecimiento (O5)."""

    procesadas: int = 0
    enriquecidas: int = 0
    sin_datos: int = 0
    fallos_red: int = 0

    def como_dict(self) -> dict[str, object]:
        return {
            "procesadas": self.procesadas,
            "enriquecidas": self.enriquecidas,
            "sin_datos": self.sin_datos,
            "fallos_red": self.fallos_red,
        }


def licitaciones_pendientes_de_enriquecer() -> "QuerySet[Licitacion]":
    """Las relevantes para algún perfil que aún no tienen ficha de la API.

    La BD es el checkpoint: enriquecida_en vacío = pendiente. Interrumpir y
    relanzar el comando retoma exactamente donde quedó (O4), sin archivos JSONL.
    """
    return (
        Licitacion.objects.filter(
            enriquecida_en__isnull=True,
            evaluaciones__resultado__in=(
                EvaluacionFiltro.Resultado.INCLUIDA,
                EvaluacionFiltro.Resultado.BYPASS,
            ),
        )
        .distinct()
        .order_by("fecha_cierre", "codigo_externo")
    )


def enriquecer_licitaciones(
    licitaciones: "QuerySet[Licitacion]",
    cliente: "ClienteDetalleMP",
    delay_segundos: float,
    dormir: "Callable[[float], None]" = time.sleep,
) -> ResultadoEnriquecimiento:
    """Completa cada licitación con su ficha oficial, al ritmo que la API permite.

    Cada licitación se guarda apenas llega (el progreso parcial ES el objetivo:
    a ~8 req/min, esperar una transacción global significaría perder 35 minutos
    de trabajo ante cualquier corte — ver decisiones.md). Fallos de red activan
    el circuit breaker; "Listado vacío" es normal y solo se registra.
    """
    resultado = ResultadoEnriquecimiento()
    fallos_consecutivos = 0

    for licitacion in licitaciones.iterator(chunk_size=100):
        detalle = cliente.consultar(licitacion.codigo_externo)
        resultado.procesadas += 1

        if detalle.ok:
            _aplicar_detalle(licitacion, detalle.datos)
            resultado.enriquecidas += 1
            fallos_consecutivos = 0
        elif detalle.fallo_red:
            resultado.fallos_red += 1
            fallos_consecutivos += 1
            logger.warning(
                "Sin ficha para %s (%s); el proceso continúa.",
                licitacion.codigo_externo,
                detalle.error,
            )
            if fallos_consecutivos >= CB_UMBRAL_FALLOS:
                logger.warning(
                    "%s fallos de red consecutivos: pausa de %ss para que la API se recupere.",
                    fallos_consecutivos,
                    CB_PAUSA_SEGUNDOS,
                )
                dormir(CB_PAUSA_SEGUNDOS)
                cliente.renovar_sesion()
                fallos_consecutivos = 0
        else:
            # Sin datos en la API (no indexada): se marca para no reintentarla a diario.
            licitacion.raw_api = {"sin_datos": True, "motivo": detalle.error}
            licitacion.enriquecida_en = timezone.now()
            licitacion.save(update_fields=["raw_api", "enriquecida_en"])
            resultado.sin_datos += 1
            fallos_consecutivos = 0

        dormir(delay_segundos)

    return resultado


def _aplicar_detalle(licitacion: Licitacion, datos: dict) -> None:
    """Proyecta la ficha de la API sobre el modelo. La API manda sobre el bulk:
    es la fuente de detalle (montos y fechas del ciclo completo)."""
    licitacion.raw_api = datos
    licitacion.enriquecida_en = timezone.now()

    monto = _parsear_monto(datos.get("monto_estimado"))
    if monto is not None:
        licitacion.monto_estimado = monto
    moneda = str(datos.get("moneda") or "").strip().upper()
    if moneda in MONEDAS_CONOCIDAS:
        licitacion.moneda = moneda
    if datos.get("estado"):
        licitacion.estado_fuente = str(datos["estado"])[:60]
    if len(str(datos.get("descripcion") or "")) > len(licitacion.descripcion):
        licitacion.descripcion = str(datos["descripcion"])

    fechas = datos.get("fechas") or {}
    fecha_pub = _parsear_fecha(fechas.get("publicacion"))
    if fecha_pub is not None:
        licitacion.fecha_publicacion = fecha_pub
    fecha_cierre = _parsear_fecha_hora(fechas.get("cierre"))
    if fecha_cierre is not None:
        licitacion.fecha_cierre = fecha_cierre

    licitacion.save(
        update_fields=[
            "raw_api",
            "enriquecida_en",
            "monto_estimado",
            "moneda",
            "estado_fuente",
            "descripcion",
            "fecha_publicacion",
            "fecha_cierre",
        ]
    )

    comuna_region = datos.get("comprador") or {}
    if licitacion.organismo and not licitacion.organismo.region and comuna_region.get("region"):
        licitacion.organismo.region = str(comuna_region["region"])[:120]
        licitacion.organismo.save(update_fields=["region"])
