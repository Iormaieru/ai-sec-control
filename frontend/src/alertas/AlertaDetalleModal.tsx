import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getAlerta, updateAlerta, vincularCaso } from "../api/alertas";
import { listCasos } from "../api/casos";
import { ApiError } from "../api/client";
import type { AlertaDetalle, AspectoAnalisis, Caso, EstadoAlerta } from "../api/types";
import { ESTADO_BADGE, ESTADO_LABELS, SEVERIDAD_BADGE, SEVERIDAD_LABELS, fechaHora, fechaHoraSegundos } from "./labels";

function errorDetail(err: unknown, fallback: string): string {
  return err instanceof ApiError && typeof err.detail === "string" ? err.detail : fallback;
}

const ACCIONES: { estado: EstadoAlerta; label: string; clase: string }[] = [
  {
    estado: "en_revision",
    label: "Tomar (en revisión)",
    clase: "btn-outline-primary",
  },
  { estado: "resuelta", label: "Resolver", clase: "btn-outline-success" },
  {
    estado: "descartada",
    label: "Descartar (falso positivo)",
    clase: "btn-outline-secondary",
  },
  { estado: "nueva", label: "Reabrir", clase: "btn-outline-danger" },
];

const EXPLICACION_TENABLE = {
  fuera_de_cobertura:
    "Netskope vio actividad de IA en este equipo y Tenable no lo inventaría (ni por hostname ni por NetBIOS): no se sabe qué tiene instalado, ni sus vulnerabilidades ni sus puertos. Verificar de quién es el equipo y si corresponde incorporarlo a Tenable.",
  servicio_ia_expuesto:
    "Tenable encontró abierto el puerto de un servicio de IA (un modelo local o un notebook) en este equipo: queda accesible desde la red. Verificar si está autorizado y, si no, cerrarlo.",
};

// El nivel nunca va sólo por color: ícono + etiqueta.
const NIVEL: Record<AspectoAnalisis["nivel"], { icono: string; clase: string; etiqueta: string }> = {
  alto: { icono: "bi-exclamation-octagon-fill", clase: "text-danger", etiqueta: "Riesgo alto" },
  medio: { icono: "bi-exclamation-triangle-fill", clase: "text-warning-emphasis", etiqueta: "Atención" },
  bajo: { icono: "bi-check-circle-fill", clase: "text-success", etiqueta: "Riesgo bajo" },
  info: { icono: "bi-info-circle", clase: "text-secondary", etiqueta: "Informativo" },
};

/** Detalle de una alerta: actividad registrada por Netskope, gestión y caso. */
export function AlertaDetalleModal({
  alertaId,
  onCambio,
  onCerrar,
}: {
  alertaId: string;
  onCambio: () => void;
  onCerrar: () => void;
}) {
  const [alerta, setAlerta] = useState<AlertaDetalle | null>(null);
  const [nota, setNota] = useState("");
  const [casos, setCasos] = useState<Caso[]>([]);
  const [casoElegido, setCasoElegido] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAlerta(alertaId)
      .then((a) => {
        setAlerta(a);
        setNota(a.nota ?? "");
      })
      .catch((err) => setError(errorDetail(err, "No se pudo cargar la alerta")));
    listCasos()
      .then(setCasos)
      .catch(() => setCasos([]));
  }, [alertaId]);

  async function accion(fn: () => Promise<AlertaDetalle>, fallback: string) {
    setError(null);
    try {
      const actualizada = await fn();
      setAlerta(actualizada);
      setNota(actualizada.nota ?? "");
      onCambio();
    } catch (err) {
      setError(errorDetail(err, fallback));
    }
  }

  const actividades = alerta ? Object.entries(alerta.actividades).sort((a, b) => b[1] - a[1]) : [];
  const deTenable = alerta?.regla_fuente === "tenable";

  return (
    <>
      <div className="modal d-block" tabIndex={-1} role="dialog" aria-modal="true" onClick={onCerrar}>
        <div
          className="modal-dialog modal-xl modal-dialog-centered modal-dialog-scrollable"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="modal-content">
            <div className="modal-header">
              <h2 className="modal-title h5">
                {alerta ? (
                  <>
                    <span className={`badge me-2 ${SEVERIDAD_BADGE[alerta.severidad]}`}>
                      {SEVERIDAD_LABELS[alerta.severidad]}
                    </span>
                    {alerta.app}
                    <span className={`badge ms-2 ${ESTADO_BADGE[alerta.estado]}`}>{ESTADO_LABELS[alerta.estado]}</span>
                  </>
                ) : (
                  "Alerta"
                )}
              </h2>
              <button type="button" className="btn-close" aria-label="Cerrar" onClick={onCerrar} />
            </div>
            <div className="modal-body">
              {error && <div className="alert alert-danger py-2">{error}</div>}
              {!alerta ? (
                !error && <div className="spinner-border text-primary" role="status" />
              ) : (
                <>
                  {deTenable && alerta.regla_tipo && (
                    <div className="alert alert-light border small py-2">
                      <i className="bi bi-info-circle me-1" />
                      {EXPLICACION_TENABLE[alerta.regla_tipo]}
                    </div>
                  )}
                  {alerta.analisis.length > 0 && (
                    <div className="card mb-3">
                      <div className="card-body py-2">
                        <h3 className="h6 mb-2">Análisis</h3>
                        <table className="table table-sm small align-middle mb-0">
                          <tbody>
                            {alerta.analisis.map((a) => (
                              <tr key={a.aspecto}>
                                <th scope="row" className="text-nowrap fw-semibold" style={{ width: "1%" }}>
                                  {a.aspecto}
                                </th>
                                <td className="text-nowrap" style={{ width: "1%" }}>
                                  <span className={NIVEL[a.nivel].clase} title={NIVEL[a.nivel].etiqueta}>
                                    <i className={`bi ${NIVEL[a.nivel].icono} me-1`} aria-hidden="true" />
                                    <span className="small">{NIVEL[a.nivel].etiqueta}</span>
                                  </span>
                                </td>
                                <td>{a.texto}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                  <dl className="row small mb-3">
                    <dt className="col-sm-3">Regla</dt>
                    <dd className="col-sm-9">{alerta.regla_nombre}</dd>
                    <dt className="col-sm-3">{deTenable ? "Equipo" : "Usuario"}</dt>
                    <dd className="col-sm-9">{alerta.usuario}</dd>
                    {deTenable ? (
                      <>
                        <dt className="col-sm-3">Detectada</dt>
                        <dd className="col-sm-9">
                          {fechaHora(alerta.primera_vez)} · última verificación {fechaHora(alerta.ultima_vez)}
                        </dd>
                      </>
                    ) : (
                      <>
                        <dt className="col-sm-3">Eventos</dt>
                        <dd className="col-sm-9">
                          {alerta.cantidad_eventos} · primera vez {fechaHora(alerta.primera_vez)} · última{" "}
                          {fechaHora(alerta.ultima_vez)}
                        </dd>
                      </>
                    )}
                    <dt className="col-sm-3">
                      {alerta.regla_tipo === "fuera_de_cobertura"
                        ? "Alertas de Netskope"
                        : deTenable
                          ? "Hallazgo"
                          : "Actividades"}
                    </dt>
                    <dd className="col-sm-9">
                      {actividades.length === 0
                        ? "—"
                        : actividades.map(([actividad, n]) => (
                            <span key={actividad} className="badge text-bg-light border fw-normal me-1">
                              {actividad} ×{n}
                            </span>
                          ))}
                    </dd>
                    <dt className="col-sm-3">Aviso por email</dt>
                    <dd className="col-sm-9">
                      {alerta.notificada_at ? fechaHora(alerta.notificada_at) : "pendiente / no corresponde"}
                    </dd>
                  </dl>

                  <div className="d-flex flex-wrap gap-2 mb-3">
                    {ACCIONES.filter((a) => a.estado !== alerta.estado).map((a) => (
                      <button
                        key={a.estado}
                        className={`btn btn-sm ${a.clase}`}
                        onClick={() =>
                          accion(
                            () =>
                              updateAlerta(alerta.id, {
                                estado: a.estado,
                                nota,
                              }),
                            "No se pudo actualizar",
                          )
                        }
                      >
                        {a.label}
                      </button>
                    ))}
                  </div>

                  <div className="row g-3 mb-3">
                    <div className="col-md-6">
                      <label className="form-label small fw-semibold">Nota del analista</label>
                      <textarea
                        className="form-control form-control-sm"
                        rows={3}
                        value={nota}
                        onChange={(e) => setNota(e.target.value)}
                      />
                      <button
                        className="btn btn-sm btn-outline-secondary mt-1"
                        disabled={nota === (alerta.nota ?? "")}
                        onClick={() => accion(() => updateAlerta(alerta.id, { nota }), "No se pudo guardar la nota")}
                      >
                        Guardar nota
                      </button>
                    </div>
                    <div className="col-md-6">
                      <label className="form-label small fw-semibold">Caso</label>
                      {alerta.caso_id ? (
                        <div className="d-flex align-items-center gap-2 small">
                          <Link to={`/casos/${alerta.caso_id}`}>{alerta.caso_nombre}</Link>
                          {alerta.caso_jira_key && <span className="text-muted">{alerta.caso_jira_key}</span>}
                          <button
                            className="btn btn-sm btn-link text-danger p-0 ms-auto"
                            onClick={() => accion(() => vincularCaso(alerta.id, {}), "No se pudo desvincular")}
                          >
                            Desvincular
                          </button>
                        </div>
                      ) : (
                        <>
                          <div className="input-group input-group-sm mb-1">
                            <select
                              className="form-select"
                              value={casoElegido}
                              onChange={(e) => setCasoElegido(e.target.value)}
                            >
                              <option value="">Vincular a un caso existente…</option>
                              {casos.map((c) => (
                                <option key={c.id} value={c.id}>
                                  {c.nombre_proyecto}
                                  {c.jira_issue_key ? ` (${c.jira_issue_key})` : ""}
                                </option>
                              ))}
                            </select>
                            <button
                              className="btn btn-outline-primary"
                              disabled={!casoElegido}
                              onClick={() =>
                                accion(
                                  () =>
                                    vincularCaso(alerta.id, {
                                      caso_id: casoElegido,
                                    }),
                                  "No se pudo vincular",
                                )
                              }
                            >
                              Vincular
                            </button>
                          </div>
                          <button
                            className="btn btn-sm btn-link p-0"
                            onClick={() => {
                              if (
                                window.confirm(
                                  `¿Crear un caso «${deTenable ? `${alerta.app} – ${alerta.usuario}` : alerta.app}»? También se crea el ticket en Jira.`,
                                )
                              ) {
                                accion(() => vincularCaso(alerta.id, { crear: true }), "No se pudo crear el caso");
                              }
                            }}
                          >
                            <i className="bi bi-plus-lg me-1" />
                            {deTenable ? "Crear un caso nuevo para este equipo" : "Crear un caso nuevo para esta app"}
                          </button>
                        </>
                      )}
                    </div>
                  </div>

                  {alerta.contexto_equipos.length > 0 && (
                    <>
                      <h3 className="h6">Equipos y contexto de Tenable</h3>
                      <div className="table-responsive mb-3">
                        <table className="table table-sm small align-middle mb-0">
                          <thead className="table-light">
                            <tr>
                              <th>Equipo</th>
                              <th>En Tenable</th>
                              <th>Sistema</th>
                              <th>Software de IA</th>
                              <th>Puertos de IA</th>
                            </tr>
                          </thead>
                          <tbody>
                            {alerta.contexto_equipos.map((e) => (
                              <tr key={e.equipo}>
                                <td className="fw-semibold">{e.equipo}</td>
                                <td>
                                  {!e.en_tenable ? (
                                    <span className="badge text-bg-warning" title="Tenable no inventaría este equipo">
                                      No
                                    </span>
                                  ) : e.con_inventario ? (
                                    <span className="badge text-bg-success">Sí{e.tiene_agente ? " · agente" : ""}</span>
                                  ) : (
                                    <span
                                      className="badge text-bg-light border"
                                      title="Escaneado sin credenciales: no hay inventario de software"
                                    >
                                      Sólo red
                                    </span>
                                  )}
                                </td>
                                <td>{e.sistema_operativo ?? "—"}</td>
                                <td>{e.software_ia.length ? e.software_ia.join(", ") : "—"}</td>
                                <td>
                                  {e.puertos_ia.length
                                    ? e.puertos_ia.map((p) => `${p.servicio} (${p.puerto})`).join(", ")
                                    : "—"}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}

                  {alerta.regla_tipo === "fuera_de_cobertura" && (
                    <>
                      <h3 className="h6">Actividad de IA vista por Netskope en este equipo</h3>
                      <div className="table-responsive mb-3">
                        <table className="table table-sm small align-middle mb-0">
                          <thead className="table-light">
                            <tr>
                              <th>Regla</th>
                              <th>App</th>
                              <th>Usuario</th>
                              <th>Estado</th>
                              <th>Última vez</th>
                            </tr>
                          </thead>
                          <tbody>
                            {alerta.alertas_origen.length === 0 ? (
                              <tr>
                                <td colSpan={5} className="text-muted">
                                  Ya no hay alertas de Netskope con este equipo.
                                </td>
                              </tr>
                            ) : (
                              alerta.alertas_origen.map((o) => (
                                <tr key={o.id}>
                                  <td>
                                    <span className={`badge me-1 ${SEVERIDAD_BADGE[o.severidad]}`}>
                                      {SEVERIDAD_LABELS[o.severidad]}
                                    </span>
                                    <Link to={`/alertas?alerta=${o.id}`}>{o.regla_nombre}</Link>
                                  </td>
                                  <td>{o.app}</td>
                                  <td className="text-break">{o.usuario}</td>
                                  <td>
                                    <span className={`badge ${ESTADO_BADGE[o.estado]}`}>{ESTADO_LABELS[o.estado]}</span>
                                  </td>
                                  <td className="text-nowrap">{fechaHora(o.ultima_vez)}</td>
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}

                  {!deTenable && (
                    <>
                      <h3 className="h6">Últimos eventos ({alerta.eventos.length})</h3>
                      <div className="table-responsive">
                        <table className="table table-sm small align-middle">
                          <thead className="table-light">
                            <tr>
                              <th>Fecha</th>
                              <th>Actividad</th>
                              <th>Sitio</th>
                              <th>Objeto</th>
                              <th>Detalle</th>
                            </tr>
                          </thead>
                          <tbody>
                            {alerta.eventos.map((e) => (
                              <tr key={e.evento_id}>
                                <td className="text-nowrap">{fechaHoraSegundos(e.fecha)}</td>
                                <td>{e.actividad ?? "—"}</td>
                                <td>{e.sitio ?? "—"}</td>
                                <td className="text-break">{e.objeto ?? "—"}</td>
                                <td className="text-muted">
                                  {Object.entries(e.datos)
                                    .filter(([k]) => !["app", "activity", "site", "object"].includes(k))
                                    .map(([k, v]) => `${k}: ${String(v)}`)
                                    .join(" · ")}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      </div>
      <div className="modal-backdrop show" />
    </>
  );
}
