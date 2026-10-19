import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { listAlertas, listReglas, type FiltrosAlertas } from "../api/alertas";
import { ApiError } from "../api/client";
import type { Alerta, EstadoAlerta, ReglaAlerta, SeveridadAlerta } from "../api/types";
import { AlertaDetalleModal } from "../alertas/AlertaDetalleModal";
import { DestinatariosTab } from "../alertas/DestinatariosTab";
import { ReglasTab } from "../alertas/ReglasTab";
import { ESTADO_BADGE, ESTADO_LABELS, SEVERIDAD_BADGE, SEVERIDAD_LABELS, fechaHora } from "../alertas/labels";
import { useAuth } from "../auth/AuthContext";

/** Alertas generadas a partir de eventos de Netskope (Skope IT) y las reglas
 * que las disparan. El enlace del email (?alerta=<id>) abre el detalle. */
export function AlertasPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab");
  const pestania = tab === "reglas" || tab === "avisos" ? tab : "alertas";
  const alertaAbierta = params.get("alerta");
  const { user } = useAuth();
  const [alertas, setAlertas] = useState<Alerta[] | null>(null);
  const [reglas, setReglas] = useState<ReglaAlerta[]>([]);
  // Por defecto, las que hay que atender.
  const [filtros, setFiltros] = useState<FiltrosAlertas & { abiertas?: boolean }>({ abiertas: true });
  const [error, setError] = useState<string | null>(null);
  // Los campos de texto se aplican al dejar de escribir, no en cada tecla.
  const [texto, setTexto] = useState({ usuario: "", app: "" });
  useEffect(() => {
    const timer = setTimeout(
      () =>
        setFiltros((prev) =>
          prev.usuario === (texto.usuario.trim() || undefined) && prev.app === (texto.app.trim() || undefined)
            ? prev
            : { ...prev, usuario: texto.usuario.trim() || undefined, app: texto.app.trim() || undefined },
        ),
      350,
    );
    return () => clearTimeout(timer);
  }, [texto]);
  const hayFiltrosExtra = Boolean(texto.usuario || texto.app || filtros.desde || filtros.hasta);

  const cargar = useCallback(() => {
    const { abiertas, ...resto } = filtros;
    Promise.all([listAlertas(resto), listReglas()])
      .then(([lista, rs]) => {
        setAlertas(
          abiertas && !resto.estado ? lista.filter((a) => a.estado === "nueva" || a.estado === "en_revision") : lista,
        );
        setReglas(rs);
      })
      .catch((err) => setError(err instanceof ApiError ? err.detail : "No se pudieron cargar las alertas"));
  }, [filtros]);

  useEffect(cargar, [cargar]);

  function abrirAlerta(id: string | null) {
    const siguiente = new URLSearchParams(params);
    if (id) siguiente.set("alerta", id);
    else siguiente.delete("alerta");
    setParams(siguiente, { replace: true });
  }

  return (
    <>
      <h1 className="h3 mb-1">Alertas</h1>
      <p className="text-muted small mb-4">
        Actividad registrada por Netskope que coincide con las reglas de AI-SEC (por ejemplo, uso de servidores MCP por
        agentes de IA). Se actualiza cada pocos minutos.
      </p>
      {error && <div className="alert alert-danger">{error}</div>}

      <ul className="nav nav-tabs mb-3">
        {[
          { id: "alertas", label: "Alertas", icono: "bi-bell" },
          { id: "reglas", label: "Reglas", icono: "bi-funnel" },
          { id: "avisos", label: "Avisos por email", icono: "bi-envelope" },
        ].map((p) => (
          <li key={p.id} className="nav-item">
            <button
              type="button"
              className={`nav-link ${pestania === p.id ? "active" : ""}`}
              onClick={() => setParams({ tab: p.id }, { replace: true })}
            >
              <i className={`bi ${p.icono} me-1`} />
              {p.label}
            </button>
          </li>
        ))}
      </ul>

      {pestania === "avisos" ? (
        <DestinatariosTab esAdmin={user?.role === "admin"} />
      ) : pestania === "reglas" ? (
        <ReglasTab reglas={reglas} esAdmin={user?.role === "admin"} onCambio={cargar} />
      ) : (
        <>
          <div className="d-flex flex-wrap gap-2 mb-3">
            <select
              className="form-select w-auto"
              value={filtros.estado ?? (filtros.abiertas ? "abiertas" : "")}
              onChange={(e) => {
                const v = e.target.value;
                setFiltros({
                  ...filtros,
                  abiertas: v === "abiertas",
                  estado: v && v !== "abiertas" ? (v as EstadoAlerta) : undefined,
                });
              }}
            >
              <option value="abiertas">Abiertas (nuevas y en revisión)</option>
              <option value="">Todas</option>
              {Object.entries(ESTADO_LABELS).map(([valor, label]) => (
                <option key={valor} value={valor}>
                  {label}
                </option>
              ))}
            </select>
            <select
              className="form-select w-auto"
              value={filtros.severidad ?? ""}
              onChange={(e) =>
                setFiltros({ ...filtros, severidad: (e.target.value || undefined) as SeveridadAlerta | undefined })
              }
            >
              <option value="">Todas las severidades</option>
              {Object.entries(SEVERIDAD_LABELS).map(([valor, label]) => (
                <option key={valor} value={valor}>
                  {label}
                </option>
              ))}
            </select>
            <select
              className="form-select w-auto"
              value={filtros.regla_id ?? ""}
              onChange={(e) => setFiltros({ ...filtros, regla_id: e.target.value || undefined })}
            >
              <option value="">Todas las reglas</option>
              {reglas.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.nombre}
                </option>
              ))}
            </select>
          </div>
          <div className="row g-2 mb-3 align-items-end">
            <div className="col-sm-6 col-lg-3">
              <label className="form-label small mb-1">Usuario o equipo</label>
              <input
                type="search"
                className="form-control"
                placeholder="Contiene…"
                value={texto.usuario}
                onChange={(e) => setTexto({ ...texto, usuario: e.target.value })}
              />
            </div>
            <div className="col-sm-6 col-lg-3">
              <label className="form-label small mb-1">Aplicación</label>
              <input
                type="search"
                className="form-control"
                placeholder="Contiene…"
                list="alertas-apps"
                value={texto.app}
                onChange={(e) => setTexto({ ...texto, app: e.target.value })}
              />
              <datalist id="alertas-apps">
                {[...new Set((alertas ?? []).map((a) => a.app))].sort().map((app) => (
                  <option key={app} value={app} />
                ))}
              </datalist>
            </div>
            <div className="col-auto">
              <label className="form-label small mb-1" title="Alertas con actividad dentro del rango">
                Actividad desde
              </label>
              <input
                type="date"
                className="form-control"
                value={filtros.desde ?? ""}
                max={filtros.hasta}
                onChange={(e) => setFiltros({ ...filtros, desde: e.target.value || undefined })}
              />
            </div>
            <div className="col-auto">
              <label className="form-label small mb-1">hasta</label>
              <input
                type="date"
                className="form-control"
                value={filtros.hasta ?? ""}
                min={filtros.desde}
                onChange={(e) => setFiltros({ ...filtros, hasta: e.target.value || undefined })}
              />
            </div>
            {hayFiltrosExtra && (
              <div className="col-auto">
                <button
                  type="button"
                  className="btn btn-link"
                  onClick={() => {
                    setTexto({ usuario: "", app: "" });
                    setFiltros({ ...filtros, usuario: undefined, app: undefined, desde: undefined, hasta: undefined });
                  }}
                >
                  Limpiar
                </button>
              </div>
            )}
          </div>

          {!alertas ? (
            <div className="spinner-border text-primary" role="status" />
          ) : (
            <div className="card">
              <table className="table table-hover mb-0 align-middle small">
                <thead className="table-light">
                  <tr>
                    <th>Severidad</th>
                    <th>Aplicación</th>
                    <th>Usuario</th>
                    <th>Regla</th>
                    <th className="text-end">Eventos</th>
                    <th>Última actividad</th>
                    <th>Estado</th>
                    <th>Caso</th>
                  </tr>
                </thead>
                <tbody>
                  {alertas.map((a) => (
                    <tr key={a.id} role="button" onClick={() => abrirAlerta(a.id)}>
                      <td>
                        <span className={`badge ${SEVERIDAD_BADGE[a.severidad]}`}>{SEVERIDAD_LABELS[a.severidad]}</span>
                      </td>
                      <td className="fw-semibold">{a.app}</td>
                      <td>{a.usuario}</td>
                      <td className="text-muted">{a.regla_nombre}</td>
                      <td className="text-end">{a.cantidad_eventos}</td>
                      <td className="text-nowrap">{fechaHora(a.ultima_vez)}</td>
                      <td>
                        <span className={`badge ${ESTADO_BADGE[a.estado]}`}>{ESTADO_LABELS[a.estado]}</span>
                      </td>
                      <td>{a.caso_nombre ?? <span className="text-muted">—</span>}</td>
                    </tr>
                  ))}
                  {alertas.length === 0 && (
                    <tr>
                      <td colSpan={8} className="text-center text-muted py-4">
                        No hay alertas con estos filtros.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {alertaAbierta && (
        <AlertaDetalleModal alertaId={alertaAbierta} onCambio={cargar} onCerrar={() => abrirAlerta(null)} />
      )}
    </>
  );
}
