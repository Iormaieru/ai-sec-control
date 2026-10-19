import type { EstadoAlerta, SeveridadAlerta } from "../api/types";

export const SEVERIDAD_LABELS: Record<SeveridadAlerta, string> = {
  critica: "Crítica",
  alta: "Alta",
  media: "Media",
  baja: "Baja",
};

export const SEVERIDAD_BADGE: Record<SeveridadAlerta, string> = {
  critica: "text-bg-danger",
  alta: "text-bg-warning",
  media: "text-bg-info",
  baja: "text-bg-light border",
};

export const ESTADO_LABELS: Record<EstadoAlerta, string> = {
  nueva: "Nueva",
  en_revision: "En revisión",
  resuelta: "Resuelta",
  descartada: "Descartada",
};

export const ESTADO_BADGE: Record<EstadoAlerta, string> = {
  nueva: "text-bg-danger",
  en_revision: "text-bg-primary",
  resuelta: "text-bg-success",
  descartada: "text-bg-secondary",
};

export function fechaHora(valor: string | null): string {
  return valor ? new Date(valor).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" }) : "—";
}

/** Con segundos: varios eventos del mismo minuto (p. ej. el saludo de MCP) no parecen repetidos. */
export function fechaHoraSegundos(valor: string | null): string {
  return valor ? new Date(valor).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "medium" }) : "—";
}
