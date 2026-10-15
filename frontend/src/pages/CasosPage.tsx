import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { createCaso, listCasos, listTiposSolicitud, type CasoFilters } from "../api/casos";
import { ApiError } from "../api/client";
import type { Caso, CasoEstado, CasoTipo, TipoSolicitud } from "../api/types";
import { Asignado } from "../casos/Asignado";
import { CasosKanban } from "../casos/CasosKanban";
import {
  ESTADO_BADGE_CLASS,
  estadoConDetalle,
  ESTADO_LABELS,
  formatGdld,
  TIPO_LABELS,
  tipoLabel,
} from "../casos/labels";

type Vista = "tablero" | "lista";
const VISTA_STORAGE_KEY = "aisec_casos_vista";

function vistaGuardada(): Vista {
  try {
    return localStorage.getItem(VISTA_STORAGE_KEY) === "lista" ? "lista" : "tablero";
  } catch {
    return "tablero";
  }
}

function coincide(caso: Caso, busqueda: string): boolean {
  const q = busqueda.trim().toLowerCase();
  if (!q) return true;
  return [caso.nombre_proyecto, caso.jira_issue_key, caso.gdld, caso.gdld && `gdld ${caso.gdld}`]
    .filter(Boolean)
    .some((v) => (v as string).toLowerCase().includes(q));
}

export function CasosPage() {
  const [casos, setCasos] = useState<Caso[]>([]);
  const [filters, setFilters] = useState<CasoFilters>({});
  const [busqueda, setBusqueda] = useState("");
  const [vista, setVista] = useState<Vista>(vistaGuardada);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const visibles = casos.filter((caso) => coincide(caso, busqueda));

  function load(activeFilters: CasoFilters) {
    setLoading(true);
    listCasos(activeFilters)
      .then(setCasos)
      .catch((err) => setError(err instanceof ApiError ? err.detail : "No se pudieron cargar los casos"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load(filters);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleFilterChange(next: Partial<CasoFilters>) {
    const merged = { ...filters, ...next };
    setFilters(merged);
    load(merged);
  }

  function handleVista(nueva: Vista) {
    setVista(nueva);
    try {
      localStorage.setItem(VISTA_STORAGE_KEY, nueva);
    } catch {
      // sin almacenamiento: la preferencia dura lo que la página
    }
    // En el tablero cada columna es un estado: el filtro por estado no aplica.
    if (nueva === "tablero" && filters.estado) handleFilterChange({ estado: undefined });
  }

  function handleCasoChanged(actualizado: Caso) {
    setCasos((prev) => prev.map((c) => (c.id === actualizado.id ? actualizado : c)));
  }

  return (
    <>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <h1 className="h3 mb-0">Casos</h1>
        <button className="btn btn-primary" onClick={() => setShowForm((v) => !v)}>
          <i className="bi bi-plus-lg me-1" />
          {showForm ? "Cancelar" : "Nuevo caso"}
        </button>
      </div>

      <div className="row g-2 mb-3 align-items-center">
        <div className="col-auto">
          <div className="btn-group" role="group" aria-label="Vista">
            <button
              type="button"
              className={`btn ${vista === "tablero" ? "btn-primary" : "btn-outline-primary"}`}
              onClick={() => handleVista("tablero")}
              aria-pressed={vista === "tablero"}
            >
              <i className="bi bi-kanban me-1" />
              Tablero
            </button>
            <button
              type="button"
              className={`btn ${vista === "lista" ? "btn-primary" : "btn-outline-primary"}`}
              onClick={() => handleVista("lista")}
              aria-pressed={vista === "lista"}
            >
              <i className="bi bi-list-ul me-1" />
              Lista
            </button>
          </div>
        </div>
        <div className="col-auto">
          <input
            className="form-control"
            placeholder="Buscar proyecto, MDA-… o GDLD"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            aria-label="Buscar"
          />
        </div>
        <div className="col-auto">
          <select
            className="form-select"
            value={filters.tipo ?? ""}
            onChange={(e) =>
              handleFilterChange({
                tipo: (e.target.value || undefined) as CasoTipo | undefined,
              })
            }
          >
            <option value="">Todos los tipos</option>
            {Object.entries(TIPO_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        {vista === "lista" && (
          <div className="col-auto">
            <select
              className="form-select"
              value={filters.estado ?? ""}
              onChange={(e) =>
                handleFilterChange({
                  estado: (e.target.value || undefined) as CasoEstado | undefined,
                })
              }
            >
              <option value="">Todos los estados</option>
              {Object.entries(ESTADO_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="col-auto">
          <input
            className="form-control"
            placeholder="Filtrar por empresa…"
            value={filters.empresa_responsable ?? ""}
            onChange={(e) =>
              handleFilterChange({
                empresa_responsable: e.target.value || undefined,
              })
            }
          />
        </div>
      </div>

      {showForm && (
        <NewCasoForm
          onCreated={(caso) => {
            setShowForm(false);
            setCasos((prev) => [caso, ...prev]);
          }}
        />
      )}

      {error && <div className="alert alert-danger">{error}</div>}

      {loading ? (
        <div className="spinner-border text-primary" role="status">
          <span className="visually-hidden">Cargando…</span>
        </div>
      ) : vista === "tablero" ? (
        <CasosKanban casos={visibles} onChanged={handleCasoChanged} />
      ) : (
        <div className="card">
          <table className="table table-hover mb-0 align-middle">
            <thead className="table-light">
              <tr>
                <th>Proyecto</th>
                <th>Jira</th>
                <th>Asignado</th>
                <th>Empresa</th>
                <th>Tipo</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {visibles.map((caso) => (
                <tr key={caso.id}>
                  <td>
                    <Link to={`/casos/${caso.id}`}>{caso.nombre_proyecto}</Link>
                    {caso.gdld && <div className="small text-muted">{formatGdld(caso.gdld)}</div>}
                  </td>
                  <td>
                    {caso.jira_url ? (
                      <a href={caso.jira_url} target="_blank" rel="noreferrer">
                        {caso.jira_issue_key}
                      </a>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                    {caso.jira_sync_estado === "error" && (
                      <i
                        className="bi bi-exclamation-triangle-fill text-danger ms-1"
                        title="Error de sincronización con Jira"
                      />
                    )}
                  </td>
                  <td>
                    {caso.jira_issue_key ? (
                      <Asignado nombre={caso.jira_asignado_nombre} avatarUrl={caso.jira_asignado_avatar_url} />
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>{caso.empresa_responsable ?? "—"}</td>
                  <td>{tipoLabel(caso.tipo)}</td>
                  <td>
                    <span className={`badge ${ESTADO_BADGE_CLASS[caso.estado]}`}>{estadoConDetalle(caso)}</span>
                  </td>
                </tr>
              ))}
              {visibles.length === 0 && (
                <tr>
                  <td colSpan={6} className="text-center text-muted py-4">
                    No hay casos que coincidan con el filtro.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function NewCasoForm({ onCreated }: { onCreated: (caso: Caso) => void }) {
  const [gdld, setGdld] = useState("");
  const [empresa, setEmpresa] = useState("");
  const [proyecto, setProyecto] = useState("");
  const [tipo, setTipo] = useState<CasoTipo | "">("");
  const [tiposSolicitud, setTiposSolicitud] = useState<TipoSolicitud[]>([]);
  const [tipoSolicitud, setTipoSolicitud] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    listTiposSolicitud()
      .then((tipos) => {
        setTiposSolicitud(tipos);
        setTipoSolicitud(tipos[0]?.id ?? "");
      })
      .catch(() => setTiposSolicitud([]));
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const caso = await createCaso({
        gdld: gdld || null,
        empresa_responsable: empresa || null,
        nombre_proyecto: proyecto,
        tipo: tipo || null,
        tipo_solicitud_id: tipoSolicitud || undefined,
      });
      onCreated(caso);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "No se pudo crear el caso");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="card mb-3">
      <div className="card-body">
        <form onSubmit={handleSubmit} className="row g-2 align-items-end">
          <div className="col-auto">
            <label className="form-label" htmlFor="nuevo-caso-gdld">
              GDLD N° (opc.)
            </label>
            <input
              id="nuevo-caso-gdld"
              className="form-control"
              inputMode="numeric"
              placeholder="Ej: 12190"
              value={gdld}
              onChange={(e) => setGdld(e.target.value.replace(/\D/g, ""))}
            />
          </div>
          <div className="col-auto">
            <label className="form-label">Empresa responsable (opc.)</label>
            <input className="form-control" value={empresa} onChange={(e) => setEmpresa(e.target.value)} />
          </div>
          <div className="col-auto">
            <label className="form-label">Nombre del proyecto</label>
            <input className="form-control" value={proyecto} onChange={(e) => setProyecto(e.target.value)} required />
          </div>
          <div className="col-auto">
            <label className="form-label">Tipo (opc.)</label>
            <select className="form-select" value={tipo} onChange={(e) => setTipo(e.target.value as CasoTipo | "")}>
              <option value="">Sin definir</option>
              {Object.entries(TIPO_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="col-auto">
            <label className="form-label">Tipo de solicitud (Jira)</label>
            <select className="form-select" value={tipoSolicitud} onChange={(e) => setTipoSolicitud(e.target.value)}>
              {tiposSolicitud.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.nombre}
                </option>
              ))}
            </select>
          </div>
          <div className="col-auto">
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? "Creando…" : "Crear caso"}
            </button>
          </div>
          <div className="col-12 small text-muted">El caso se crea también como ticket en Jira (tablero IA-SEC).</div>
          {error && (
            <div className="col-12">
              <div className="alert alert-danger py-2 mb-0">{error}</div>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
