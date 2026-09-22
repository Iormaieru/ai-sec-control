import type { CasoEstado, CasoTipo } from "../api/types";

export const TIPO_LABELS: Record<CasoTipo, string> = {
  candidato: "Candidato",
  ingresado: "Ingresado",
  herramienta_tercero: "Herramienta de tercero",
};

export const ESTADO_LABELS: Record<CasoEstado, string> = {
  abierto: "Abierto",
  en_analisis: "En análisis",
  esperando_proveedor: "Esperando proveedor",
  cerrado_aprobado: "Cerrado / Aprobado",
  rechazado: "Rechazado",
};

// Espeja app/casos/service.py::ALLOWED_TRANSITIONS del backend — sólo para
// no ofrecer en la UI un botón que el servidor va a rechazar; el backend
// sigue siendo quien realmente valida la transición.
export const ALLOWED_TRANSITIONS: Record<CasoEstado, CasoEstado[]> = {
  abierto: ["en_analisis", "rechazado"],
  en_analisis: ["esperando_proveedor", "cerrado_aprobado", "rechazado"],
  esperando_proveedor: ["en_analisis", "cerrado_aprobado", "rechazado"],
  cerrado_aprobado: [],
  rechazado: [],
};
