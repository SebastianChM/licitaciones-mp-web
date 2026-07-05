# Registro de decisiones (ADR ligero)

Formato por entrada: **Contexto → Decisión → Consecuencias**. Toda desviación de PLAN.md
y toda dependencia nueva se registra aquí (O1 y P7 de CLAUDE.md).

---

## 2026-07-05 — Django 5.2 LTS en lugar de 6.0

**Contexto:** pip instala Django 6.0 por defecto (última versión). PLAN.md especifica 5.x LTS.
**Decisión:** fijar `django~=5.2.0` (LTS, soporte extendido hasta abril 2028).
**Consecuencias:** el stack coincide con el que las empresas mantienen en producción;
actualizar a la siguiente LTS será una decisión explícita, no un accidente de pip.

## 2026-07-05 — Dependencias iniciales

| Paquete | Problema que resuelve | Alternativa descartada |
|---|---|---|
| djangorestframework | API REST (serialización, viewsets, auth) | API a mano con JsonResponse (reinventar validación) |
| django-filter | Filtros declarativos en endpoints de listado | Parseo manual de query params |
| pydantic-settings | Variables de entorno tipadas con validación fail-fast; continuidad con Licitaciones_MP | django-environ (menos validación de tipos) |
| pytest / pytest-django | Suite de tests; mismo runner que el proyecto original | unittest (más verboso) |
| factory-boy | Fábricas de modelos en tests | fixtures JSON (frágiles, difíciles de mantener) |
| ruff | Lint + format, mismo estándar del proyecto original | flake8+isort+black (3 herramientas) |
| coverage | Gate de cobertura 85% | — |
| pre-commit | Calidad antes de cada commit | confiar en la disciplina manual |
| requests | HTTP hacia portal/API MP (M1/M4); mismas políticas de resiliencia del original | httpx (async innecesario en batch) |
| openpyxl | Parseo del Excel masivo del portal (adaptador de ingesta) y export desde Admin | pandas (dependencia pesada innecesaria: no hay análisis, solo lectura de filas) |

**Nota sobre pandas:** el proyecto original lo usa porque su dominio ES DataFrames. Aquí el
dominio son objetos y filas de BD; openpyxl en modo read-only basta para iterar el XLSX del
portal. Menos dependencias, menos superficie.
