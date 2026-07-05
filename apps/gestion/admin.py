from django.contrib import admin

from .models import GestionLicitacion


@admin.register(GestionLicitacion)
class GestionLicitacionAdmin(admin.ModelAdmin):
    list_display = ("licitacion", "perfil", "estado", "asignado_a", "updated_at")
    list_filter = ("perfil", "estado")
    search_fields = ("licitacion__codigo_externo", "licitacion__nombre", "notas")
    list_select_related = ("licitacion", "perfil", "asignado_a")
