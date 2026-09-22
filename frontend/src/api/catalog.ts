import { api } from "./client";
import type { PreguntaCatalogo } from "./types";

export function listPreguntasCatalogo(dominioCodigo: string): Promise<PreguntaCatalogo[]> {
  return api.get<PreguntaCatalogo[]>(`/catalogo/preguntas?dominio=${encodeURIComponent(dominioCodigo)}`);
}
