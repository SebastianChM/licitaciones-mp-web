"""Comando: importa PIVOT_MAESTRO.xlsx del proyecto original a la BD.

Adaptador de entrada (PLAN.md 2.1). Orquesta transacción, dry-run y observabilidad;
el parseo del PIVOT vive en apps.perfiles.pivot_import.
"""

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from apps.ops.models import EjecucionPipeline
from apps.perfiles.pivot_import import PivotImportError, importar_pivot


class Command(BaseCommand):
    help = "Importa equipos, reglas de filtrado e intención global desde un PIVOT_MAESTRO.xlsx"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("ruta_pivot", type=Path, help="Ruta al archivo PIVOT_MAESTRO.xlsx")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra qué se importaría sin escribir en la BD (O4)",
        )

    # ANN401 justificado: firma heredada de BaseCommand (Django tipa options como Any).
    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ANN401
        ruta: Path = options["ruta_pivot"]
        dry_run: bool = options["dry_run"]

        ejecucion = EjecucionPipeline.objects.create(tipo=EjecucionPipeline.Tipo.IMPORTACION_PIVOT)
        try:
            with transaction.atomic():
                resultado = importar_pivot(ruta)
                if dry_run:
                    transaction.set_rollback(True)
        except PivotImportError as e:
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
                f"{prefijo}Importación completada: "
                f"{resultado.perfiles_creados} perfiles nuevos, "
                f"{resultado.perfiles_actualizados} actualizados, "
                f"{resultado.reglas_creadas} reglas nuevas, "
                f"{resultado.reglas_existentes} ya existentes, "
                f"{resultado.intencion_creadas} palabras de intención nuevas."
            )
        )
        for advertencia in resultado.advertencias:
            self.stdout.write(self.style.WARNING(f"Advertencia: {advertencia}"))
