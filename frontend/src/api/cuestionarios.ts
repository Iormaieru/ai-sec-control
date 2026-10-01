import { api, request } from "./client";
import type { EnvioResultado, Formulario, Invitacion, RespuestaValor } from "./types";

export function enviarCuestionario(casoId: string, contactoIds: string[]): Promise<Invitacion[]> {
  return api.post<Invitacion[]>(`/casos/${casoId}/cuestionarios`, { contacto_ids: contactoIds });
}

export function listInvitaciones(casoId: string): Promise<Invitacion[]> {
  return api.get<Invitacion[]>(`/casos/${casoId}/cuestionarios`);
}

// --- Formulario público: el token va en un header (no en la URL de la API)
// para que no quede en los logs de acceso del backend.

export interface RespuestaFormulario {
  pregunta_id: string;
  respuesta: RespuestaValor;
  comentario: string | null;
}

function withToken(token: string, method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { "X-Cuestionario-Token": token },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  };
}

export function getFormulario(token: string): Promise<Formulario> {
  return request<Formulario>("/cuestionario", withToken(token, "GET"));
}

export function guardarBorrador(token: string, respuestas: RespuestaFormulario[]): Promise<void> {
  return request<void>("/cuestionario/borrador", withToken(token, "PUT", { respuestas }));
}

export function enviarRespuestas(token: string, respuestas: RespuestaFormulario[]): Promise<EnvioResultado> {
  return request<EnvioResultado>("/cuestionario/enviar", withToken(token, "POST", { respuestas }));
}
