"""Comando: completa las licitaciones relevantes con su ficha oficial de la API.

Adaptador de entrada batch (port de la etapa 3 del original). Por diseño procesa
solo las RELEVANTES pendientes: a ~8 req/min (delay 7s, P12) enriquecer el
universo completo tomaría más de un día; las ~80 relevantes toman ~10 minutos.
La BD es el checkpoint: interrumpir y relanzar retoma donde quedó.
"""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from apps.licitaciones.api_mp import ClienteDetalleMP
from apps.licitaciones.services import (
    enriquecer_licitaciones,
    licitaciones_pendientes_de_enriquecer,
)
from apps.ops.models import EjecucionPipeline


class Command(BaseCommand):
    help = "Trae la ficha oficial (API MP) de las licitaciones relevantes pendientes"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--limite",
            type=int,
            default=None,
            help="Procesar como máximo N licitaciones (útil para corridas parciales)",
        )

    # ANN401 justificado: firma heredada de BaseCommand (Django tipa options como Any).
    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ANN401
        limite: int | None = options["limite"]

        ticket = settings.MERCADO_PUBLICO_TICKET
        if not ticket:
            raise CommandError(
                "Falta el ticket de la API: define LICITAWEB_MERCADO_PUBLICO_TICKET en .env "
                "(se solicita gratis en api.mercadopublico.cl)."
            )

        pendientes = licitaciones_pendientes_de_enriquecer()
        total_pendientes = pendientes.count()
        if limite is not None:
            # slicing sobre PKs para conservar un queryset filtrable
            ids = list(pendientes.values_list("pk", flat=True)[:limite])
            pendientes = pendientes.filter(pk__in=ids)

        a_procesar = min(total_pendientes, limite) if limite else total_pendientes
        delay = settings.MP_API_DELAY_SEGUNDOS
        self.stdout.write(
            f"{total_pendientes} relevantes pendientes; se procesarán {a_procesar} "
            f"(~{a_procesar * delay / 60:.0f} min al ritmo de la API)."
        )
        if a_procesar == 0:
            self.stdout.write(self.style.SUCCESS("Nada pendiente: todo enriquecido."))
            return

        ejecucion = EjecucionPipeline.objects.create(tipo=EjecucionPipeline.Tipo.ENRIQUECIMIENTO)
        cliente = ClienteDetalleMP(base_url=settings.MP_API_BASE_URL, ticket=ticket)
        try:
            resultado = enriquecer_licitaciones(pendientes, cliente, delay_segundos=delay)
        finally:
            cliente.cerrar()

        ejecucion.estado = EjecucionPipeline.Estado.EXITOSA
        ejecucion.terminada_en = timezone.now()
        ejecucion.metricas = resultado.como_dict()
        ejecucion.save(update_fields=["estado", "terminada_en", "metricas"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Enriquecimiento completado: {resultado.procesadas} procesadas, "
                f"{resultado.enriquecidas} con ficha, {resultado.sin_datos} sin datos en la API, "
                f"{resultado.fallos_red} fallos de red (quedan pendientes para la próxima corrida)."
            )
        )
