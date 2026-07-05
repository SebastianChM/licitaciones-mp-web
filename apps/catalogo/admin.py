from django.contrib import admin

from .models import Organismo, Rubro


@admin.register(Organismo)
class OrganismoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "region")
    search_fields = ("nombre", "codigo")
    list_filter = ("region",)


@admin.register(Rubro)
class RubroAdmin(admin.ModelAdmin):
    list_display = ("nombre", "nivel")
    search_fields = ("nombre",)
    list_filter = ("nivel",)
