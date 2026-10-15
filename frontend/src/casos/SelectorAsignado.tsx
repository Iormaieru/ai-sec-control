import { useEffect, useState } from "react";
import { asignarCaso, listAsignables, listEquipoJira } from "../api/casos";
import { ApiError } from "../api/client";
import type { Caso, PersonaJira } from "../api/types";
import { Asignado } from "./Asignado";

function errorDetail(err: unknown, fallback: string): string {
  return err instanceof ApiError && typeof err.detail === "string" ? err.detail : fallback;
}

/** Modal para asignar el ticket de Jira del caso. Sin búsqueda muestra al
 * equipo (quienes ya tienen casos); al escribir, busca en Jira entre las
 * personas asignables del proyecto. */
export function SelectorAsignado({
  caso,
  onAsignado,
  onCerrar,
}: {
  caso: Caso;
  onAsignado: (caso: Caso) => void;
  onCerrar: () => void;
}) {
  const [query, setQuery] = useState("");
  const [equipo, setEquipo] = useState<PersonaJira[] | null>(null);
  const [busqueda, setBusqueda] = useState<PersonaJira[] | null>(null);
  const [buscando, setBuscando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listEquipoJira()
      .then(setEquipo)
      .catch(() => setEquipo([]));
  }, []);

  useEffect(() => {
    const texto = query.trim();
    if (!texto) return;
    // Espera a que se deje de escribir para no consultar Jira en cada tecla.
    let vigente = true;
    const timer = setTimeout(() => {
      setBuscando(true);
      listAsignables(caso.id, texto)
        .then((personas) => vigente && setBusqueda(personas))
        .catch((err) => vigente && setError(errorDetail(err, "No se pudo buscar en Jira")))
        .finally(() => vigente && setBuscando(false));
    }, 300);
    return () => {
      vigente = false;
      clearTimeout(timer);
    };
  }, [query, caso.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCerrar();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCerrar]);

  async function elegir(accountId: string | null) {
    setError(null);
    setGuardando(true);
    try {
      onAsignado(await asignarCaso(caso.id, accountId));
    } catch (err) {
      setError(errorDetail(err, "No se pudo asignar en Jira"));
      setGuardando(false);
    }
  }

  // Sin texto se muestra el equipo, aunque haya quedado una búsqueda anterior.
  const resultados = query.trim() ? busqueda : null;
  const personas = resultados ?? equipo ?? [];
  const actualId = caso.jira_asignado_id;

  return (
    <>
      <div className="modal d-block" tabIndex={-1} role="dialog" aria-modal="true" onClick={onCerrar}>
        <div className="modal-dialog modal-dialog-centered" onClick={(e) => e.stopPropagation()}>
          <div className="modal-content">
            <div className="modal-header">
              <h2 className="modal-title h5">Asignar en Jira</h2>
              <button type="button" className="btn-close" aria-label="Cerrar" onClick={onCerrar} />
            </div>
            <div className="modal-body">
              <p className="small text-muted mb-2">
                {caso.nombre_proyecto} · {caso.jira_issue_key}
              </p>
              <input
                className="form-control mb-3"
                placeholder="Buscar persona en Jira…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                autoFocus
                aria-label="Buscar persona"
              />

              <div className="small text-muted text-uppercase fw-semibold mb-1">
                {resultados ? "Resultados en Jira" : "Equipo IA-SEC"}
                {buscando && <span className="spinner-border spinner-border-sm ms-2" role="status" />}
              </div>
              <div className="list-group selector-asignado-lista">
                {!resultados && (
                  <button
                    type="button"
                    className={`list-group-item list-group-item-action d-flex justify-content-between align-items-center ${
                      !actualId ? "active" : ""
                    }`}
                    onClick={() => elegir(null)}
                    disabled={guardando || !actualId}
                  >
                    <Asignado nombre={null} />
                  </button>
                )}
                {personas.map((p) => {
                  const actual = p.account_id === actualId;
                  return (
                    <button
                      key={p.account_id}
                      type="button"
                      className={`list-group-item list-group-item-action d-flex justify-content-between align-items-center ${
                        actual ? "active" : ""
                      }`}
                      onClick={() => elegir(p.account_id)}
                      disabled={guardando || actual}
                    >
                      <span className="d-flex align-items-center gap-2">
                        <Asignado nombre={p.nombre} avatarUrl={p.avatar_url} compacto />
                        {p.nombre}
                      </span>
                      {actual && <i className="bi bi-check-lg" />}
                    </button>
                  );
                })}
                {resultados && resultados.length === 0 && !buscando && (
                  <div className="list-group-item text-muted">Nadie asignable con ese nombre.</div>
                )}
                {!resultados && equipo !== null && equipo.length === 0 && (
                  <div className="list-group-item text-muted">Buscá a la persona por nombre.</div>
                )}
              </div>

              {guardando && (
                <div className="d-flex align-items-center gap-2 mt-3 small text-muted">
                  <span className="spinner-border spinner-border-sm" role="status" /> Asignando en Jira…
                </div>
              )}
              {error && <div className="alert alert-danger mt-3 mb-0 py-2">{error}</div>}
            </div>
          </div>
        </div>
      </div>
      <div className="modal-backdrop show" />
    </>
  );
}
