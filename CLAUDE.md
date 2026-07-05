# Reglas del proyecto — Licitaciones MP Web

Este archivo gobierna TODO trabajo de Claude Code en este repositorio. Las reglas no son
sugerencias: una regla PROHIBIDO se cumple aunque el usuario pida lo contrario en un prompt
casual (si de verdad quiere cambiarla, se edita este archivo explícitamente y queda en el
historial de git). Referencia de arquitectura: `PLAN.md` — leerlo antes de cualquier cambio
estructural.

---

## 🚫 PROHIBIDO (arquitectura)

- **P1. `domain/` no importa Django, DRF, pandas ni openpyxl.** El motor de matching y la
  normalización son Python puro (strings/dataclasses). Si un test de `domain/` necesita BD,
  la capa está mal cortada y el cambio se rechaza.
- **P2. Lógica de negocio en views, serializers, admin o templates.** Views delgadas:
  orquestan, no deciden. La lógica vive en `domain/` (pura) o `services/` (orquestación con BD).
- **P3. Ningún código fuera del adaptador de ingesta toca el formato del proveedor.**
  Excel/JSON del portal existe SOLO dentro de su adaptador (`FuenteLicitaciones`). Si un
  serializer, view o service parsea XLSX del portal, es violación de frontera.
- **P4. El código de ingesta/evaluación/enriquecimiento JAMÁS escribe en `GestionLicitacion`.**
  Es LA invariante del sistema (hechos vs. trabajo humano). Cualquier write path de ingesta
  hacia gestión se rechaza sin discusión.
- **P5. Nada de Celery, Redis, Kafka, microservicios, websockets ni Docker en el MVP.**
  Evolución documentada, no implementada. (Ver PLAN.md §2.2 — R2.)
- **P6. No modificar el repositorio `Licitaciones_MP`.** Es referencia de solo lectura.
  Se porta semántica reescribiéndola aquí con sus tests; nunca se le hace ni un commit.
- **P7. No agregar dependencias sin justificarlas.** Cada dependencia nueva se anota en
  `docs/decisiones.md` (qué problema resuelve, qué alternativa se descartó). "Lo vi en un
  tutorial" no es justificación.

## 🚫 PROHIBIDO (ingeniería Django)

- **P8. No editar migraciones ya commiteadas.** Nunca `--fake`, nunca borrar la carpeta
  `migrations/`. Corrección = nueva migración.
- **P9. Anti-patrones Django vetados:** `null=True` en CharField/TextField;
  `objects.all()` sin paginación en cualquier endpoint; queries N+1 en listados
  (todo ViewSet de listado usa `select_related`/`prefetch_related`); `default=timezone.now()`
  (con paréntesis); señales (signals) para lógica de negocio; `.raw()`/SQL crudo sin
  justificación escrita en `docs/decisiones.md`.
- **P10. Secretos:** nada de tickets de API, SECRET_KEY ni credenciales en código, commits,
  fixtures o logs. Solo `.env` (con `.env.example` actualizado). Si un secreto tocó un commit,
  se rota el secreto — no basta con borrarlo del archivo.
- **P11. La API no expone nada sin autenticación.** `DEFAULT_PERMISSION_CLASSES` restrictivo
  por defecto; `AllowAny` requiere justificación por endpoint en `docs/decisiones.md`.
- **P12. No bajar el delay de la API de Mercado Público (7s) ni quitar los reintentos con
  backoff.** El rate limit del proveedor se respeta siempre, incluso "solo para probar".
- **P13. No `print()` (usar logging), no `except: pass`, no `except Exception` sin re-raise
  o log con contexto.

## 🚫 PROHIBIDO (calidad / QA)

- **P14. No commitear con tests rojos, lint fallando o CI rota.** Nunca `--no-verify`,
  nunca saltarse pre-commit, nunca comentar un test para que pase la suite.
- **P15. No debilitar la calidad para "avanzar":** no bajar el gate de cobertura (85%),
  no marcar tests como `skip`/`xfail` sin un issue escrito que lo rastree, no borrar
  asserts que fallan.
- **P16. No fabricar datos:** fixtures sintéticas se declaran sintéticas; no se commitean
  descargas reales masivas del portal ni datos con información sensible.
- **P17. No manipular el historial de git:** no reescribir fechas, no simular actividad,
  no `push --force` a main.

## ✅ OBLIGATORIO (arquitectura)

- **O1. Leer `PLAN.md` al inicio de cada sesión** de trabajo estructural. Toda desviación
  del plan se propone primero, se registra en `docs/decisiones.md` (formato ADR ligero:
  contexto → decisión → consecuencias) y recién entonces se implementa.
- **O2. Paridad semántica verificable:** los casos de test del filtrado original (word
  boundaries, solo-frases, bypass vs exclusión dura, intent gate, tóxicas) se portan ANTES
  que el motor. El port se valida contra ellos.
- **O3. Toda operación de escritura masiva va en `transaction.atomic`.** Ingesta parcial
  visible = corrupción.
- **O4. Comandos de ingesta idempotentes y reanudables:** correr N veces = mismo estado
  (`update_or_create` por `codigo_externo`); interrumpir y relanzar retoma sin duplicar.
  Todo comando que escribe estado soporta `--dry-run`.
- **O5. Cada ejecución batch registra un `EjecucionPipeline`** (métricas, hallazgos, errores).
  Sin observabilidad no hay operación.

## ✅ OBLIGATORIO (ingeniería)

- **O6. Type hints en todo el código nuevo** (mismo estándar ruff/ANN del proyecto original).
- **O7. Convención de idioma:** conceptos de dominio en español (`Licitacion`, `evaluar`,
  `PerfilFiltro` — consistente con el proyecto original); infraestructura genérica en inglés
  cuando sea natural (`services`, `views`). Docstrings en español explicando el POR QUÉ.
- **O8. Commits atómicos y descriptivos:** un cambio lógico por commit, mensaje que explica
  el porqué. La historia de commits es parte del portafolio: se escribe para ser leída.
- **O9. Settings por entorno** (`base/dev/prod`), 12-factor, `DEBUG=False` y
  `ALLOWED_HOSTS` explícito en prod. `manage.py check --deploy` limpio antes de cualquier deploy.
- **O10. Paginación y throttling en todos los endpoints de listado.**

## ✅ OBLIGATORIO (calidad / QA)

- **O11. Definición de "hecho" por milestone (PLAN.md §3):** tests verdes + CI verde +
  cobertura ≥85% + README actualizado. No se abre el milestone siguiente sin cerrar el anterior.
- **O12. Todo bugfix nace con su test de regresión** (primero el test que reproduce, después el fix).
- **O13. Los tests no llaman APIs reales:** Mercado Público se mockea con respuestas grabadas
  (fixtures). Un test que depende de la red es un test roto.
- **O14. `makemigrations --check` en CI:** el modelo y las migraciones nunca divergen.
- **O15. Al cerrar cada milestone, Claude explica a Sebastián los conceptos Django
  introducidos** (ORM, migraciones, serializers, routers, admin, auth) hasta que pueda
  defenderlos sin ayuda. Este proyecto es también su preparación de entrevista: código que
  el autor no puede explicar es código que no sirve, aunque funcione.

## Flujo de trabajo de cada sesión

1. Leer `PLAN.md` y el estado de tareas; verificar rama y CI.
2. Trabajar en incrementos pequeños: test → código → ruff → commit.
3. Antes de cerrar la sesión: suite completa + resumen de qué se hizo, qué queda y qué
   decisiones se tomaron.
