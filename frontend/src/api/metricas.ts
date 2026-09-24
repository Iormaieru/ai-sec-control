import { api, fetchBlob } from "./client";
import type { CasoTipo, Metricas } from "./types";

export interface MetricasFilters {
  desde?: string;
  hasta?: string;
  tipo?: CasoTipo;
}

export function metricasQuery(filters: MetricasFilters): string {
  const params = new URLSearchParams();
  if (filters.desde) params.set("desde", filters.desde);
  if (filters.hasta) params.set("hasta", filters.hasta);
  if (filters.tipo) params.set("tipo", filters.tipo);
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function getMetricas(filters: MetricasFilters = {}): Promise<Metricas> {
  return api.get<Metricas>(`/metricas${metricasQuery(filters)}`);
}

export async function downloadReporteMetricas(filters: MetricasFilters): Promise<void> {
  const blob = await fetchBlob(`/metricas/export/docx${metricasQuery(filters)}`);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "reporte-metricas.docx";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
