import { useState, type FormEvent } from "react";
import { createRegla, deleteRegla, probarRegla, updateRegla, type ReglaPayload } from "../api/alertas";
import { ApiError } from "../api/client";
import type { PruebaRegla, ReglaAlerta, SeveridadAlerta } from "../api/types";
import { SEVERIDAD_BADGE, SEVERIDAD_LABELS, fechaHora } from "./labels";

function errorDetail(err: unknown, fallback: string): string {
  return err instanceof ApiError && typeof err.detail === "string" ? err.detail : fallback;
}

const VACIA: ReglaPayload = {
  nombre: "",
  descripcion: "",
  consulta: "",
  severidad: "media",
  activa: true,
  notificar_email: true,
  modo: "alerta",
};

/** Reglas que disparan alertas: consultas de Skope IT que el worker ejecuta
 * contra Netskope cada pocos minutos. */
export function ReglasTab({
  reglas,
  esAdmin,
  onCambio,
}: {
  reglas: ReglaAlerta[];
  esAdmin: boolean;
  onCambio: () => void;
}) {
  const [editando, setEditando] = useState<ReglaAlerta | "nueva" | null>(null);
  const [datos, setDatos] = useState<ReglaPayload>(VACIA);
  const [prueba, setPrueba] = useState<{ regla: string; resultado: PruebaRegla } | null>(null);
  const [probando, setProbando] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function abrir(regla: ReglaAlerta | "nueva") {
    setError(null);
    setEditando(regla);
    setDatos(regla === "nueva" ? VACIA : { ...regla, descripcion: regla.descripcion ?? "" });
  }

  async function guardar(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const payload = { ...datos, descripcion: datos.descripcion || null };
      if (editando === "nueva") await createRegla(payload);
      else if (editando) await updateRegla(editando.id, payload);
      setEditando(null);
      onCambio();
    } catch (err) {
      setError(errorDetail(err, "No se pudo guardar la regla"));
    }
  }

  async function probar(regla: ReglaAlerta) {
    setError(null);
    setPrueba(null);
    setProbando(regla.id);
    try {
      setPrueba({ regla: regla.nombre, resultado: await probarRegla(regla.id) });
    } catch (err) {
      setError(errorDetail(err, "No se pudo consultar Netskope"));
    } finally {
      setProbando(null);
    }
  }

  async function eliminar(regla: ReglaAlerta) {
    if (!window.confirm(`¿Eliminar la regla «${regla.nombre}» y sus alertas?`)) return;
    try {
      await deleteRegla(regla.id);
      onCambio();
    } catch (err) {
      setError(errorDetail(err, "No se pudo eliminar"));
    }
  }

  return (
    <>
      <div className="d-flex align-items-center mb-3">
        <p className="small text-muted mb-0 me-auto">
          Cada regla es una consulta con la sintaxis de búsqueda de Netskope Skope IT (por ejemplo{" "}
          <code>app like mcp</code>). Los eventos que la cumplen se agrupan en una alerta por aplicación y usuario.
        </p>
        {esAdmin && (
          <button className="btn btn-primary ms-3 text-nowrap" onClick={() => abrir("nueva")}>
            <i className="bi bi-plus-lg me-1" />
            Nueva regla
          </button>
        )}
      </div>
      {error && <div className="alert alert-danger py-2">{error}</div>}

      <div className="list-group mb-3">
        {reglas.map((r) => (
          <div key={r.id} className={`list-group-item ${r.activa ? "" : "bg-body-tertiary"}`}>
            <div className="d-flex flex-wrap align-items-center gap-2">
              <span className={`badge ${SEVERIDAD_BADGE[r.severidad]}`}>{SEVERIDAD_LABELS[r.severidad]}</span>
              <span className="fw-semibold">{r.nombre}</span>
              {!r.activa && <span className="badge text-bg-secondary">inactiva</span>}
              {r.fuente === "tenable" && <span className="badge text-bg-dark">Tenable</span>}
              {r.modo === "metrica" && (
                <span
                  className="badge text-bg-light border"
                  title="Sólo junta totales para el tablero: no genera alertas"
                >
                  <i className="bi bi-bar-chart me-1" />
                  métrica
                </span>
              )}
              {r.notificar_email && <i className="bi bi-envelope text-muted" title="Avisa por email" />}
              <code className="small">{r.consulta}</code>
              <span className="small text-muted ms-auto">
                {r.modo === "alerta" ? `${r.alertas_abiertas} abierta(s) · ` : ""}consultada hasta{" "}
                {fechaHora(r.consultada_hasta)}
              </span>
              {esAdmin && (
                <span className="text-nowrap">
                  <button
                    className="btn btn-sm btn-outline-primary me-1"
                    onClick={() => probar(r)}
                    disabled={probando === r.id || r.fuente !== "netskope"}
                    title={
                      r.fuente !== "netskope"
                        ? "Las reglas de Tenable se evalúan sobre el inventario diario"
                        : undefined
                    }
                  >
                    {probando === r.id ? <span className="spinner-border spinner-border-sm" /> : "Probar"}
                  </button>
                  <button className="btn btn-sm btn-outline-secondary me-1" title="Editar" onClick={() => abrir(r)}>
                    <i className="bi bi-pencil" />
                  </button>
                  <button className="btn btn-sm btn-outline-danger" title="Eliminar" onClick={() => eliminar(r)}>
                    <i className="bi bi-trash" />
                  </button>
                </span>
              )}
            </div>
            {r.descripcion && <div className="small text-muted mt-1">{r.descripcion}</div>}
            {r.ultimo_error && (
              <div className="small text-danger mt-1">
                <i className="bi bi-exclamation-triangle me-1" />
                Última consulta con error: {r.ultimo_error}
              </div>
            )}
          </div>
        ))}
      </div>

      {prueba && (
        <div className="card mb-3">
          <div className="card-body small">
            <div className="d-flex justify-content-between">
              <h3 className="h6">Prueba de «{prueba.regla}» (últimas 24 h)</h3>
              <button type="button" className="btn-close" aria-label="Cerrar" onClick={() => setPrueba(null)} />
            </div>
            <p className="mb-2">
              <strong>{prueba.resultado.cantidad}</strong> evento(s) de <strong>{prueba.resultado.usuarios}</strong>{" "}
              usuario(s) entre {fechaHora(prueba.resultado.desde)} y {fechaHora(prueba.resultado.hasta)}.
            </p>
            {Object.entries(prueba.resultado.por_app).map(([app, n]) => (
              <span key={app} className="badge text-bg-light border fw-normal me-1">
                {app} ×{n}
              </span>
            ))}
          </div>
        </div>
      )}

      {editando && (
        <>
          <div
            className="modal d-block"
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            onClick={() => setEditando(null)}
          >
            <div className="modal-dialog modal-dialog-centered" onClick={(e) => e.stopPropagation()}>
              <form className="modal-content" onSubmit={guardar}>
                <div className="modal-header">
                  <h2 className="modal-title h5">
                    {editando === "nueva" ? "Nueva regla" : `Editar «${editando.nombre}»`}
                  </h2>
                  <button type="button" className="btn-close" aria-label="Cerrar" onClick={() => setEditando(null)} />
                </div>
                <div className="modal-body">
                  <label className="form-label">Nombre</label>
                  <input
                    className="form-control mb-2"
                    required
                    minLength={3}
                    value={datos.nombre}
                    onChange={(e) => setDatos({ ...datos, nombre: e.target.value })}
                  />
                  <label className="form-label">
                    {editando !== "nueva" && editando.fuente === "tenable" ? "Tipo (Tenable)" : "Consulta de Skope IT"}
                  </label>
                  <input
                    className="form-control font-monospace"
                    required
                    minLength={3}
                    placeholder="app like mcp"
                    readOnly={editando !== "nueva" && editando.fuente === "tenable"}
                    value={datos.consulta}
                    onChange={(e) => setDatos({ ...datos, consulta: e.target.value })}
                  />
                  <div className="form-text mb-2">
                    La misma que se escribe en Skope IT → Application Events. Si la cambiás, se vuelve a revisar el
                    historial reciente.
                  </div>
                  <label className="form-label">Descripción</label>
                  <textarea
                    className="form-control mb-2"
                    rows={2}
                    value={datos.descripcion ?? ""}
                    onChange={(e) => setDatos({ ...datos, descripcion: e.target.value })}
                  />
                  <div className="row g-2 align-items-center">
                    <div className="col-6">
                      <label className="form-label">Severidad</label>
                      <select
                        className="form-select"
                        value={datos.severidad}
                        onChange={(e) => setDatos({ ...datos, severidad: e.target.value as SeveridadAlerta })}
                      >
                        {Object.entries(SEVERIDAD_LABELS).map(([valor, label]) => (
                          <option key={valor} value={valor}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="col-12">
                      <label className="form-label">Modo</label>
                      <select
                        className="form-select"
                        value={datos.modo}
                        onChange={(e) => setDatos({ ...datos, modo: e.target.value as "alerta" | "metrica" })}
                      >
                        <option value="alerta">Alerta: una alerta por app y usuario, con aviso por email</option>
                        <option value="metrica">Métrica: sólo totales para el tablero (consultas muy amplias)</option>
                      </select>
                    </div>
                    <div className="col-6 pt-4">
                      <div className="form-check">
                        <input
                          id="regla-activa"
                          type="checkbox"
                          className="form-check-input"
                          checked={datos.activa}
                          onChange={(e) => setDatos({ ...datos, activa: e.target.checked })}
                        />
                        <label htmlFor="regla-activa" className="form-check-label">
                          Activa
                        </label>
                      </div>
                      <div className="form-check">
                        <input
                          id="regla-email"
                          type="checkbox"
                          className="form-check-input"
                          checked={datos.notificar_email}
                          onChange={(e) => setDatos({ ...datos, notificar_email: e.target.checked })}
                        />
                        <label htmlFor="regla-email" className="form-check-label">
                          Avisar por email
                        </label>
                      </div>
                    </div>
                  </div>
                  {error && <div className="alert alert-danger py-2 mt-3 mb-0">{error}</div>}
                </div>
                <div className="modal-footer">
                  <button type="button" className="btn btn-outline-secondary" onClick={() => setEditando(null)}>
                    Cancelar
                  </button>
                  <button type="submit" className="btn btn-primary">
                    Guardar
                  </button>
                </div>
              </form>
            </div>
          </div>
          <div className="modal-backdrop show" />
        </>
      )}
    </>
  );
}
