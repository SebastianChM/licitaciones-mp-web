# Arquitectura y Plan — Licitaciones MP Web (v2)

> v2 reemplaza el plan inicial tras el análisis en profundidad del código fuente de
> [Licitaciones_MP](https://github.com/SebastianChM/Licitaciones_MP). La sección 1 documenta
> lo que el sistema ES realmente; la sección 2, las decisiones arquitectónicas que se derivan.

---

## 1. Análisis del sistema existente (lo que el código dice, no el README)

### 1.1 Anatomía real del flujo de datos

```
   PORTAL MP (att.ashx?id=5)          API oficial MP (JSON)         CMF / Frankfurter
   Excel masivo ~12.000/día           licitaciones.json             (UTM / USD)
        |                                  |                              |
        v                                  v                              v
  [E0 Descarga]---(histórico 30d)   [E3 Enriquecimiento]          [E4 Reporte Excel]
        |                            - ticket en .env               - conversión moneda
        v                            - delay 7s (≈8 req/min!)       - formato ejecutivo
  [E1 Auditoría taxonomía]           - circuit breaker                    |
        |                            - checkpoints JSONL                  v
        v                              reanudables (hash dataset)  [E5 Incremental]
  [E2 Filtrado multi-equipo]         - caché por código            - merge con reporte previo
   FilterProfile por equipo                                        - PRESERVA celdas editadas
   (PIVOT_MAESTRO.xlsx)                                              a mano por los usuarios
```

### 1.2 Fortalezas de diseño (se conservan conceptualmente)

1. **Capa de dominio pura.** `FilterProfile`, `EquipoInfo`, `IntencionGlobal` son dataclasses congeladas sin dependencia de pandas/Excel. El `ProfileLoader` es un adaptador Excel→dominio. Esto ya es arquitectura hexagonal en miniatura y es la pieza más valiosa a portar.
2. **Contrato de etapas.** `BaseStage` (Template Method: bind→validate→execute→cleanup) + `StageResult` + `PipelineContext` desacoplan orquestación de lógica.
3. **Semántica de filtrado no trivial.** No son "3 fases con keywords": hay mapeo campo→grupo de reglas (nombre/nivel1-3/genérico/organismo/valor/componente), word-boundary para siglas ≤4 chars (evita que "ITO" matchee "circuITO"), solo-frases en descripción libre, **trazabilidad por fila** (qué keyword la incluyó/excluyó), detección de **exclusiones tóxicas** (keyword que mata >10% del universo), exclusión dura no bypasseable, **intent gate** con veto/confianza (ALTA/REVISAR) y boost por taxonomía UNSPSC.
4. **Resiliencia HTTP madura.** Retries con backoff, renovación de sesión TCP tras timeout, respeto de Retry-After en 429, health check previo, checkpoints reanudables.
5. **Calidad:** 501 tests, 95% cobertura, ruff estricto, CI.

### 1.3 Restricciones arquitectónicas que el plan v1 ignoraba

| # | Hecho del sistema real | Implicancia para la versión web |
|---|---|---|
| R1 | La fuente primaria es el **Excel masivo diario** (12k filas), no la API. La API pública permite ~8 req/min (delay 7s) — enumerar 12k licitaciones por API tomaría 25 horas. | La ingesta web mantiene la misma asimetría: bulk Excel → BD, API solo para enriquecer el subconjunto filtrado (~300). |
| R2 | Enriquecer ~300 licitaciones a 7s c/u toma **~35 minutos**. | Jamás puede ocurrir en un request HTTP. Ingesta y enriquecimiento son **procesos batch** (management commands + scheduler), la web solo lee BD. Sin Celery: un comando + cron es honesto y suficiente. |
| R3 | El sistema es **multi-equipo**: cada equipo tiene su FilterProfile y hoy el pipeline corre por-equipo generando archivos disjuntos. | El resultado de filtrado NO es un atributo de la licitación: es una relación. `EvaluacionFiltro(licitacion, perfil_equipo)` N:M con trazabilidad y confianza por evaluación. El modelo relacional expresa lo que los archivos no pueden: una licitación evaluada por 3 equipos a la vez. |
| R4 | La etapa 5 existe porque **el reporte Excel es el espacio de trabajo del usuario** (colores, anotaciones, seguimiento) y cada regeneración amenaza ese trabajo. | Insight central del re-modelado: separar **hechos** (datos de la fuente, refrescables por ingesta) de **gestión humana** (estado, notas, asignación — que la ingesta jamás toca). `Licitacion` vs `GestionLicitacion`. La invariante reemplaza al hack de preservación de celdas. |
| R5 | La configuración vive en `PIVOT_MAESTRO.xlsx` y los usuarios reales la editan ahí. | El Admin la reemplaza, pero se construye un **puente**: comando `importar_pivot` que carga el PIVOT existente a la BD. Migración sin fricción y demuestra respeto por el workflow real. |
| R6 | El filtrado opera sobre DataFrames con columnas normalizadas y regex por keyword. | Portarlo "a QuerySets" (plan v1) era ingenuo: se perdería trazabilidad por keyword y la semántica de boundaries. El motor de matching se porta como **módulo de dominio puro** (strings → resultado), sin imports de Django ni pandas. La BD guarda resultados, no ejecuta la semántica. |
| R7 | Conversión de moneda con APIs externas (CMF/Frankfurter) y fallbacks hardcodeados (UTM=65000). | Modelo `TipoCambio` con tasa diaria cacheada en BD; conversión en ingesta; fallback explícito y auditable. |

## 2. Arquitectura propuesta

### 2.1 Vista de capas (hexagonal pragmático)

```
ADAPTADORES DE ENTRADA (batch, programables por scheduler)
  Puerto: FuenteLicitaciones — interfaz que entrega objetos de dominio.
  El formato del proveedor (XLSX hoy, JSON mañana) toca SOLO su adaptador;
  si ChileCompra cambia el canal, se escribe un adaptador nuevo y nada más.

  manage.py ingestar_bulk         # adaptador BulkPortalSource: descarga el Excel
                                  #   masivo del portal → upsert Licitacion (idempotente).
                                  #   Única vía con los campos que el filtrado necesita.
  manage.py sincronizar_estados   # adaptador ApiListSource: API listado (1 request,
                                  #   barata) → refresca estado/fecha_cierre de las
                                  #   licitaciones YA seguidas. Corre intradía.
  manage.py evaluar --equipo X    # corre el motor de matching → EvaluacionFiltro
  manage.py enriquecer            # API detalle, delay 7s, reanudable → completa Licitacion
  manage.py importar_pivot        # PIVOT_MAESTRO.xlsx → PerfilFiltro/Reglas en BD
        |
        v
DOMINIO PURO (sin imports de Django — extraíble a paquete compartido a futuro)
  domain/matching.py    # port fiel de la semántica de etapa2:
                        #   evaluar(campos_texto, perfil) -> Evaluacion(
                        #     incluida, trazabilidad, motivo_exclusion,
                        #     bypass, confianza ALTA/REVISAR/N/A)
  domain/normalizacion.py  # port de text_processing (mismos casos de test)
        |
        v
MODELOS (persistencia, fuente de verdad)
  catalogo:  Organismo, Rubro
  licitaciones: Licitacion (hechos, raw_payload JSON, refrescable)
                EvaluacionFiltro (licitacion × perfil, resultado + trazabilidad)
  perfiles:  PerfilFiltro (equipo), ReglaKeyword (tipo: inclusion/exclusion/
             bypass/exclusion_dura, campo_objetivo), IntencionGlobal
  gestion:   GestionLicitacion (estado workflow, notas, asignado) ← ingesta NUNCA escribe aquí
  ops:       EjecucionPipeline (runs, métricas, hallazgos), TipoCambio
        |
        v
INTERFACES DE SALIDA
  DRF API: /api/licitaciones/ (filtros por equipo/confianza/monto/región/fecha,
           búsqueda, paginación), /api/licitaciones/nuevas/, auth token
  Admin:   CRUD de perfiles/reglas, dashboard de ejecuciones, export Excel (openpyxl)
```

### 2.2 Decisiones y su justificación (defendibles en entrevista)

| Decisión | Alternativa descartada | Por qué |
|---|---|---|
| Repo nuevo; ETL intacto | Importar el ETL como librería | El ETL está sanamente acoplado a SU contexto (filesystem, Config de rutas Windows, ciclo BaseStage). Forzar su reuso acoplaría la web al pipeline de archivos. Los dos repos cuentan la evolución. |
| Motor de matching como dominio puro (strings→resultado) | Filtrar con QuerySets/SQL | Preserva semántica 1:1 (boundaries, frases, trazabilidad), testeable con los mismos casos del original, independiente de BD. SQL no puede reportar QUÉ keyword matcheó sin N consultas. |
| Batch commands + scheduler para ingesta/enriquecimiento | Celery/Redis | R2: el enriquecimiento tarda ~35 min por rate limit externo. Un command idempotente y reanudable + cron resuelve lo mismo sin infraestructura. Celery queda como evolución documentada. |
| `Licitacion` (hechos) separado de `GestionLicitacion` (humano) | Un solo modelo | R4: la ingesta refresca hechos sin riesgo para el trabajo humano. Es la versión relacional correcta del problema que etapa5 resuelve con copias de celdas. |
| `EvaluacionFiltro` como relación licitacion×perfil | Campo `resultado_filtro` en Licitacion (plan v1) | R3: multi-equipo. Además permite re-evaluar al cambiar reglas sin re-ingestar, y comparar perfiles. |
| Puente `importar_pivot` | Migración manual de reglas | R5: onboarding en un comando; demuestra pensamiento de migración real. |
| SQLite dev / PostgreSQL prod | Solo SQLite | JSONField y `iregex` funcionan en ambos; settings por entorno hacen el switch. |

### 2.3 Modelo de datos (v2)

```
Organismo         codigo (unique), nombre, region
Rubro             nivel (1/2/3), nombre (los "Nivel 1-3" de la taxonomía UNSPSC)
Licitacion        codigo_externo (unique, index), nombre, descripcion, organismo FK,
                  rubros M2M, tipo_adquisicion, estado_fuente, monto_estimado,
                  moneda (CLP/UTM/USD), monto_clp_calculado, fecha_publicacion,
                  fecha_cierre, url_ficha, raw_bulk (JSON), raw_api (JSON, nullable),
                  enriquecida_en (nullable), first_seen_run FK, created/updated
PerfilFiltro      codigo ("TELECOM"), nombre, activo
ReglaKeyword      perfil FK, texto, tipo (incluir/excluir/bypass/exclusion_dura),
                  campo_objetivo (nombre/nivel1/nivel2/nivel3/generico/organismo/
                  valor/componente), activa
IntencionGlobal   singleton lógico: palabras requeridas / vetadas
EvaluacionFiltro  licitacion FK, perfil FK, resultado (incluida/excluida/bypass/
                  vetada_intencion/exclusion_dura), trazabilidad (JSON: keywords
                  que matchearon y en qué campo), confianza (ALTA/REVISAR/NA),
                  evaluada_en — unique_together (licitacion, perfil)
GestionLicitacion licitacion FK, perfil FK, estado (nueva/en_revision/preparando_
                  oferta/presentada/descartada), notas, asignado_a FK User,
                  actualizado_por, updated_at
EjecucionPipeline tipo (ingesta/evaluacion/enriquecimiento), iniciada/terminada,
                  metricas (JSON: totales por fase, exclusiones tóxicas, hallazgos)
TipoCambio        fecha, moneda, tasa_clp, fuente (unique fecha+moneda)
```

### 2.4 Qué se porta, qué se re-modela, qué se descarta

- **Se porta fiel (con sus tests):** normalización de texto, semántica completa de matching de etapa2 (incluye trazabilidad, tóxicas, intent gate, boost UNSPSC), políticas HTTP (retry/backoff/429), patrón checkpoint para el enriquecimiento.
- **Se re-modela:** persistencia (Excel→BD), incremental (merge de archivos→consulta por `first_seen_run`), trabajo manual (formato de celdas→`GestionLicitacion`), configuración (PIVOT→Admin, con puente de importación), multi-equipo (archivos disjuntos→`EvaluacionFiltro`).
- **Se descarta:** GUI Tkinter (reemplazada por Admin + API), launcher VBS/instalador (reemplazado por README + settings), gestión de carpetas numeradas.

## 3. Milestones (v2)

| # | Entregable | Definición de "hecho" |
|---|---|---|
| M0 | Scaffold: proyecto, settings por entorno, custom user, ruff/pytest/CI, repo GitHub | pytest y CI verdes, admin arriba |
| M1 | Modelos §2.3 + migraciones + Admin básico + `importar_pivot` + `ingestar_bulk` (idempotente, con archivo real del portal) | BD poblada con licitaciones del día real; perfiles importados del PIVOT de ejemplo |
| M2 | `domain/matching.py`: port fiel de etapa2 + comando `evaluar` + tests portados (boundaries, frases, bypass vs exclusión dura, intent gate) | Resultados equivalentes al original sobre el mismo dataset de prueba |
| M3 | API DRF (filtros por equipo/confianza/región/monto/fechas, búsqueda, paginación, token) + `GestionLicitacion` endpoints + tests | Cobertura ≥85%; colección de requests en README |
| M4 | `enriquecer` (API MP, delay 7s, reanudable) + export Excel desde Admin + README con esta arquitectura | Clonable y corrible con 3 comandos; presentable |
| M5 | (Stretch) vista HTML con templates, resumen LLM, Docker, deploy | Solo si M0–M4 sólidos |

## 4. Directivas (sin cambios de la v1, más dos nuevas)

Se mantienen todas las directivas de hacer/no hacer de la v1 (servicios delgados, idempotencia,
migraciones disciplinadas, sin Celery/microservicios, sin fabricar historia, secretos en .env,
no postular hasta M4). Se agregan:

11. **El motor de matching no importa Django ni pandas.** Si un test del dominio necesita
    levantar la BD, la capa está mal cortada.
12. **Paridad semántica verificable:** los casos de test del filtrado del proyecto original
    (word boundaries, frases, bypass, tóxicas, intent gate) se portan ANTES que el motor.
    El port se valida contra ellos (TDD sobre semántica existente).
