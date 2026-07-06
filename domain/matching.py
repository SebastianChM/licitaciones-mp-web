"""Motor de matching: port fiel de la semántica de la etapa 2 del proyecto original.

Capa de dominio puro (P1): sin Django, sin pandas, sin BD. Opera sobre strings y
dataclasses; quien persiste resultados es la capa de servicios. La semántica
portada, validada por los tests del proyecto original (O2):

- Inclusión por grupos de campos (nombre/nivel1-3); el grupo 'nombre' aplica
  sobre nombre Y descripción, pero en descripción (texto libre) solo matchean
  frases multi-palabra, para evitar falsos positivos de keywords sueltas.
- Word boundary para keywords cortas (≤4 chars) en inclusión y bypass: 'ITO'
  no debe matchear 'circuITO', 'WAN' no debe rescatar 'WANDERSLEBEN'.
- Exclusión por substring plano sobre 8 grupos de campos, con trazabilidad.
- Bypass solo sobre nombre+descripción: rescata filas excluidas.
- Exclusión dura sobre nivel1/nivel2: no bypasseable.
- Intent gate global: 'vetada' descarta (frases por substring, palabras sueltas
  con boundary); 'requerida' marca confianza ALTA; zona gris queda REVISAR;
  boost por taxonomía UNSPSC eleva REVISAR a ALTA.

Corrección respecto del original (documentada en docs/decisiones.md): las
constantes del boost UNSPSC se normalizan igual que los campos; en el original
llevaban acentos y se comparaban contra texto des-acentuado, por lo que el
boost de Nivel 2 no podía disparar.
"""

import re
from dataclasses import dataclass, field

from domain.normalizacion import normalizar_texto

# Keywords de hasta este largo matchean como palabra completa en inclusión/bypass
# (siglas: BI, IA, ITS, ITO, GPS, CCTV, MPLS...). Mismo umbral que el original.
WORD_BOUNDARY_MAX_LEN = 4

# Resultados posibles de una evaluación. Los valores coinciden con los choices
# de EvaluacionFiltro.Resultado; el dominio no importa el modelo (P1).
RESULTADO_INCLUIDA = "incluida"
RESULTADO_BYPASS = "bypass"
RESULTADO_SIN_MATCH = "sin_match"
RESULTADO_EXCLUIDA = "excluida"
RESULTADO_EXCLUSION_DURA = "exclusion_dura"
RESULTADO_VETADA = "vetada"

CONFIANZA_ALTA = "alta"
CONFIANZA_REVISAR = "revisar"
CONFIANZA_NO_APLICA = "na"

# Taxonomía UNSPSC que implica confianza ALTA por definición (normalizada, ver docstring).
_TAXONOMIA_ALTA_NIVEL1 = tuple(normalizar_texto(t) for t in ("consultoría",))
_TAXONOMIA_ALTA_NIVEL2 = tuple(
    normalizar_texto(t)
    for t in (
        "servicios profesionales de ingeniería",
        "servicios de consultoría de ingeniería",
    )
)


@dataclass(frozen=True)
class ReglasEquipo:
    """Reglas de filtrado de un equipo, ya normalizadas (la capa de servicios las
    construye desde ReglaKeyword/PalabraIntencion; los tests, directamente)."""

    incluir: dict[str, tuple[str, ...]] = field(default_factory=dict)
    excluir: dict[str, tuple[str, ...]] = field(default_factory=dict)
    bypass: tuple[str, ...] = ()
    exclusion_dura: tuple[str, ...] = ()
    intencion_requerida: tuple[str, ...] = ()
    intencion_vetada: tuple[str, ...] = ()

    @property
    def intencion_habilitada(self) -> bool:
        return bool(self.intencion_requerida) or bool(self.intencion_vetada)


@dataclass(frozen=True)
class CamposLicitacion:
    """Los campos de texto de una licitación que participan del matching."""

    nombre: str = ""
    descripcion: str = ""
    nivel1: str = ""
    nivel2: str = ""
    nivel3: str = ""
    generico: str = ""
    organismo: str = ""
    tipo_adquisicion: str = ""
    descripcion_producto: str = ""


@dataclass(frozen=True)
class Evaluacion:
    """Resultado del motor para una licitación bajo un conjunto de reglas."""

    resultado: str
    confianza: str = CONFIANZA_NO_APLICA
    # {"inclusion": ["FIBRA OPTICA (nombre)"], "exclusion": [...], "bypass": [...],
    #  "exclusion_dura": [...], "intencion_vetada": [...]}
    trazabilidad: dict[str, list[str]] = field(default_factory=dict)

    @property
    def es_relevante(self) -> bool:
        return self.resultado in (RESULTADO_INCLUIDA, RESULTADO_BYPASS)


def _patron_con_boundary(keyword: str) -> str:
    """Escapa la keyword; las cortas (≤4) exigen palabra completa."""
    escapado = re.escape(keyword)
    if len(keyword) <= WORD_BOUNDARY_MAX_LEN:
        return rf"\b{escapado}\b"
    return escapado


def _patron_intencion(palabra: str) -> str:
    """Frases multi-palabra → substring; palabras sueltas → palabra completa."""
    escapado = re.escape(palabra)
    if " " in palabra.strip():
        return escapado
    return rf"\b{escapado}\b"


def _buscar(patron: str, texto: str) -> bool:
    return bool(re.search(patron, texto, re.IGNORECASE))


def _es_frase(keyword: str) -> bool:
    return " " in keyword.strip()


@dataclass(frozen=True)
class _CamposNormalizados:
    nombre: str
    descripcion: str
    nivel1: str
    nivel2: str
    nivel3: str
    generico: str
    organismo: str
    tipo_adquisicion: str
    descripcion_producto: str

    @classmethod
    def desde(cls, campos: CamposLicitacion) -> "_CamposNormalizados":
        return cls(
            nombre=normalizar_texto(campos.nombre),
            descripcion=normalizar_texto(campos.descripcion),
            nivel1=normalizar_texto(campos.nivel1),
            nivel2=normalizar_texto(campos.nivel2),
            nivel3=normalizar_texto(campos.nivel3),
            generico=normalizar_texto(campos.generico),
            organismo=normalizar_texto(campos.organismo),
            tipo_adquisicion=normalizar_texto(campos.tipo_adquisicion),
            descripcion_producto=normalizar_texto(campos.descripcion_producto),
        )


def _matches_inclusion(c: _CamposNormalizados, reglas: ReglasEquipo) -> list[str]:
    """Mapa de campos de inclusión del original: el grupo 'nombre' revisa nombre y
    descripción (esta última solo con frases); nivel1-3 revisan su campo."""
    objetivos = [
        (c.nombre, "nombre", "nombre", False),
        (c.descripcion, "nombre", "descripcion", True),
        (c.nivel1, "nivel1", "nivel1", False),
        (c.nivel2, "nivel2", "nivel2", False),
        (c.nivel3, "nivel3", "nivel3", False),
    ]
    encontrados: list[str] = []
    for texto, grupo, etiqueta, solo_frases in objetivos:
        if not texto:
            continue
        for keyword in reglas.incluir.get(grupo, ()):
            if solo_frases and not _es_frase(keyword):
                continue
            if _buscar(_patron_con_boundary(keyword), texto):
                entrada = f"{keyword} ({etiqueta})"
                if entrada not in encontrados:
                    encontrados.append(entrada)
    return encontrados


def _matches_exclusion(c: _CamposNormalizados, reglas: ReglasEquipo) -> list[str]:
    """Exclusión: substring plano (sin boundary), 8 grupos de campos como el original."""
    objetivos = [
        (c.nombre, "nombre", "nombre"),
        (c.descripcion, "nombre", "descripcion"),
        (c.nivel1, "nivel1", "nivel1"),
        (c.nivel2, "nivel2", "nivel2"),
        (c.nivel3, "nivel3", "nivel3"),
        (c.generico, "generico", "generico"),
        (c.organismo, "organismo", "organismo"),
        (c.tipo_adquisicion, "valor", "tipo_adquisicion"),
        (c.descripcion_producto, "componente", "descripcion_producto"),
    ]
    encontrados: list[str] = []
    for texto, grupo, etiqueta in objetivos:
        if not texto:
            continue
        for keyword in reglas.excluir.get(grupo, ()):
            if _buscar(re.escape(keyword), texto):
                entrada = f"{keyword} ({etiqueta})"
                if entrada not in encontrados:
                    encontrados.append(entrada)
    return encontrados


def _matches_bypass(c: _CamposNormalizados, reglas: ReglasEquipo) -> list[str]:
    """Bypass solo sobre nombre y descripción: organismo/tipo/producto generan
    falsos rescates (decisión del original)."""
    encontrados: list[str] = []
    for texto, etiqueta in ((c.nombre, "nombre"), (c.descripcion, "descripcion")):
        if not texto:
            continue
        for keyword in reglas.bypass:
            if _buscar(_patron_con_boundary(keyword), texto):
                entrada = f"{keyword} ({etiqueta})"
                if entrada not in encontrados:
                    encontrados.append(entrada)
    return encontrados


def _matches_exclusion_dura(c: _CamposNormalizados, reglas: ReglasEquipo) -> list[str]:
    encontrados: list[str] = []
    for texto, etiqueta in ((c.nivel1, "nivel1"), (c.nivel2, "nivel2")):
        if not texto:
            continue
        for categoria in reglas.exclusion_dura:
            if _buscar(re.escape(categoria), texto):
                entrada = f"{categoria} ({etiqueta})"
                if entrada not in encontrados:
                    encontrados.append(entrada)
    return encontrados


def _evaluar_intencion(
    c: _CamposNormalizados, reglas: ReglasEquipo
) -> tuple[str | None, str, list[str]]:
    """Devuelve (veto, confianza, trazabilidad_veto).

    veto: la palabra vetada que descarta la fila, o None.
    confianza: ALTA/REVISAR si el gate está habilitado; NO_APLICA si no.
    """
    if not reglas.intencion_habilitada:
        return None, CONFIANZA_NO_APLICA, []

    texto = f"{c.nombre} {c.descripcion}".strip()

    for palabra in reglas.intencion_vetada:
        if _buscar(_patron_intencion(palabra), texto):
            return palabra, CONFIANZA_NO_APLICA, [palabra]

    confianza = CONFIANZA_REVISAR
    if any(_buscar(_patron_intencion(p), texto) for p in reglas.intencion_requerida):
        confianza = CONFIANZA_ALTA

    # Boost UNSPSC: si el propio portal clasifica como consultoría/ingeniería,
    # esa señal supera al texto libre.
    if confianza == CONFIANZA_REVISAR:
        boost_n1 = any(_buscar(re.escape(t), c.nivel1) for t in _TAXONOMIA_ALTA_NIVEL1)
        boost_n2 = any(_buscar(re.escape(t), c.nivel2) for t in _TAXONOMIA_ALTA_NIVEL2)
        if boost_n1 or boost_n2:
            confianza = CONFIANZA_ALTA

    return None, confianza, []


def evaluar(campos: CamposLicitacion, reglas: ReglasEquipo) -> Evaluacion:
    """Evalúa una licitación contra las reglas de un equipo.

    Mismo orden de fases que la etapa 2 original: inclusión → exclusión →
    bypass → exclusión dura → intent gate.
    """
    c = _CamposNormalizados.desde(campos)
    trazabilidad: dict[str, list[str]] = {}

    inclusion = _matches_inclusion(c, reglas)
    if not inclusion:
        return Evaluacion(resultado=RESULTADO_SIN_MATCH)
    trazabilidad["inclusion"] = inclusion

    via_bypass = False
    exclusion = _matches_exclusion(c, reglas)
    if exclusion:
        trazabilidad["exclusion"] = exclusion
        bypass = _matches_bypass(c, reglas)
        if not bypass:
            return Evaluacion(resultado=RESULTADO_EXCLUIDA, trazabilidad=trazabilidad)
        trazabilidad["bypass"] = bypass
        via_bypass = True

    dura = _matches_exclusion_dura(c, reglas)
    if dura:
        trazabilidad["exclusion_dura"] = dura
        return Evaluacion(resultado=RESULTADO_EXCLUSION_DURA, trazabilidad=trazabilidad)

    veto, confianza, traza_veto = _evaluar_intencion(c, reglas)
    if veto is not None:
        trazabilidad["intencion_vetada"] = traza_veto
        return Evaluacion(resultado=RESULTADO_VETADA, trazabilidad=trazabilidad)

    resultado = RESULTADO_BYPASS if via_bypass else RESULTADO_INCLUIDA
    return Evaluacion(resultado=resultado, confianza=confianza, trazabilidad=trazabilidad)
