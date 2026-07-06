"""Tests del comando evaluar: reglas en BD -> motor de dominio -> EvaluacionFiltro."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalogo.models import Rubro
from apps.licitaciones.models import EvaluacionFiltro
from apps.perfiles.models import PalabraIntencion, ReglaKeyword
from tests.factories import LicitacionFactory, PerfilFiltroFactory, ReglaKeywordFactory

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def perfil_telecom():
    """Perfil con las 4 clases de reglas, keywords ya normalizadas (como importar_pivot)."""
    perfil = PerfilFiltroFactory(codigo="TELECOM")
    ReglaKeywordFactory(
        perfil=perfil,
        tipo=ReglaKeyword.Tipo.INCLUIR,
        campo=ReglaKeyword.Campo.NOMBRE,
        texto="FIBRA OPTICA",
    )
    ReglaKeywordFactory(
        perfil=perfil,
        tipo=ReglaKeyword.Tipo.INCLUIR,
        campo=ReglaKeyword.Campo.NIVEL1,
        texto="CONSULTORIA",
    )
    ReglaKeywordFactory(
        perfil=perfil,
        tipo=ReglaKeyword.Tipo.EXCLUIR,
        campo=ReglaKeyword.Campo.NOMBRE,
        texto="PAVIMENTACION",
    )
    ReglaKeywordFactory(perfil=perfil, tipo=ReglaKeyword.Tipo.BYPASS, campo="", texto="SCADA")
    return perfil


def licitacion_con_nivel1(nombre: str, nivel1: str = ""):
    licitacion = LicitacionFactory(nombre=nombre)
    if nivel1:
        rubro, _ = Rubro.objects.get_or_create(nivel=1, nombre=nivel1)
        licitacion.rubros.add(rubro)
    return licitacion


def test_evalua_y_persiste_resultados(perfil_telecom) -> None:
    incluida = licitacion_con_nivel1("Tendido de fibra óptica regional")
    excluida = licitacion_con_nivel1("Pavimentación con fibra óptica incorporada")
    rescatada = licitacion_con_nivel1("Pavimentación ruta con fibra óptica y sistema SCADA")
    sin_match = licitacion_con_nivel1("Compra de escritorios")

    call_command("evaluar", "--equipo", "TELECOM")

    assert EvaluacionFiltro.objects.count() == 4
    resultados = {e.licitacion_id: e.resultado for e in EvaluacionFiltro.objects.all()}
    assert resultados[incluida.pk] == EvaluacionFiltro.Resultado.INCLUIDA
    assert resultados[excluida.pk] == EvaluacionFiltro.Resultado.EXCLUIDA
    assert resultados[rescatada.pk] == EvaluacionFiltro.Resultado.BYPASS
    assert resultados[sin_match.pk] == EvaluacionFiltro.Resultado.SIN_MATCH

    trazabilidad = EvaluacionFiltro.objects.get(licitacion=rescatada).trazabilidad
    assert "SCADA (nombre)" in trazabilidad["bypass"]


def test_reevaluar_tras_cambiar_reglas_actualiza_sin_duplicar(perfil_telecom) -> None:
    """R3/R6: cambiar reglas en el Admin y re-correr actualiza el resultado."""
    licitacion = licitacion_con_nivel1("Tendido de fibra óptica regional")
    call_command("evaluar", "--equipo", "TELECOM")
    assert EvaluacionFiltro.objects.get(licitacion=licitacion).resultado == (
        EvaluacionFiltro.Resultado.INCLUIDA
    )

    ReglaKeywordFactory(
        perfil=perfil_telecom,
        tipo=ReglaKeyword.Tipo.EXCLUIR,
        campo=ReglaKeyword.Campo.NOMBRE,
        texto="REGIONAL",
    )
    call_command("evaluar", "--equipo", "TELECOM")

    assert EvaluacionFiltro.objects.filter(licitacion=licitacion).count() == 1
    assert EvaluacionFiltro.objects.get(licitacion=licitacion).resultado == (
        EvaluacionFiltro.Resultado.EXCLUIDA
    )


def test_intencion_global_veta(perfil_telecom) -> None:
    PalabraIntencion.objects.create(tipo=PalabraIntencion.Tipo.VETADA, texto="ADQUISICION DE")
    vetada = licitacion_con_nivel1("Adquisición de fibra óptica en rollos")

    call_command("evaluar", "--equipo", "TELECOM")

    assert EvaluacionFiltro.objects.get(licitacion=vetada).resultado == (
        EvaluacionFiltro.Resultado.VETADA
    )


def test_dry_run_no_persiste_evaluaciones(perfil_telecom) -> None:
    licitacion_con_nivel1("Tendido de fibra óptica")

    call_command("evaluar", "--equipo", "TELECOM", "--dry-run")

    assert EvaluacionFiltro.objects.count() == 0


def test_equipo_inexistente_falla_accionable(perfil_telecom) -> None:
    with pytest.raises(CommandError, match="TELECOM"):
        call_command("evaluar", "--equipo", "NOEXISTE")


def test_sin_perfiles_con_inclusion_falla_accionable() -> None:
    PerfilFiltroFactory(codigo="VACIO")
    with pytest.raises(CommandError, match="inclusi"):
        call_command("evaluar")
