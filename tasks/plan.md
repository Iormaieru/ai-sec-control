# Incremento 1 — Casos + Motor de Scoring — Plan de tareas

Fuente: `docs/SPEC.md`. Cada tarea se implementa con TDD (test primero), se corre la suite
completa + build, y se commitea individualmente antes de pasar a la siguiente. Orden = orden de
dependencias.

- [x] **T1 — Scaffold backend + docker-compose**
  FastAPI app factory (`backend/app/main.py`), config con pydantic-settings, sesión SQLAlchemy,
  Alembic inicializado, `docker-compose.yml` (postgres + backend), `requirements`/`pyproject`.
  Aceptación: `docker compose up` levanta Postgres + backend; `GET /health` devuelve 200;
  `alembic upgrade head` corre sin error sobre una base vacía.

- [x] **T2 — Auditoría genérica**
  `audit/mixin.py` (AuditMixin: created_by/at, updated_by/at) + modelo `AuditLog` + eventos
  SQLAlchemy `before_insert/update` y `before_flush` que leen el actor desde un `ContextVar`.
  Aceptación: test que crea/edita una entidad de prueba y verifica que se completan los campos de
  auditoría y se emite una fila en `AuditLog`.

- [x] **T3 — Auth (JWT local, roles admin/user)**
  Modelo `User`, hashing de contraseña, emisión/verificación de JWT, dependencias
  `get_current_user`/`require_role`. Endpoints `POST /auth/login`, `POST /auth/register`
  (solo admin), `GET /auth/me`.
  Aceptación: tests de login OK/credenciales inválidas, registro rechazado sin rol admin, ruta
  protegida rechaza sin token válido.
  Depende de: T1, T2.

- [x] **T4 — Modelos de catálogo (Dominio, Pregunta)**
  Modelos + migración Alembic. Sin datos todavía (eso es T5).
  Aceptación: migración aplica limpio sobre la base de T1.
  Depende de: T1, T2.

- [x] **T5 — Extracción y seed del catálogo maestro (138 preguntas)**
  Script de extracción (openpyxl) desde
  `AISEC_PLOT4AI_Final -05-2026-Proveedor.xlsx` → `data/seed/catalogo_maestro.json`
  (artefacto versionado, no se relee el Excel en runtime). Loader que carga ese JSON a
  `Dominio`/`Pregunta`.
  Aceptación: tests de integridad — 138 preguntas totales, conteo por dominio
  (10/7/18/37/25/15/13/13), pesos suman 1.00, `multiplicador` coherente con `tier` (crítico=3,
  alto=2, estándar=1).
  Depende de: T4.

- [x] **T6 — Motor de scoring: fórmulas por pregunta (funciones puras)**
  `threat_model/scoring.py`: `compute_estado`, `compute_pts_obtenidos`, `compute_riesgo_residual`
  — funciones puras sobre primitivos (sin ORM/DB), según la lógica documentada en `docs/SPEC.md`
  sección "Motor de scoring".
  Aceptación: tests golden parametrizados extraídos de filas reales del Excel, cubriendo cada
  tier × correcta/incorrecta × NA-Arq/NA-Fase/Pendiente/blanco × con/sin factor de mitigación,
  incluyendo el caso crítico incorrecto = 0 puntos sin crédito parcial.
  Depende de: ninguna (módulo independiente, se puede paralelizar con T1-T5).

- [x] **T7 — Motor de scoring: agregación por dominio y global**
  `domain_aggregate()` y `global_score()` sobre listas de respuestas.
  Aceptación: test golden transcribiendo un dominio completo del Excel (Transparency &
  Accessibility, 7 preguntas) contra los % ya calculados en la hoja `⚙️ Cálculos` (tolerancia
  1e-6); test de subconjunto parcial con denominador 0 → 0%, no excepción.
  Depende de: T6.

- [x] **T8 — Caso + Contacto (modelos, migración, CRUD)**
  Modelos con AuditMixin, migración, endpoints `POST|GET /casos`, `GET|PATCH /casos/{id}`
  (transición de `estado` validada server-side), `POST|DELETE /casos/{id}/contactos`.
  Aceptación: tests de CRUD, transición de estado inválida rechazada (403/400), requiere auth.
  Depende de: T2, T3.

- [x] **T9 — CasoPregunta + CasoRespuesta (selección + respuestas)**
  Modelos + migración. Endpoints `POST /casos/{id}/preguntas` (agregar al alcance, por IDs o por
  dominio), `GET /casos/{id}/preguntas` (grilla con Estado/Pts/Riesgo calculados vía scoring.py),
  `PUT /casos/{id}/preguntas/{pregunta_id}/respuesta` (upsert, dispara auditoría).
  Aceptación: tests de selección/upsert, valores calculados en la respuesta del endpoint coinciden
  con `scoring.py`, auditoría registrada en cada upsert de respuesta.
  Depende de: T5, T7, T8.

- [x] **T10 — Endpoint de score por caso**
  `GET /casos/{id}/score`: por dominio (compliance%, residual%, contribución, completitud,
  brechas críticas, semáforo) + global.
  Aceptación: test construyendo un caso multi-dominio con valores conocidos a mano y verificando
  el resultado exacto, incluyendo el semáforo en cada umbral (80/60/40%).
  Depende de: T9.

- [x] **T11 — Scaffold frontend (React) + flujo de login**
  Vite+React, cliente API tipado, ruteo, pantalla de login contra `POST /auth/login`,
  persistencia de sesión, rutas protegidas.
  Aceptación: `npm run build` sin errores; login manual contra el backend funciona.
  Depende de: T3.

- [x] **T12 — Frontend: gestión de Casos**
  Listado (filtrable por estado/tipo/empresa), alta, detalle, edición de estado, contactos.
  Aceptación: verificación manual end-to-end (crear caso, agregar contacto, cambiar estado).
  Depende de: T8, T11.

- [x] **T13 — Frontend: grilla de preguntas + dashboard de score**
  Selección de preguntas por dominio, edición inline de respuestas, tarjetas de score por dominio
  con color de semáforo, resumen global.
  Aceptación: verificación manual completa — crear caso, seleccionar preguntas de 2-3 dominios,
  responder, comparar el score mostrado contra el mismo caso calculado a mano en el Excel de
  referencia (criterio de demo del Incremento 1 en `docs/SPEC.md`).
  Depende de: T9, T10, T12.

---

# Incremento 2 — Capa LLM + análisis de documentos — Plan de tareas

Decisión de diseño confirmada con el usuario: se **unifica** el análisis de IA de Módulo 1
(candidatos) y la segunda mitad de Módulo 2 (ingresados/terceros) en un solo flujo — subir un
documento, la IA clasifica la solución y recomienda qué preguntas del catálogo de 138 aplican,
con instrucciones de cómo responder cada una en ES/EN. El catálogo PLOT4AI ya incorpora OWASP (21
preguntas) y MITRE ATLAS (13 preguntas) como referencias, así que no se pierde cobertura al no
generar preguntas ad-hoc fuera del catálogo. Proveedor default: **OpenAI**, con la interfaz
agnóstica de todos modos (`LLMProvider` ABC).

- [ ] **T14 — Parsing de documentos (PDF/DOCX → texto)**
  `documents/parsing.py::extract_text(contenido: bytes, content_type: str) -> str` usando pypdf
  y python-docx. Aceptación: tests con un PDF y un DOCX de prueba, texto no vacío extraído;
  content-type no soportado -> error claro.

- [ ] **T15 — Capa LLM: interfaz + MockProvider**
  `llm/base.py` (`LLMProvider` ABC, un solo método `analyze_document(texto, catalogo) ->
  DocumentAnalysisResult` con `clasificacion` + lista de preguntas recomendadas con
  `instrucciones_es/en`), `llm/schemas.py` (pydantic), `llm/factory.py` (`get_llm_provider()`
  según `settings.llm_provider`), `llm/providers/mock_provider.py` (determinístico, sin red, para
  tests). Aceptación: tests del factory y del mock provider.

- [ ] **T16 — Adapter OpenAI**
  `llm/providers/openai_provider.py`: llamada a la API de OpenAI con structured output (JSON
  schema) para garantizar una respuesta parseable. Aceptación: tests con el cliente de OpenAI
  mockeado (sin red en CI) verificando el mapeo request/response; un test adicional que hace una
  llamada real, marcado `skipif` no hay `AISEC_OPENAI_API_KEY` configurada.

- [ ] **T17 — Persistencia + endpoint de análisis**
  `documents/models.py::CasoDocumento` (caso_id, nombre_archivo, texto_extraido, clasificacion) +
  migración. `CasoRespuesta` suma `instrucciones_respuesta_es/en` + migración. Servicio que
  extrae texto -> llama al LLMProvider -> crea CasoPregunta para las preguntas recomendadas que
  no estaban ya en alcance -> guarda instrucciones en su CasoRespuesta -> persiste CasoDocumento.
  Endpoint `POST /casos/{id}/documentos` (multipart). Aceptación: test de integración con el
  MockProvider inyectado, verificando que las preguntas recomendadas aparecen en
  `GET /casos/{id}/preguntas` con sus instrucciones.

- [ ] **T18 — Export a Word**
  `documents/export_docx.py` con python-docx: informe bilingüe por caso (clasificación +
  preguntas seleccionadas con texto/instrucciones/explicación del control en ES/EN). Endpoint
  `GET /casos/{id}/export/docx`. Aceptación: test que genera el .docx y verifica que el archivo
  resultante es un docx válido con el contenido esperado (abrirlo con python-docx y leer texto).

- [ ] **T19 — Frontend: subir documento + descargar informe**
  En `CasoPreguntasPage` (o el detalle del caso): input de archivo "Analizar documento con IA",
  muestra la clasificación devuelta y refresca la grilla (ahora con instrucciones visibles al
  expandir una pregunta), botón "Descargar informe Word". Aceptación: build limpio + verificación
  manual de las llamadas HTTP contra el backend real (mismo método que T11-T13, no hay navegador
  headless en este entorno).
