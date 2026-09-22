import type { Estado, RespuestaValor, Semaforo, Tier } from "../api/types";

export const RESPUESTA_OPTIONS: RespuestaValor[] = ["PENDIENTE", "SI", "NO", "NA_ARQ", "NA_FASE"];

export const RESPUESTA_LABELS: Record<RespuestaValor, string> = {
  PENDIENTE: "Pendiente",
  SI: "Sí",
  NO: "No",
  NA_ARQ: "No aplica (arquitectura)",
  NA_FASE: "No aplica (fase)",
};

export const ESTADO_LABELS: Record<Estado, string> = {
  cumple: "✅ Cumple",
  brecha: "⚠️ Brecha",
  pendiente: "Pendiente",
  no_aplica_arquitectura: "No aplica - arquitectura",
  no_aplica_fase: "No aplica - fase",
};

export const TIER_LABELS: Record<Tier, string> = {
  critico: "🔴 Crítico",
  alto: "🟡 Alto",
  estandar: "⚪ Estándar",
};

export const SEMAFORO_LABELS: Record<Semaforo, string> = {
  solido: "✅ Sólido",
  moderado: "🟡 Moderado",
  vulnerable: "🟠 Vulnerable",
  critico: "🔴 Crítico",
};

export function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}
