"""Smoke tests del scaffold: si esto falla, el proyecto no arranca."""

import pytest
from django.contrib.auth import get_user_model


@pytest.mark.unit
def test_settings_cargan() -> None:
    from django.conf import settings

    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == [
        "rest_framework.permissions.IsAuthenticated"
    ]


@pytest.mark.unit
def test_settings_del_proveedor_expuestos_en_mayusculas() -> None:
    """Regresión: django.conf.settings solo expone atributos en MAYÚSCULAS.

    ingestar_bulk fallaba con AttributeError al leer settings.env (minúscula).
    Los valores del proveedor deben estar como settings estándar.
    """
    from django.conf import settings

    assert settings.MP_BULK_URL.startswith("https://")
    assert settings.MP_API_BASE_URL.startswith("https://")
    # P12: el delay de la API pública de MP nunca baja de 7 segundos.
    assert settings.MP_API_DELAY_SEGUNDOS >= 7.0


@pytest.mark.integration
@pytest.mark.django_db
def test_custom_user_se_crea() -> None:
    user = get_user_model().objects.create_user(username="sebastian", password="x1y2z3!seguro")
    assert user.pk is not None
    assert user.check_password("x1y2z3!seguro")


@pytest.mark.integration
@pytest.mark.django_db
def test_admin_responde(client) -> None:
    respuesta = client.get("/admin/login/")
    assert respuesta.status_code == 200
