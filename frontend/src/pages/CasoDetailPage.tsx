import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { addContacto, getCaso, removeContacto, updateCaso } from "../api/casos";
import { ApiError } from "../api/client";
import type { Caso, CasoEstado } from "../api/types";
import { ALLOWED_TRANSITIONS, ESTADO_BADGE_CLASS, ESTADO_LABELS, TIPO_LABELS } from "../casos/labels";
import { PentestResultadosSection } from "./PentestResultadosSection";

export function CasoDetailPage() {
  const { casoId } = useParams<{ casoId: string }>();
  const [caso, setCaso] = useState<Caso | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  function reload() {
    if (!casoId) return;
    setLoading(true);
    getCaso(casoId)
      .then(setCaso)
      .catch((err) => setError(err instanceof ApiError ? err.detail : "No se pudo cargar el caso"))
      .finally(() => setLoading(false));
  }

  useEffect(reload, [casoId]);

  async function handleTransition(nuevoEstado: CasoEstado) {
    if (!casoId) return;
    setError(null);
    try {
      const updated = await updateCaso(casoId, { estado: nuevoEstado });
      setCaso(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "No se pudo cambiar el estado");
    }
  }

  if (loading) {
    return (
      <div className="spinner-border text-primary" role="status">
        <span className="visually-hidden">Cargando…</span>
      </div>
    );
  }
  if (!caso) return <div className="alert alert-danger">{error ?? "Caso no encontrado"}</div>;

  return (
    <>
      <Link to="/casos" className="d-inline-flex align-items-center gap-1 mb-3 text-decoration-none">
        <i className="bi bi-arrow-left" /> Volver a casos
      </Link>

      <div className="d-flex justify-content-between align-items-center mb-3">
        <h1 className="h3 mb-0">{caso.nombre_proyecto}</h1>
        <span className={`badge fs-6 ${ESTADO_BADGE_CLASS[caso.estado]}`}>{ESTADO_LABELS[caso.estado]}</span>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="card mb-3">
        <div className="card-body">
          <dl className="row mb-0">
            <dt className="col-sm-3">Empresa responsable</dt>
            <dd className="col-sm-9">{caso.empresa_responsable}</dd>
            <dt className="col-sm-3">Tipo</dt>
            <dd className="col-sm-9">{TIPO_LABELS[caso.tipo]}</dd>
            <dt className="col-sm-3">GDLD</dt>
            <dd className="col-sm-9">{caso.gdld ?? "—"}</dd>
          </dl>
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-body">
          <h2 className="h5">Cambiar estado</h2>
          <div className="d-flex gap-2 flex-wrap">
            {ALLOWED_TRANSITIONS[caso.estado].length === 0 && (
              <p className="text-muted mb-0">Estado final, sin más transiciones.</p>
            )}
            {ALLOWED_TRANSITIONS[caso.estado].map((estado) => (
              <button
                key={estado}
                className="btn btn-outline-primary btn-sm"
                onClick={() => handleTransition(estado)}
              >
                → {ESTADO_LABELS[estado]}
              </button>
            ))}
          </div>
        </div>
      </div>

      <ContactosSection caso={caso} onChanged={reload} />

      <PentestResultadosSection casoId={caso.id} />

      <div className="card">
        <div className="card-body d-flex justify-content-between align-items-center">
          <div>
            <h2 className="h5 mb-1">Modelado de amenazas</h2>
            <p className="text-muted mb-0">Selección de preguntas, respuestas y score de riesgo.</p>
          </div>
          <Link to={`/casos/${caso.id}/preguntas`} className="btn btn-primary">
            Ir a preguntas y score <i className="bi bi-arrow-right ms-1" />
          </Link>
        </div>
      </div>
    </>
  );
}

function ContactosSection({ caso, onChanged }: { caso: Caso; onChanged: () => void }) {
  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [rol, setRol] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleAdd(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await addContacto(caso.id, { nombre, email: email || null, rol: rol || null });
      setNombre("");
      setEmail("");
      setRol("");
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "No se pudo agregar el contacto");
    }
  }

  async function handleRemove(contactoId: string) {
    try {
      await removeContacto(caso.id, contactoId);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "No se pudo eliminar el contacto");
    }
  }

  return (
    <div className="card mb-3">
      <div className="card-body">
        <h2 className="h5">Contactos</h2>
        <ul className="list-group list-group-flush mb-3">
          {caso.contactos.map((contacto) => (
            <li key={contacto.id} className="list-group-item d-flex justify-content-between align-items-center px-0">
              <span>
                {contacto.nombre}
                {contacto.rol && <span className="text-muted"> — {contacto.rol}</span>}
                {contacto.email && <span className="text-muted"> ({contacto.email})</span>}
              </span>
              <button className="btn btn-sm btn-outline-danger" onClick={() => handleRemove(contacto.id)}>
                Quitar
              </button>
            </li>
          ))}
          {caso.contactos.length === 0 && (
            <li className="list-group-item px-0 text-muted">Sin contactos cargados.</li>
          )}
        </ul>
        <form onSubmit={handleAdd} className="row g-2 align-items-end">
          <div className="col-auto">
            <input
              className="form-control"
              placeholder="Nombre"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              required
            />
          </div>
          <div className="col-auto">
            <input
              className="form-control"
              placeholder="Email (opcional)"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="col-auto">
            <input
              className="form-control"
              placeholder="Rol (opcional)"
              value={rol}
              onChange={(e) => setRol(e.target.value)}
            />
          </div>
          <div className="col-auto">
            <button type="submit" className="btn btn-outline-primary">
              Agregar contacto
            </button>
          </div>
        </form>
        {error && <div className="alert alert-danger mt-2 mb-0 py-2">{error}</div>}
      </div>
    </div>
  );
}
