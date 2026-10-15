import type { Caso, CasoEstado, CasoTipo, JiraSyncEstado } from "../api/types";

export const TIPO_LABELS: Record<CasoTipo, string> = {
  candidato: "Candidato",
  ingresado: "Ingresado",
  herramienta_tercero: "Herramienta de tercero",
};

/** Columnas del tablero IA-SEC de Jira. */
export const ESTADO_LABELS: Record<CasoEstado, string> = {
  por_hacer: "Por hacer",
  en_curso: "En curso",
  esperando_respuesta: "Esperando respuesta",
  hecho: "Hecho",
};

export const ESTADO_BADGE_CLASS: Record<CasoEstado, string> = {
  por_hacer: "text-bg-primary",
  en_curso: "text-bg-info",
  esperando_respuesta: "text-bg-warning",
  hecho: "text-bg-success",
};

export const SYNC_LABELS: Record<JiraSyncEstado, string> = {
  ok: "Sincronizado con Jira",
  pendiente: "Pendiente de enviar a Jira",
  error: "Error de sincronización con Jira",
};

export const SYNC_BADGE_CLASS: Record<JiraSyncEstado, string> = {
  ok: "text-bg-light border",
  pendiente: "text-bg-secondary",
  error: "text-bg-danger",
};

/** "Hecho · Cancelado": la columna y, si difiere, el status exacto de Jira. */
export function estadoConDetalle(caso: Caso): string {
  const columna = ESTADO_LABELS[caso.estado];
  const status = caso.jira_status_nombre;
  return status && status.toLowerCase() !== columna.toLowerCase() ? `${columna} · ${status}` : columna;
}

export function tipoLabel(tipo: CasoTipo | null): string {
  return tipo ? TIPO_LABELS[tipo] : "—";
}

/** El backend guarda sólo el número del GDLD; se muestra como "GDLD 12190". */
export function formatGdld(gdld: string | null): string | null {
  return gdld ? `GDLD ${gdld}` : null;
}

/** "Ivan Omar Rios Maieru" -> "IM": primera y última palabra, como en Jira. */
export function iniciales(nombre: string): string {
  const partes = nombre.trim().split(/\s+/);
  const ultima = partes.length > 1 ? partes[partes.length - 1][0] : "";
  return ((partes[0]?.[0] ?? "") + ultima).toUpperCase();
}

/** "Ivan Omar Rios Maieru" -> "Ivan Maieru", para la tarjeta. */
export function nombreCorto(nombre: string): string {
  const partes = nombre.trim().split(/\s+/);
  return partes.length > 2 ? `${partes[0]} ${partes[partes.length - 1]}` : nombre.trim();
}

const AVATAR_COLORES = ["#203ae9", "#003057", "#0f766e", "#7c3aed", "#b45309", "#be123c", "#0369a1"];

/** Color estable por persona, para reconocerla de un vistazo en el tablero. */
export function colorAvatar(nombre: string): string {
  let hash = 0;
  for (const c of nombre) hash = (hash * 31 + c.charCodeAt(0)) >>> 0;
  return AVATAR_COLORES[hash % AVATAR_COLORES.length];
}
