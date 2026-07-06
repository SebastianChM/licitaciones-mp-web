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

## 2026-07-05 — El bulk del portal es por ÍTEM, no por licitación

**Contexto:** la primera ingesta real leyó 17.812 filas pero solo 4.174 licitaciones únicas:
el Excel del portal repite la licitación una vez por cada producto/servicio que incluye
(por eso existe la columna "Descripción del producto/servicio").
**Decisión:** el upsert por `codigo_externo` colapsa las filas-ítem en una licitación (la
última fila gana en los campos escalares) y los rubros se ACUMULAN con `add()` en vez de
`set()` para conservar la taxonomía de todos los ítems.
**Consecuencias:** el conteo "actualizadas" de la ingesta incluye filas-ítem del mismo día,
no solo refrescos entre días. Limitación conocida a evaluar en M2: hoy `descripcion_producto`
conserva solo el último ítem; si el matching por COMPONENTE pierde señal, se acumularán los
ítems en un campo texto o tabla propia.

## 2026-07-05 — Port del motor corrige bug latente del boost UNSPSC

**Contexto:** en el original, `_TAXONOMIA_ALTA_N2` contiene frases CON acento
("servicios profesionales de ingeniería") que se comparan contra columnas normalizadas
SIN acentos; con o sin IGNORECASE, la í nunca matchea la I, así que el boost de Nivel 2
no podía disparar (el de Nivel 1, "consultoria", sí funciona por estar des-acentuado).
**Decisión:** en `domain/matching.py` las constantes del boost pasan por `normalizar_texto`
igual que los campos, con test que lo demuestra (`test_boost_unspsc_nivel2_dispara...`).
**Consecuencias:** el port NO es bit a bit idéntico al original: es fiel a la INTENCIÓN
documentada del original. Algunas licitaciones que allá quedaban en REVISAR aquí quedan
en ALTA, que es el comportamiento diseñado.
