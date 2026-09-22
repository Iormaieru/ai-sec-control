import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { createCaso, listCasos, type CasoFilters } from "../api/casos";
import { ApiError } from "../api/client";
import type { Caso, CasoEstado, CasoTipo } from "../api/types";
import { ESTADO_BADGE_CLASS, ESTADO_LABELS, TIPO_LABELS } from "../casos/labels";

export function CasosPage() {
  const [casos, setCasos] = useState<Caso[]>([]);
  const [filters, setFilters] = useState<CasoFilters>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

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

  return (
    <>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <h1 className="h3 mb-0">Casos</h1>
        <button className="btn btn-primary" onClick={() => setShowForm((v) => !v)}>
          <i className="bi bi-plus-lg me-1" />
          {showForm ? "Cancelar" : "Nuevo caso"}
        </button>
      </div>

      <div className="row g-2 mb-3">
        <div className="col-auto">
          <select
            className="form-select"
            value={filters.tipo ?? ""}
            onChange={(e) =>
              handleFilterChange({ tipo: (e.target.value || undefined) as CasoTipo | undefined })
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
        <div className="col-auto">
          <select
            className="form-select"
            value={filters.estado ?? ""}
            onChange={(e) =>
              handleFilterChange({ estado: (e.target.value || undefined) as CasoEstado | undefined })
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
        <div className="col-auto">
          <input
            className="form-control"
            placeholder="Filtrar por empresa…"
            value={filters.empresa_responsable ?? ""}
            onChange={(e) => handleFilterChange({ empresa_responsable: e.target.value || undefined })}
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
      ) : (
        <div className="card">
          <table className="table table-hover mb-0 align-middle">
            <thead className="table-light">
              <tr>
                <th>Proyecto</th>
                <th>Empresa</th>
                <th>Tipo</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {casos.map((caso) => (
                <tr key={caso.id}>
                  <td>
                    <Link to={`/casos/${caso.id}`}>{caso.nombre_proyecto}</Link>
                  </td>
                  <td>{caso.empresa_responsable}</td>
                  <td>{TIPO_LABELS[caso.tipo]}</td>
                  <td>
                    <span className={`badge ${ESTADO_BADGE_CLASS[caso.estado]}`}>
                      {ESTADO_LABELS[caso.estado]}
                    </span>
                  </td>
                </tr>
              ))}
              {casos.length === 0 && (
                <tr>
                  <td colSpan={4} className="text-center text-muted py-4">
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
  const [tipo, setTipo] = useState<CasoTipo>("candidato");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const caso = await createCaso({
        gdld: gdld || null,
        empresa_responsable: empresa,
        nombre_proyecto: proyecto,
        tipo,
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
            <label className="form-label">GDLD (opcional)</label>
            <input className="form-control" value={gdld} onChange={(e) => setGdld(e.target.value)} />
          </div>
          <div className="col-auto">
            <label className="form-label">Empresa responsable</label>
            <input
              className="form-control"
              value={empresa}
              onChange={(e) => setEmpresa(e.target.value)}
              required
            />
          </div>
          <div className="col-auto">
            <label className="form-label">Nombre del proyecto</label>
            <input
              className="form-control"
              value={proyecto}
              onChange={(e) => setProyecto(e.target.value)}
              required
            />
          </div>
          <div className="col-auto">
            <label className="form-label">Tipo</label>
            <select className="form-select" value={tipo} onChange={(e) => setTipo(e.target.value as CasoTipo)}>
              {Object.entries(TIPO_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="col-auto">
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? "Creando…" : "Crear caso"}
            </button>
          </div>
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
