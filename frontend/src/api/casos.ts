import { api } from "./client";
import type { Caso, CasoEstado, CasoTipo, Comentario, Contacto, PersonaJira, TipoSolicitud, Transicion } from "./types";

export interface CasoFilters {
  estado?: CasoEstado;
  tipo?: CasoTipo;
  empresa_responsable?: string;
}

export function listCasos(filters: CasoFilters = {}): Promise<Caso[]> {
  const params = new URLSearchParams();
  if (filters.estado) params.set("estado", filters.estado);
  if (filters.tipo) params.set("tipo", filters.tipo);
  if (filters.empresa_responsable) params.set("empresa_responsable", filters.empresa_responsable);
  const query = params.toString();
  return api.get<Caso[]>(`/casos${query ? `?${query}` : ""}`);
}

export function getCaso(id: string): Promise<Caso> {
  return api.get<Caso>(`/casos/${id}`);
}

export interface CasoCreatePayload {
  gdld?: string | null;
  empresa_responsable?: string | null;
  nombre_proyecto: string;
  tipo?: CasoTipo | null;
  tipo_solicitud_id?: string;
}

export function createCaso(payload: CasoCreatePayload): Promise<Caso> {
  return api.post<Caso>("/casos", payload);
}

export interface CasoUpdatePayload {
  gdld?: string | null;
  empresa_responsable?: string;
  nombre_proyecto?: string;
  tipo?: CasoTipo;
  /** Sólo para casos que no están en Jira; los demás usan transicionarCaso. */
  estado?: CasoEstado;
}

export function updateCaso(id: string, payload: CasoUpdatePayload): Promise<Caso> {
  return api.patch<Caso>(`/casos/${id}`, payload);
}

export interface ContactoPayload {
  nombre: string;
  email?: string | null;
  rol?: string | null;
}

export function addContacto(casoId: string, payload: ContactoPayload): Promise<Contacto> {
  return api.post<Contacto>(`/casos/${casoId}/contactos`, payload);
}

export function removeContacto(casoId: string, contactoId: string): Promise<void> {
  return api.delete<void>(`/casos/${casoId}/contactos/${contactoId}`);
}

export function listTiposSolicitud(): Promise<TipoSolicitud[]> {
  return api.get<TipoSolicitud[]>("/casos/tipos-solicitud");
}

export function listComentarios(casoId: string): Promise<Comentario[]> {
  return api.get<Comentario[]>(`/casos/${casoId}/comentarios`);
}

export function addComentario(casoId: string, cuerpo: string): Promise<Comentario> {
  return api.post<Comentario>(`/casos/${casoId}/comentarios`, { cuerpo });
}

/** Transiciones que el workflow de Jira permite hoy para el ticket del caso. */
export function listTransiciones(casoId: string): Promise<Transicion[]> {
  return api.get<Transicion[]>(`/casos/${casoId}/transiciones`);
}

export function transicionarCaso(casoId: string, transitionId: string): Promise<Caso> {
  return api.post<Caso>(`/casos/${casoId}/transiciones`, { transition_id: transitionId });
}

export function reintentarJira(casoId: string): Promise<Caso> {
  return api.post<Caso>(`/casos/${casoId}/jira/reintentar`);
}

/** Personas que ya tienen casos asignados (atajo del selector). */
export function listEquipoJira(): Promise<PersonaJira[]> {
  return api.get<PersonaJira[]>("/casos/equipo-jira");
}

/** Personas de Jira a las que se puede asignar el ticket del caso. */
export function listAsignables(casoId: string, query: string): Promise<PersonaJira[]> {
  return api.get<PersonaJira[]>(`/casos/${casoId}/asignables?query=${encodeURIComponent(query)}`);
}

/** Asigna el ticket en Jira; null lo deja sin asignar. */
export function asignarCaso(casoId: string, accountId: string | null): Promise<Caso> {
  return api.put<Caso>(`/casos/${casoId}/asignado`, { account_id: accountId });
}
