import { api } from "./client";
import type { Caso, CasoEstado, CasoTipo, Contacto } from "./types";

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
  empresa_responsable: string;
  nombre_proyecto: string;
  tipo: CasoTipo;
}

export function createCaso(payload: CasoCreatePayload): Promise<Caso> {
  return api.post<Caso>("/casos", payload);
}

export interface CasoUpdatePayload {
  gdld?: string | null;
  empresa_responsable?: string;
  nombre_proyecto?: string;
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
