"""Servicios de licitaciones: orquestación entre adaptadores de ingesta y modelos.

Capa de servicios (P2): aquí vive la lógica de upsert. NUNCA escribe en
apps.gestion (P4): los hechos se refrescan, el trabajo humano no se toca.
"""

import datetime
import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from apps.catalogo.models import Organismo, Rubro
from apps.licitaciones.ingesta import FilaBulk
from apps.licitaciones.models import Licitacion
from apps.ops.models import EjecucionPipeline

logger = logging.getLogger(__name__)

MONEDAS_CONOCIDAS = frozenset(Licitacion.Moneda.values)


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

        # add(), no set(): el bulk trae una fila POR ITEM de la licitación, y la
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
