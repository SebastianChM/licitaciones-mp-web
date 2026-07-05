"""Modelo de usuario propio.

Se define desde la primera migración (PLAN.md §2.3): Django no permite cambiar
AUTH_USER_MODEL después sin reescribir el esquema. Hoy no agrega campos; existe
para que agregar equipo/rol/preferencias mañana sea una migración trivial.
"""

from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
