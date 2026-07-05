"""Tests del dominio de normalización (puros, sin BD).

Casos portados de la semántica de utils/text_processing.py del proyecto original:
el motor de matching (M2) depende de que estos comportamientos sean idénticos.
"""

import pytest

from domain.normalizacion import limpiar_codigo_licitacion, normalizar_texto

pytestmark = pytest.mark.unit


class TestNormalizarTexto:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ("Construcción de Cañerías", "CONSTRUCCION DE CANERIAS"),
            ("fibra   óptica", "FIBRA OPTICA"),
            ("  ingeniería  ", "INGENIERIA"),
            ("ADQUISICIÓN", "ADQUISICION"),
            ("señalética vial", "SENALETICA VIAL"),
        ],
    )
    def test_remueve_acentos_y_colapsa_espacios(self, entrada: str, esperado: str) -> None:
        assert normalizar_texto(entrada) == esperado

    def test_nulos_y_vacios_devuelven_string_vacio(self) -> None:
        assert normalizar_texto(None) == ""
        assert normalizar_texto("") == ""
        assert normalizar_texto("   ") == ""
        assert normalizar_texto(float("nan")) == ""

    def test_minusculas_cuando_se_pide(self) -> None:
        assert normalizar_texto("Fibra Óptica", uppercase=False) == "fibra optica"

    def test_acepta_valores_no_string(self) -> None:
        assert normalizar_texto(1234) == "1234"


class TestLimpiarCodigoLicitacion:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ("1234 - 56 - L126 ", "1234-56-L126"),
            ("1234-56-le26", "1234-56-LE26"),
            ("  748-33-LQ26", "748-33-LQ26"),
            ("748/33*LQ26", "74833LQ26"),
        ],
    )
    def test_limpia_espacios_y_caracteres_extranos(self, entrada: str, esperado: str) -> None:
        assert limpiar_codigo_licitacion(entrada) == esperado

    def test_nulo_devuelve_vacio(self) -> None:
        assert limpiar_codigo_licitacion(None) == ""
