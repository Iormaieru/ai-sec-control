import { api } from "./client";
import type {
  Alerta,
  AlertaDetalle,
  DestinatariosAlerta,
  EstadoAlerta,
  PruebaRegla,
  ReglaAlerta,
  SeveridadAlerta,
} from "./types";

export interface FiltrosAlertas {
  estado?: EstadoAlerta;
  severidad?: SeveridadAlerta;
  regla_id?: string;
  caso_id?: string;
  /** Contiene (usuario o, en las de Tenable, equipo). */
  usuario?: string;
  /** Contiene. */
  app?: string;
  /** Con actividad dentro del rango (YYYY-MM-DD). */
  desde?: string;
  hasta?: string;
}

export function listAlertas(filtros: FiltrosAlertas = {}): Promise<Alerta[]> {
  const params = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v) as [string, string][]);
  const q = params.toString();
  return api.get<Alerta[]>(`/alertas${q ? `?${q}` : ""}`);
}

export function getAlerta(id: string): Promise<AlertaDetalle> {
  return api.get<AlertaDetalle>(`/alertas/${id}`);
}

export function updateAlerta(id: string, cambios: { estado?: EstadoAlerta; nota?: string }): Promise<AlertaDetalle> {
  return api.patch<AlertaDetalle>(`/alertas/${id}`, cambios);
}

/** Vincular a un caso (caso_id), crear uno nuevo (crear) o desvincular ({}). */
export function vincularCaso(id: string, payload: { caso_id?: string; crear?: boolean }): Promise<AlertaDetalle> {
  return api.post<AlertaDetalle>(`/alertas/${id}/caso`, payload);
}

export function getResumenAlertas(): Promise<{ nuevas: number; en_revision: number }> {
  return api.get<{ nuevas: number; en_revision: number }>("/alertas/resumen");
}

export interface ReglaPayload {
  nombre: string;
  descripcion?: string | null;
  consulta: string;
  severidad: SeveridadAlerta;
  activa: boolean;
  notificar_email: boolean;
  modo: "alerta" | "metrica";
}

export function listReglas(): Promise<ReglaAlerta[]> {
  return api.get<ReglaAlerta[]>("/alertas/reglas");
}

export function createRegla(payload: ReglaPayload): Promise<ReglaAlerta> {
  return api.post<ReglaAlerta>("/alertas/reglas", payload);
}

export function updateRegla(id: string, payload: Partial<ReglaPayload>): Promise<ReglaAlerta> {
  return api.patch<ReglaAlerta>(`/alertas/reglas/${id}`, payload);
}

export function deleteRegla(id: string): Promise<void> {
  return api.delete<void>(`/alertas/reglas/${id}`);
}

/** Ejecuta la consulta contra Netskope (últimas 24 h) sin crear alertas. */
export function probarRegla(id: string): Promise<PruebaRegla> {
  return api.post<PruebaRegla>(`/alertas/reglas/${id}/probar`);
}

export function listDestinatarios(): Promise<DestinatariosAlerta> {
  return api.get<DestinatariosAlerta>("/alertas/destinatarios");
}

export function addDestinatario(payload: { email: string; nombre?: string | null }): Promise<DestinatariosAlerta> {
  return api.post<DestinatariosAlerta>("/alertas/destinatarios", payload);
}

export function updateDestinatario(
  id: string,
  payload: { nombre?: string | null; activo?: boolean },
): Promise<DestinatariosAlerta> {
  return api.patch<DestinatariosAlerta>(`/alertas/destinatarios/${id}`, payload);
}

export function deleteDestinatario(id: string): Promise<DestinatariosAlerta> {
  return api.delete<DestinatariosAlerta>(`/alertas/destinatarios/${id}`);
}
