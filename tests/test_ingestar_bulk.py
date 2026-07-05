"""Tests del comando ingestar_bulk contra un bulk sintético (P16, O13: sin red ni portal)."""

import datetime
from pathlib import Path

import openpyxl
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalogo.models import Organismo, Rubro
from apps.licitaciones.models import Licitacion
from apps.ops.models import EjecucionPipeline

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

ENCABEZADO = [
    "Numero Adquisición",
    "Nombre Adquisición",
    "Descripción",
    "Nivel 1",
    "Nivel 2",
    "Nivel 3",
    "Genérico",
    "Organismo",
    "Tipo Adquisición",
    "Descripción del producto/servicio",
    "Región",
    "Moneda",
    "Monto Estimado",
    "Fecha Publicación",
    "Fecha Cierre",
]


def crear_bulk_sintetico(ruta: Path) -> Path:
    """Bulk mínimo con el layout real: fila de título decorativa + header + datos."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Licitaciones publicadas - datos sintéticos de prueba"])
    ws.append(ENCABEZADO)
    ws.append(
        [
            "1234-56-L126",
            "Consultoría en ingeniería de tránsito",
            "Estudio de flujos vehiculares",
            "Consultoría",
            "Servicios profesionales de ingeniería",
            "Ingeniería de tránsito",
            "Servicios",
            "Ministerio de Obras Públicas",
            "Licitación Pública",
            "Servicio de consultoría",
            "Región Metropolitana",
            "CLP",
            15000000,
            datetime.date(2026, 7, 1),
            datetime.datetime(2026, 7, 20, 15, 0),
        ]
    )
    ws.append(
        [
            "  7890 - 12 - LE26",
            "Adquisición de alimentos",
            "Compra de víveres",
            "Alimentos",
            "Comestibles",
            "Víveres",
            "Bienes",
            "Municipalidad de Prueba",
            "Licitación Pública",
            "Alimentos varios",
            "Valparaíso",
            "XXX",
            None,
            None,
            None,
        ]
    )
    # Fila decorativa sin código: debe descartarse.
    ws.append([None, "Subtotal", None, None, None, None, None, None])
    wb.save(ruta)
    return ruta


def test_ingesta_crea_licitaciones_organismos_y_rubros(tmp_path: Path) -> None:
    bulk = crear_bulk_sintetico(tmp_path / "bulk.xlsx")

    call_command("ingestar_bulk", "--archivo", str(bulk))

    assert Licitacion.objects.count() == 2
    licitacion = Licitacion.objects.get(codigo_externo="1234-56-L126")
    assert licitacion.organismo is not None
    assert licitacion.organismo.nombre == "Ministerio de Obras Públicas"
    assert licitacion.moneda == "CLP"
    assert licitacion.fecha_publicacion == datetime.date(2026, 7, 1)
    assert licitacion.raw_bulk  # la fila cruda queda auditable
    assert set(licitacion.rubros.values_list("nivel", flat=True)) == {1, 2, 3}
    # El código con espacios se limpia con la misma regla del proyecto original.
    assert Licitacion.objects.filter(codigo_externo="7890-12-LE26").exists()


def test_reingestar_actualiza_sin_duplicar_y_preserva_first_seen(tmp_path: Path) -> None:
    """O4 (idempotencia) + base del incremental: first_seen_run no cambia al refrescar."""
    bulk = crear_bulk_sintetico(tmp_path / "bulk.xlsx")
    call_command("ingestar_bulk", "--archivo", str(bulk))
    primera_run = Licitacion.objects.get(codigo_externo="1234-56-L126").first_seen_run

    call_command("ingestar_bulk", "--archivo", str(bulk))

    assert Licitacion.objects.count() == 2
    assert Organismo.objects.count() == 2
    assert Rubro.objects.count() == 6
    segunda = EjecucionPipeline.objects.order_by("-iniciada_en").first()
    assert segunda is not None
    assert segunda.metricas["creadas"] == 0
    assert segunda.metricas["actualizadas"] == 2
    assert Licitacion.objects.get(codigo_externo="1234-56-L126").first_seen_run == primera_run


def test_moneda_desconocida_genera_advertencia_y_no_rompe(tmp_path: Path) -> None:
    bulk = crear_bulk_sintetico(tmp_path / "bulk.xlsx")

    call_command("ingestar_bulk", "--archivo", str(bulk))

    licitacion = Licitacion.objects.get(codigo_externo="7890-12-LE26")
    assert licitacion.moneda == ""
    ejecucion = EjecucionPipeline.objects.get()
    assert any("XXX" in a for a in ejecucion.metricas["advertencias"])


def test_dry_run_no_escribe(tmp_path: Path) -> None:
    bulk = crear_bulk_sintetico(tmp_path / "bulk.xlsx")

    call_command("ingestar_bulk", "--archivo", str(bulk), "--dry-run")

    assert Licitacion.objects.count() == 0
    assert EjecucionPipeline.objects.get().metricas["dry_run"] is True


def test_bulk_envuelto_en_zip_se_desempaqueta(tmp_path: Path) -> None:
    """Regresión: el portal entrega el XLSX dentro de un ZIP contenedor.

    La primera ingesta real falló con KeyError '[Content_Types].xml' porque
    openpyxl recibió el ZIP envolvente en lugar del Excel interno (caso que la
    etapa 0 del proyecto original ya manejaba).
    """
    import zipfile

    interno = crear_bulk_sintetico(tmp_path / "interno.xlsx")
    envuelto = tmp_path / "descarga.zip"
    with zipfile.ZipFile(envuelto, "w") as zf:
        zf.write(interno, arcname="Licitacion_Publicada.xlsx")
    interno.unlink()

    call_command("ingestar_bulk", "--archivo", str(envuelto))

    assert Licitacion.objects.count() == 2


def test_archivo_sin_columna_de_referencia_falla_accionable(tmp_path: Path) -> None:
    ruta = tmp_path / "roto.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["cualquier", "cosa"])
    wb.save(ruta)

    with pytest.raises(CommandError, match=r"NIVEL 1"):
        call_command("ingestar_bulk", "--archivo", str(ruta))

    assert EjecucionPipeline.objects.get().estado == EjecucionPipeline.Estado.FALLIDA
