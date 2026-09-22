import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { createCaso, listCasos, type CasoFilters } from "../api/casos";
import { ApiError } from "../api/client";
import type { Caso, CasoEstado, CasoTipo } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { ESTADO_LABELS, TIPO_LABELS } from "../casos/labels";

export function CasosPage() {
  const { user, logout } = useAuth();
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
    <main>
      <header className="page-header">
        <h1>Casos</h1>
        <div>
          <span>{user?.username}</span>
          <button onClick={logout}>Salir</button>
        </div>
      </header>

      <section className="filters">
        <select
          value={filters.tipo ?? ""}
          onChange={(e) => handleFilterChange({ tipo: (e.target.value || undefined) as CasoTipo | undefined })}
        >
          <option value="">Todos los tipos</option>
          {Object.entries(TIPO_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
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
        <input
          placeholder="Filtrar por empresa…"
          value={filters.empresa_responsable ?? ""}
          onChange={(e) => handleFilterChange({ empresa_responsable: e.target.value || undefined })}
        />
        <button onClick={() => setShowForm((v) => !v)}>{showForm ? "Cancelar" : "Nuevo caso"}</button>
      </section>

      {showForm && (
        <NewCasoForm
          onCreated={(caso) => {
            setShowForm(false);
            setCasos((prev) => [caso, ...prev]);
          }}
        />
      )}

      {error && <p className="error">{error}</p>}
      {loading ? (
        <p>Cargando…</p>
      ) : (
        <table className="casos-table">
          <thead>
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
                  <span className={`badge badge-${caso.estado}`}>{ESTADO_LABELS[caso.estado]}</span>
                </td>
              </tr>
            ))}
            {casos.length === 0 && (
              <tr>
                <td colSpan={4}>No hay casos que coincidan con el filtro.</td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </main>
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
    <form onSubmit={handleSubmit} className="new-caso-form">
      <input placeholder="GDLD (opcional)" value={gdld} onChange={(e) => setGdld(e.target.value)} />
      <input
        placeholder="Empresa responsable"
        value={empresa}
        onChange={(e) => setEmpresa(e.target.value)}
        required
      />
      <input
        placeholder="Nombre del proyecto"
        value={proyecto}
        onChange={(e) => setProyecto(e.target.value)}
        required
      />
      <select value={tipo} onChange={(e) => setTipo(e.target.value as CasoTipo)}>
        {Object.entries(TIPO_LABELS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
      <button type="submit" disabled={submitting}>
        {submitting ? "Creando…" : "Crear caso"}
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
