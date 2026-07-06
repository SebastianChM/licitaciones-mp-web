"""Tests del motor de matching: paridad semántica con la etapa 2 original (O2).

Los casos provienen de tests/unit/test_filtrado.py y test_intencion_gate.py del
proyecto Licitaciones_MP, reescritos contra el dominio puro (sin pandas ni BD).
"""

import pytest

from domain.matching import (
    CONFIANZA_ALTA,
    CONFIANZA_NO_APLICA,
    CONFIANZA_REVISAR,
    RESULTADO_BYPASS,
    RESULTADO_EXCLUIDA,
    RESULTADO_EXCLUSION_DURA,
    RESULTADO_INCLUIDA,
    RESULTADO_SIN_MATCH,
    RESULTADO_VETADA,
    CamposLicitacion,
    Evaluacion,
    ReglasEquipo,
    evaluar,
)

pytestmark = pytest.mark.unit


def reglas(**kwargs) -> ReglasEquipo:
    """Atajo: reglas ya normalizadas (como las entrega la capa de servicios)."""
    return ReglasEquipo(**kwargs)


class TestInclusion:
    def test_incluye_por_keyword_en_nombre(self) -> None:
        evaluacion = evaluar(
            CamposLicitacion(nombre="Consultoría en gestión de proyectos TI"),
            reglas(incluir={"nombre": ("CONSULTORIA",)}),
        )
        assert evaluacion.resultado == RESULTADO_INCLUIDA
        assert "CONSULTORIA (nombre)" in evaluacion.trazabilidad["inclusion"]

    def test_incluye_por_nivel1(self) -> None:
        evaluacion = evaluar(
            CamposLicitacion(nombre="Cualquier cosa", nivel1="Servicios"),
            reglas(incluir={"nivel1": ("SERVICIOS",)}),
        )
        assert evaluacion.resultado == RESULTADO_INCLUIDA

    def test_keyword_con_acento_matchea_texto_acentuado(self) -> None:
        """El original normaliza ambos lados: 'consultoria' matchea 'Consultoría'."""
        evaluacion = evaluar(
            CamposLicitacion(nombre="Consultoría en gestión"),
            reglas(incluir={"nombre": ("CONSULTORIA",)}),
        )
        assert evaluacion.resultado == RESULTADO_INCLUIDA

    def test_sin_reglas_de_inclusion_no_matchea(self) -> None:
        evaluacion = evaluar(
            CamposLicitacion(nombre="Consultoría TI"),
            reglas(incluir={"nombre": ()}),
        )
        assert evaluacion.resultado == RESULTADO_SIN_MATCH

    def test_boundary_sigla_corta_no_matchea_dentro_de_palabra(self) -> None:
        """'ITO' capturaba 'circuITO' en versiones viejas del original."""
        r = reglas(incluir={"nombre": ("ITO",)})
        assert evaluar(CamposLicitacion(nombre="Reparación de circuito"), r).resultado == (
            RESULTADO_SIN_MATCH
        )
        assert evaluar(CamposLicitacion(nombre="Servicio ITO obra vial"), r).resultado == (
            RESULTADO_INCLUIDA
        )

    def test_descripcion_solo_acepta_frases(self) -> None:
        """En texto libre, keywords de una palabra generan ruido: solo frases."""
        r = reglas(incluir={"nombre": ("SISTEMA", "SISTEMA DE MONITOREO")})
        sin_frase = evaluar(CamposLicitacion(descripcion="incluye sistema central"), r)
        assert sin_frase.resultado == RESULTADO_SIN_MATCH
        con_frase = evaluar(CamposLicitacion(descripcion="incluye sistema de monitoreo remoto"), r)
        assert con_frase.resultado == RESULTADO_INCLUIDA

    def test_keywords_con_caracteres_de_regex_no_rompen(self) -> None:
        evaluacion = evaluar(
            CamposLicitacion(nombre="Servicio (consultoría) TI+"),
            reglas(incluir={"nombre": ("(CONSULTORIA)", "TI+")}),
        )
        assert isinstance(evaluacion, Evaluacion)
        assert evaluacion.resultado == RESULTADO_INCLUIDA


class TestExclusionYBypass:
    def test_exclusion_por_nombre(self) -> None:
        evaluacion = evaluar(
            CamposLicitacion(nombre="Construcción de escuela con sistema TI"),
            reglas(incluir={"nombre": ("SISTEMA",)}, excluir={"nombre": ("CONSTRUCCION",)}),
        )
        assert evaluacion.resultado == RESULTADO_EXCLUIDA
        assert "CONSTRUCCION (nombre)" in evaluacion.trazabilidad["exclusion"]

    def test_exclusion_por_organismo(self) -> None:
        evaluacion = evaluar(
            CamposLicitacion(nombre="Sistema de gestión", organismo="Hospital de Prueba"),
            reglas(incluir={"nombre": ("SISTEMA",)}, excluir={"organismo": ("HOSPITAL",)}),
        )
        assert evaluacion.resultado == RESULTADO_EXCLUIDA

    def test_sin_match_de_exclusion_queda_incluida(self) -> None:
        evaluacion = evaluar(
            CamposLicitacion(nombre="Consultoría en gestión de proyectos TI"),
            reglas(incluir={"nombre": ("CONSULTORIA",)}, excluir={"nombre": ("CONSTRUCCION",)}),
        )
        assert evaluacion.resultado == RESULTADO_INCLUIDA

    def test_bypass_rescata_excluida(self) -> None:
        """Caso portado tal cual: excluida por 'construccion', rescatada por 'corfo'."""
        evaluacion = evaluar(
            CamposLicitacion(nombre="Construcción instalaciones CORFO", nivel1="Obras"),
            reglas(
                incluir={"nombre": ("INSTALACIONES",)},
                excluir={"nombre": ("CONSTRUCCION",)},
                bypass=("CORFO",),
            ),
        )
        assert evaluacion.resultado == RESULTADO_BYPASS
        assert evaluacion.es_relevante is True
        assert "CORFO (nombre)" in evaluacion.trazabilidad["bypass"]

    def test_bypass_no_mira_organismo(self) -> None:
        """Decisión del original: bypass solo en nombre/descripción."""
        evaluacion = evaluar(
            CamposLicitacion(nombre="Construcción de sede", organismo="CORFO"),
            reglas(
                incluir={"nombre": ("SEDE",)},
                excluir={"nombre": ("CONSTRUCCION",)},
                bypass=("CORFO",),
            ),
        )
        assert evaluacion.resultado == RESULTADO_EXCLUIDA

    def test_bypass_sigla_corta_exige_palabra_completa(self) -> None:
        """'WAN' no debe rescatar 'WANDERSLEBEN' (comentario literal del original)."""
        r = reglas(
            incluir={"nombre": ("SERVICIO",)},
            excluir={"nombre": ("COMPRA",)},
            bypass=("WAN",),
        )
        no_rescatada = evaluar(CamposLicitacion(nombre="Compra servicio sede WANDERSLEBEN"), r)
        assert no_rescatada.resultado == RESULTADO_EXCLUIDA
        rescatada = evaluar(CamposLicitacion(nombre="Compra servicio enlace WAN"), r)
        assert rescatada.resultado == RESULTADO_BYPASS


class TestExclusionDura:
    def test_bloquea_incluso_rescatadas_por_bypass(self) -> None:
        evaluacion = evaluar(
            CamposLicitacion(nombre="Construcción CORFO", nivel1="Alimentación"),
            reglas(
                incluir={"nombre": ("CORFO",)},
                excluir={"nombre": ("CONSTRUCCION",)},
                bypass=("CORFO",),
                exclusion_dura=("ALIMENTACION",),
            ),
        )
        assert evaluacion.resultado == RESULTADO_EXCLUSION_DURA
        assert evaluacion.es_relevante is False

    def test_solo_aplica_sobre_nivel1_y_nivel2(self) -> None:
        evaluacion = evaluar(
            CamposLicitacion(nombre="Servicio de alimentación TI", nivel1="Servicios"),
            reglas(incluir={"nombre": ("SERVICIO",)}, exclusion_dura=("ALIMENTACION",)),
        )
        assert evaluacion.resultado == RESULTADO_INCLUIDA


class TestIntentGate:
    """Las 4 ramas semánticas del original + boundary + boost UNSPSC."""

    def test_deshabilitado_marca_no_aplica(self) -> None:
        evaluacion = evaluar(
            CamposLicitacion(nombre="Cualquier cosa con sistema"),
            reglas(incluir={"nombre": ("SISTEMA",)}),
        )
        assert evaluacion.resultado == RESULTADO_INCLUIDA
        assert evaluacion.confianza == CONFIANZA_NO_APLICA

    def test_vetada_descarta(self) -> None:
        evaluacion = evaluar(
            CamposLicitacion(nombre="Adquisición de computadores"),
            reglas(
                incluir={"nombre": ("COMPUTADORES",)},
                intencion_vetada=("ADQUISICION DE",),
            ),
        )
        assert evaluacion.resultado == RESULTADO_VETADA

    def test_vetada_tambien_evalua_descripcion(self) -> None:
        evaluacion = evaluar(
            CamposLicitacion(nombre="Servicio ABC", descripcion="Incluye mantención de equipos"),
            reglas(incluir={"nombre": ("SERVICIO",)}, intencion_vetada=("MANTENCION",)),
        )
        assert evaluacion.resultado == RESULTADO_VETADA

    def test_requerida_marca_alta_y_zona_gris_revisar(self) -> None:
        r = reglas(
            incluir={"nombre": ("RED", "ALGO AMBIGUO")},
            intencion_requerida=("INGENIERIA", "CONSULTORIA"),
        )
        alta = evaluar(CamposLicitacion(nombre="Ingeniería conceptual de red"), r)
        assert (alta.resultado, alta.confianza) == (RESULTADO_INCLUIDA, CONFIANZA_ALTA)
        gris = evaluar(CamposLicitacion(nombre="Algo ambiguo de red"), r)
        assert (gris.resultado, gris.confianza) == (RESULTADO_INCLUIDA, CONFIANZA_REVISAR)

    def test_palabra_suelta_vetada_exige_palabra_completa(self) -> None:
        """'COMPRA' no debe vetar 'COMPRAVENTA' (boundary en palabras sueltas)."""
        r = reglas(incluir={"nombre": ("SERVICIO",)}, intencion_vetada=("COMPRA",))
        no_vetada = evaluar(CamposLicitacion(nombre="Servicio de compraventa"), r)
        assert no_vetada.resultado == RESULTADO_INCLUIDA
        vetada = evaluar(CamposLicitacion(nombre="Servicio de compra directa"), r)
        assert vetada.resultado == RESULTADO_VETADA

    def test_boost_unspsc_nivel1_eleva_revisar_a_alta(self) -> None:
        evaluacion = evaluar(
            CamposLicitacion(nombre="Estudio de demanda vial", nivel1="Consultoría"),
            reglas(incluir={"nombre": ("ESTUDIO",)}, intencion_requerida=("INGENIERIA",)),
        )
        assert evaluacion.confianza == CONFIANZA_ALTA

    def test_boost_unspsc_nivel2_dispara_con_texto_desacentuado(self) -> None:
        """Corrección al original: sus constantes N2 con acentos no podían matchear
        contra texto normalizado; aquí el boost N2 sí funciona."""
        evaluacion = evaluar(
            CamposLicitacion(
                nombre="Estudio de demanda",
                nivel2="Servicios profesionales de ingeniería",
            ),
            reglas(incluir={"nombre": ("ESTUDIO",)}, intencion_requerida=("CONSULTORIA",)),
        )
        assert evaluacion.confianza == CONFIANZA_ALTA
