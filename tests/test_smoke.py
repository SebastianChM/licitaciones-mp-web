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
