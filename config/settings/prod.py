"""Settings de producción: DEBUG apagado, seguridad reforzada.

Requiere en el entorno: LICITAWEB_SECRET_KEY y LICITAWEB_ALLOWED_HOSTS reales.
Verificar con `manage.py check --deploy` antes de desplegar (O9 de CLAUDE.md).
"""

from .base import *
from .base import env

DEBUG = False

if env.secret_key == "dev-only-insecure-key-change-me":  # noqa: S105 # pragma: no cover
    msg = "LICITAWEB_SECRET_KEY no configurada: producción no puede usar la clave de desarrollo."
    raise RuntimeError(msg)

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
