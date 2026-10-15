import { useRef, useState, type DragEvent } from "react";
import { Link } from "react-router-dom";
import { listTransiciones, transicionarCaso, updateCaso } from "../api/casos";
import { ApiError } from "../api/client";
import type { Caso, CasoEstado, Transicion } from "../api/types";
import { Asignado } from "./Asignado";
import { SelectorAsignado } from "./SelectorAsignado";
import { ESTADO_LABELS, formatGdld, tipoLabel } from "./labels";

const COLUMNAS = Object.keys(ESTADO_LABELS) as CasoEstado[];

function errorDetail(err: unknown, fallback: string): string {
  return err instanceof ApiError && typeof err.detail === "string" ? err.detail : fallback;
}

/** Un caso vinculado a Jira se mueve con las transiciones de su workflow; uno
 * anterior a la integración, libremente; uno cuyo ticket todavía se está
 * creando, no se puede mover. */
function modo(caso: Caso): "jira" | "libre" | "bloqueado" {
  if (caso.jira_sync_estado === null) return "libre";
  return caso.jira_issue_key ? "jira" : "bloqueado";
}

interface Arrastre {
  caso: Caso;
  /** Pedido de transiciones en curso; se resuelve también si se suelta antes. */
  transiciones: Promise<Transicion[]> | null;
  /** Columnas válidas una vez que llegan las transiciones (null = cargando). */
  validas: Set<CasoEstado> | null;
}

interface Eleccion {
  caso: Caso;
  opciones: Transicion[];
  titulo: string;
}

export function CasosKanban({ casos, onChanged }: { casos: Caso[]; onChanged: (caso: Caso) => void }) {
  const [arrastre, setArrastre] = useState<Arrastre | null>(null);
  const [sobre, setSobre] = useState<CasoEstado | null>(null);
  const [moviendo, setMoviendo] = useState<string | null>(null);
  const [eleccion, setEleccion] = useState<Eleccion | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [asignando, setAsignando] = useState<Caso | null>(null);
  // El último arrastre iniciado: evita aplicar transiciones de uno anterior.
  const arrastreActual = useRef<string | null>(null);

  const porColumna = new Map<CasoEstado, Caso[]>(COLUMNAS.map((c) => [c, []]));
  for (const caso of casos) porColumna.get(caso.estado)?.push(caso);
  for (const lista of porColumna.values()) lista.sort((a, b) => b.updated_at.localeCompare(a.updated_at));

  function handleDragStart(event: DragEvent, caso: Caso) {
    if (modo(caso) === "bloqueado" || moviendo) {
      event.preventDefault();
      return;
    }
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", caso.id);
    setAviso(null);
    arrastreActual.current = caso.id;

    if (modo(caso) === "libre") {
      setArrastre({
        caso,
        transiciones: null,
        validas: new Set(COLUMNAS.filter((c) => c !== caso.estado)),
      });
      return;
    }
    const pedido = listTransiciones(caso.id);
    setArrastre({ caso, transiciones: pedido, validas: null });
    pedido
      .then((ts) => {
        if (arrastreActual.current !== caso.id) return;
        const validas = new Set(ts.map((t) => t.estado).filter((e) => e !== caso.estado));
        setArrastre((prev) => (prev && prev.caso.id === caso.id ? { ...prev, validas } : prev));
      })
      .catch(() => {
        /* el error se muestra al soltar */
      });
  }

  function handleDragEnd() {
    setArrastre(null);
    setSobre(null);
  }

  function handleDragOver(event: DragEvent, columna: CasoEstado) {
    if (!arrastre || columna === arrastre.caso.estado) return;
    // Mientras cargan las transiciones se permite soltar; al soltar se valida.
    if (arrastre.validas && !arrastre.validas.has(columna)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    if (sobre !== columna) setSobre(columna);
  }

  async function handleDrop(event: DragEvent, columna: CasoEstado) {
    event.preventDefault();
    const actual = arrastre;
    setArrastre(null);
    setSobre(null);
    if (!actual || columna === actual.caso.estado) return;
    const { caso } = actual;

    if (modo(caso) === "libre") {
      await ejecutar(caso, () => updateCaso(caso.id, { estado: columna }));
      return;
    }

    let transiciones: Transicion[];
    try {
      transiciones = await (actual.transiciones ?? listTransiciones(caso.id));
    } catch (err) {
      setAviso(errorDetail(err, "No se pudieron consultar las transiciones en Jira"));
      return;
    }
    const opciones = transiciones.filter((t) => t.estado === columna);
    if (opciones.length === 0) {
      const destinos = [...new Set(transiciones.map((t) => ESTADO_LABELS[t.estado]))];
      setAviso(
        `Jira no permite mover ${caso.jira_issue_key} de "${caso.jira_status_nombre ?? ESTADO_LABELS[caso.estado]}" ` +
          `a ${ESTADO_LABELS[columna]}.` +
          (destinos.length ? ` Desde acá puede ir a: ${destinos.join(", ")}.` : " No tiene transiciones disponibles."),
      );
      return;
    }
    if (opciones.length === 1) {
      await transicionar(caso, opciones[0]);
      return;
    }
    setEleccion({
      caso,
      opciones,
      titulo: `Mover a ${ESTADO_LABELS[columna]}`,
    });
  }

  /** Alternativa al arrastre (teclado, pantallas táctiles). */
  async function handleMover(caso: Caso) {
    setAviso(null);
    if (modo(caso) === "libre") {
      setEleccion({
        caso,
        titulo: "Mover a",
        opciones: COLUMNAS.filter((c) => c !== caso.estado).map((c) => ({
          id: c,
          nombre: ESTADO_LABELS[c],
          destino: ESTADO_LABELS[c],
          estado: c,
        })),
      });
      return;
    }
    try {
      const opciones = await listTransiciones(caso.id);
      if (opciones.length === 0) {
        setAviso(`Jira no ofrece transiciones para ${caso.jira_issue_key} desde "${caso.jira_status_nombre}".`);
        return;
      }
      setEleccion({ caso, opciones, titulo: "Mover a" });
    } catch (err) {
      setAviso(errorDetail(err, "No se pudieron consultar las transiciones en Jira"));
    }
  }

  async function handleElegir(transicion: Transicion) {
    const actual = eleccion;
    setEleccion(null);
    if (!actual) return;
    if (modo(actual.caso) === "libre") {
      await ejecutar(actual.caso, () => updateCaso(actual.caso.id, { estado: transicion.estado }));
    } else {
      await transicionar(actual.caso, transicion);
    }
  }

  function transicionar(caso: Caso, transicion: Transicion) {
    return ejecutar(caso, () => transicionarCaso(caso.id, transicion.id));
  }

  async function ejecutar(caso: Caso, accion: () => Promise<Caso>) {
    setMoviendo(caso.id);
    try {
      onChanged(await accion());
    } catch (err) {
      setAviso(errorDetail(err, "No se pudo mover el caso"));
    } finally {
      setMoviendo(null);
    }
  }

  return (
    <>
      {aviso && (
        <div className="alert alert-warning d-flex justify-content-between align-items-start" role="alert">
          <span>{aviso}</span>
          <button type="button" className="btn-close" aria-label="Cerrar" onClick={() => setAviso(null)} />
        </div>
      )}

      <div className="kanban">
        {COLUMNAS.map((columna) => {
          const lista = porColumna.get(columna) ?? [];
          const esOrigen = arrastre?.caso.estado === columna;
          const valida = !!arrastre && !esOrigen && (arrastre.validas === null || arrastre.validas.has(columna));
          const clases = [
            "kanban-columna",
            `kanban-columna-${columna}`,
            arrastre && !esOrigen && !valida ? "kanban-columna-invalida" : "",
            valida ? "kanban-columna-valida" : "",
            sobre === columna ? "kanban-columna-sobre" : "",
          ].join(" ");
          return (
            <section
              key={columna}
              className={clases}
              aria-label={ESTADO_LABELS[columna]}
              onDragOver={(e) => handleDragOver(e, columna)}
              onDragLeave={() => sobre === columna && setSobre(null)}
              onDrop={(e) => handleDrop(e, columna)}
            >
              <header className="kanban-columna-titulo">
                <span>{ESTADO_LABELS[columna]}</span>
                <span className="badge rounded-pill text-bg-light border">{lista.length}</span>
              </header>
              <div className="kanban-columna-cuerpo">
                {lista.map((caso) => (
                  <Tarjeta
                    key={caso.id}
                    caso={caso}
                    moviendo={moviendo === caso.id}
                    arrastrando={arrastre?.caso.id === caso.id}
                    onDragStart={(e) => handleDragStart(e, caso)}
                    onDragEnd={handleDragEnd}
                    onMover={() => handleMover(caso)}
                    onAsignar={() => setAsignando(caso)}
                  />
                ))}
                {lista.length === 0 && <p className="kanban-vacia">Sin casos</p>}
              </div>
            </section>
          );
        })}
      </div>

      {asignando && (
        <SelectorAsignado
          caso={asignando}
          onCerrar={() => setAsignando(null)}
          onAsignado={(actualizado) => {
            setAsignando(null);
            onChanged(actualizado);
          }}
        />
      )}

      {eleccion && (
        <ElegirTransicion eleccion={eleccion} onElegir={handleElegir} onCancelar={() => setEleccion(null)} />
      )}
    </>
  );
}

function Tarjeta({
  caso,
  moviendo,
  arrastrando,
  onDragStart,
  onDragEnd,
  onMover,
  onAsignar,
}: {
  caso: Caso;
  moviendo: boolean;
  arrastrando: boolean;
  onDragStart: (event: DragEvent) => void;
  onDragEnd: () => void;
  onMover: () => void;
  onAsignar: () => void;
}) {
  const bloqueado = modo(caso) === "bloqueado";
  const statusDistinto =
    caso.jira_status_nombre && caso.jira_status_nombre.toLowerCase() !== ESTADO_LABELS[caso.estado].toLowerCase();

  return (
    <article
      className={`kanban-tarjeta ${arrastrando ? "kanban-tarjeta-arrastrando" : ""} ${bloqueado ? "kanban-tarjeta-bloqueada" : ""}`}
      draggable={!bloqueado && !moviendo}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      title={bloqueado ? "El ticket todavía se está creando en Jira" : undefined}
    >
      <Link to={`/casos/${caso.id}`} className="kanban-tarjeta-titulo" draggable={false}>
        {caso.nombre_proyecto}
      </Link>
      <div className="kanban-tarjeta-meta">
        {caso.gdld && <span>{formatGdld(caso.gdld)}</span>}
        {caso.empresa_responsable && <span>{caso.empresa_responsable}</span>}
        {caso.tipo && <span>{tipoLabel(caso.tipo)}</span>}
      </div>
      {statusDistinto && <div className="kanban-tarjeta-status">{caso.jira_status_nombre}</div>}
      {caso.jira_issue_key && (
        <div className="kanban-tarjeta-asignado">
          <button
            type="button"
            className="asignado-boton"
            onClick={onAsignar}
            draggable={false}
            title="Cambiar persona asignada"
          >
            <Asignado nombre={caso.jira_asignado_nombre} avatarUrl={caso.jira_asignado_avatar_url} />
          </button>
        </div>
      )}
      <footer className="kanban-tarjeta-pie">
        {caso.jira_url ? (
          <a href={caso.jira_url} target="_blank" rel="noreferrer" draggable={false} className="kanban-tarjeta-key">
            <i className="bi bi-box-arrow-up-right me-1" />
            {caso.jira_issue_key}
          </a>
        ) : caso.jira_sync_estado === null ? (
          <span className="text-muted">Sin Jira</span>
        ) : (
          <span className="text-muted">Creando ticket…</span>
        )}
        <span className="d-flex align-items-center gap-2">
          {caso.jira_sync_estado === "error" && (
            <i
              className="bi bi-exclamation-triangle-fill text-danger"
              title={caso.jira_sync_error ?? "Error de sincronización"}
            />
          )}
          {caso.jira_sync_estado === "pendiente" && caso.jira_issue_key && (
            <i className="bi bi-arrow-repeat text-secondary" title="Cambios pendientes de enviar a Jira" />
          )}
          {moviendo ? (
            <span className="spinner-border spinner-border-sm text-primary" role="status">
              <span className="visually-hidden">Moviendo…</span>
            </span>
          ) : (
            <button
              type="button"
              className="btn btn-link btn-sm p-0 kanban-tarjeta-mover"
              onClick={onMover}
              disabled={bloqueado}
              aria-label={`Mover ${caso.nombre_proyecto}`}
              title="Mover"
            >
              <i className="bi bi-arrow-left-right" />
            </button>
          )}
        </span>
      </footer>
    </article>
  );
}

function ElegirTransicion({
  eleccion,
  onElegir,
  onCancelar,
}: {
  eleccion: Eleccion;
  onElegir: (transicion: Transicion) => void;
  onCancelar: () => void;
}) {
  const { caso } = eleccion;
  return (
    <>
      <div className="modal d-block" tabIndex={-1} role="dialog" aria-modal="true" onClick={onCancelar}>
        <div className="modal-dialog modal-dialog-centered" onClick={(e) => e.stopPropagation()}>
          <div className="modal-content">
            <div className="modal-header">
              <h2 className="modal-title h5">{eleccion.titulo}</h2>
              <button type="button" className="btn-close" aria-label="Cerrar" onClick={onCancelar} />
            </div>
            <div className="modal-body">
              <p className="mb-3">
                <strong>{caso.nombre_proyecto}</strong>
                {caso.jira_issue_key && <span className="text-muted"> · {caso.jira_issue_key}</span>}
                <br />
                <span className="small text-muted">
                  Hoy: {ESTADO_LABELS[caso.estado]}
                  {caso.jira_status_nombre && ` · ${caso.jira_status_nombre}`}
                </span>
              </p>
              <div className="d-grid gap-2">
                {eleccion.opciones.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className="btn btn-outline-primary text-start"
                    onClick={() => onElegir(t)}
                  >
                    {t.nombre === t.destino ? t.nombre : `${t.nombre} → ${t.destino}`}
                    <span className="small text-muted d-block">Columna: {ESTADO_LABELS[t.estado]}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="modal-backdrop show" />
    </>
  );
}
