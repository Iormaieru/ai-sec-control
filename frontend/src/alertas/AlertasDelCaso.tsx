import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listAlertas } from "../api/alertas";
import type { Alerta } from "../api/types";
import { ESTADO_BADGE, ESTADO_LABELS, SEVERIDAD_BADGE, SEVERIDAD_LABELS, fechaHora } from "./labels";

/** Alertas de Netskope vinculadas a un caso (evidencia de uso real). */
export function AlertasDelCaso({ casoId }: { casoId: string }) {
  const [alertas, setAlertas] = useState<Alerta[]>([]);

  useEffect(() => {
    listAlertas({ caso_id: casoId })
      .then(setAlertas)
      .catch(() => setAlertas([]));
  }, [casoId]);

  if (alertas.length === 0) return null;
  return (
    <div className="card mb-3">
      <div className="card-body">
        <h2 className="h5">
          <i className="bi bi-bell me-2" />
          Alertas de Netskope
        </h2>
        <ul className="list-group list-group-flush small">
          {alertas.map((a) => (
            <li key={a.id} className="list-group-item px-0 d-flex flex-wrap gap-2 align-items-center">
              <span className={`badge ${SEVERIDAD_BADGE[a.severidad]}`}>{SEVERIDAD_LABELS[a.severidad]}</span>
              <Link to={`/alertas?alerta=${a.id}`} className="fw-semibold">
                {a.app}
              </Link>
              <span>{a.usuario}</span>
              <span className="text-muted">
                {a.cantidad_eventos} eventos · última {fechaHora(a.ultima_vez)}
              </span>
              <span className={`badge ms-auto ${ESTADO_BADGE[a.estado]}`}>{ESTADO_LABELS[a.estado]}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
