import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import {
  addComentario,
  addContacto,
  getCaso,
  listComentarios,
  listTransiciones,
  reintentarJira,
  removeContacto,
  transicionarCaso,
  updateCaso,
} from "../api/casos";
import { ApiError } from "../api/client";
import type { Caso, CasoEstado, CasoTipo, Comentario, Transicion } from "../api/types";
import {
  ESTADO_BADGE_CLASS,
  ESTADO_LABELS,
  estadoConDetalle,
  formatGdld,
  SYNC_BADGE_CLASS,
  SYNC_LABELS,
  TIPO_LABELS,
  tipoLabel,
} from "../casos/labels";
import { AlertasDelCaso } from "../alertas/AlertasDelCaso";
import { Asignado } from "../casos/Asignado";
import { SelectorAsignado } from "../casos/SelectorAsignado";
import { CasoPentestsSection } from "../pentesting/CasoPentestsSection";
import { CuestionarioEmailSection } from "../threatModel/CuestionarioEmailSection";

function errorDetail(err: unknown, fallback: string): string {
  return err instanceof ApiError && typeof err.detail === "string" ? err.detail : fallback;
}

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
      .catch((err) => setError(errorDetail(err, "No se pudo cargar el caso")))
      .finally(() => setLoading(false));
  }

  useEffect(reload, [casoId]);

  if (loading && !caso) {
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

      <div className="d-flex justify-content-between align-items-center mb-3 gap-2 flex-wrap">
        <h1 className="h3 mb-0">{caso.nombre_proyecto}</h1>
        <span className={`badge fs-6 ${ESTADO_BADGE_CLASS[caso.estado]}`}>{estadoConDetalle(caso)}</span>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <JiraSection caso={caso} onChanged={setCaso} />

      <DatosSection caso={caso} onChanged={setCaso} />

      <EstadoSection caso={caso} onChanged={setCaso} />

      <ComentariosSection caso={caso} />

      <AlertasDelCaso casoId={caso.id} />

      <ContactosSection caso={caso} onChanged={reload} />

      <CasoPentestsSection casoId={caso.id} />

      <div className="card mb-3">
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

      <CuestionarioEmailSection caso={caso} />
    </>
  );
}

function JiraSection({ caso, onChanged }: { caso: Caso; onChanged: (caso: Caso) => void }) {
  const [error, setError] = useState<string | null>(null);
  const [asignando, setAsignando] = useState(false);
  const [enviando, setEnviando] = useState(false);

  if (caso.jira_sync_estado === null) {
    return (
      <p className="text-muted small mb-3">
        <i className="bi bi-info-circle me-1" />
        Caso anterior a la integración con Jira: no tiene ticket asociado.
      </p>
    );
  }

  async function handleReintentar() {
    setError(null);
    setEnviando(true);
    try {
      onChanged(await reintentarJira(caso.id));
    } catch (err) {
      setError(errorDetail(err, "No se pudo reintentar"));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="d-flex align-items-center gap-2 flex-wrap mb-3">
      {caso.jira_url ? (
        <a href={caso.jira_url} target="_blank" rel="noreferrer" className="btn btn-sm btn-outline-primary">
          <i className="bi bi-box-arrow-up-right me-1" />
          {caso.jira_issue_key}
        </a>
      ) : (
        <span className="text-muted small">Ticket de Jira en creación…</span>
      )}
      <span className={`badge ${SYNC_BADGE_CLASS[caso.jira_sync_estado]}`}>{SYNC_LABELS[caso.jira_sync_estado]}</span>
      {caso.origen === "jira" && <span className="badge text-bg-light border">Importado de Jira</span>}
      {caso.jira_issue_key && (
        <button
          type="button"
          className="asignado-boton"
          onClick={() => setAsignando(true)}
          title="Cambiar persona asignada"
        >
          <Asignado nombre={caso.jira_asignado_nombre} avatarUrl={caso.jira_asignado_avatar_url} />
          <i className="bi bi-pencil small text-muted" />
        </button>
      )}
      {asignando && (
        <SelectorAsignado
          caso={caso}
          onCerrar={() => setAsignando(false)}
          onAsignado={(actualizado) => {
            setAsignando(false);
            onChanged(actualizado);
          }}
        />
      )}
      {caso.jira_sync_estado === "error" && (
        <>
          <span className="small text-danger">{caso.jira_sync_error}</span>
          <button className="btn btn-sm btn-outline-danger" onClick={handleReintentar} disabled={enviando}>
            Reintentar
          </button>
        </>
      )}
      {error && <span className="small text-danger">{error}</span>}
    </div>
  );
}

function DatosSection({ caso, onChanged }: { caso: Caso; onChanged: (caso: Caso) => void }) {
  const [editando, setEditando] = useState(false);
  const [nombre, setNombre] = useState(caso.nombre_proyecto);
  const [gdld, setGdld] = useState(caso.gdld ?? "");
  const [empresa, setEmpresa] = useState(caso.empresa_responsable ?? "");
  const [tipo, setTipo] = useState<CasoTipo | "">(caso.tipo ?? "");
  const [error, setError] = useState<string | null>(null);

  function startEdit() {
    setNombre(caso.nombre_proyecto);
    setGdld(caso.gdld ?? "");
    setEmpresa(caso.empresa_responsable ?? "");
    setTipo(caso.tipo ?? "");
    setError(null);
    setEditando(true);
  }

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const updated = await updateCaso(caso.id, {
        nombre_proyecto: nombre,
        gdld: gdld || undefined,
        empresa_responsable: empresa || undefined,
        tipo: tipo || undefined,
      });
      onChanged(updated);
      setEditando(false);
    } catch (err) {
      setError(errorDetail(err, "No se pudieron guardar los datos"));
    }
  }

  if (editando) {
    return (
      <div className="card mb-3">
        <div className="card-body">
          <form onSubmit={handleSave} className="row g-2">
            <div className="col-md-6">
              <label className="form-label">Nombre del proyecto</label>
              <input
                className="form-control"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                required
                maxLength={200}
              />
            </div>
            <div className="col-md-6">
              <label className="form-label">GDLD</label>
              <input
                className="form-control"
                value={gdld}
                onChange={(e) => setGdld(e.target.value)}
                placeholder="Número"
              />
            </div>
            <div className="col-md-6">
              <label className="form-label">Empresa responsable</label>
              <input className="form-control" value={empresa} onChange={(e) => setEmpresa(e.target.value)} />
            </div>
            <div className="col-md-6">
              <label className="form-label">Tipo</label>
              <select className="form-select" value={tipo} onChange={(e) => setTipo(e.target.value as CasoTipo | "")}>
                <option value="">Sin definir</option>
                {Object.entries(TIPO_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            {caso.jira_sync_estado !== null && (
              <p className="small text-muted mb-0">El nombre y el GDLD también se actualizan en el ticket de Jira.</p>
            )}
            <div className="col-12 d-flex gap-2">
              <button type="submit" className="btn btn-primary btn-sm">
                Guardar
              </button>
              <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setEditando(false)}>
                Cancelar
              </button>
            </div>
            {error && <div className="alert alert-danger mt-2 mb-0 py-2">{error}</div>}
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="card mb-3">
      <div className="card-body">
        <div className="d-flex justify-content-between align-items-start">
          <dl className="row mb-0 flex-grow-1">
            <dt className="col-sm-3">Empresa responsable</dt>
            <dd className="col-sm-9">{caso.empresa_responsable ?? <span className="text-muted">Sin definir</span>}</dd>
            <dt className="col-sm-3">Tipo</dt>
            <dd className="col-sm-9">
              {caso.tipo ? tipoLabel(caso.tipo) : <span className="text-muted">Sin definir</span>}
            </dd>
            <dt className="col-sm-3">GDLD</dt>
            <dd className="col-sm-9">{formatGdld(caso.gdld) ?? "—"}</dd>
          </dl>
          <button className="btn btn-sm btn-outline-secondary" onClick={startEdit}>
            <i className="bi bi-pencil me-1" />
            Editar
          </button>
        </div>
      </div>
    </div>
  );
}

function EstadoSection({ caso, onChanged }: { caso: Caso; onChanged: (caso: Caso) => void }) {
  const [transiciones, setTransiciones] = useState<Transicion[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const vinculado = caso.jira_issue_key !== null;

  useEffect(() => {
    if (!vinculado) return;
    setTransiciones(null);
    setError(null);
    listTransiciones(caso.id)
      .then(setTransiciones)
      .catch((err) => setError(errorDetail(err, "No se pudieron consultar las transiciones en Jira")));
  }, [caso.id, caso.jira_status_nombre, vinculado]);

  async function handleTransicion(transicion: Transicion) {
    setError(null);
    setEnviando(true);
    try {
      onChanged(await transicionarCaso(caso.id, transicion.id));
    } catch (err) {
      setError(errorDetail(err, "No se pudo cambiar el estado"));
    } finally {
      setEnviando(false);
    }
  }

  async function handleEstadoLocal(estado: CasoEstado) {
    setError(null);
    try {
      onChanged(await updateCaso(caso.id, { estado }));
    } catch (err) {
      setError(errorDetail(err, "No se pudo cambiar el estado"));
    }
  }

  return (
    <div className="card mb-3">
      <div className="card-body">
        <h2 className="h5">Cambiar estado</h2>
        {caso.jira_sync_estado === null ? (
          // Caso que no está en Jira: se mueve libremente entre las columnas.
          <div className="d-flex gap-2 flex-wrap">
            {(Object.keys(ESTADO_LABELS) as CasoEstado[])
              .filter((estado) => estado !== caso.estado)
              .map((estado) => (
                <button
                  key={estado}
                  className="btn btn-outline-primary btn-sm"
                  onClick={() => handleEstadoLocal(estado)}
                >
                  → {ESTADO_LABELS[estado]}
                </button>
              ))}
          </div>
        ) : !vinculado ? (
          <p className="text-muted mb-0">El estado se podrá cambiar cuando el ticket esté creado en Jira.</p>
        ) : transiciones === null && !error ? (
          <div className="spinner-border spinner-border-sm text-primary" role="status">
            <span className="visually-hidden">Consultando Jira…</span>
          </div>
        ) : (
          <div className="d-flex gap-2 flex-wrap">
            {transiciones?.length === 0 && (
              <p className="text-muted mb-0">Jira no ofrece transiciones desde este estado.</p>
            )}
            {transiciones?.map((t) => (
              <button
                key={t.id}
                className="btn btn-outline-primary btn-sm"
                onClick={() => handleTransicion(t)}
                disabled={enviando}
                title={`Pasa a "${t.destino}" (${ESTADO_LABELS[t.estado]})`}
              >
                {t.nombre} → {t.destino}
              </button>
            ))}
          </div>
        )}
        {error && <div className="alert alert-danger mt-2 mb-0 py-2">{error}</div>}
      </div>
    </div>
  );
}

function ComentariosSection({ caso }: { caso: Caso }) {
  const [comentarios, setComentarios] = useState<Comentario[]>([]);
  const [cuerpo, setCuerpo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    listComentarios(caso.id)
      .then(setComentarios)
      .catch((err) => setError(errorDetail(err, "No se pudieron cargar los comentarios")));
  }, [caso.id, caso.updated_at]);

  async function handleAdd(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      const nuevo = await addComentario(caso.id, cuerpo);
      setComentarios((prev) => [...prev, nuevo]);
      setCuerpo("");
    } catch (err) {
      setError(errorDetail(err, "No se pudo agregar el comentario"));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="card mb-3">
      <div className="card-body">
        <h2 className="h5">Comentarios</h2>
        <ul className="list-group list-group-flush mb-3">
          {comentarios.map((c) => (
            <li key={c.id} className="list-group-item px-0">
              <div className="d-flex gap-2 align-items-center small text-muted mb-1 flex-wrap">
                <strong className="text-body">{c.autor_nombre}</strong>
                <span>{new Date(c.fecha).toLocaleString("es-AR")}</span>
                <span className="badge text-bg-light border">{c.origen === "jira" ? "Jira" : "Plataforma"}</span>
                {c.publico ? (
                  <span className="badge text-bg-warning">Visible para el solicitante</span>
                ) : (
                  <span className="badge text-bg-light border">Interno</span>
                )}
              </div>
              <div style={{ whiteSpace: "pre-wrap" }}>{c.cuerpo}</div>
            </li>
          ))}
          {comentarios.length === 0 && <li className="list-group-item px-0 text-muted">Sin comentarios.</li>}
        </ul>
        <form onSubmit={handleAdd}>
          <textarea
            className="form-control mb-2"
            rows={3}
            placeholder="Escribí un comentario"
            value={cuerpo}
            onChange={(e) => setCuerpo(e.target.value)}
            required
            maxLength={10000}
          />
          <div className="d-flex align-items-center gap-2">
            <button type="submit" className="btn btn-outline-primary btn-sm" disabled={enviando}>
              Comentar
            </button>
            {caso.jira_sync_estado !== null && (
              <span className="small text-muted">Se publica en Jira como comentario interno.</span>
            )}
          </div>
        </form>
        {error && <div className="alert alert-danger mt-2 mb-0 py-2">{error}</div>}
      </div>
    </div>
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
      setError(errorDetail(err, "No se pudo agregar el contacto"));
    }
  }

  async function handleRemove(contactoId: string) {
    try {
      await removeContacto(caso.id, contactoId);
      onChanged();
    } catch (err) {
      setError(errorDetail(err, "No se pudo eliminar el contacto"));
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
          {caso.contactos.length === 0 && <li className="list-group-item px-0 text-muted">Sin contactos cargados.</li>}
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
