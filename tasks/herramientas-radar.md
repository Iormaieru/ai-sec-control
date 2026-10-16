# Herramientas de pentesting: Catálogo, Radar y Distribuciones — Especificación y plan

## 1. Objetivo

Que la sección **Pentesting → Herramientas** se mantenga sola con herramientas que realmente sirven. Cada 15 días, el worker:

- revisa las herramientas ya aprobadas: versión, mantenimiento, si se archivaron o se mudaron;
- descubre herramientas nuevas en fuentes públicas;
- las deja para que un analista las apruebe.

Cada herramienta queda vinculada a los pasos de los estándares donde se usa.

**Foco:** seguridad de IA (LLM, ML, deep learning, red teaming), que es lo que cubren los estándares. Las herramientas web clásicas son secundarias.

## 2. Secciones

| Sección | Qué contiene | Quién la alimenta |
|---|---|---|
| **Catálogo** | Herramientas aprobadas: las que se usan en los pentests | Analista: aprueba desde el Radar o carga a mano |
| **Radar** | Herramientas **descubiertas** pendientes de evaluación, con los datos para decidir | Worker, cada 15 días |
| **Distribuciones** | Suites de herramientas: Kali, Parrot, BlackArch | Worker, cada 15 días |

Ciclo de vida:

```text
                 aprobar                       revisión: archivada / sin actividad
   [Radar] ─────────────────▶ [Catálogo: activa] ────────────────────▶ [Catálogo: en observación]
      │                                ▲                                         │
      │ descartar (con motivo)         └──────────── vuelve a tener actividad ───┘
      ▼                                                                          │ el analista la retira
 [descartada]  (no se vuelve a sugerir)                                          ▼
                                                                          [Catálogo: retirada]
```

Reglas:

- Una herramienta **retirada no se borra**: los pentests que la usaron la siguen mostrando.
- Una herramienta **descartada** queda registrada con su motivo, para no volver a proponerla en cada revisión.

## 3. Tipos de herramienta

1. **Seguridad de IA** (núcleo). Lista inicial verificada el 2026-10-16:

   | Herramienta | Repo | Estado al verificar |
   |---|---|---|
   | garak | NVIDIA/garak | ★9.6k, activa, v0.17.0 |
   | PyRIT | microsoft/PyRIT | ★4.6k, activa, v1.1.0 (antes `Azure/PyRIT`, hoy archivado) |
   | promptfoo | promptfoo/promptfoo | ★26k, activa |
   | Adversarial Robustness Toolbox | Trusted-AI/adversarial-robustness-toolbox | ★6.3k, activa; último release 2025-07 |
   | TextAttack | QData/TextAttack | ★3.5k, activa, v0.3.11 |
   | Giskard | Giskard-AI/giskard-oss (renombrado) | ★5.9k, activa |
   | LLM Guard | protectai/llm-guard | ★3.2k, **archivada desde 2026-07** → entra "en observación" |

2. **Especializadas** (web y otras), con documentación:
   - Burp Suite (Community y Professional)
   - sqlmap
   - OWASP ZAP
   - nuclei

   Para Burp Professional, la versión y la licencia se cargan a mano: ninguna fuente pública la sigue.

3. **Distribuciones**:
   - **Kali Linux**: 29 categorías (`kali-tools-*`), top10 incluido.
   - **Parrot Security**: 16 categorías (`parrot-tools-*`).
   - **BlackArch**: ~2.800 herramientas en grupos `blackarch-*`, incluido **`blackarch-ai`** (garak, promptfoo, ART, CleverHans…).

## 4. Fuentes (verificadas, gratuitas)

| Fuente | Se usa para | Notas |
|---|---|---|
| GitHub API | Actividad (último push), estrellas, archivada, licencia, web de documentación, mudanzas de repo (redirect). Descubrimiento por temas: `llm-security`, `ai-red-teaming`, `prompt-injection`, `adversarial-machine-learning`, `ai-security` (~120 candidatos con ≥500★ y actividad en el último año) | Necesita un token (`AISEC_GITHUB_TOKEN`, sólo lectura pública): sin token, el límite es 60 consultas por hora |
| PyPI / npm | Versión publicada de la herramienta | Los releases de GitHub no sirven: el último release de promptfoo es el de una acción de GitHub |
| Índice de Kali (`http.kali.org/.../Packages.gz`) | Versión empaquetada y categorías (metapaquetes). Ficha de la distribución | Burp Community 2026.8, sqlmap 1.10.9 |
| Índice de Parrot (`deb.parrot.sh/.../Packages.gz`) | Ídem | `parrot-tools-ai` sólo trae hexstrike-ai: IA *para* pentest, no para atacar IA |
| Base de BlackArch (`blackarch.db.tar.gz`) | Ídem. Grupo `blackarch-ai` como fuente de descubrimiento de IA | Burp 2026.9, pyrit 0.5.0 (desactualizado) |

## 5. Criterios: qué es una herramienta "que sirve"

Cada revisión calcula estas señales y las muestra en la ficha, en el Radar y en el Catálogo:

| Señal | Verde | Rojo |
|---|---|---|
| Mantenida | push o release en los últimos 12 meses | sin actividad hace más de 12 meses, o repo archivado |
| Adoptada | ≥500★, o empaquetada en 2 o más distribuciones | <100★ y en ninguna distribución |
| Instalable | versión publicada en PyPI/npm o en alguna distribución | sólo código fuente |
| Licencia | reconocida (MIT, Apache-2.0, GPL…) | sin licencia |

Uso de las señales:

- **Descubrimiento:** al Radar entran sólo candidatas con "mantenida" y "adoptada" en verde.
- **Catálogo:** si "mantenida" pasa a rojo, la herramienta queda **en observación**, con el motivo (por ejemplo, "archivada en GitHub el 2026-07-08" o "se mudó a microsoft/PyRIT").

## 6. Vínculo herramienta ↔ paso de estándar

- Tabla `herramienta_paso`: herramienta, paso, origen (`curado` | `sugerido_ia` | `analista`) y estado (`sugerido` | `confirmado`).
- **Lista inicial:** vínculos curados, ya confirmados. Por ejemplo:
  - garak → OWASP LLM01 (prompt injection), LLM02, LLM07…
  - ART → ML01 (input manipulation), pasos de AISEC-DL-ADVERSARIAL.
- **Herramientas descubiertas:** al entrar al Radar, el proveedor LLM que ya tiene la app (`app/llm`) propone los pasos que aplican, a partir de la descripción, los temas y el README. Quedan como `sugerido`, y el analista los confirma o quita **al aprobar**.
- **Dónde se ve:**
  - en el paso del estándar, como "Herramientas recomendadas";
  - en la ficha de la herramienta, como "Sirve para";
  - al registrar un ataque sobre un paso, como herramientas ofrecidas primero.

## 7. Revisión cada 15 días (worker)

- Segunda tarea del worker. Una vez por día verifica si pasaron `AISEC_HERRAMIENTAS_REVISION_DIAS` (15) desde la última revisión **exitosa**; si pasaron, la ejecuta.
- **Pasos:**
  1. Descarga los índices de las tres distribuciones y actualiza sus fichas.
  2. Actualiza el Catálogo: señales, versión y estado.
  3. Descubre candidatas (temas de GitHub y `blackarch-ai`), filtra por criterios y por descartadas, y las suma al Radar con los vínculos sugeridos.
  4. Registra la corrida en `revision_herramientas`: fecha, novedades, errores.
- **Idempotente:** si una fuente falla, el resto sigue y la revisión queda "con errores".
- **Ejecución manual:** desde la UI, con "Revisar ahora", para un admin.
- **Novedades visibles:** el Radar muestra la cantidad pendiente, y el Catálogo destaca los cambios de la última revisión ("nueva versión", "pasó a observación").

## 8. Fuera de alcance (por ahora)

- Instalar o ejecutar herramientas desde la plataforma.
- Notificaciones por email de las novedades.
- Herramientas comerciales distintas de Burp: se pueden cargar a mano en el Catálogo.

---

## Plan de tareas

Cada tarea sigue el flujo del proyecto: test primero, suite completa + build, y commit individual. El orden respeta las dependencias.

- [x] **H1 — Modelo y migración**
  - `HerramientaPentest` suma:
    - `tipo` (ia, especializada), `estado` (candidata, activa, en_observacion, retirada, descartada), `motivo_estado`;
    - `repo_github`, `paquete` (pypi/npm), `version`, `documentacion_url`, `notas_version_url`, `licencia`;
    - `senales` (JSON), `distribuciones` (dónde está empaquetada), `revisada_at`, `novedad`.
  - Tablas nuevas: `distribuciones`, `herramienta_paso`, `revision_herramientas`.
  - Las herramientas existentes pasan a `especializada` / `activa`.

  Aceptación: la migración aplica sobre la base actual (sube y baja), y las herramientas usadas en ataques siguen vinculadas.

- [x] **H2 — Clientes de fuentes**
  - GitHub (con token, detecta mudanzas por redirect), PyPI, npm.
  - Lectores de los índices de Kali/Parrot (Debian `Packages.gz`) y BlackArch (`desc` de pacman).

  Aceptación: tests con respuestas grabadas de cada fuente, sin red. Un fallo de una fuente devuelve un error tipado que no interrumpe a las demás.

  Depende de: —

- [x] **H3 — Evaluación (criterios de la sección 5)**
  - Funciones puras: señales → semáforo, ¿candidata válida?, ¿pasa a observación?

  Aceptación: tests por cada regla. LLM Guard archivada → en observación. Repo mudado → motivo con la nueva dirección.

  Depende de: H2.

- [x] **H4 — Catálogo inicial**
  - Migración de datos desde `alembic/data/herramientas_v1.json`:
    - las 7 de IA y las 4 especializadas;
    - las 3 distribuciones, con descripción, documentación y web;
    - los vínculos curados a los pasos de los 6 estándares.

  Aceptación: test de integridad (cantidades, todo vínculo apunta a un paso existente) y migración idempotente.

  Depende de: H1.

- [x] **H5 — Sugerencia de vínculos con IA**
  - A partir de la descripción, los temas y el README de una candidata, el proveedor LLM propone pasos (por código: LLM01, ML01…) con una justificación breve.
  - Con el proveedor `mock`, devuelve una sugerencia determinística.

  Aceptación: tests con el mock. Los códigos inválidos se descartan. Nunca confirma: siempre queda `sugerido`.

  Depende de: H1.

- [x] **H6 — Revisión cada 15 días en el worker**
  - Orquesta H2–H5 según la sección 7.
  - Registra la corrida y respeta el intervalo; el lock evita dos revisiones simultáneas.

  Aceptación (tests con fuentes falsas):
  - una herramienta nueva llega al Radar con sus vínculos sugeridos;
  - una descartada no vuelve;
  - una archivada pasa a observación;
  - si una fuente falla, el resto se actualiza igual;
  - no corre antes de los 15 días.

  Depende de: H2–H5.

- [x] **H7 — API**
  - Catálogo (alta manual, edición, retirar).
  - Radar: listar, aprobar con los vínculos confirmados, descartar con motivo.
  - Distribuciones.
  - Vínculos: confirmar o quitar.
  - `GET /pentesting/estandares/{id}/pasos/{paso}/herramientas`.
  - `POST` para "revisar ahora" (sólo admin) y estado de la última revisión.

  Aceptación: tests de cada endpoint y de los permisos. Con los roles actuales (`admin`, `user`): aprobar y descartar, cualquier usuario autenticado; revisar ahora, sólo admin.

  Depende de: H1, H4.

- [x] **H8 — Frontend**
  - **Herramientas**, con pestañas Catálogo | Radar (con el contador de pendientes) | Distribuciones.
  - Ficha de herramienta: señales, versión, documentación, "Sirve para".
  - Aprobación en el Radar: ver los datos, ajustar los pasos sugeridos, aprobar o descartar.
  - "Herramientas recomendadas" en el paso del estándar y al registrar un ataque.

  Aceptación: build y lint limpios. Flujo manual: aprobar una candidata y verla en el Catálogo y en el paso vinculado.

  Depende de: H7.

- [ ] **H9 — Verificación real y despliegue**
  - Corrida real de la revisión contra las fuentes.
  - Revisión de los vínculos sugeridos.
  - `AISEC_GITHUB_TOKEN` en Railway para el worker.
  - Documentación en `worker/README.md`.

  Aceptación: la primera revisión real termina sin errores, y el Radar muestra candidatas razonables.

  Depende de: H6, H8.

## Primera revisión real (2026-10-16, base local, sin token de GitHub)

- **Duración:** 91 s.
- **Distribuciones:** Kali 2026.3 (407 herramientas, 29 categorías), Parrot 7.4 (311 herramientas, 15 categorías), BlackArch (2.856 herramientas, 52 grupos).
- **Catálogo:** las 11 herramientas actualizadas. LLM Guard pasa a observación (archivada). Las versiones salen de PyPI/npm o de las distribuciones.
- **Radar:** 25 candidatas (el tope por revisión) y 140 vínculos sugeridos por el LLM.
  - Reales y relevantes: NeMo Guardrails, Tencent AI-Infra-Guard, superagent, strix, etc.
  - A 6 la IA no les encontró pasos, y son justamente las que no son herramientas: colecciones de enlaces, cursos, guías. El Radar las muestra al final.
- **Errores:** 1, un repo de `blackarch-ai` borrado de GitHub (404).

**Pendiente de H9:**
- Token de GitHub fine-grained en el worker de Railway.
- Variables del LLM en el worker.
- Primera revisión en Railway: la dispara el worker al arrancar, porque nunca se revisó.

## Decisiones (resueltas)

1. **Nombre de las secciones:** "Catálogo" y "Radar".
2. **Roles:** provisorios hasta tener los de Entra ID. Cualquier usuario autenticado aprueba y descarta; "revisar ahora", sólo admin.
3. **Token de GitHub:** fine-grained, de sólo lectura de repos públicos.
