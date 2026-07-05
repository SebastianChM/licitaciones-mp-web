from django.contrib import admin

from .models import PalabraIntencion, PerfilFiltro, ReglaKeyword


class ReglaKeywordInline(admin.TabularInline):
    model = ReglaKeyword
    extra = 0
    fields = ("texto", "tipo", "campo", "activa")


@admin.register(PerfilFiltro)
class PerfilFiltroAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "activo", "total_reglas")
    list_filter = ("activo",)
    search_fields = ("codigo", "nombre")
    inlines = [ReglaKeywordInline]

    @admin.display(description="Reglas")
    def total_reglas(self, obj: PerfilFiltro) -> int:
        return obj.reglas.count()


@admin.register(ReglaKeyword)
class ReglaKeywordAdmin(admin.ModelAdmin):
    list_display = ("texto", "perfil", "tipo", "campo", "activa")
    list_filter = ("perfil", "tipo", "campo", "activa")
    search_fields = ("texto",)
    list_select_related = ("perfil",)


@admin.register(PalabraIntencion)
class PalabraIntencionAdmin(admin.ModelAdmin):
    list_display = ("texto", "tipo", "activa")
    list_filter = ("tipo", "activa")
    search_fields = ("texto",)
