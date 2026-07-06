"""Formularios del portal: la escritura humana pasa por validación de formulario.

Las reglas creadas aquí pasan por la MISMA normalización que usaba el import
del PIVOT (domain.normalizacion): el motor de matching espera keywords
normalizadas, venga de donde venga la regla.
"""

from django import forms
from django.utils.text import slugify

from apps.gestion.models import GestionLicitacion
from apps.perfiles.models import PerfilFiltro, ReglaKeyword
from domain.normalizacion import normalizar_texto

LARGO_MINIMO_KEYWORD = 2
LARGO_MAX_CODIGO = 24


class GestionForm(forms.ModelForm):
    class Meta:
        model = GestionLicitacion
        fields = ["estado", "notas"]
        widgets = {
            "notas": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Tus notas sobre esta licitación..."}
            ),
        }


class BusquedaForm(forms.ModelForm):
    class Meta:
        model = PerfilFiltro
        fields = ["nombre", "descripcion"]
        widgets = {
            "nombre": forms.TextInput(
                attrs={"placeholder": "Ej: Fibra óptica y redes", "autofocus": True}
            ),
            "descripcion": forms.Textarea(
                attrs={"rows": 2, "placeholder": "Opcional: qué buscas con este perfil"}
            ),
        }

    def generar_codigo(self) -> str:
        """Código único para URLs/API a partir del nombre (el usuario no lo escribe)."""
        base = slugify(self.cleaned_data["nombre"]).replace("-", "").upper()[:LARGO_MAX_CODIGO]
        base = base or "BUSQUEDA"
        codigo = base
        sufijo = 2
        while PerfilFiltro.objects.filter(codigo=codigo).exists():
            codigo = f"{base}{sufijo}"
            sufijo += 1
        return codigo


class ReglaForm(forms.ModelForm):
    class Meta:
        model = ReglaKeyword
        fields = ["texto", "tipo", "campo"]
        widgets = {
            "texto": forms.TextInput(attrs={"placeholder": "Palabra o frase clave..."}),
        }

    def clean_texto(self) -> str:
        texto = normalizar_texto(self.cleaned_data["texto"])
        if len(texto) < LARGO_MINIMO_KEYWORD:
            raise forms.ValidationError(
                "La keyword necesita al menos 2 caracteres: las de 1 generan ruido masivo."
            )
        return texto

    def clean(self) -> dict:
        datos = super().clean()
        tipo = datos.get("tipo")
        campo = datos.get("campo", "")
        if tipo in (ReglaKeyword.Tipo.INCLUIR, ReglaKeyword.Tipo.EXCLUIR) and not campo:
            self.add_error(
                "campo",
                "Indica sobre qué campo aplica (bypass y exclusión dura no lo necesitan).",
            )
        if tipo in (ReglaKeyword.Tipo.BYPASS, ReglaKeyword.Tipo.EXCLUSION_DURA):
            datos["campo"] = ""
        return datos
