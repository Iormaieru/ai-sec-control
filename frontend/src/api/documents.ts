import { api, fetchBlob } from "./client";
import type { DocumentoAnalizado } from "./types";

export function analyzeDocument(casoId: string, file: File): Promise<DocumentoAnalizado> {
  const form = new FormData();
  form.append("file", file);
  return api.postFile<DocumentoAnalizado>(`/casos/${casoId}/documentos`, form);
}

export async function downloadExportDocx(casoId: string, filenameHint: string): Promise<void> {
  const blob = await fetchBlob(`/casos/${casoId}/export/docx`);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `informe-${filenameHint}.docx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
