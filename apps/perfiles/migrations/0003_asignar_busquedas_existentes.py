"""Migración de datos del pivote de producto (decisiones.md 2026-07-06).

Las búsquedas creadas antes de existir `propietario` (los equipos importados
del PIVOT) se asignan al primer usuario del sistema para que su portal siga
funcionando; si no hay usuarios, quedan sin dueño y el Admin las administra.
"""

from django.db import migrations


def asignar_al_primer_usuario(apps, schema_editor):  # noqa: ANN001, ARG001
    PerfilFiltro = apps.get_model("perfiles", "PerfilFiltro")
    User = apps.get_model("accounts", "User")
    primero = User.objects.order_by("pk").first()
    if primero is not None:
        PerfilFiltro.objects.filter(propietario__isnull=True).update(propietario=primero.pk)


def desasignar(apps, schema_editor):  # noqa: ANN001, ARG001
    PerfilFiltro = apps.get_model("perfiles", "PerfilFiltro")
    PerfilFiltro.objects.update(propietario=None)


class Migration(migrations.Migration):
    dependencies = [
        ("perfiles", "0002_alter_perfilfiltro_options_perfilfiltro_propietario"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(asignar_al_primer_usuario, desasignar),
    ]
