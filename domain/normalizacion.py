"""Normalización de texto: port fiel de utils/text_processing.py del proyecto original.

Capa de dominio puro (P1): sin Django ni pandas. La única diferencia con el original
es el manejo de nulos, que allá dependía de pd.isna y aquí es Python estándar.
Toda keyword de regla y todo campo de licitación pasan por aquí ANTES de matchear,
de modo que 'Fibra Óptica' y 'FIBRA OPTICA' sean el mismo texto.
"""

import re
import unicodedata

_ESPACIOS_MULTIPLES = re.compile(r"\s+")
_ESPACIOS_EN_GUIONES = re.compile(r"\s*-\s*")
_NO_ALFANUMERICO_NI_GUION = re.compile(r"[^\w\-]")


def _es_nulo(valor: object) -> bool:
    """Equivalente sin pandas de pd.isna: None o float NaN (NaN != NaN)."""
    return valor is None or (isinstance(valor, float) and valor != valor)


def normalizar_texto(texto: object, *, uppercase: bool = True) -> str:
    """Remueve acentos (NFKD → ascii), colapsa espacios y unifica mayúsculas.

    Misma semántica que el original: 'Construcción  de   Cañerías' → 'CONSTRUCCION DE CANERIAS'.
    """
    if _es_nulo(texto):
        return ""

    resultado = str(texto).strip()
    if not resultado:
        return ""

    resultado = unicodedata.normalize("NFKD", resultado)
    resultado = resultado.encode("ascii", "ignore").decode("ascii")
    resultado = _ESPACIOS_MULTIPLES.sub(" ", resultado).strip()

    return resultado.upper() if uppercase else resultado.lower()


def limpiar_codigo_licitacion(codigo: object) -> str:
    """Normaliza un código de licitación: '1234 - 56 - L126 ' → '1234-56-L126'."""
    if _es_nulo(codigo):
        return ""

    resultado = _ESPACIOS_EN_GUIONES.sub("-", str(codigo).strip())
    resultado = _NO_ALFANUMERICO_NI_GUION.sub("", resultado)
    return resultado.upper()
