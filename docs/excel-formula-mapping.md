# Trazabilidad: fórmulas del Excel ↔ funciones Python

Mapea cada fórmula del Excel `AISEC_PLOT4AI_Final -05-2026-Proveedor.xlsx` a la función que la
replica, para que alguien del área AI-SEC que conoce el Excel pueda auditar el código sin leer
Python.

## Por pregunta (hoja de cada dominio, ej. `Cybersecurity!J4`)

Fórmula original de `J4` (Pts. Obtenidos), tal como está en el Excel:

```
=IF(OR(H4="",H4="NA-Arq",H4="NA-Fase",H4="Pendiente"),"-",
   IF((LEFT(E4,2)="+1")*(H4="SI")+(LEFT(E4,2)="-1")*(H4="NO"),G4,
      IF(G4=3,0,G4*0.25)))
```

Fórmula original de `O4` (Riesgo Residual):

```
=IF(OR(H4="NA-Arq",H4="NA-Fase"),"-",
   IF(OR(H4="",H4="Pendiente"),G4*0.75,
      IF((LEFT(E4,2)="+1")*(H4="SI")+(LEFT(E4,2)="-1")*(H4="NO"),0,
         G4*(1-IFERROR(N4/100,0)))))
```

| Columna Excel | Significado | Función Python |
|---|---|---|
| `I` (Estado) | Pendiente / No aplica-arq / No aplica-fase / ✅ Cumple / ⚠️ Brecha | `threat_model/scoring.py::compute_estado` |
| `J` (Pts. Obtenidos) | Puntos según tier, con zero-tolerance en Crítico | `threat_model/scoring.py::compute_pts_obtenidos` |
| `K` (Máx. Aplicable) | Multiplicador si la pregunta cuenta, 0 si NA/Pendiente | `threat_model/scoring.py::compute_maximo_aplicable` |
| `O` (Riesgo Residual) | Riesgo remanente, afectado por el factor de mitigación | `threat_model/scoring.py::compute_riesgo_residual` |
| — | ¿La respuesta es la "correcta" según polaridad? | `threat_model/scoring.py::is_correcta` |

Tests: `backend/tests/unit/test_scoring.py` (golden values, ver docstring del archivo para el
origen de cada caso).

## Por dominio y global (hoja `⚙️ Cálculos`)

Ver `docs/SPEC.md` sección "Motor de scoring" para el pseudocódigo de agregación por dominio y
global (Compliance%, Residual%, Contribución, Gap Ponderado, Total Ponderado). Implementado en
`threat_model/scoring.py::domain_aggregate` / `global_score` (T7) — se actualiza esta tabla cuando
esas funciones existan.

## Pesos y parámetros (hoja `⚙️ Parámetros`)

Tabla de pesos, conteos y umbrales de semáforo transcripta en `docs/SPEC.md`. Fuente de verdad
runtime: `backend/data/seed/catalogo_maestro.json` (ver `scripts/extract_catalog_from_excel.py`).
