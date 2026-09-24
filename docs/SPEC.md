# AI-SEC Control — Plan de desarrollo

## Contexto

AI-SEC Control reemplaza el flujo manual actual del área AI-SEC de Banco Macro (archivos
Excel/Word dispersos) para analizar amenazas de proyectos que usan IA y de herramientas de
terceros. El corazón del problema es el **modelado de amenazas**: hoy se copia manualmente un
subconjunto de preguntas desde un Excel maestro (`AISEC_PLOT4AI_Final -05-2026-Proveedor.xlsx`,
138 preguntas en 8 dominios PLOT4AI) a otro Excel con fórmulas que calculan pesos y % de riesgo.
Ese proceso manual no tiene trazabilidad ni permite generar estadísticas trimestrales sin
esfuerzo manual adicional.

Decisiones ya tomadas con el usuario:
- **Stack**: React (frontend) + FastAPI (backend) + **PostgreSQL** (DB).
- **Auth**: local usuario/contraseña + JWT, roles `admin`/`user`.
- **LLM**: capa de abstracción agnóstica de proveedor (OpenAI/Claude/Gemini intercambiables).
- **Alcance**: desarrollo **incremental por módulo**, empezando por el núcleo (Casos + motor de
  scoring del Módulo 2, que replica el Excel), antes de sumar IA, pentesting y dashboards.

Analicé el Excel a fondo (16 hojas: 8 hojas de dominio + Perfil/Parámetros/Cálculos/Catálogo
Maestro/Dashboard/Gráficos/Executive Summary/Hallazgos) para extraer la lógica exacta de scoring
que hay que replicar en el backend — ver sección "Motor de scoring" abajo.

## Arquitectura

Monorepo:

```
ai-sec-control/
  backend/app/
    core/            # config, security (JWT/hashing), deps (get_current_user, role guards)
    db/               # SQLAlchemy base + session
    audit/            # AuditMixin + AuditLog genérico (ver abajo)
    auth/             # login/register/me
    casos/            # Caso, Contacto
    catalog/          # Dominio, Pregunta + seed desde el Excel
    threat_model/      # CasoPregunta, CasoRespuesta, scoring.py (motor de cálculo)
    llm/              # Incremento 2 — LLMProvider ABC + adapters
    documents/        # Incremento 2 — parsing PDF/docx + export docx
    pentesting/        # Incremento 3
    dashboards/        # Incremento 4
  backend/alembic/
  backend/tests/unit/test_scoring.py   # tests "golden" contra el Excel
  frontend/src/
    features/{auth,casos,threat-model,pentesting,dashboards}/
  backend/data/seed/catalogo_maestro.json      # extracción versionada del Excel (138 preguntas)
  docker-compose.yml                   # postgres + backend + frontend
```

**Capa LLM (agnóstica):** `LLMProvider` ABC en `llm/base.py` con métodos de negocio, no un
passthrough genérico: `classify_solution_type()`, `generate_security_questions()`,
`analyze_document_for_questions()`. Cada proveedor (`openai_provider.py`,
`anthropic_provider.py`, `gemini_provider.py`) implementa la interfaz; `factory.py` decide cuál
instanciar según config. Esta capa no se construye hasta el Incremento 2.

**Auditoría genérica** (no ad-hoc por entidad), como pide el punto 5 de "Otras definiciones":
1. `AuditMixin` (created_by/at, updated_by/at) en toda tabla, poblado vía eventos SQLAlchemy
   `before_insert/update` leyendo el usuario actual de un `ContextVar`.
2. Tabla `AuditLog` genérica (`entity_type, entity_id, action, actor_id, timestamp, diff`),
   emitida automáticamente en `before_flush`/`after_flush` recorriendo `session.new/dirty/deleted`
   — así ningún desarrollador se olvida de loguear una mutación.

**Bilingüismo:** limitado por el spec a texto de pregunta, instrucciones de cómo responder y
"Explicación del Control" (columna U). Se modela como columnas pareadas (`texto_es`/`texto_en`,
`explicacion_control_es`/`_en`), no como tabla de traducciones genérica — el resto de la UI queda
en español.

## Motor de scoring (Módulo 2) — la pieza crítica del Incremento 1

**Por pregunta** (`respuesta` H, `polaridad` E, `multiplicador` G según tier 3/2/1, `factor_mitigación%` N):

```
correcta = (polaridad="+1" y respuesta="SI") o (polaridad="-1" y respuesta="NO")
es_na = respuesta en (NA-Arq, NA-Fase)
es_pendiente = respuesta en ("", Pendiente)

Estado = Pendiente | No aplica-arquitectura | No aplica-fase | ✅ Cumple | ⚠️ Brecha
Pts_Obtenidos = "-" si es_na/pendiente
              = multiplicador si correcta
              = 0 si incorrecta y tier=Crítico (zero tolerance, SIN crédito parcial)
              = multiplicador*0.25 si incorrecta y tier=Alto/Estándar (25% crédito parcial)
Riesgo_Residual = "-" si es_na
                = multiplicador*0.75 si pendiente
                = 0 si correcta
                = multiplicador*(1-factor_mitigación/100) si incorrecta
```

**Por dominio** (excluye NA/Pendiente del numerador y denominador de Compliance%; excluye solo NA
de Residual%):
```
Compliance% = Σ(Pts_Obtenidos respondidas) / Σ(multiplicador respondidas)      # 0 si denom=0
Residual%   = Σ(Riesgo_Residual respondidas+pendientes) / Σ(multiplicador respondidas+pendientes)
Contrib_Cumplim = Compliance% * Peso_dominio
Gap_Ponderado = (1-Compliance%) * Peso_dominio
```

**Pesos por dominio** (suman 1.00): Data&Governance 0.15, Transparency 0.06, Privacy 0.20,
Cybersecurity 0.22, Safety 0.11, Bias 0.10, Ethics 0.07, Accountability 0.09.

**Global** = Σ(Contrib_Cumplim por dominio) — ya es el promedio ponderado, sin dividir de nuevo.

**Semáforo**: ≥80% Sólido · 60-79% Moderado · 40-59% Vulnerable · <40% Crítico.

Estas fórmulas se implementan como **funciones puras** en `threat_model/scoring.py`
(`compute_estado`, `compute_pts_obtenidos`, `compute_riesgo_residual`, `domain_aggregate`,
`global_score`) tomando primitivos, no filas de Excel ni ORM — esto es lo que se testea contra
valores reales extraídos del workbook.

**Campos calculados: compute-on-read, no columnas cacheadas.** Son sumas/promedios sobre ≤138
filas por caso, triviales de recalcular en cada lectura; cachear introduciría un problema de
invalidación (exactamente el tipo de bug que se busca eliminar al reemplazar el Excel "siempre
vivo"). Excepción: al cerrar un caso (`CERRADO_APROBADO`/`RECHAZADO`) conviene congelar un
snapshot para que el reporte trimestral no cambie si el catálogo se actualiza después — se
construye recién en el Incremento 4, pero el punto de enganche (transición de `estado` en
`casos/service.py`) se deja previsto desde ahora.

## Modelo de datos (Incremento 1)

- **Caso**: `gdld` (varchar opcional), `empresa_responsable`, `nombre_proyecto`, `tipo` (CANDIDATO
  / INGRESADO / HERRAMIENTA_TERCERO), `estado` (ABIERTO / EN_ANALISIS / ESPERANDO_PROVEEDOR /
  CERRADO_APROBADO / RECHAZADO), + AuditMixin.
- **Contacto**: FK a Caso, `nombre`, `email`, `rol` (1-a-muchos).
- **Dominio**: `codigo`, `nombre`, `peso`, `total_preguntas` (seed, validado contra el Excel).
- **Pregunta**: FK a Dominio, `numero`, `texto_es/en`, `tipo`, `polaridad`, `tier`,
  `multiplicador`, `impacto_primario`, `referencias_regulatorias`, `justificacion_tier`,
  `explicacion_control_es/en`.
- **CasoPregunta**: `caso_id`+`pregunta_id` (UNIQUE) — qué preguntas están "en alcance" para ese
  caso (el subconjunto que hoy se copia a mano a otro Excel).
- **CasoRespuesta**: FK a CasoPregunta (UNIQUE), `respuesta` (SI/NO/NA_ARQ/NA_FASE/PENDIENTE),
  `control_compensatorio`, `factor_mitigacion_pct`, `owner_responsable`, `accion_remediacion`,
  `fecha_objetivo`, `evidencia_esperada`, `observaciones` + AuditMixin (columnas M-U del Excel;
  I/J/K/L/O son calculadas, no se guardan).

**Seed del catálogo**: extracción única del Excel a `backend/data/seed/catalogo_maestro.json`
(versionado, revisable), cargado por migración/script — el runtime nunca vuelve a leer el .xlsx.
Test de integridad: 138 preguntas totales, conteo por dominio (10/7/18/37/25/15/13/13), pesos
suman 1.00, `multiplicador` coherente con `tier`.

## API (Incremento 1)

- `POST /auth/login`, `POST /auth/register` (solo admin), `GET /auth/me`
- `POST|GET /casos`, `GET|PATCH /casos/{id}` (incl. transición de estado validada server-side)
- `POST /casos/{id}/contactos`, `DELETE /casos/{id}/contactos/{contacto_id}`
- `GET /catalogo/dominios`, `GET /catalogo/preguntas?dominio=CYB`
- `POST /casos/{id}/preguntas` (agrega al alcance, por IDs o por dominio completo)
- `GET /casos/{id}/preguntas` (grilla: pregunta + respuesta actual + Estado/Pts/Riesgo calculados)
- `PUT /casos/{id}/preguntas/{pregunta_id}/respuesta` (upsert de la respuesta, dispara auditoría)
- `GET /casos/{id}/score` (resultado completo por dominio + global, con semáforo)

Pentesting/Dashboards en incrementos posteriores siguen el mismo patrón CRUD (no se detalla cada
endpoint acá).

## Roadmap por incrementos

1. **Casos + motor de scoring** (este incremento): auth, Caso/Contacto, catálogo seed, selección
   de subconjunto de preguntas por caso, captura de respuestas, scoring completo con semáforo,
   auditoría genérica, grilla de preguntas + dashboard de score en el frontend. **Sin LLM, sin
   export a Word/PDF todavía** — el valor demostrable es "reemplaza el Excel con cálculo en vivo y
   confiable", verificable en pantalla contra el Excel de referencia. El export se posterga al
   Incremento 2 porque el contenido de los informes (Módulo 1 y la mitad IA del Módulo 2) depende
   de las llamadas al LLM; construirlo antes implicaría rehacerlo.
2. **Capa LLM + análisis de documentos** (Módulo 1 completo + segunda mitad del Módulo 2):
   `LLMProvider` + primer adapter, carga y parseo de PDF/Word, clasificación de arquitectura,
   generación de preguntas pertinentes + instrucciones bilingües, export a Word/PDF. La selección
   de preguntas asistida por IA puede poblar el `CasoPregunta` del Incremento 1.
3. **Pentesting (Módulo 3)**: catálogo de herramientas + registro de resultados por caso, CRUD
   simple reutilizando AuditMixin.
4. **Dashboards y reporte trimestral (Módulo 4)**: agregaciones sobre `/casos/{id}/score` para un
   conjunto filtrado de casos, gráficos, export de reporte trimestral; acá se implementa el
   snapshot-on-close previsto en el Incremento 1.

## Verificación

1. **Tests unitarios "golden"** en `test_scoring.py`: casos parametrizados extraídos directamente
   de filas reales del Excel (cada tier × correcta/incorrecta × NA-Arq/NA-Fase/Pendiente/blanco ×
   con/sin factor de mitigación), cubriendo explícitamente el caso más delicado (Crítico incorrecto
   = 0 puntos, sin crédito parcial, a diferencia de Alto/Estándar).
2. **Tests de agregación por dominio y global**: transcribir un dominio chico (ej. Transparency,
   7 preguntas) completo con sus % ya calculados en la hoja `⚙️ Cálculos` del Excel, y verificar que
   el backend reproduce exactamente esos porcentajes (tolerancia 1e-6).
3. **Test de independencia de subconjunto**: verificar que el cálculo funciona correctamente con
   solo un subconjunto de preguntas seleccionadas (no las 138), incluyendo el caso de denominador
   0 → debe dar 0%, no una excepción.
4. **Integridad del seed**: 138 preguntas, conteos por dominio, pesos suman 1.00.
5. **Verificación end-to-end manual**: crear un caso, seleccionar preguntas de 2-3 dominios,
   responderlas, y comparar el score que muestra la UI contra el mismo caso calculado a mano en el
   Excel de referencia.
