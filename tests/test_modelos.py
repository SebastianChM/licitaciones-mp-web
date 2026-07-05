"""Tests de modelos: constraints que sostienen las invariantes del PLAN.md.

Prueban comportamiento (unicidad, semántica de relevancia), no implementación.
"""

import pytest
from django.db import IntegrityError

from apps.licitaciones.models import EvaluacionFiltro
from tests.factories import (
    EvaluacionFiltroFactory,
    GestionLicitacionFactory,
    LicitacionFactory,
    PerfilFiltroFactory,
    ReglaKeywordFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


class TestLicitacion:
    def test_codigo_externo_es_unico(self) -> None:
        """La idempotencia de la ingesta (O4) depende de esta constraint."""
        LicitacionFactory(codigo_externo="1234-56-L126")
        with pytest.raises(IntegrityError):
            LicitacionFactory(codigo_externo="1234-56-L126")


class TestEvaluacionFiltro:
    def test_una_sola_evaluacion_por_licitacion_y_perfil(self) -> None:
        """R3: el resultado es por (licitacion, perfil); re-evaluar actualiza, no duplica."""
        evaluacion = EvaluacionFiltroFactory()
        with pytest.raises(IntegrityError):
            EvaluacionFiltroFactory(licitacion=evaluacion.licitacion, perfil=evaluacion.perfil)

    def test_misma_licitacion_evaluable_por_varios_equipos(self) -> None:
        licitacion = LicitacionFactory()
        primera = EvaluacionFiltroFactory(licitacion=licitacion)
        segunda = EvaluacionFiltroFactory(
            licitacion=licitacion,
            resultado=EvaluacionFiltro.Resultado.EXCLUIDA,
        )
        assert primera.perfil != segunda.perfil
        assert licitacion.evaluaciones.count() == 2

    @pytest.mark.parametrize(
        ("resultado", "esperado"),
        [
            (EvaluacionFiltro.Resultado.INCLUIDA, True),
            (EvaluacionFiltro.Resultado.BYPASS, True),
            (EvaluacionFiltro.Resultado.EXCLUIDA, False),
            (EvaluacionFiltro.Resultado.EXCLUSION_DURA, False),
            (EvaluacionFiltro.Resultado.VETADA, False),
            (EvaluacionFiltro.Resultado.SIN_MATCH, False),
        ],
    )
    def test_es_relevante_refleja_la_semantica_del_filtrado(
        self, resultado: str, esperado: bool
    ) -> None:
        """Incluida y bypass son las dos vias de entrada al reporte del equipo."""
        evaluacion = EvaluacionFiltroFactory(resultado=resultado)
        assert evaluacion.es_relevante is esperado


class TestGestionLicitacion:
    def test_una_gestion_por_licitacion_y_equipo(self) -> None:
        gestion = GestionLicitacionFactory()
        with pytest.raises(IntegrityError):
            GestionLicitacionFactory(licitacion=gestion.licitacion, perfil=gestion.perfil)

    def test_dos_equipos_gestionan_la_misma_licitacion_sin_pisarse(self) -> None:
        """R4: lo que los archivos Excel por equipo no podian expresar."""
        licitacion = LicitacionFactory()
        gestion_a = GestionLicitacionFactory(licitacion=licitacion)
        gestion_b = GestionLicitacionFactory(licitacion=licitacion)
        assert gestion_a.perfil != gestion_b.perfil
        assert licitacion.gestiones.count() == 2


class TestReglaKeyword:
    def test_regla_duplicada_en_mismo_perfil_rechazada(self) -> None:
        regla = ReglaKeywordFactory(texto="fibra optica")
        with pytest.raises(IntegrityError):
            ReglaKeywordFactory(
                perfil=regla.perfil, texto="fibra optica", tipo=regla.tipo, campo=regla.campo
            )

    def test_misma_keyword_permitida_en_perfiles_distintos(self) -> None:
        regla = ReglaKeywordFactory(texto="scada")
        otro_perfil = PerfilFiltroFactory()
        otra = ReglaKeywordFactory(
            perfil=otro_perfil, texto="scada", tipo=regla.tipo, campo=regla.campo
        )
        assert otra.pk != regla.pk
