import { api, fetchBlob } from "./client";
import type { PoblacionIA, SeveridadAlerta, TableroIA } from "./types";

export interface FiltrosTableroIA {
  desde?: string;
  hasta?: string;
  regla_id?: string;
  severidad?: SeveridadAlerta;
  poblacion?: PoblacionIA;
}

export type TablaCSV = "alertas" | "eventos" | "actividad";

function query(filtros: FiltrosTableroIA, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams(
    Object.entries({ ...filtros, ...extra }).filter(([, v]) => v) as [string, string][],
  );
  const q = params.toString();
  return q ? `?${q}` : "";
}

export function getTableroIA(filtros: FiltrosTableroIA): Promise<TableroIA> {
  return api.get<TableroIA>(`/metricas/ia${query(filtros)}`);
}

async function descargar(path: string, nombre: string): Promise<void> {
  const blob = await fetchBlob(path);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = nombre;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function descargarExcelIA(filtros: FiltrosTableroIA, periodo: string): Promise<void> {
  return descargar(`/metricas/ia/export.xlsx${query(filtros)}`, `seguridad-ia_${periodo}.xlsx`);
}

export function descargarCsvIA(filtros: FiltrosTableroIA, tabla: TablaCSV, periodo: string): Promise<void> {
  return descargar(`/metricas/ia/export.csv${query(filtros, { tabla })}`, `seguridad-ia_${tabla}_${periodo}.csv`);
}
