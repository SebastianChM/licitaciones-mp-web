from django.contrib import admin

from .models import EjecucionPipeline, TipoCambio


@admin.register(EjecucionPipeline)
class EjecucionPipelineAdmin(admin.ModelAdmin):
    list_display = ("tipo", "estado", "iniciada_en", "terminada_en")
    list_filter = ("tipo", "estado")
    readonly_fields = ("tipo", "estado", "iniciada_en", "terminada_en", "metricas", "log_resumen")

    def has_add_permission(self, request) -> bool:  # noqa: ANN001
        # Las ejecuciones las crean los comandos batch, no las personas.
        return False


@admin.register(TipoCambio)
class TipoCambioAdmin(admin.ModelAdmin):
    list_display = ("fecha", "moneda", "tasa_clp", "fuente")
    list_filter = ("moneda",)
    date_hierarchy = "fecha"
