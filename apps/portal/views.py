"""Vistas del portal: la interfaz diaria del equipo comercial.

Capa de interfaz (P2): componen querysets y delegan; la lógica vive en dominio
y servicios. La fila del listado es EvaluacionFiltro (la relevancia ES por
equipo), con la gestión del equipo resuelta en una sola consulta adicional.
"""

import datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, ListView, View

from apps.gestion.models import GestionLicitacion
from apps.licitaciones.models import EvaluacionFiltro, Licitacion
from apps.perfiles.models import PerfilFiltro, ReglaKeyword
from apps.portal.forms import GestionForm

RESULTADOS_RELEVANTES = (
    EvaluacionFiltro.Resultado.INCLUIDA,
    EvaluacionFiltro.Resultado.BYPASS,
)
DIAS_CIERRE_URGENTE = 7
FILAS_POR_PAGINA = 25


def _perfiles_operables() -> QuerySet[PerfilFiltro]:
    """Solo equipos activos con reglas de inclusión: los demás no producen resultados."""
    return (
        PerfilFiltro.objects.filter(
            activo=True, reglas__tipo=ReglaKeyword.Tipo.INCLUIR, reglas__activa=True
        )
        .distinct()
        .order_by("codigo")
    )


def _perfil_activo(request) -> PerfilFiltro | None:  # noqa: ANN001
    perfiles = _perfiles_operables()
    codigo = request.GET.get("equipo") or request.POST.get("equipo") or ""
    return perfiles.filter(codigo=codigo.upper()).first() or perfiles.first()


class ListaRelevantesView(LoginRequiredMixin, ListView):
    """Bandeja de trabajo: las licitaciones relevantes del equipo seleccionado."""

    template_name = "portal/lista.html"
    context_object_name = "evaluaciones"
    paginate_by = FILAS_POR_PAGINA

    def get_queryset(self) -> QuerySet[EvaluacionFiltro]:
        self.perfil = _perfil_activo(self.request)
        if self.perfil is None:
            return EvaluacionFiltro.objects.none()

        queryset = (
            EvaluacionFiltro.objects.filter(perfil=self.perfil, resultado__in=RESULTADOS_RELEVANTES)
            .select_related("licitacion__organismo")
            .order_by("licitacion__fecha_cierre", "licitacion__codigo_externo")
        )
        confianza = self.request.GET.get("confianza", "")
        if confianza in EvaluacionFiltro.Confianza.values:
            queryset = queryset.filter(confianza=confianza)
        busqueda = self.request.GET.get("q", "").strip()
        if busqueda:
            queryset = queryset.filter(licitacion__nombre__icontains=busqueda)
        return queryset

    def get_context_data(self, **kwargs: object) -> dict:
        contexto = super().get_context_data(**kwargs)
        perfil = self.perfil
        contexto["perfiles"] = _perfiles_operables()
        contexto["perfil"] = perfil
        contexto["confianza_seleccionada"] = self.request.GET.get("confianza", "")
        contexto["busqueda"] = self.request.GET.get("q", "")

        if perfil is not None:
            base = EvaluacionFiltro.objects.filter(
                perfil=perfil, resultado__in=RESULTADOS_RELEVANTES
            )
            limite_urgente = timezone.now() + datetime.timedelta(days=DIAS_CIERRE_URGENTE)
            contexto["stats"] = {
                "total": base.count(),
                "alta": base.filter(confianza=EvaluacionFiltro.Confianza.ALTA).count(),
                "revisar": base.filter(confianza=EvaluacionFiltro.Confianza.REVISAR).count(),
                "cierran_pronto": base.filter(
                    licitacion__fecha_cierre__gte=timezone.now(),
                    licitacion__fecha_cierre__lte=limite_urgente,
                ).count(),
            }
            # Estado de gestión del equipo para cada fila, en UNA consulta (sin N+1),
            # adjuntado a cada evaluación para que el template no indexe dicts.
            ids_pagina = [e.licitacion_id for e in contexto["evaluaciones"]]
            gestiones = {
                g.licitacion_id: g
                for g in GestionLicitacion.objects.filter(
                    perfil=perfil, licitacion_id__in=ids_pagina
                )
            }
            for evaluacion in contexto["evaluaciones"]:
                evaluacion.gestion_equipo = gestiones.get(evaluacion.licitacion_id)
        contexto["hoy"] = timezone.now()
        contexto["limite_urgente"] = timezone.now() + datetime.timedelta(days=DIAS_CIERRE_URGENTE)
        return contexto


class DetalleLicitacionView(LoginRequiredMixin, DetailView):
    """Ficha completa: hechos, trazabilidad del filtro y panel de gestión del equipo."""

    template_name = "portal/detalle.html"
    context_object_name = "licitacion"
    slug_field = "codigo_externo"
    slug_url_kwarg = "codigo_externo"

    def get_queryset(self) -> QuerySet[Licitacion]:
        return Licitacion.objects.select_related("organismo").prefetch_related(
            "rubros", "evaluaciones__perfil"
        )

    def get_context_data(self, **kwargs: object) -> dict:
        contexto = super().get_context_data(**kwargs)
        perfil = _perfil_activo(self.request)
        contexto["perfil"] = perfil
        contexto["perfiles"] = _perfiles_operables()
        gestion = None
        if perfil is not None:
            gestion = GestionLicitacion.objects.filter(
                licitacion=self.object, perfil=perfil
            ).first()
        contexto["gestion"] = gestion
        contexto["form"] = GestionForm(instance=gestion)
        contexto["evaluacion_equipo"] = next(
            (e for e in self.object.evaluaciones.all() if perfil and e.perfil_id == perfil.pk),
            None,
        )
        contexto["hoy"] = timezone.now()
        return contexto


class ActualizarGestionView(LoginRequiredMixin, View):
    """POST del panel de gestión: crea o actualiza el estado del equipo (autor registrado)."""

    def post(self, request, codigo_externo: str):  # noqa: ANN001, ANN201
        licitacion = get_object_or_404(Licitacion, codigo_externo=codigo_externo)
        perfil = _perfil_activo(request)
        if perfil is None:
            return redirect(reverse("portal:lista"))

        gestion = GestionLicitacion.objects.filter(licitacion=licitacion, perfil=perfil).first()
        form = GestionForm(request.POST, instance=gestion)
        if form.is_valid():
            nueva = form.save(commit=False)
            nueva.licitacion = licitacion
            nueva.perfil = perfil
            nueva.actualizado_por = request.user
            if nueva.asignado_a_id is None:
                nueva.asignado_a = request.user
            nueva.save()
        destino = reverse("portal:detalle", kwargs={"codigo_externo": codigo_externo})
        return redirect(f"{destino}?equipo={perfil.codigo}")
