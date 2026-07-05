"""Fábricas de modelos para tests (datos sintéticos, declarados como tales — P16)."""

import factory
from factory.django import DjangoModelFactory

from apps.catalogo.models import Organismo, Rubro
from apps.gestion.models import GestionLicitacion
from apps.licitaciones.models import EvaluacionFiltro, Licitacion
from apps.perfiles.models import PalabraIntencion, PerfilFiltro, ReglaKeyword


class OrganismoFactory(DjangoModelFactory):
    class Meta:
        model = Organismo

    nombre = factory.Sequence(lambda n: f"Organismo Sintetico {n}")
    region = "Región Metropolitana"


class RubroFactory(DjangoModelFactory):
    class Meta:
        model = Rubro

    nivel = Rubro.Nivel.NIVEL_1
    nombre = factory.Sequence(lambda n: f"Rubro Sintetico {n}")


class PerfilFiltroFactory(DjangoModelFactory):
    class Meta:
        model = PerfilFiltro

    codigo = factory.Sequence(lambda n: f"EQUIPO{n}")
    nombre = factory.Sequence(lambda n: f"Equipo Sintetico {n}")


class ReglaKeywordFactory(DjangoModelFactory):
    class Meta:
        model = ReglaKeyword

    perfil = factory.SubFactory(PerfilFiltroFactory)
    texto = factory.Sequence(lambda n: f"keyword{n}")
    tipo = ReglaKeyword.Tipo.INCLUIR
    campo = ReglaKeyword.Campo.NOMBRE


class PalabraIntencionFactory(DjangoModelFactory):
    class Meta:
        model = PalabraIntencion

    texto = factory.Sequence(lambda n: f"intencion{n}")
    tipo = PalabraIntencion.Tipo.REQUERIDA


class LicitacionFactory(DjangoModelFactory):
    class Meta:
        model = Licitacion

    codigo_externo = factory.Sequence(lambda n: f"9999-{n}-L126")
    nombre = factory.Sequence(lambda n: f"Licitacion sintetica de consultoria {n}")
    organismo = factory.SubFactory(OrganismoFactory)


class EvaluacionFiltroFactory(DjangoModelFactory):
    class Meta:
        model = EvaluacionFiltro

    licitacion = factory.SubFactory(LicitacionFactory)
    perfil = factory.SubFactory(PerfilFiltroFactory)
    resultado = EvaluacionFiltro.Resultado.INCLUIDA


class GestionLicitacionFactory(DjangoModelFactory):
    class Meta:
        model = GestionLicitacion

    licitacion = factory.SubFactory(LicitacionFactory)
    perfil = factory.SubFactory(PerfilFiltroFactory)
