"""Vistas del portal: la interfaz diaria del equipo comercial.

Capa de interfaz (P2): componen querysets y delegan; la lógica vive en dominio
y servicios. La fila del listado es EvaluacionFiltro (la relevancia ES por
equipo), con la gestión del equipo resuelta en una sola consulta adicional.
"""

import datetime

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, QuerySet
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, ListView, View

from apps.gestion.models import GestionLicitacion
from apps.licitaciones.models import EvaluacionFiltro, Licitacion
from apps.licitaciones.services import evaluar_perfil
from apps.perfiles.models import PerfilFiltro, ReglaKeyword
from apps.portal.forms import BusquedaForm, GestionForm, ReglaForm

RESULTADOS_RELEVANTES = (
    EvaluacionFiltro.Resultado.INCLUIDA,
    EvaluacionFiltro.Resultado.BYPASS,
)
DIAS_CIERRE_URGENTE = 7
FILAS_POR_PAGINA = 25


def _mis_busquedas(usuario) -> QuerySet[PerfilFiltro]:  # noqa: ANN001
    """Las búsquedas del usuario (aislamiento: nadie ve las ajenas), con su
    conteo de relevantes para el sidebar."""
    return (
        PerfilFiltro.objects.filter(propietario=usuario, activo=True)
        .annotate(
            relevantes=Count(
                "evaluaciones",
                filter=Q(evaluaciones__resultado__in=RESULTADOS_RELEVANTES),
                distinct=True,
            )
        )
        .order_by("codigo")
    )


def _perfil_activo(request) -> PerfilFiltro | None:  # noqa: ANN001
    perfiles = _mis_busquedas(request.user)
    # "equipo" se acepta como alias legado del parámetro (links guardados).
    codigo = (
        request.GET.get("perfil")
        or request.POST.get("perfil")
        or request.GET.get("equipo")
        or request.POST.get("equipo")
        or ""
    )
    return perfiles.filter(codigo=codigo.upper()).first() or perfiles.first()


def _busqueda_propia_o_404(request, codigo: str) -> PerfilFiltro:  # noqa: ANN001
    """Toda vista de gestión de una búsqueda exige ser su dueño (404 si no)."""
    return get_object_or_404(PerfilFiltro, codigo=codigo.upper(), propietario=request.user)


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
        if self.request.GET.get("cierra") == "pronto":
            queryset = queryset.filter(
                licitacion__fecha_cierre__gte=timezone.now(),
                licitacion__fecha_cierre__lte=timezone.now()
                + datetime.timedelta(days=DIAS_CIERRE_URGENTE),
            )
        busqueda = self.request.GET.get("q", "").strip()
        if busqueda:
            queryset = queryset.filter(licitacion__nombre__icontains=busqueda)
        return queryset

    def get_context_data(self, **kwargs: object) -> dict:
        contexto = super().get_context_data(**kwargs)
        perfil = self.perfil
        contexto["perfiles"] = _mis_busquedas(self.request.user)
        contexto["perfil"] = perfil
        contexto["confianza_seleccionada"] = self.request.GET.get("confianza", "")
        contexto["cierra_pronto"] = self.request.GET.get("cierra") == "pronto"
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
            hoy = timezone.localdate()
            for evaluacion in contexto["evaluaciones"]:
                evaluacion.gestion_equipo = gestiones.get(evaluacion.licitacion_id)
                cierre = evaluacion.licitacion.fecha_cierre
                evaluacion.dias_cierre = (
                    (timezone.localtime(cierre).date() - hoy).days if cierre else None
                )
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
        contexto["perfiles"] = _mis_busquedas(self.request.user)
        gestion = None
        if perfil is not None:
            gestion = GestionLicitacion.objects.filter(
                licitacion=self.object, perfil=perfil
            ).first()
        contexto["gestion"] = gestion
        contexto["form"] = GestionForm(instance=gestion)
        evaluaciones = list(self.object.evaluaciones.all())
        contexto["evaluacion_equipo"] = next(
            (e for e in evaluaciones if perfil and e.perfil_id == perfil.pk), None
        )
        contexto["otras_evaluaciones"] = [
            e for e in evaluaciones if not perfil or e.perfil_id != perfil.pk
        ]
        cierre = self.object.fecha_cierre
        contexto["dias_cierre"] = (
            (timezone.localtime(cierre).date() - timezone.localdate()).days if cierre else None
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
        return redirect(f"{destino}?perfil={perfil.codigo}")


class BusquedaCrearView(LoginRequiredMixin, View):
    """Alta de una búsqueda: el usuario pone el nombre, el sistema genera el código."""

    template_name = "portal/busqueda_nueva.html"

    def get(self, request):  # noqa: ANN001, ANN201
        return render(
            request,
            self.template_name,
            {"form": BusquedaForm(), "perfiles": _mis_busquedas(request.user)},
        )

    def post(self, request):  # noqa: ANN001, ANN201
        form = BusquedaForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {"form": form, "perfiles": _mis_busquedas(request.user)},
            )
        busqueda = form.save(commit=False)
        busqueda.codigo = form.generar_codigo()
        busqueda.propietario = request.user
        busqueda.save()
        messages.success(
            request,
            f"Búsqueda '{busqueda.nombre}' creada. Agrega reglas de inclusión y evalúa.",
        )
        return redirect(reverse("portal:reglas", kwargs={"codigo": busqueda.codigo}))


class ReglasView(LoginRequiredMixin, View):
    """El centro del self-service: ver, agregar y quitar reglas de una búsqueda propia."""

    def get(self, request, codigo: str):  # noqa: ANN001, ANN201
        busqueda = _busqueda_propia_o_404(request, codigo)
        reglas = busqueda.reglas.order_by("tipo", "campo", "texto")
        grupos = [
            (
                etiqueta,
                tipo,
                descripcion,
                [r for r in reglas if r.tipo == tipo],
            )
            for etiqueta, tipo, descripcion in (
                (
                    "Inclusión",
                    ReglaKeyword.Tipo.INCLUIR,
                    "Lo que SÍ te interesa: sin esto, la búsqueda no produce resultados.",
                ),
                (
                    "Exclusión",
                    ReglaKeyword.Tipo.EXCLUIR,
                    "Lo que descarta una licitación aunque haya matcheado.",
                ),
                (
                    "Bypass",
                    ReglaKeyword.Tipo.BYPASS,
                    "Rescata excluidas si aparecen estas señales en nombre o descripción.",
                ),
                (
                    "Exclusión dura",
                    ReglaKeyword.Tipo.EXCLUSION_DURA,
                    "Categorías (Nivel 1/2) que nunca son relevantes, ni con bypass.",
                ),
            )
        ]
        return render(
            request,
            "portal/reglas.html",
            {
                "busqueda": busqueda,
                "perfil": busqueda,
                "perfiles": _mis_busquedas(request.user),
                "grupos": grupos,
                "form": ReglaForm(),
                "campos_por_tipo": True,
            },
        )

    def post(self, request, codigo: str):  # noqa: ANN001, ANN201
        """Alta de regla (el POST de la misma página)."""
        busqueda = _busqueda_propia_o_404(request, codigo)
        form = ReglaForm(request.POST)
        if form.is_valid():
            regla = form.save(commit=False)
            regla.perfil = busqueda
            if busqueda.reglas.filter(
                tipo=regla.tipo, campo=regla.campo, texto=regla.texto
            ).exists():
                messages.info(request, f"'{regla.texto}' ya estaba en esas reglas.")
            else:
                regla.save()
                messages.success(
                    request,
                    f"Regla '{regla.texto}' agregada. Re-evalúa para aplicarla.",
                )
        else:
            for errores in form.errors.values():
                for error in errores:
                    messages.error(request, error)
        return redirect(reverse("portal:reglas", kwargs={"codigo": busqueda.codigo}))


class ReglaEliminarView(LoginRequiredMixin, View):
    def post(self, request, codigo: str, regla_id: int):  # noqa: ANN001, ANN201
        busqueda = _busqueda_propia_o_404(request, codigo)
        regla = get_object_or_404(ReglaKeyword, pk=regla_id, perfil=busqueda)
        texto = regla.texto
        regla.delete()
        messages.success(request, f"Regla '{texto}' eliminada. Re-evalúa para aplicarlo.")
        return redirect(reverse("portal:reglas", kwargs={"codigo": busqueda.codigo}))


class EvaluarAhoraView(LoginRequiredMixin, View):
    """El motor de filtrado corre desde la página: evalúa ~4k licitaciones en segundos."""

    def post(self, request, codigo: str):  # noqa: ANN001, ANN201
        busqueda = _busqueda_propia_o_404(request, codigo)
        if not busqueda.reglas.filter(tipo=ReglaKeyword.Tipo.INCLUIR, activa=True).exists():
            messages.error(
                request,
                "Agrega al menos una regla de inclusión antes de evaluar: "
                "sin ellas no hay resultados.",
            )
            return redirect(reverse("portal:reglas", kwargs={"codigo": busqueda.codigo}))

        resultado = evaluar_perfil(busqueda)
        relevantes = resultado.por_resultado.get("incluida", 0) + resultado.por_resultado.get(
            "bypass", 0
        )
        messages.success(
            request,
            f"Evaluadas {resultado.total} licitaciones: {relevantes} relevantes para "
            f"'{busqueda.nombre}' ({resultado.confianza_alta} con confianza alta).",
        )
        for kw, n, pct in resultado.exclusiones_toxicas:
            messages.warning(
                request,
                f"La keyword de exclusión '{kw}' descarta {n} licitaciones ({pct}%): "
                f"puede ser demasiado genérica.",
            )
        return redirect(f"{reverse('portal:lista')}?perfil={busqueda.codigo}")


class BusquedaEliminarView(LoginRequiredMixin, View):
    def post(self, request, codigo: str):  # noqa: ANN001, ANN201
        busqueda = _busqueda_propia_o_404(request, codigo)
        nombre = busqueda.nombre
        busqueda.delete()
        messages.success(request, f"Búsqueda '{nombre}' eliminada con sus reglas y evaluaciones.")
        return redirect(reverse("portal:lista"))
