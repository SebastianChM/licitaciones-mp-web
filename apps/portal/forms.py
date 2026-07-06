"""Formularios del portal: la escritura humana pasa por validación de formulario."""

from django import forms

from apps.gestion.models import GestionLicitacion


class GestionForm(forms.ModelForm):
    class Meta:
        model = GestionLicitacion
        fields = ["estado", "notas"]
        widgets = {
            "notas": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Notas del equipo sobre esta licitación..."}
            ),
        }
