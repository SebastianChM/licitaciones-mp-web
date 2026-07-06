"""Tests del self-service: CRUD de búsquedas y reglas desde la página, con aislamiento.

Nada de este flujo toca Excel ni comandos: es el pivote de producto de
decisiones.md (2026-07-06).
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.licitaciones.models import EvaluacionFiltro
from apps.perfiles.models import PerfilFiltro, ReglaKeyword
from tests.factories import LicitacionFactory, PerfilFiltroFactory, ReglaKeywordFactory

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def usuario():
    return get_user_model().objects.create_user(username="ana", password="clave!segura1")


@pytest.fixture
def cliente(usuario) -> Client:
    cliente_web = Client()
    cliente_web.force_login(usuario)
    return cliente_web


@pytest.fixture
def intruso() -> Client:
    otro = get_user_model().objects.create_user(username="intruso", password="clave!segura1")
    cliente_web = Client()
    cliente_web.force_login(otro)
    return cliente_web


class TestCrearBusqueda:
    def test_crea_con_dueno_y_codigo_generado(self, cliente, usuario) -> None:
        respuesta = cliente.post(
            "/busquedas/nueva/", {"nombre": "Fibra óptica y redes", "descripcion": ""}
        )

        busqueda = PerfilFiltro.objects.get()
        assert respuesta.status_code == 302
        assert respuesta["Location"].endswith(f"/busquedas/{busqueda.codigo}/reglas/")
        assert busqueda.propietario == usuario
        assert busqueda.codigo == "FIBRAOPTICAYREDES"

    def test_codigos_no_chocan(self, cliente) -> None:
        cliente.post("/busquedas/nueva/", {"nombre": "Redes"})
        cliente.post("/busquedas/nueva/", {"nombre": "redes"})

        codigos = set(PerfilFiltro.objects.values_list("codigo", flat=True))
        assert codigos == {"REDES", "REDES2"}


class TestReglas:
    def test_agregar_normaliza_como_el_import(self, cliente, usuario) -> None:
        busqueda = PerfilFiltroFactory(codigo="REDES", propietario=usuario)

        cliente.post(
            "/busquedas/REDES/reglas/",
            {"texto": "  fibra óptica ", "tipo": "incluir", "campo": "nombre"},
        )

        regla = busqueda.reglas.get()
        assert regla.texto == "FIBRA OPTICA"
        assert regla.tipo == ReglaKeyword.Tipo.INCLUIR

    def test_incluir_sin_campo_es_rechazada(self, cliente, usuario) -> None:
        busqueda = PerfilFiltroFactory(codigo="REDES", propietario=usuario)

        cliente.post("/busquedas/REDES/reglas/", {"texto": "fibra", "tipo": "incluir", "campo": ""})

        assert busqueda.reglas.count() == 0

    def test_eliminar_regla(self, cliente, usuario) -> None:
        busqueda = PerfilFiltroFactory(codigo="REDES", propietario=usuario)
        regla = ReglaKeywordFactory(perfil=busqueda, tipo=ReglaKeyword.Tipo.INCLUIR)

        respuesta = cliente.post(f"/busquedas/REDES/reglas/{regla.pk}/eliminar/")

        assert respuesta.status_code == 302
        assert busqueda.reglas.count() == 0


class TestEvaluarDesdeLaPagina:
    def test_evaluar_ahora_crea_evaluaciones_sin_comandos(self, cliente, usuario) -> None:
        busqueda = PerfilFiltroFactory(codigo="REDES", propietario=usuario)
        ReglaKeywordFactory(
            perfil=busqueda,
            tipo=ReglaKeyword.Tipo.INCLUIR,
            campo=ReglaKeyword.Campo.NOMBRE,
            texto="FIBRA",
        )
        relevante = LicitacionFactory(nombre="Tendido de fibra en La Serena")
        LicitacionFactory(nombre="Compra de escritorios")

        respuesta = cliente.post("/busquedas/REDES/evaluar/")

        assert respuesta.status_code == 302
        evaluacion = EvaluacionFiltro.objects.get(licitacion=relevante, perfil=busqueda)
        assert evaluacion.resultado == EvaluacionFiltro.Resultado.INCLUIDA
        assert EvaluacionFiltro.objects.count() == 2  # también la sin_match queda registrada

    def test_evaluar_sin_reglas_de_inclusion_avisa_en_vez_de_correr(self, cliente, usuario) -> None:
        PerfilFiltroFactory(codigo="VACIA", propietario=usuario)
        LicitacionFactory()

        respuesta = cliente.post("/busquedas/VACIA/evaluar/", follow=True)

        assert EvaluacionFiltro.objects.count() == 0
        assert "regla de inclusión" in respuesta.content.decode()


class TestAislamiento:
    """Cada usuario ve y toca SOLO sus búsquedas: lo ajeno responde 404."""

    def test_reglas_de_otro_usuario_son_404(self, cliente, intruso, usuario) -> None:
        PerfilFiltroFactory(codigo="MIA", propietario=usuario)

        assert intruso.get("/busquedas/MIA/reglas/").status_code == 404
        assert intruso.post("/busquedas/MIA/evaluar/").status_code == 404
        assert intruso.post("/busquedas/MIA/eliminar/").status_code == 404
        assert cliente.get("/busquedas/MIA/reglas/").status_code == 200

    def test_sidebar_no_lista_busquedas_ajenas(self, intruso, usuario) -> None:
        PerfilFiltroFactory(codigo="MIA", nombre="Busqueda Privada", propietario=usuario)

        respuesta = intruso.get("/")

        assert "Busqueda Privada" not in respuesta.content.decode()


def test_eliminar_busqueda_borra_en_cascada(cliente, usuario) -> None:
    busqueda = PerfilFiltroFactory(codigo="REDES", propietario=usuario)
    ReglaKeywordFactory(perfil=busqueda, tipo=ReglaKeyword.Tipo.INCLUIR)

    respuesta = cliente.post("/busquedas/REDES/eliminar/")

    assert respuesta.status_code == 302
    assert PerfilFiltro.objects.count() == 0
    assert ReglaKeyword.objects.count() == 0
