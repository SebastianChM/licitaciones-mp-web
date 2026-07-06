"""Comando: evalúa las licitaciones de la BD contra los perfiles de filtrado.

Adaptador de entrada batch. Re-ejecutable: al cambiar reglas en el Admin se
corre de nuevo y las evaluaciones se actualizan sin re-ingestar (PLAN.md R3/R6).
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from apps.licitaciones.services import ResultadoEvaluacion, evaluar_perfil
from apps.ops.models import EjecucionPipeline
from apps.perfiles.models import PerfilFiltro, ReglaKeyword


class Command(BaseCommand):
    help = "Evalúa todas las licitaciones contra los perfiles de filtrado activos"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--equipo",
            type=str,
            default=None,
            help=(
                "Código de un perfil (ej: TELECOM); por defecto, todos los "
                "activos con reglas de inclusión"
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Evalúa e informa métricas sin escribir en la BD (O4)",
        )

    # ANN401 justificado: firma heredada de BaseCommand (Django tipa options como Any).
    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ANN401
        codigo: str | None = options["equipo"]
        dry_run: bool = options["dry_run"]

        perfiles = self._resolver_perfiles(codigo)

        ejecucion = EjecucionPipeline.objects.create(tipo=EjecucionPipeline.Tipo.EVALUACION)
        resultados_perfiles: list[dict[str, object]] = []

        with transaction.atomic():
            for perfil in perfiles:
                resultado = evaluar_perfil(perfil)
                resultados_perfiles.append(resultado.como_dict())
                self._reportar(perfil.codigo, resultado, dry_run)
            if dry_run:
                transaction.set_rollback(True)

        # Fuera del atomic: el registro de observabilidad sobrevive al rollback del dry-run.
        ejecucion.estado = EjecucionPipeline.Estado.EXITOSA
        ejecucion.terminada_en = timezone.now()
        ejecucion.metricas = {"dry_run": dry_run, "perfiles": resultados_perfiles}
        ejecucion.save(update_fields=["estado", "terminada_en", "metricas"])

    def _resolver_perfiles(self, codigo: str | None) -> list[PerfilFiltro]:
        if codigo is not None:
            try:
                return [PerfilFiltro.objects.get(codigo=codigo.strip().upper())]
            except PerfilFiltro.DoesNotExist as e:
                disponibles = list(PerfilFiltro.objects.values_list("codigo", flat=True))
                raise CommandError(
                    f"El perfil '{codigo}' no existe. Disponibles: {disponibles}. "
                    f"Importa perfiles con: manage.py importar_pivot <ruta>"
                ) from e

        con_inclusion = PerfilFiltro.objects.filter(
            activo=True,
            reglas__tipo=ReglaKeyword.Tipo.INCLUIR,
            reglas__activa=True,
        ).distinct()
        if not con_inclusion:
            raise CommandError(
                "No hay perfiles activos con reglas de inclusión: sin ellas el filtrado "
                "no produce resultados. Importa el PIVOT o crea reglas en el Admin."
            )
        return list(con_inclusion)

    def _reportar(self, codigo: str, resultado: ResultadoEvaluacion, dry_run: bool) -> None:
        prefijo = "[DRY-RUN] " if dry_run else ""
        r = resultado.por_resultado
        relevantes = r.get("incluida", 0) + r.get("bypass", 0)
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefijo}{codigo}: {resultado.total} evaluadas -> "
                f"{relevantes} relevantes ({r.get('incluida', 0)} incluidas, "
                f"{r.get('bypass', 0)} por bypass), {r.get('excluida', 0)} excluidas, "
                f"{r.get('exclusion_dura', 0)} exclusión dura, {r.get('vetada', 0)} vetadas, "
                f"{r.get('sin_match', 0)} sin match. "
                f"Confianza: {resultado.confianza_alta} ALTA / "
                f"{resultado.confianza_revisar} REVISAR."
            )
        )
        for kw, n, pct in resultado.exclusiones_toxicas:
            self.stdout.write(
                self.style.WARNING(
                    f"Keyword de exclusión tóxica en {codigo}: '{kw}' excluye {n} "
                    f"licitaciones ({pct}% del subconjunto post-inclusión). Considera "
                    f"reemplazarla por una frase más específica en el Admin."
                )
            )
