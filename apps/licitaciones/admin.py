from django.contrib import admin

from .models import EvaluacionFiltro, Licitacion


@admin.register(Licitacion)
class LicitacionAdmin(admin.ModelAdmin):
    list_display = (
        "codigo_externo",
        "nombre_corto",
        "organismo",
        "moneda",
        "monto_estimado",
        "fecha_publicacion",
        "fecha_cierre",
    )
    search_fields = ("codigo_externo", "nombre", "organismo__nombre")
    list_filter = ("moneda", "estado_fuente", "fecha_publicacion")
    date_hierarchy = "fecha_publicacion"
    list_select_related = ("organismo",)
    readonly_fields = ("raw_bulk", "raw_api", "created_at", "updated_at", "enriquecida_en")

    @admin.display(description="Nombre")
    def nombre_corto(self, obj: Licitacion) -> str:
        limite = 70
        return obj.nombre if len(obj.nombre) <= limite else f"{obj.nombre[:limite]}..."


@admin.register(EvaluacionFiltro)
class EvaluacionFiltroAdmin(admin.ModelAdmin):
    list_display = ("licitacion", "perfil", "resultado", "confianza", "evaluada_en")
    list_filter = ("perfil", "resultado", "confianza")
    search_fields = ("licitacion__codigo_externo", "licitacion__nombre")
    list_select_related = ("licitacion", "perfil")
    readonly_fields = ("trazabilidad", "evaluada_en")
