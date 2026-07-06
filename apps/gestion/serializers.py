"""Serializers de gestión: el único punto de escritura humana de la API.

Los hechos de la licitación NO se editan por aquí (P4 en espejo: así como la
ingesta no toca gestión, la gestión no toca hechos).
"""

from rest_framework import serializers

from apps.gestion.models import GestionLicitacion


class GestionLicitacionSerializer(serializers.ModelSerializer):
    codigo_licitacion = serializers.CharField(source="licitacion.codigo_externo", read_only=True)
    equipo = serializers.CharField(source="perfil.codigo", read_only=True)
    asignado_a = serializers.SlugRelatedField(slug_field="username", read_only=True)

    class Meta:
        model = GestionLicitacion
        fields = [
            "id",
            "licitacion",
            "codigo_licitacion",
            "perfil",
            "equipo",
            "estado",
            "notas",
            "asignado_a",
            "actualizado_por",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["actualizado_por", "created_at", "updated_at"]

    def validate(self, attrs: dict) -> dict:
        """La dupla (licitacion, perfil) es inmutable tras la creación: el workflow
        de un equipo sobre una licitación no se 'mueve' a otra, se crea otro."""
        if self.instance is not None:
            for campo in ("licitacion", "perfil"):
                if campo in attrs and attrs[campo] != getattr(self.instance, campo):
                    raise serializers.ValidationError(
                        {campo: "No se puede cambiar tras la creación; crea una gestión nueva."}
                    )
        return attrs
