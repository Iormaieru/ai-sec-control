import { useEffect, useState, type FormEvent } from "react";
import { addDestinatario, deleteDestinatario, listDestinatarios, updateDestinatario } from "../api/alertas";
import { ApiError } from "../api/client";
import type { DestinatarioAlerta, DestinatariosAlerta } from "../api/types";

function errorDetail(err: unknown, fallback: string): string {
  return err instanceof ApiError && typeof err.detail === "string" ? err.detail : fallback;
}

/** Casillas que reciben el email resumen de alertas nuevas. Las edita un
 * admin; en el futuro saldrán de un grupo de Entra ID. */
export function DestinatariosTab({ esAdmin }: { esAdmin: boolean }) {
  const [datos, setDatos] = useState<DestinatariosAlerta | null>(null);
  const [nuevo, setNuevo] = useState({ email: "", nombre: "" });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listDestinatarios()
      .then(setDatos)
      .catch((err) => setError(errorDetail(err, "No se pudieron cargar los destinatarios")));
  }, []);

  async function accion(fn: () => Promise<DestinatariosAlerta>, fallback: string): Promise<boolean> {
    setError(null);
    try {
      setDatos(await fn());
      return true;
    } catch (err) {
      setError(errorDetail(err, fallback));
      return false;
    }
  }

  async function agregar(event: FormEvent) {
    event.preventDefault();
    const ok = await accion(
      () => addDestinatario({ email: nuevo.email, nombre: nuevo.nombre || null }),
      "No se pudo agregar el destinatario",
    );
    if (ok) setNuevo({ email: "", nombre: "" });
  }

  function quitar(d: DestinatarioAlerta) {
    if (window.confirm(`¿Quitar ${d.email} de los avisos?`)) {
      accion(() => deleteDestinatario(d.id), "No se pudo quitar el destinatario");
    }
  }

  if (!datos) {
    return error ? (
      <div className="alert alert-danger">{error}</div>
    ) : (
      <div className="spinner-border text-primary" role="status" />
    );
  }

  return (
    <>
      <p className="text-muted small mb-3">
        Reciben un email resumen con las alertas nuevas o reincidentes de las reglas que tienen el aviso activado (uno
        por vuelta del worker, cada pocos minutos). Más adelante esta lista va a salir de un grupo de Entra ID.
      </p>

      {datos.origen === "variable" && (
        <div className="alert alert-info small py-2">
          <i className="bi bi-info-circle me-1" />
          No hay destinatarios cargados: hoy se avisa a la configuración del servidor (
          <code>AISEC_ALERTAS_EMAIL_DESTINO</code>): {datos.en_uso.join(", ")}. Al cargar el primero, se usa esta lista.
        </div>
      )}
      {datos.origen === "ninguno" && (
        <div className="alert alert-warning small py-2">
          <i className="bi bi-exclamation-triangle me-1" />
          No hay destinatarios activos: las alertas nuevas no se avisan por email.
        </div>
      )}
      {error && <div className="alert alert-danger py-2">{error}</div>}

      {esAdmin && (
        <form className="row g-2 align-items-end mb-3" onSubmit={agregar}>
          <div className="col-sm-5 col-lg-4">
            <label className="form-label small mb-1">Email</label>
            <input
              type="email"
              className="form-control"
              required
              placeholder="nombre@macro.com.ar"
              value={nuevo.email}
              onChange={(e) => setNuevo({ ...nuevo, email: e.target.value })}
            />
          </div>
          <div className="col-sm-4 col-lg-3">
            <label className="form-label small mb-1">Nombre o área (opcional)</label>
            <input
              className="form-control"
              maxLength={200}
              value={nuevo.nombre}
              onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })}
            />
          </div>
          <div className="col-auto">
            <button className="btn btn-primary">
              <i className="bi bi-plus-lg me-1" />
              Agregar
            </button>
          </div>
        </form>
      )}

      <div className="card">
        <table className="table mb-0 align-middle small">
          <thead className="table-light">
            <tr>
              <th>Email</th>
              <th>Nombre o área</th>
              <th>Recibe avisos</th>
              {esAdmin && <th />}
            </tr>
          </thead>
          <tbody>
            {datos.destinatarios.map((d) => (
              <tr key={d.id} className={d.activo ? undefined : "text-muted"}>
                <td className="fw-semibold">{d.email}</td>
                <td>{d.nombre ?? "—"}</td>
                <td>
                  {esAdmin ? (
                    <div className="form-check form-switch mb-0">
                      <input
                        className="form-check-input"
                        type="checkbox"
                        role="switch"
                        id={`activo-${d.id}`}
                        checked={d.activo}
                        onChange={(e) =>
                          accion(() => updateDestinatario(d.id, { activo: e.target.checked }), "No se pudo actualizar")
                        }
                      />
                      <label className="form-check-label" htmlFor={`activo-${d.id}`}>
                        {d.activo ? "Sí" : "Pausado"}
                      </label>
                    </div>
                  ) : d.activo ? (
                    "Sí"
                  ) : (
                    "Pausado"
                  )}
                </td>
                {esAdmin && (
                  <td className="text-end">
                    <button className="btn btn-sm btn-link text-danger" onClick={() => quitar(d)}>
                      Quitar
                    </button>
                  </td>
                )}
              </tr>
            ))}
            {datos.destinatarios.length === 0 && (
              <tr>
                <td colSpan={esAdmin ? 4 : 3} className="text-center text-muted py-4">
                  Todavía no hay destinatarios cargados.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
