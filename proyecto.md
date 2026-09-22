# AI-SEC Control

## Introducción

AI-SEC Control es una plataforma de gestión y administración para el área AI-SEC del Banco Macro.
Permite administrar documentación, proyectos, herramientas, métricas y dashboards del área en un
único sistema, reemplazando el trabajo manual actual basado en múltiples archivos Excel/Word.

## Problema actual

El área tiene como responsabilidad principal el análisis de amenazas de:
- Proyectos que están por ingresar o que ya ingresaron para desarrollo dentro del banco.
- Herramientas de terceros usadas para desarrollo o control.

### Flujo actual (manual)

**1. Proyecto con intención de ingreso (aún no maduro / prototipo)**
Se presenta a alto nivel una arquitectura que utiliza IA de algún modo, y se realizan preguntas
de seguridad basadas en estándares internacionales (OWASP, MITRE, PLOT4AI).

**2. Proyecto aprobado que ingresa a desarrollo final**
Se presenta la arquitectura final con el detalle de las soluciones de IA a utilizar. Se completa
un modelado de amenazas cuyas preguntas surgen del documento:

`/media/desarrollo/Macro/ai-sec_control/AISEC_PLOT4AI_Final-05-2026-Proveedor.xlsx`

Del modelado de amenazas, según la necesidad planteada, se hace una copia manual en otro Excel
dejando solo las preguntas correspondientes a la solución. Ese Excel tiene varias hojas y fórmulas
que calculan pesos y porcentajes de riesgo.

**3. Reporte trimestral**
Cada 3 meses se generan estadísticas manuales: cantidad de proyectos ingresados, análisis de
herramientas/proyectos realizados, modelados de amenazas hechos (y sus porcentajes resultantes),
pentestings realizados (cantidad, herramientas usadas, resultados obtenidos).

### Por qué es un problema

Todo el proceso se hace manualmente con archivos dispersos, lo que dificulta el control, la
trazabilidad y la generación de estadísticas.

## Solución propuesta

Sistema web con:
- **Frontend:** React.js
- **Backend:** FastAPI
- **Base de datos:** SQL (a definir motor: PostgreSQL / SQL Server / otro)

### Módulo 1 — Proyectos candidatos (aún no ingresados)

- Carga de la arquitectura del proyecto candidato (PDF o Word).
- Un módulo de IA analiza el documento y lo clasifica según el tipo de solución de IA que utiliza.
- En base a esa clasificación, se generan automáticamente las preguntas de seguridad pertinentes
  (OWASP / MITRE / PLOT4AI) en un informe Word para enviar al usuario/proveedor.

### Módulo 2 — Proyectos ya ingresados / herramientas de terceros

- Carga del modelado de amenazas a la base de datos, con los cálculos de pesos/porcentajes
  automatizados (matriz de riesgo generada por el sistema, replicando la lógica del Excel actual).
- Carga del documento del proyecto o herramienta (PDF o Word) para que la IA lo analice y devuelva:
  - Las preguntas pertinentes en español e inglés.
  - Instrucciones de cómo responder cada pregunta, en español e inglés.
  - Todo esto compilado en un documento para entregar al usuario.
- Mismo flujo aplicable a herramientas de terceros que requieran análisis.

### Módulo 3 — Pentesting

- Catálogo de herramientas de pentesting: nombre, descripción de para qué sirve, URL de referencia.
- Registro de resultados de pentesting asociados a un caso (hallazgos, severidad, fecha, herramienta usada).

### Concepto transversal — "Caso"

Cualquier trabajo (test de preguntas para proyecto candidato, modelado de amenazas para proyecto
ingresado, o pentesting) se organiza dentro de un **"caso"**, que identifica qué se está haciendo
y agrupa todo lo que se carga y genera en ese proceso. El caso debe tener un GDLD asociado (varchar-opcional), empresa responsable, nombre del proyecto, contactos (personas de la empresa involuvcradas)

### Módulo 4 — Métricas y dashboards

Sector de dashboards con métricas del área y generación de reportes filtrables, incluyendo como
mínimo:
- Cantidad de proyectos ingresados por período.
- Cantidad de análisis de herramientas/proyectos realizados.
- Cantidad de modelados de amenazas realizados y sus porcentajes de riesgo resultantes.
- Cantidad de pentestings realizados, herramientas utilizadas y resultados obtenidos.

---

## Otras definiciones

1. **Roles y permisos**: admin, user
2. **Modelo de IA a usar**: api externa openai/claude/gemini
3. **Estados de un "caso"**: abierto, en análisis, esperando respuesta del proveedor, cerrado/aprobado, rechazado.
4. **Réplica de fórmulas del Excel PLOT4AI**: documentar exactamente cómo se calculan los pesos y
   porcentajes hoy, para poder migrarlos a lógica de backend sin perder precisión.
5. **Auditoría**: registro de quién hizo qué acción y cuándo (carga, edición, aprobación).
6. **Alcance del bilingüismo**: preguntas/respuestas de los informes y explicaciones de control columna U de las preguntas.
7. **Notificaciones**: informes se descargan manualmente.
8. **Formato de exportación**: los informes deben ser Word (.docx) o pdf. 
9. **Origen de los datos históricos**: lo historico se cargara manualmente.