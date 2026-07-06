# Registro de decisiones (ADR ligero)

## 2026-07-06 — Pivote de producto: de equipos corporativos a búsquedas por usuario

**Contexto:** el concepto "equipo" (TELECOM, ARQ...) venía del contexto IDOM del proyecto
original, con reglas mantenidas en un Excel (PIVOT_MAESTRO). El owner quiere un producto
usable por cualquier persona: crear búsquedas y administrar reglas desde la página, sin
intervención en Excel.
**Decisión:** `PerfilFiltro` se re-semantiza como "búsqueda guardada" con `propietario`
(FK a User): mismo modelo relacional (EvaluacionFiltro por licitación x perfil,
GestionLicitacion por perfil), nueva semántica de producto. El portal agrega CRUD de
búsquedas y reglas (con la misma normalización del import) y un botón "Re-evaluar ahora"
que corre el motor en la request (el motor evalúa ~4k licitaciones en segundos; no
necesita cola). Cada usuario ve SOLO sus búsquedas (aislamiento con 404). `importar_pivot`
pasa de requisito a herramienta opcional de migración. La ingesta y el enriquecimiento
siguen siendo batch programado: son infraestructura de datos, no reglas del usuario.
**Consecuencias:** el parámetro de URL pasa de `equipo` a `perfil` en el portal; la API
acepta ambos (`equipo` queda como alias deprecado). Las búsquedas existentes se asignan
al primer usuario en una migración de datos.

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

## 2026-07-06 — Frontend: templates de Django + CSS propio, sin SPA ni build step

**Contexto:** el Admin es una herramienta de operación, no un producto usable por el
equipo comercial. Se necesita una interfaz amigable para el flujo diario (ver relevantes,
revisar trazabilidad, avanzar el estado de gestión).
**Decisión:** app `portal` con vistas server-rendered (Django templates) y un design
system CSS propio (custom properties, un solo archivo estático). Sin React/Vue (P5:
sobre-ingeniería para un MVP de equipo interno; agregaría build step, CORS y manejo de
estado duplicado), sin Tailwind/Bootstrap (P7: dependencia no justificada cuando el
alcance visual es una lista, un detalle y un formulario), sin htmx por ahora (candidato
natural si el portal crece; queda como evolución documentada).
**Consecuencias:** interactividad por formularios GET/POST estándar (funciona sin JS);
la API DRF queda para integraciones externas y el portal usa vistas propias con la
sesión de Django. Si el producto crece a interacciones ricas, el paso siguiente es htmx,
no un SPA.

**Rediseño v2 (mismo día, feedback del owner):** la primera versión era competente pero
genérica. El rediseño parte del trabajo del usuario (triaje diario contra fecha de
cierre): la cuenta regresiva de cierre es el elemento protagonista de la tabla; los
equipos pasan de dropdown a navegación primaria en sidebar; las tarjetas de resumen son
filtros clicables; la trazabilidad se presenta como pipeline de pasos y no como lista de
chips. Tipografía Inter variable self-hosted (un solo woff2 estático, licencia OFL, sin
CDN) con numerales tabulares para códigos y montos.

## 2026-07-06 — Enriquecimiento: la BD reemplaza a los checkpoints JSONL

**Contexto:** la etapa 3 del original persiste checkpoints JSONL (hash del dataset,
recuperación de registros exitosos) para reanudar tras cortes, porque su almacenamiento
son archivos. Aquí la fuente de verdad es la BD.
**Decisión:** el checkpoint ES el modelo: `enriquecida_en` vacío = pendiente. El comando
`enriquecer` procesa `relevantes sin enriquecer` y guarda cada licitación apenas llega su
ficha; interrumpir y relanzar retoma exactamente donde quedó, sin archivos auxiliares.
Las licitaciones que la API no indexa ("Listado vacío") se marcan con
`raw_api.sin_datos` para no reintentarlas a diario. Cada ficha se guarda en su propia
escritura (excepción deliberada a O3: a ~8 req/min, una transacción global perdería
media hora de trabajo ante cualquier corte; el ítem es la unidad atómica correcta).
**Consecuencias:** menos piezas móviles que el original (sin archivos de checkpoint, sin
hash de dataset, sin limpieza por retención); "reanudar" y "correr de nuevo" son el mismo
comando. Solo se enriquecen las relevantes: el universo completo tomaría más de un día al
ritmo del rate limit.

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
