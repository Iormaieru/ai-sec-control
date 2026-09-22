import { api } from "./client";
import type { CasoPregunta, CasoScore, Dominio, RespuestaValor } from "./types";

export function listDominios(): Promise<Dominio[]> {
  return api.get<Dominio[]>("/catalogo/dominios");
}

export function listCasoPreguntas(casoId: string): Promise<CasoPregunta[]> {
  return api.get<CasoPregunta[]>(`/casos/${casoId}/preguntas`);
}

export function seleccionarDominioCompleto(casoId: string, dominioCodigo: string): Promise<CasoPregunta[]> {
  return api.post<CasoPregunta[]>(`/casos/${casoId}/preguntas`, { dominio_codigo: dominioCodigo });
}

export interface RespuestaUpdatePayload {
  respuesta: RespuestaValor;
  control_compensatorio?: string | null;
  factor_mitigacion_pct?: number | null;
  owner_responsable?: string | null;
  accion_remediacion?: string | null;
  fecha_objetivo?: string | null;
  evidencia_esperada?: string | null;
  observaciones?: string | null;
}

export function actualizarRespuesta(
  casoId: string,
  preguntaId: string,
  payload: RespuestaUpdatePayload,
): Promise<CasoPregunta> {
  return api.put<CasoPregunta>(`/casos/${casoId}/preguntas/${preguntaId}/respuesta`, payload);
}

export function getCasoScore(casoId: string): Promise<CasoScore> {
  return api.get<CasoScore>(`/casos/${casoId}/score`);
}
