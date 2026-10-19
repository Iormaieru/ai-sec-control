# Seguridad de IA: reglas de Netskope, correlación con Tenable y tablero — Plan

Sigue al sector **Alertas** (Netskope → alertas agrupadas por regla + app + usuario, email resumen), que ya funciona contra el tenant real.

## Contexto

En los últimos 30 días, la integración con Netskope mostró:
- uso de servidores MCP por agentes (Katalon, Claude Code → Notion y Monday, Exa ejecutando herramientas);
- **701 eventos de DeepSeek de 12 usuarios, con 82 subidas de archivos**;
- descargas de modelos desde Hugging Face con `python.exe`, de Ollama, y uso de Groq, OpenRouter y Qwen.

El cruce con Tenable (Vulnerability Management, exportación validada con las claves del área) mostró que **12 de los 19 equipos con actividad de IA no están en el inventario de Tenable**, y que el inventario estándar no ve las instalaciones por usuario (Ollama, LM Studio).

Fortinet queda fuera por ahora: no hay acceso por API fuera de la red del banco.

## Decisiones

- **Fuentes:** Netskope (uso real de IA) y Tenable (lo instalado y expuesto), cruzadas por equipo.
- **Tablero "Seguridad de IA"** dentro de Dashboards, con gráficos y métricas.
  - Exporta a **Excel (.xlsx)** y **CSV**, con los filtros aplicados.
  - Lo ven todos los usuarios, igual que el sector Alertas, aunque muestra emails.
- **Orden:** 1) reglas de Netskope, 2) Tenable y correlación, 3) tablero.

---

## A. Reglas de Netskope (13)

Cada consulta se valida contra el tenant antes de activarla: con "Probar" o con un script de sólo lectura. Las que validen entran como **activas** en una migración de datos; las que no tengan tráfico o no validen entran **inactivas**, para activarlas desde la plataforma cuando se confirmen.

| Familia | Reglas | Severidad |
|---|---|---|
| Agentes y MCP | Uso de servidores MCP *(ya existe)* · Agente ejecuta herramientas (CallTool) · Servidores MCP sin nombre (por IP) · Terceros (`@bmexternos`) usando agentes o MCP | Alta |
| Modelos abiertos e IA china | **Subida de archivos a DeepSeek o Qwen** (crítica) · Uso de DeepSeek o Qwen · DeepSeek por API o scripts (procesos que no son navegadores) · Modelos bajados por código desde Hugging Face · Descarga de Ollama o LM Studio · Agregadores de inferencia (OpenRouter, Groq) | Crítica / alta / media |
| Fuga y shadow AI | Subida de archivos a apps de IA · Apps de IA de riesgo alto (CCL bajo) · Cuentas personales en apps aprobadas | Alta |

Aceptación: cada regla tiene su consulta validada (o figura como inactiva con el motivo), y la migración es idempotente por nombre.

### Validación contra el tenant (2026-10-19, 30 días)

- **Valores reales del tenant:**
  - categorías `Generative AI` y `MCP Server`;
  - las apps aprobadas caen en categorías propias del banco ("Custom Exception Grupo 0/1/2");
  - `ccl` toma los valores `poor`, `low` y `medium`;
  - actividades `AI Post` y `AI Response`.
- **Bug corregido:** el cliente devolvía resultados parciales al llegar al tope de 20.000 eventos. Ahora ese caso es un error explícito (`DemasiadosEventos`), y el procesamiento parte la ventana en mitades.
- **Reglas de alerta validadas (9 nuevas):**
  - CallTool: 160 eventos, 25 usuarios;
  - terceros con MCP: 403 / 5;
  - MCP por IP: 1 / 1;
  - **subida de archivos a DeepSeek o Qwen: 82 / 6 (crítica)**;
  - uso de DeepSeek o Qwen: 707 / 12;
  - DeepSeek por API: 23 / 1;
  - Hugging Face por código: 41 / 3;
  - Ollama o LM Studio: 10 / 2;
  - agregadores: 90 / 2.
- **Reglas demasiado amplias para alertar, que pasan a modo `metrica`:**
  - subida de archivos a "Generative AI": 23.439 eventos, 1.042 usuarios;
  - apps de IA de riesgo alto: 77.558 eventos, 3.188 usuarios.

  En modo métrica no generan alertas ni emails: el worker las agrega por día, app, usuario y actividad en `metricas_ia`, y alimentan el tablero.
- **Afuera por ahora:** cuentas personales en apps aprobadas, porque los eventos no traen un campo de instancia que distinga la cuenta corporativa de la personal.

## B. Tenable y correlación por equipo

- **Cliente** `app/alertas/tenable.py`: claves `X-ApiKeys` y exportación de vulnerabilidades (`/vulns/export`, por chunks). Las claves del área tienen alcance sobre `/assets` y `/vulns/export`, y no sobre escaneos ni plugins.
- **Tabla `equipos_tenable`:** hostname, nombre NetBIOS, sistema operativo, si tiene agente, software relevante (Python, Anaconda, runtimes de IA), puertos de IA abiertos (11434 Ollama, 1234 LM Studio), cantidad y severidad máxima de vulnerabilidades de IA, y última vez visto. La actualiza el **worker una vez por día**, porque la exportación de ~11 mil equipos es pesada.
- **Correlación:** cada alerta de Netskope guarda los equipos (`hostname`) de sus eventos. El detalle muestra, por equipo, si está en Tenable, su software y sus vulnerabilidades de IA.
- **Reglas de origen Tenable** (`ReglaAlerta.fuente`: `netskope` | `tenable`; tipos predefinidos, sin consulta libre):
  - **Servicio de IA expuesto** (puerto 11434 o 1234 abierto). Alta.
  - **Vulnerabilidad en software de IA** (Ollama, PyTorch, Transformers, LangChain…, por nombre del plugin). Alta.
  - **Equipo con actividad de IA fuera de Tenable** (está en eventos de Netskope y no en el inventario). Media. Es la brecha de cobertura.
- **Datos personales:** los logs no llevan usuarios ni nombres de equipo, sólo cantidades.

Aceptación:
- tests con Tenable simulado (exportación por chunks, extracción de software y puertos, correlación por hostname o NetBIOS, regla de brecha);
- una corrida real que reproduzca el cruce manual (12 de 19 fuera de Tenable).

## C. Tablero "Seguridad de IA"

- **Menú:** Dashboards pasa a ser un grupo con **General** (el actual, sin cambios) y **Seguridad de IA**.
- **Filtros:** rango (7, 30 o 90 días, o personalizado), regla, severidad, y usuarios internos, externos o todos.
- **Indicadores:**
  - alertas abiertas;
  - críticas y altas abiertas;
  - usuarios con actividad de IA;
  - apps de IA detectadas;
  - externos con actividad;
  - equipos con actividad de IA fuera de Tenable;
  - tiempo medio de atención y de cierre.

  Para los tiempos se agregan a `Alerta` las columnas `atendida_at` (primera vez que sale de "nueva") y `cerrada_at` (resuelta o descartada).
- **Gráficos:**
  1. Eventos por día, por regla o severidad (barras apiladas).
  2. Alertas nuevas por día.
  3. Top apps de IA.
  4. Top usuarios.
  5. Internos vs. externos.
  6. Estado de las alertas.
  7. Actividades sensibles en el tiempo (Upload, Post, CallTool).
  8. Cobertura de Tenable sobre los equipos con actividad de IA.
  9. Software de IA en el inventario de Tenable (reemplaza a "vulnerabilidades de IA": no hay vulnerabilidades de IA abiertas en el tenant).
- **Exportación** (con los filtros aplicados):
  - **Excel:** hojas Resumen (indicadores), Alertas, Eventos y Equipos.
  - **CSV:** alertas y eventos.
- **Técnica:**
  - endpoint `GET /metricas/ia` (agregaciones en SQL sobre `alertas`, `alerta_eventos` y `equipos_tenable`) y `GET /metricas/ia/export.xlsx|.csv`;
  - gráficos con **Recharts** (dependencia nueva del frontend), con la guía de visualización del proyecto (paleta, accesibilidad, modo claro);
  - Excel con **openpyxl** (dependencia nueva del backend).

Aceptación:
- tests de las agregaciones con datos armados (conteos por día, internos vs. externos, tiempos de atención);
- el export Excel abre con sus hojas y respeta los filtros;
- build y lint del frontend limpios;
- el tablero con los datos reales de la base local.

### Resultado (2026-10-19)

- **Backend:** `GET /metricas/ia`, `GET /metricas/ia/export.xlsx` y `GET /metricas/ia/export.csv?tabla=alertas|eventos|actividad`, en `app/alertas/tablero*.py`.
  - La "actividad" une los eventos de las reglas de alerta con los totales de las reglas de métrica.
  - Días en UTC; en el Excel, las horas en hora argentina.
  - En Excel y CSV, los valores que empiezan con `=`, `+`, `-` o `@` se escriben como texto (evita inyección de fórmulas).
- **Frontend:** Dashboards → General y Seguridad de IA (`/dashboards/seguridad-ia`).
  - Recharts en un chunk aparte.
  - Cada gráfico tiene vista de tabla.
- **Datos reales, 30 días:** 99 alertas abiertas (66 críticas o altas), 3.526 usuarios con actividad de IA (89 externos), 62 apps y 50 equipos con actividad, de los cuales 24 están fuera de Tenable.

## Verificación general

- Suites del backend y del worker **en secuencia** (comparten la base de test).
- Corrida real: `python -m aisec_worker --alertas` (con las reglas nuevas) y la actualización de Tenable, sobre la base local.
- El tablero muestra las métricas reales.
