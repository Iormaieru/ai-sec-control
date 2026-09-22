import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { addContacto, getCaso, removeContacto, updateCaso } from "../api/casos";
import { ApiError } from "../api/client";
import type { Caso, CasoEstado } from "../api/types";
import { ALLOWED_TRANSITIONS, ESTADO_LABELS, TIPO_LABELS } from "../casos/labels";

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

  if (loading) return <p>Cargando…</p>;
  if (!caso) return <p className="error">{error ?? "Caso no encontrado"}</p>;

  return (
    <main>
      <p>
        <Link to="/casos">← Volver a casos</Link>
      </p>
      <header className="page-header">
        <h1>{caso.nombre_proyecto}</h1>
        <span className={`badge badge-${caso.estado}`}>{ESTADO_LABELS[caso.estado]}</span>
      </header>

      <dl className="caso-info">
        <dt>Empresa responsable</dt>
        <dd>{caso.empresa_responsable}</dd>
        <dt>Tipo</dt>
        <dd>{TIPO_LABELS[caso.tipo]}</dd>
        <dt>GDLD</dt>
        <dd>{caso.gdld ?? "—"}</dd>
      </dl>

      {error && <p className="error">{error}</p>}

      <section>
        <h2>Cambiar estado</h2>
        <div className="transition-buttons">
          {ALLOWED_TRANSITIONS[caso.estado].length === 0 && <p>Estado final, sin más transiciones.</p>}
          {ALLOWED_TRANSITIONS[caso.estado].map((estado) => (
            <button key={estado} onClick={() => handleTransition(estado)}>
              → {ESTADO_LABELS[estado]}
            </button>
          ))}
        </div>
      </section>

      <ContactosSection caso={caso} onChanged={reload} />

      <section>
        <h2>Modelado de amenazas</h2>
        <Link to={`/casos/${caso.id}/preguntas`}>Ir a preguntas y score →</Link>
      </section>
    </main>
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
    <section>
      <h2>Contactos</h2>
      <ul className="contactos-list">
        {caso.contactos.map((contacto) => (
          <li key={contacto.id}>
            {contacto.nombre}
            {contacto.rol && ` — ${contacto.rol}`}
            {contacto.email && ` (${contacto.email})`}
            <button onClick={() => handleRemove(contacto.id)}>Quitar</button>
          </li>
        ))}
        {caso.contactos.length === 0 && <li>Sin contactos cargados.</li>}
      </ul>
      <form onSubmit={handleAdd} className="contacto-form">
        <input placeholder="Nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} required />
        <input placeholder="Email (opcional)" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input placeholder="Rol (opcional)" value={rol} onChange={(e) => setRol(e.target.value)} />
        <button type="submit">Agregar contacto</button>
      </form>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
