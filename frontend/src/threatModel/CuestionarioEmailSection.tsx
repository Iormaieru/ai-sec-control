import { useEffect, useState } from "react";
import { ApiError } from "../api/client";
import { enviarCuestionario, listInvitaciones } from "../api/cuestionarios";
import type { Caso, Invitacion, InvitacionEstado } from "../api/types";

const ESTADO_INVITACION: Record<InvitacionEstado, { label: string; badge: string }> = {
  enviada: { label: "Enviado", badge: "text-bg-secondary" },
  abierta: { label: "Abierto", badge: "text-bg-info" },
  respondida: { label: "Respondido", badge: "text-bg-success" },
  anulada: { label: "Reemplazado", badge: "text-bg-light" },
};

function fecha(valor: string | null): string {
  return valor ? new Date(valor).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" }) : "—";
}

/** Envío del cuestionario de modelado de amenazas por email: cada contacto
 * recibe un enlace propio a un formulario público, y lo que responde se
 * carga solo en las preguntas del caso. */
export function CuestionarioEmailSection({ caso }: { caso: Caso }) {
  const [invitaciones, setInvitaciones] = useState<Invitacion[]>([]);
  const [seleccionados, setSeleccionados] = useState<Set<string>>(new Set());
  const [enlaces, setEnlaces] = useState<Invitacion[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const conEmail = caso.contactos.filter((c) => c.email);

  function reload() {
    listInvitaciones(caso.id)
      .then(setInvitaciones)
      .catch((err) => setError(err instanceof ApiError ? err.detail : "No se pudieron cargar los envíos"));
  }

  useEffect(reload, [caso.id]);

  function toggle(contactoId: string) {
    setSeleccionados((prev) => {
      const next = new Set(prev);
      if (next.has(contactoId)) next.delete(contactoId);
      else next.add(contactoId);
      return next;
    });
  }

  async function handleEnviar() {
    setError(null);
    setEnviando(true);
    try {
      const creadas = await enviarCuestionario(caso.id, [...seleccionados]);
      setEnlaces(creadas.filter((i) => i.enlace));
      setSeleccionados(new Set());
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "No se pudo enviar el cuestionario");
      reload();
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="card mb-3">
      <div className="card-body">
        <h2 className="h5 mb-1">Cuestionario por email</h2>
        <p className="text-muted small">
          Cada contacto recibe un enlace personal a un formulario con las preguntas pendientes del caso. Lo que
          responde se carga solo en el modelado de amenazas, sin pisar lo que ya respondió el equipo. Reenviar a un
          contacto invalida su enlace anterior.
        </p>

        {conEmail.length === 0 ? (
          <p className="text-muted mb-0">Agregá un contacto con email para poder enviar el cuestionario.</p>
        ) : (
          <div className="d-flex flex-wrap align-items-center gap-3">
            {conEmail.map((contacto) => (
              <label
                key={contacto.id}
                className={`opcion-check${seleccionados.has(contacto.id) ? " opcion-check--activa" : ""}`}
              >
                <input
                  className="form-check-input"
                  type="checkbox"
                  checked={seleccionados.has(contacto.id)}
                  onChange={() => toggle(contacto.id)}
                />
                <span>
                  {contacto.nombre} <span className="text-muted">({contacto.email})</span>
                </span>
              </label>
            ))}
            <button
              className="btn btn-primary btn-sm"
              onClick={handleEnviar}
              disabled={seleccionados.size === 0 || enviando}
            >
              <i className="bi bi-envelope me-1" />
              {enviando ? "Enviando…" : "Enviar cuestionario"}
            </button>
          </div>
        )}

        {error && <div className="alert alert-danger mt-3 mb-0 py-2">{error}</div>}

        {enlaces.length > 0 && (
          <div className="alert alert-warning mt-3 mb-0">
            <p className="mb-2 small">
              <strong>El envío de emails no está configurado</strong> (modo desarrollo). Copiá el enlace y mandalo a
              mano — no se vuelve a mostrar.
            </p>
            {enlaces.map((inv) => (
              <div key={inv.id} className="input-group input-group-sm mb-1">
                <span className="input-group-text">{inv.contacto_nombre}</span>
                <input className="form-control" readOnly value={inv.enlace ?? ""} onFocus={(e) => e.target.select()} />
                <button
                  className="btn btn-outline-secondary"
                  onClick={() => navigator.clipboard.writeText(inv.enlace ?? "")}
                  title="Copiar"
                >
                  <i className="bi bi-clipboard" />
                </button>
              </div>
            ))}
          </div>
        )}

        {invitaciones.length > 0 && (
          <div className="table-responsive mt-3">
            <table className="table table-sm align-middle mb-0">
              <thead className="table-light">
                <tr>
                  <th>Contacto</th>
                  <th>Estado</th>
                  <th>Enviado</th>
                  <th>Respondido</th>
                  <th>Vence</th>
                </tr>
              </thead>
              <tbody>
                {invitaciones.map((inv) => {
                  const estado = ESTADO_INVITACION[inv.estado];
                  return (
                    <tr key={inv.id} className={inv.estado === "anulada" ? "text-muted" : undefined}>
                      <td>
                        {inv.contacto_nombre} <span className="text-muted small">({inv.email})</span>
                      </td>
                      <td>
                        <span className={`badge ${inv.vencida ? "text-bg-warning" : estado.badge}`}>
                          {inv.vencida ? "Vencido" : estado.label}
                        </span>
                      </td>
                      <td>{fecha(inv.created_at)}</td>
                      <td>{fecha(inv.respondida_at)}</td>
                      <td>{inv.estado === "respondida" || inv.estado === "anulada" ? "—" : fecha(inv.expira_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
