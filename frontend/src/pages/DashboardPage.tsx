import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { getMetricas, type MetricasFilters } from "../api/metricas";
import { ApiError } from "../api/client";
import type { CasoTipo, Metricas, Severidad } from "../api/types";
import { TIPO_LABELS } from "../casos/labels";
import { SEVERIDAD_BADGE_CLASS, SEVERIDAD_LABELS } from "../pentesting/labels";
import { SEMAFORO_LABELS, formatPct } from "../threatModel/labels";

export function DashboardPage() {
  const [filters, setFilters] = useState<MetricasFilters>({});
  const [metricas, setMetricas] = useState<Metricas | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getMetricas(filters)
      .then(setMetricas)
      .catch((err) => setError(err instanceof ApiError ? err.detail : "No se pudieron cargar las métricas"))
      .finally(() => setLoading(false));
  }, [filters]);

  function update(next: Partial<MetricasFilters>) {
    setFilters((prev) => ({ ...prev, ...next }));
  }

  return (
    <>
      <h1 className="h3 mb-3">Dashboard de métricas</h1>

      <div className="row g-2 mb-4 align-items-end">
        <div className="col-auto">
          <label className="form-label mb-1">Desde</label>
          <input
            type="date"
            className="form-control"
            value={filters.desde ?? ""}
            onChange={(e) => update({ desde: e.target.value || undefined })}
          />
        </div>
        <div className="col-auto">
          <label className="form-label mb-1">Hasta</label>
          <input
            type="date"
            className="form-control"
            value={filters.hasta ?? ""}
            onChange={(e) => update({ hasta: e.target.value || undefined })}
          />
        </div>
        <div className="col-auto">
          <label className="form-label mb-1">Tipo de caso</label>
          <select
            className="form-select"
            value={filters.tipo ?? ""}
            onChange={(e) => update({ tipo: (e.target.value || undefined) as CasoTipo | undefined })}
          >
            <option value="">Todos</option>
            {Object.entries(TIPO_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="col-auto">
          <button className="btn btn-outline-secondary" onClick={() => setFilters({})}>
            Limpiar filtros
          </button>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}
      {loading && !metricas && (
        <div className="spinner-border text-primary" role="status">
          <span className="visually-hidden">Cargando…</span>
        </div>
      )}
      {metricas && <DashboardContent metricas={metricas} />}
    </>
  );
}

function StatCard({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="col-6 col-xl-3">
      <div className="card h-100">
        <div className="card-body">
          <div className="text-muted small">{label}</div>
          <div className="display-6 fw-semibold">{value}</div>
          {hint && <div className="text-muted small">{hint}</div>}
        </div>
      </div>
    </div>
  );
}

function BarRow({ label, value, max, extra }: { label: ReactNode; value: number; max: number; extra?: string }) {
  const width = max > 0 ? Math.max((value / max) * 100, value > 0 ? 3 : 0) : 0;
  return (
    <div className="mb-2">
      <div className="d-flex justify-content-between small">
        <span>{label}</span>
        <span className="fw-semibold">{extra ?? value}</span>
      </div>
      <div className="progress" style={{ height: 8 }}>
        <div className="progress-bar" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function DashboardContent({ metricas }: { metricas: Metricas }) {
  const { proyectos_ingresados: pi, analisis, modelados, pentesting } = metricas;
  const maxMes = Math.max(0, ...pi.por_mes.map((m) => m.cantidad));
  const maxHerramienta = Math.max(0, ...pentesting.por_herramienta.map((h) => h.cantidad));

  return (
    <>
      <div className="row g-3 mb-4">
        <StatCard label="Proyectos ingresados" value={pi.total} />
        <StatCard
          label="Análisis con IA"
          value={analisis.casos_analizados}
          hint={`${analisis.documentos_analizados} documento(s)`}
        />
        <StatCard
          label="Modelados de amenazas"
          value={modelados.cantidad}
          hint={
            modelados.promedio_compliance_pct !== null
              ? `${formatPct(modelados.promedio_compliance_pct)} cumplimiento promedio`
              : "sin datos"
          }
        />
        <StatCard
          label="Pentestings"
          value={pentesting.total}
          hint={`en ${pentesting.casos_con_pentest} caso(s)`}
        />
      </div>

      <div className="row g-3 mb-4">
        <div className="col-lg-7">
          <div className="card h-100">
            <div className="card-body">
              <h2 className="h5">Proyectos ingresados por mes</h2>
              {pi.por_mes.length === 0 ? (
                <p className="text-muted mb-0">Sin proyectos en el período.</p>
              ) : (
                pi.por_mes.map((m) => <BarRow key={m.periodo} label={m.periodo} value={m.cantidad} max={maxMes} />)
              )}
            </div>
          </div>
        </div>
        <div className="col-lg-5">
          <div className="card h-100">
            <div className="card-body">
              <h2 className="h5">Por tipo de caso</h2>
              <table className="table table-sm mb-0">
                <thead>
                  <tr>
                    <th>Tipo</th>
                    <th className="text-end">Ingresados</th>
                    <th className="text-end">Analizados con IA</th>
                  </tr>
                </thead>
                <tbody>
                  {(Object.keys(TIPO_LABELS) as CasoTipo[]).map((tipo) => (
                    <tr key={tipo}>
                      <td>{TIPO_LABELS[tipo]}</td>
                      <td className="text-end">{pi.por_tipo[tipo]}</td>
                      <td className="text-end">{analisis.por_tipo[tipo]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <div className="card mb-4">
        <div className="card-body">
          <h2 className="h5">Modelados de amenazas y riesgo resultante</h2>
          <div className="d-flex gap-2 flex-wrap mb-3">
            {(["solido", "moderado", "vulnerable", "critico"] as const).map((s) => (
              <span key={s} className={`badge score-card--${s} text-dark border`}>
                {SEMAFORO_LABELS[s]}: {modelados.por_semaforo[s] ?? 0}
              </span>
            ))}
          </div>
          {modelados.casos.length === 0 ? (
            <p className="text-muted mb-0">
              Ningún caso del período tiene preguntas respondidas todavía.
            </p>
          ) : (
            <div className="table-responsive">
              <table className="table table-hover align-middle mb-0">
                <thead className="table-light">
                  <tr>
                    <th>Proyecto</th>
                    <th>Empresa</th>
                    <th>Tipo</th>
                    <th className="text-end">Cumplimiento</th>
                    <th className="text-end">Riesgo residual</th>
                    <th className="text-end">Completitud</th>
                    <th className="text-end">Brechas críticas</th>
                    <th>Semáforo</th>
                  </tr>
                </thead>
                <tbody>
                  {modelados.casos.map((c) => (
                    <tr key={c.caso_id}>
                      <td>
                        <Link to={`/casos/${c.caso_id}/preguntas`}>{c.nombre_proyecto}</Link>
                      </td>
                      <td>{c.empresa_responsable}</td>
                      <td>{TIPO_LABELS[c.tipo]}</td>
                      <td className="text-end">{formatPct(c.compliance_pct)}</td>
                      <td className="text-end">{formatPct(c.residual_pct)}</td>
                      <td className="text-end">{formatPct(c.completitud_pct)}</td>
                      <td className="text-end">{c.brechas_criticas}</td>
                      <td>{SEMAFORO_LABELS[c.semaforo]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <div className="row g-3">
        <div className="col-lg-6">
          <div className="card h-100">
            <div className="card-body">
              <h2 className="h5">Pentestings por herramienta</h2>
              {pentesting.por_herramienta.length === 0 ? (
                <p className="text-muted mb-0">Sin pentestings en el período.</p>
              ) : (
                pentesting.por_herramienta.map((h) => (
                  <BarRow key={h.nombre} label={h.nombre} value={h.cantidad} max={maxHerramienta} />
                ))
              )}
            </div>
          </div>
        </div>
        <div className="col-lg-6">
          <div className="card h-100">
            <div className="card-body">
              <h2 className="h5">Resultados por severidad</h2>
              <div className="d-flex gap-3 flex-wrap">
                {(Object.keys(SEVERIDAD_LABELS) as Severidad[]).map((s) => (
                  <div key={s} className="text-center">
                    <div className="display-6 fw-semibold">{pentesting.por_severidad[s]}</div>
                    <span className={`badge ${SEVERIDAD_BADGE_CLASS[s]}`}>{SEVERIDAD_LABELS[s]}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
