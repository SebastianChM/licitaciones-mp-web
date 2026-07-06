"""Tests del enriquecimiento: mapeo de la ficha, checkpoint en BD y circuit breaker.

El cliente de la API se inyecta como stub (O13: los tests no tocan la red).
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.licitaciones.api_mp import ResultadoDetalle, estructurar_detalle
from apps.licitaciones.models import EvaluacionFiltro, Licitacion
from apps.licitaciones.services import (
    CB_PAUSA_SEGUNDOS,
    CB_UMBRAL_FALLOS,
    enriquecer_licitaciones,
    licitaciones_pendientes_de_enriquecer,
)
from tests.factories import EvaluacionFiltroFactory, LicitacionFactory

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

RESPUESTA_API_SINTETICA = {
    "Nombre": "Consultoría de tránsito",
    "Descripcion": "Descripción larga y detallada que viene de la API oficial",
    "Estado": "Publicada",
    "CodigoEstado": 5,
    "Moneda": "CLP",
    "MontoEstimado": 25000000,
    "TiempoDuracionContrato": "12",
    "UnidadTiempo": "Meses",
    "Obras": 0,
    "Fechas": {
        "FechaPublicacion": "2026-07-01T09:00:00",
        "FechaCierre": "2026-07-20T15:00:00",
        "FechaAdjudicacion": "2026-08-15T12:00:00",
    },
    "Comprador": {
        "NombreUnidad": "Dirección de Vialidad",
        "RegionUnidad": "Región del Biobío",
        "ComunaUnidad": "Concepción",
    },
    "Items": {
        "Listado": [
            {"NombreProducto": "Servicios de ingeniería de tránsito", "Categoria": "81101500"},
            {"NombreProducto": "Estudios de demanda", "Categoria": "81101600"},
        ]
    },
    "Adjuntos": {"Listado": [{"Nombre": "bases.pdf"}]},
}


class ClienteFalso:
    """Stub del cliente de la API: respuestas programadas por código externo."""

    def __init__(self, respuestas: dict[str, ResultadoDetalle]) -> None:
        self.respuestas = respuestas
        self.renovaciones = 0

    def consultar(self, codigo_externo: str) -> ResultadoDetalle:
        return self.respuestas.get(
            codigo_externo, ResultadoDetalle(ok=False, error="Listado vacío")
        )

    def renovar_sesion(self) -> None:
        self.renovaciones += 1


def licitacion_relevante(**kwargs) -> Licitacion:
    evaluacion = EvaluacionFiltroFactory(
        resultado=EvaluacionFiltro.Resultado.INCLUIDA, licitacion=LicitacionFactory(**kwargs)
    )
    return evaluacion.licitacion


class TestEstructurarDetalle:
    def test_aplana_la_respuesta_anidada(self) -> None:
        datos = estructurar_detalle(RESPUESTA_API_SINTETICA)

        assert datos["estado"] == "Publicada"
        assert datos["fechas"]["adjudicacion"] == "2026-08-15T12:00:00"
        assert datos["comprador"]["comuna"] == "Concepción"
        assert datos["items_total"] == 2
        assert datos["items"][0]["producto"] == "Servicios de ingeniería de tránsito"
        assert datos["es_obra"] is False
        assert datos["adjuntos_total"] == 1


class TestPendientes:
    def test_solo_relevantes_sin_enriquecer(self) -> None:
        pendiente = licitacion_relevante()
        EvaluacionFiltroFactory(resultado=EvaluacionFiltro.Resultado.EXCLUIDA)  # no relevante
        ya_lista = licitacion_relevante()
        ya_lista.enriquecida_en = ya_lista.created_at
        ya_lista.save(update_fields=["enriquecida_en"])

        assert list(licitaciones_pendientes_de_enriquecer()) == [pendiente]


class TestEnriquecer:
    def test_ficha_ok_proyecta_campos_y_marca_checkpoint(self) -> None:
        licitacion = licitacion_relevante(descripcion="corta")
        cliente = ClienteFalso(
            {
                licitacion.codigo_externo: ResultadoDetalle(
                    ok=True, datos=estructurar_detalle(RESPUESTA_API_SINTETICA)
                )
            }
        )

        resultado = enriquecer_licitaciones(
            licitaciones_pendientes_de_enriquecer(), cliente, 0, dormir=lambda _s: None
        )

        licitacion.refresh_from_db()
        assert resultado.enriquecidas == 1
        assert licitacion.enriquecida_en is not None
        assert licitacion.monto_estimado == 25000000
        assert licitacion.estado_fuente == "Publicada"
        assert "API oficial" in licitacion.descripcion
        assert licitacion.raw_api["comprador"]["unidad"] == "Dirección de Vialidad"
        # Ya no está pendiente: la BD es el checkpoint.
        assert licitaciones_pendientes_de_enriquecer().count() == 0

    def test_sin_datos_se_marca_para_no_reintentar_a_diario(self) -> None:
        licitacion = licitacion_relevante()
        cliente = ClienteFalso({})  # todo responde "Listado vacío"

        resultado = enriquecer_licitaciones(
            licitaciones_pendientes_de_enriquecer(), cliente, 0, dormir=lambda _s: None
        )

        licitacion.refresh_from_db()
        assert resultado.sin_datos == 1
        assert licitacion.raw_api["sin_datos"] is True
        assert licitaciones_pendientes_de_enriquecer().count() == 0

    def test_fallo_de_red_deja_pendiente_y_activa_circuit_breaker(self) -> None:
        for _ in range(CB_UMBRAL_FALLOS):
            licitacion_relevante()
        fallo = ResultadoDetalle(ok=False, error="timeout", fallo_red=True)
        cliente = ClienteFalso(
            dict.fromkeys(
                licitaciones_pendientes_de_enriquecer().values_list("codigo_externo", flat=True),
                fallo,
            )
        )
        pausas: list[float] = []

        resultado = enriquecer_licitaciones(
            licitaciones_pendientes_de_enriquecer(), cliente, 0, dormir=pausas.append
        )

        assert resultado.fallos_red == CB_UMBRAL_FALLOS
        # Nada se marcó: siguen pendientes para la próxima corrida (checkpoint en BD).
        assert licitaciones_pendientes_de_enriquecer().count() == CB_UMBRAL_FALLOS
        assert CB_PAUSA_SEGUNDOS in pausas
        assert cliente.renovaciones == 1


def test_comando_sin_ticket_falla_accionable(settings) -> None:
    settings.MERCADO_PUBLICO_TICKET = ""
    with pytest.raises(CommandError, match="LICITAWEB_MERCADO_PUBLICO_TICKET"):
        call_command("enriquecer")
