"""Tests de la API REST: auth, filtros por evaluación, incremental y gestión."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.gestion.models import GestionLicitacion
from apps.licitaciones.models import EvaluacionFiltro
from apps.ops.models import EjecucionPipeline
from tests.factories import (
    EvaluacionFiltroFactory,
    LicitacionFactory,
    PerfilFiltroFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def usuario():
    return get_user_model().objects.create_user(username="analista", password="clave!segura1")


@pytest.fixture
def cliente(usuario) -> APIClient:
    cliente_api = APIClient()
    cliente_api.force_authenticate(user=usuario)
    return cliente_api


class TestAutenticacion:
    def test_api_cerrada_sin_credenciales(self) -> None:
        """P11: ningún endpoint responde datos sin autenticación."""
        anonimo = APIClient()
        assert anonimo.get("/api/licitaciones/").status_code in (401, 403)
        assert anonimo.get("/api/gestiones/").status_code in (401, 403)

    def test_obtener_token(self, usuario) -> None:
        anonimo = APIClient()
        respuesta = anonimo.post(
            "/api/token/", {"username": "analista", "password": "clave!segura1"}
        )
        assert respuesta.status_code == 200
        assert "token" in respuesta.json()


class TestLicitaciones:
    def test_listado_paginado(self, cliente) -> None:
        LicitacionFactory.create_batch(3)
        datos = cliente.get("/api/licitaciones/").json()
        assert datos["count"] == 3
        assert len(datos["results"]) == 3

    def test_detalle_por_codigo_externo(self, cliente) -> None:
        licitacion = LicitacionFactory(codigo_externo="1234-56-L126")
        EvaluacionFiltroFactory(licitacion=licitacion)
        datos = cliente.get("/api/licitaciones/1234-56-L126/").json()
        assert datos["codigo_externo"] == "1234-56-L126"
        assert len(datos["evaluaciones"]) == 1

    def test_filtro_equipo_y_resultado_sobre_la_misma_evaluacion(self, cliente) -> None:
        """'incluida PARA TELECOM', no 'evaluada por TELECOM e incluida para otro'."""
        telecom = PerfilFiltroFactory(codigo="TELECOM")
        otro = PerfilFiltroFactory(codigo="ARQ")
        cruzada = LicitacionFactory()
        EvaluacionFiltroFactory(
            licitacion=cruzada, perfil=telecom, resultado=EvaluacionFiltro.Resultado.EXCLUIDA
        )
        EvaluacionFiltroFactory(
            licitacion=cruzada, perfil=otro, resultado=EvaluacionFiltro.Resultado.INCLUIDA
        )
        correcta = LicitacionFactory()
        EvaluacionFiltroFactory(
            licitacion=correcta, perfil=telecom, resultado=EvaluacionFiltro.Resultado.INCLUIDA
        )

        datos = cliente.get("/api/licitaciones/?equipo=TELECOM&resultado=incluida").json()

        codigos = [fila["codigo_externo"] for fila in datos["results"]]
        assert codigos == [correcta.codigo_externo]

    def test_filtro_relevantes_incluye_bypass(self, cliente) -> None:
        telecom = PerfilFiltroFactory(codigo="TELECOM")
        rescatada = LicitacionFactory()
        EvaluacionFiltroFactory(
            licitacion=rescatada, perfil=telecom, resultado=EvaluacionFiltro.Resultado.BYPASS
        )
        descartada = LicitacionFactory()
        EvaluacionFiltroFactory(
            licitacion=descartada, perfil=telecom, resultado=EvaluacionFiltro.Resultado.VETADA
        )

        datos = cliente.get("/api/licitaciones/?equipo=TELECOM&relevantes=true").json()

        codigos = [fila["codigo_externo"] for fila in datos["results"]]
        assert codigos == [rescatada.codigo_externo]

    def test_nuevas_devuelve_solo_la_ultima_ingesta(self, cliente) -> None:
        vieja_run = EjecucionPipeline.objects.create(
            tipo=EjecucionPipeline.Tipo.INGESTA, estado=EjecucionPipeline.Estado.EXITOSA
        )
        nueva_run = EjecucionPipeline.objects.create(
            tipo=EjecucionPipeline.Tipo.INGESTA, estado=EjecucionPipeline.Estado.EXITOSA
        )
        LicitacionFactory(first_seen_run=vieja_run)
        reciente = LicitacionFactory(first_seen_run=nueva_run)

        datos = cliente.get("/api/licitaciones/nuevas/").json()

        codigos = [fila["codigo_externo"] for fila in datos["results"]]
        assert codigos == [reciente.codigo_externo]

    def test_listado_sin_n_mas_uno(self, cliente, django_assert_max_num_queries) -> None:
        """Presupuesto de queries del listado: constante, no proporcional a filas (P9)."""
        LicitacionFactory.create_batch(15)
        with django_assert_max_num_queries(5):
            respuesta = cliente.get("/api/licitaciones/")
        assert respuesta.json()["count"] == 15


class TestGestiones:
    def test_crear_y_actualizar_registra_autor(self, cliente, usuario) -> None:
        licitacion = LicitacionFactory()
        perfil = PerfilFiltroFactory()

        creacion = cliente.post(
            "/api/gestiones/",
            {"licitacion": licitacion.pk, "perfil": perfil.pk, "estado": "en_revision"},
        )
        assert creacion.status_code == 201, creacion.content

        gestion = GestionLicitacion.objects.get()
        assert gestion.actualizado_por == usuario

        actualizacion = cliente.patch(
            f"/api/gestiones/{gestion.pk}/",
            {"estado": "preparando_oferta", "notas": "Revisar bases"},
        )
        assert actualizacion.status_code == 200
        gestion.refresh_from_db()
        assert gestion.estado == GestionLicitacion.Estado.PREPARANDO_OFERTA
        assert gestion.notas == "Revisar bases"

    def test_duplicado_licitacion_perfil_rechazado(self, cliente) -> None:
        licitacion = LicitacionFactory()
        perfil = PerfilFiltroFactory()
        primera = cliente.post(
            "/api/gestiones/", {"licitacion": licitacion.pk, "perfil": perfil.pk}
        )
        assert primera.status_code == 201
        duplicada = cliente.post(
            "/api/gestiones/", {"licitacion": licitacion.pk, "perfil": perfil.pk}
        )
        assert duplicada.status_code == 400

    def test_licitacion_y_perfil_inmutables_tras_crear(self, cliente) -> None:
        licitacion = LicitacionFactory()
        otra = LicitacionFactory()
        perfil = PerfilFiltroFactory()
        creacion = cliente.post(
            "/api/gestiones/", {"licitacion": licitacion.pk, "perfil": perfil.pk}
        )
        gestion_id = creacion.json()["id"]

        cambio = cliente.patch(f"/api/gestiones/{gestion_id}/", {"licitacion": otra.pk})

        assert cambio.status_code == 400
        assert "licitacion" in cambio.json()
