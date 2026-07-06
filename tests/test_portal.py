"""Tests del portal web: acceso, render de lista/detalle y panel de gestión."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.gestion.models import GestionLicitacion
from apps.licitaciones.models import EvaluacionFiltro
from apps.perfiles.models import ReglaKeyword
from tests.factories import (
    EvaluacionFiltroFactory,
    LicitacionFactory,
    PerfilFiltroFactory,
    ReglaKeywordFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def usuario():
    return get_user_model().objects.create_user(username="comercial", password="clave!segura1")


@pytest.fixture
def cliente(usuario) -> Client:
    cliente_web = Client()
    cliente_web.force_login(usuario)
    return cliente_web


@pytest.fixture
def perfil_operable(usuario):
    """Una búsqueda del usuario con regla de inclusión (el portal solo muestra las propias)."""
    perfil = PerfilFiltroFactory(codigo="TELECOM", nombre="Telecomunicaciones", propietario=usuario)
    ReglaKeywordFactory(perfil=perfil, tipo=ReglaKeyword.Tipo.INCLUIR, texto="FIBRA")
    return perfil


def test_portal_exige_login() -> None:
    respuesta = Client().get("/")
    assert respuesta.status_code == 302
    assert "/accounts/login/" in respuesta["Location"]


def test_lista_muestra_solo_relevantes_del_equipo(cliente, perfil_operable) -> None:
    relevante = EvaluacionFiltroFactory(
        perfil=perfil_operable,
        resultado=EvaluacionFiltro.Resultado.INCLUIDA,
        confianza=EvaluacionFiltro.Confianza.ALTA,
    )
    EvaluacionFiltroFactory(perfil=perfil_operable, resultado=EvaluacionFiltro.Resultado.EXCLUIDA)

    respuesta = cliente.get("/", {"equipo": "TELECOM"})

    assert respuesta.status_code == 200
    contenido = respuesta.content.decode()
    assert relevante.licitacion.codigo_externo in contenido
    assert respuesta.context["stats"]["total"] == 1
    assert respuesta.context["stats"]["alta"] == 1


def test_filtro_de_confianza(cliente, perfil_operable) -> None:
    alta = EvaluacionFiltroFactory(
        perfil=perfil_operable,
        resultado=EvaluacionFiltro.Resultado.INCLUIDA,
        confianza=EvaluacionFiltro.Confianza.ALTA,
    )
    revisar = EvaluacionFiltroFactory(
        perfil=perfil_operable,
        resultado=EvaluacionFiltro.Resultado.BYPASS,
        confianza=EvaluacionFiltro.Confianza.REVISAR,
    )

    respuesta = cliente.get("/", {"equipo": "TELECOM", "confianza": "alta"})

    contenido = respuesta.content.decode()
    assert alta.licitacion.codigo_externo in contenido
    assert revisar.licitacion.codigo_externo not in contenido


def test_detalle_muestra_trazabilidad(cliente, perfil_operable) -> None:
    evaluacion = EvaluacionFiltroFactory(
        perfil=perfil_operable,
        resultado=EvaluacionFiltro.Resultado.BYPASS,
        trazabilidad={
            "inclusion": ["FIBRA OPTICA (nombre)"],
            "exclusion": ["CONSTRUCCION (nombre)"],
            "bypass": ["SCADA (nombre)"],
        },
    )

    respuesta = cliente.get(
        f"/licitacion/{evaluacion.licitacion.codigo_externo}/", {"equipo": "TELECOM"}
    )

    contenido = respuesta.content.decode()
    assert "FIBRA OPTICA (nombre)" in contenido
    assert "CONSTRUCCION (nombre)" in contenido
    assert "SCADA (nombre)" in contenido
    assert "Rescatada por bypass" in contenido


def test_guardar_gestion_registra_autor_y_asignacion(cliente, usuario, perfil_operable) -> None:
    licitacion = LicitacionFactory()

    respuesta = cliente.post(
        f"/licitacion/{licitacion.codigo_externo}/gestion/",
        {"equipo": "TELECOM", "estado": "en_revision", "notas": "Pedir bases técnicas"},
    )

    assert respuesta.status_code == 302
    gestion = GestionLicitacion.objects.get(licitacion=licitacion, perfil=perfil_operable)
    assert gestion.estado == GestionLicitacion.Estado.EN_REVISION
    assert gestion.notas == "Pedir bases técnicas"
    assert gestion.actualizado_por == usuario
    assert gestion.asignado_a == usuario


def test_actualizar_gestion_existente_no_duplica(cliente, perfil_operable) -> None:
    licitacion = LicitacionFactory()
    url = f"/licitacion/{licitacion.codigo_externo}/gestion/"
    cliente.post(url, {"equipo": "TELECOM", "estado": "en_revision", "notas": ""})

    cliente.post(url, {"equipo": "TELECOM", "estado": "presentada", "notas": "Enviada"})

    assert GestionLicitacion.objects.filter(licitacion=licitacion).count() == 1
    assert (
        GestionLicitacion.objects.get(licitacion=licitacion).estado
        == GestionLicitacion.Estado.PRESENTADA
    )


def test_lista_sin_n_mas_uno(cliente, perfil_operable, django_assert_max_num_queries) -> None:
    for _ in range(12):
        EvaluacionFiltroFactory(
            perfil=perfil_operable, resultado=EvaluacionFiltro.Resultado.INCLUIDA
        )
    # Presupuesto holgado pero constante: sesión+usuario, perfiles, stats (4),
    # count paginación, página, gestiones.
    with django_assert_max_num_queries(12):
        respuesta = cliente.get("/", {"equipo": "TELECOM"})
    assert respuesta.status_code == 200
