# Licitaciones MP Web

Plataforma web para descubrimiento, filtrado y gestión de licitaciones públicas de
[Mercado Público](https://www.mercadopublico.cl) (Chile). Django 5.2 LTS + Django REST
Framework.

Cada día el portal publica ~12.000 filas de licitaciones. Este sistema las ingesta,
las evalúa contra reglas de filtrado por equipo (con trazabilidad de por qué cada una
entró o salió) y las expone en una API REST donde los equipos gestionan su trabajo
sobre las relevantes (~80 por equipo).

## De dónde viene

Es la **evolución web** de [Licitaciones_MP](https://github.com/SebastianChM/Licitaciones_MP),
un pipeline ETL de escritorio (Python, 501 tests, 95% cobertura) que resolvía el mismo
problema con archivos Excel como almacenamiento. Esta versión ataca sus límites
estructurales:

| Problema del sistema de escritorio | Solución en esta versión |
|---|---|
| El Excel de salida era también el espacio de trabajo: cada regeneración amenazaba las anotaciones manuales (la etapa 5 preservaba formato celda a celda) | Separación de modelos: `Licitacion` (hechos, refrescables por ingesta) vs `GestionLicitacion` (estado humano que la ingesta tiene prohibido tocar) |
| Un pipeline por equipo generaba archivos disjuntos | `EvaluacionFiltro` es una relación licitación x perfil: una licitación puede ser relevante para Telecom e irrelevante para Arquitectura a la vez |
| Análisis incremental comparando archivos históricos | Una consulta: `first_seen_run` de la última ingesta (`GET /api/licitaciones/nuevas/`) |
| Configuración en `PIVOT_MAESTRO.xlsx` | Reglas en BD editables por Django Admin, con puente de migración: `manage.py importar_pivot` lee el PIVOT original |
| Filtrado acoplado a pandas/DataFrames | Motor de matching como **dominio puro** (`domain/matching.py`, sin imports de Django ni pandas), validado portando los tests del original |

## Arquitectura

```
ChileCompra (bulk XLSX diario)          API oficial MP (JSON)
        |                                     |
        v                                     v
  manage.py ingestar_bulk              manage.py enriquecer
  (upsert idempotente,                 (ficha completa de las relevantes:
   ZIP-unwrap, header dinamico)         delay 7s, circuit breaker,
                                        checkpoint en BD, reanudable)
        |
        v
  +--------------------- BD (fuente de verdad) ----------------------+
  | catalogo   : Organismo, Rubro (taxonomia UNSPSC)                 |
  | licitaciones: Licitacion (hechos + raw payloads auditables)      |
  |               EvaluacionFiltro (resultado x perfil, trazabilidad)|
  | perfiles   : PerfilFiltro, ReglaKeyword, PalabraIntencion        |
  | gestion    : GestionLicitacion (workflow humano)                 |
  | ops        : EjecucionPipeline (observabilidad), TipoCambio      |
  +------------------------------------------------------------------+
        ^                          |                        |
        |                          v                        v
  manage.py evaluar          DRF API (token auth)      Django Admin
  (motor domain/matching:    /api/licitaciones/        (reglas, export
   inclusion, exclusion,     /api/gestiones/            Excel, operacion)
   bypass, intent gate,      /api/token/
   deteccion de keywords
   toxicas)
```

La ingesta y la evaluación son procesos batch (el rate limit de la API pública de MP,
~8 req/min, hace inviable cualquier enfoque online); la web consulta la BD. El formato
del proveedor solo existe dentro de su adaptador (`apps/licitaciones/ingesta.py`): si
ChileCompra cambia el canal, se reescribe un módulo.

## Arranque rápido

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
```

Cargar datos y evaluar:

```bash
python manage.py importar_pivot ruta/al/PIVOT_MAESTRO.xlsx  # reglas por equipo
python manage.py ingestar_bulk                              # bulk diario del portal
python manage.py evaluar                                    # motor de filtrado
python manage.py enriquecer                                 # ficha oficial de las relevantes (requiere ticket)
python manage.py runserver
```

Todos los comandos soportan `--dry-run` y registran su ejecución con métricas en
`EjecucionPipeline` (visible en el Admin).

## API

Autenticación: `POST /api/token/` con `username`/`password` devuelve el token
(`Authorization: Token <valor>`).

| Request | Devuelve |
|---|---|
| `GET /api/licitaciones/?equipo=TELECOM&relevantes=true` | Las relevantes para un equipo (incluidas + rescatadas por bypass) |
| `GET /api/licitaciones/?equipo=TELECOM&confianza=alta&cierra_desde=2026-07-10` | Combinable con confianza del intent gate, fechas, montos, región |
| `GET /api/licitaciones/?search=fibra+optica` | Búsqueda por código, nombre y organismo |
| `GET /api/licitaciones/1234-56-L126/` | Detalle con taxonomía, evaluaciones y trazabilidad de keywords |
| `GET /api/licitaciones/nuevas/` | Licitaciones nuevas de la última ingesta (el "incremental") |
| `POST /api/gestiones/` `{licitacion, perfil, estado}` | Abre el seguimiento de un equipo sobre una licitación |
| `PATCH /api/gestiones/{id}/` `{estado, notas}` | Avanza el workflow (autor registrado automáticamente) |

## Calidad

```bash
ruff check . && ruff format --check .      # lint estricto (reglas E,F,I,UP,B,SIM,DTZ,RUF,C4,PTH,PERF,S,ANN,DJ)
coverage run -m pytest && coverage report  # gate 85% (actual: 93%)
```

- 80+ tests: dominio puro (paridad semántica con el sistema original), constraints de
  modelos, comandos con fixtures sintéticas (sin red), API con presupuesto de queries
  (listados sin N+1).
- CI en GitHub Actions: lint, `makemigrations --check` y tests con gate de cobertura.
- Reglas de ingeniería del proyecto en [CLAUDE.md](CLAUDE.md); decisiones y hallazgos
  (incluido un bug latente del sistema original detectado por los tests de paridad) en
  [docs/decisiones.md](docs/decisiones.md).

## Roadmap

- `manage.py sincronizar_estados`: refresco intradía de estado/fecha de cierre
- `TipoCambio` alimentado por CMF/Frankfurter para conversión CLP auditable
- Deploy con PostgreSQL

## Stack

Django 5.2 LTS · Django REST Framework · django-filter · pydantic-settings ·
openpyxl · pytest-django · factory-boy · ruff · SQLite (dev) / PostgreSQL-ready
