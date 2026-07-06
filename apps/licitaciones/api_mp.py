"""Adaptador ApiDetalleSource: la ficha completa de una licitación vía API oficial.

Puerto de salida hacia api.mercadopublico.cl (port de la etapa 3 del proyecto
original). Es el UNICO módulo que conoce el formato JSON de la API (P3); entrega
un dict estructurado con claves propias. Políticas de resiliencia portadas:
reintentos con backoff para 429/5xx/timeouts y renovación de sesión tras fallo
de red. El rate limit (P12) lo administra el servicio llamador, no este módulo.
"""

import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 40
MAX_REINTENTOS = 3
# Espera mínima antes de reintentar, por tipo de fallo (port de utils/http.py).
DELAY_MIN_SERVIDOR_S = 30.0
DELAY_MIN_RED_S = 15.0
DELAY_MIN_RATE_S = 60.0
STATUS_REINTENTABLES = frozenset({429, 500, 502, 503, 504})


@dataclass
class ResultadoDetalle:
    """Resultado de consultar el detalle de UNA licitación."""

    ok: bool
    datos: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    # Distingue fallos de red (cuentan para el circuit breaker) de respuestas
    # normales sin datos ("Listado vacío": la licitación no está indexada).
    fallo_red: bool = False


class ClienteDetalleMP:
    """Cliente del endpoint de detalle, con sesión renovable y reintentos."""

    def __init__(self, base_url: str, ticket: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._ticket = ticket
        self._session = self._nueva_sesion()

    @staticmethod
    def _nueva_sesion() -> requests.Session:
        sesion = requests.Session()
        sesion.headers.update(
            {
                "User-Agent": "licitaciones-mp-web/0.1 (Python/requests)",
                "Accept": "application/json",
            }
        )
        return sesion

    def renovar_sesion(self) -> None:
        """Tras un timeout la conexión TCP queda en estado indefinido: se descarta."""
        # Cerrar una sesión rota no puede fallar el proceso.
        with contextlib.suppress(Exception):
            self._session.close()
        self._session = self._nueva_sesion()

    def cerrar(self) -> None:
        self._session.close()

    def consultar(self, codigo_externo: str) -> ResultadoDetalle:
        """Trae y estructura la ficha de una licitación. No levanta excepciones."""
        url = f"{self._base_url}/licitaciones.json"
        params = {"codigo": codigo_externo, "ticket": self._ticket}

        intentos = 0
        while True:
            try:
                respuesta = self._session.get(url, params=params, timeout=TIMEOUT_SEGUNDOS)
                if respuesta.status_code not in STATUS_REINTENTABLES:
                    break
                if respuesta.status_code == 429:
                    retry_after = respuesta.headers.get("Retry-After", "")
                    espera = float(retry_after) if retry_after.isdigit() else DELAY_MIN_RATE_S
                    motivo = "límite de tasa (429)"
                else:
                    espera = DELAY_MIN_SERVIDOR_S * (2**intentos)
                    motivo = f"error del servidor ({respuesta.status_code})"
            except requests.Timeout:
                espera = DELAY_MIN_RED_S * (2**intentos)
                motivo = f"sin respuesta en {TIMEOUT_SEGUNDOS}s"
                self.renovar_sesion()
            except requests.RequestException as e:
                espera = DELAY_MIN_RED_S * (2**intentos)
                motivo = f"fallo de conexión: {e}"
                self.renovar_sesion()

            intentos += 1
            if intentos > MAX_REINTENTOS:
                return ResultadoDetalle(
                    ok=False,
                    error=f"API sin respuesta tras {MAX_REINTENTOS} reintentos ({motivo})",
                    fallo_red=True,
                )
            logger.warning(
                "API MP: %s. Reintento %s/%s en %.0fs", motivo, intentos, MAX_REINTENTOS, espera
            )
            time.sleep(espera)

        if respuesta.status_code >= 400:
            return ResultadoDetalle(ok=False, error=f"HTTP {respuesta.status_code}", fallo_red=True)
        try:
            data = respuesta.json()
        except ValueError as e:
            # Respuesta no-JSON: NO es fallo de red (no dispara circuit breaker).
            return ResultadoDetalle(ok=False, error=f"respuesta no-JSON: {e}")

        listado = data.get("Listado") if isinstance(data, dict) else None
        if not listado:
            # HTTP 200 sin datos: la licitación no está indexada en la API (normal).
            return ResultadoDetalle(ok=False, error="Listado vacío")

        return ResultadoDetalle(ok=True, datos=estructurar_detalle(listado[0]))


def estructurar_detalle(crudo: dict[str, Any]) -> dict[str, Any]:
    """Aplana la respuesta de la API al esquema propio (port de _procesar_respuesta_api).

    Este dict va integro a Licitacion.raw_api; el servicio ademas proyecta
    algunos valores a campos del modelo (monto, moneda, fechas, estado).
    """
    fechas = crudo.get("Fechas") or {}
    comprador = crudo.get("Comprador") or {}
    items_raw = crudo.get("Items") or {}
    listado_items = items_raw.get("Listado") or []
    adjuntos = crudo.get("Adjuntos") or {}

    items = [
        {
            "producto": it.get("NombreProducto", ""),
            "categoria": it.get("Categoria", ""),
            "descripcion": it.get("Descripcion", ""),
            "cantidad": it.get("Cantidad", ""),
        }
        for it in listado_items
    ]

    # La API entrega duración 0 cuando no aplica, y la unidad como código numérico
    # sin diccionario público confiable: se conserva solo una duración real.
    duracion = str(crudo.get("TiempoDuracionContrato") or "").strip()
    if duracion == "0":
        duracion = ""
    unidad_tiempo = str(crudo.get("UnidadTiempo") or "").strip()
    if not duracion:
        unidad_tiempo = ""

    return {
        "nombre": crudo.get("Nombre", ""),
        "descripcion": crudo.get("Descripcion", ""),
        "estado": crudo.get("Estado", ""),
        "codigo_estado": crudo.get("CodigoEstado", ""),
        "moneda": crudo.get("Moneda", ""),
        "monto_estimado": crudo.get("MontoEstimado", ""),
        "duracion_contrato": duracion,
        "unidad_tiempo_contrato": unidad_tiempo,
        # 0 = no es obra, 2 = es obra: distingue consultoría de ejecución.
        "es_obra": bool(crudo.get("Obras", 0)),
        "fechas": {
            "publicacion": fechas.get("FechaPublicacion", ""),
            "cierre": fechas.get("FechaCierre", ""),
            "inicio_preguntas": fechas.get("FechaInicio", ""),
            "final_preguntas": fechas.get("FechaFinal", ""),
            "publicacion_respuestas": fechas.get("FechaPubRespuestas", ""),
            "apertura_tecnica": fechas.get("FechaActoAperturaTecnica", ""),
            "apertura_economica": fechas.get("FechaActoAperturaEconomica", ""),
            "adjudicacion": fechas.get("FechaAdjudicacion", ""),
        },
        "comprador": {
            "unidad": comprador.get("NombreUnidad", ""),
            "region": comprador.get("RegionUnidad", ""),
            "comuna": comprador.get("ComunaUnidad", ""),
        },
        "items_total": len(items),
        "items": items,
        "adjuntos_total": len(adjuntos.get("Listado") or []),
    }
