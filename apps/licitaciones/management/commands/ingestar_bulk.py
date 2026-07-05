"""Comando: ingesta el Excel masivo diario del portal Mercado Público a la BD.

Adaptador de entrada batch (PLAN.md R1/R2): pensado para correr una vez al día
vía scheduler. Descarga el bulk (o usa --archivo para uno local, útil en tests
y para re-procesar) y hace upsert idempotente. JAMÁS toca apps.gestion (P4).
"""

import tempfile
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from apps.licitaciones.ingesta import (
    FormatoBulkError,
    descargar_bulk,
    desempaquetar_bulk,
    leer_bulk,
)
from apps.licitaciones.services import ingestar_filas
from apps.ops.models import EjecucionPipeline

NOMBRE_ARCHIVO_DESCARGA = "licitaciones_bulk.xlsx"


class Command(BaseCommand):
    help = "Descarga (o lee de --archivo) el bulk diario del portal y lo ingesta en la BD"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--archivo",
            type=Path,
            default=None,
            help="Usar un XLSX local en lugar de descargar del portal",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parsea e informa métricas sin escribir en la BD (O4)",
        )

    # ANN401 justificado: firma heredada de BaseCommand (Django tipa options como Any).
    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ANN401
        archivo: Path | None = options["archivo"]
        dry_run: bool = options["dry_run"]

        ejecucion = EjecucionPipeline.objects.create(tipo=EjecucionPipeline.Tipo.INGESTA)
        try:
            if archivo is None:
                destino = Path(tempfile.gettempdir()) / NOMBRE_ARCHIVO_DESCARGA
                archivo = descargar_bulk(settings.MP_BULK_URL, destino)
            elif not archivo.exists():
                raise FormatoBulkError(
                    f"El archivo '{archivo}' no existe. Verifica la ruta pasada en --archivo."
                )

            filas = leer_bulk(desempaquetar_bulk(archivo))
            with transaction.atomic():
                resultado = ingestar_filas(filas, ejecucion)
                if dry_run:
                    transaction.set_rollback(True)
        except FormatoBulkError as e:
            ejecucion.estado = EjecucionPipeline.Estado.FALLIDA
            ejecucion.terminada_en = timezone.now()
            ejecucion.log_resumen = str(e)
            ejecucion.save(update_fields=["estado", "terminada_en", "log_resumen"])
            raise CommandError(str(e)) from e

        ejecucion.estado = EjecucionPipeline.Estado.EXITOSA
        ejecucion.terminada_en = timezone.now()
        ejecucion.metricas = {**resultado.como_dict(), "dry_run": dry_run}
        ejecucion.save(update_fields=["estado", "terminada_en", "metricas"])

        prefijo = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefijo}Ingesta completada: {resultado.total_filas} filas leídas, "
                f"{resultado.creadas} licitaciones nuevas, {resultado.actualizadas} actualizadas."
            )
        )
        for advertencia in resultado.advertencias[:10]:
            self.stdout.write(self.style.WARNING(f"Advertencia: {advertencia}"))
