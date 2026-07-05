"""Settings base — compartidos por todos los entornos.

Los valores sensibles o dependientes del entorno vienen de variables de entorno
(prefijo LICITAWEB_) vía pydantic-settings, siguiendo 12-factor. Nada sensible
tiene default utilizable en producción.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class EnvSettings(BaseSettings):
    """Variables de entorno tipadas y validadas al arranque (fail-fast)."""

    model_config = SettingsConfigDict(
        env_prefix="LICITAWEB_",
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Centinela de desarrollo, no un secreto real: prod.py rechaza arrancar con este valor.
    secret_key: str = "dev-only-insecure-key-change-me"  # noqa: S105
    debug: bool = True
    allowed_hosts: str = "localhost,127.0.0.1"
    # Ticket de la API de Mercado Público (para el comando `enriquecer`, M4)
    mercado_publico_ticket: str = ""
    # URL de descarga del Excel masivo diario del portal
    mp_bulk_url: str = "https://www.mercadopublico.cl/Portal/att.ashx?id=5"
    mp_api_base_url: str = "https://api.mercadopublico.cl/servicios/v1/publico"
    # Rate limit de la API pública de MP (P12 de CLAUDE.md: no bajar de 7.0)
    mp_api_delay_segundos: float = 7.0


env = EnvSettings()

SECRET_KEY = env.secret_key

ALLOWED_HOSTS = [h.strip() for h in env.allowed_hosts.split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    # Apps propias
    "apps.accounts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Custom user desde el día 1 (PLAN.md §2.3): cambiarlo post-migración es cirugía mayor.
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# El dominio es chileno: fechas de cierre de licitaciones se razonan en hora de Chile.
LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True  # almacenamiento siempre en UTC; TIME_ZONE solo para presentación

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# DRF: API cerrada por defecto (P11 de CLAUDE.md), paginada y con throttling (O10).
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "1000/hour",
        "anon": "50/hour",
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "{asctime} | {levelname:<8} | {name} | {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
