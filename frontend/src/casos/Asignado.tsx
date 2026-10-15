import { useState } from "react";
import { colorAvatar, iniciales, nombreCorto } from "./labels";

/** Persona asignada al ticket en Jira: su foto de perfil (o, si no carga,
 * un avatar con iniciales) y, salvo en modo compacto, el nombre. */
export function Asignado({
  nombre,
  avatarUrl = null,
  compacto = false,
}: {
  nombre: string | null;
  avatarUrl?: string | null;
  compacto?: boolean;
}) {
  const [fotoRota, setFotoRota] = useState(false);

  if (!nombre) {
    return (
      <span className="asignado asignado-vacio" title="Sin asignar">
        <span className="asignado-avatar">
          <i className="bi bi-person" />
        </span>
        {!compacto && <span className="asignado-nombre">Sin asignar</span>}
      </span>
    );
  }
  return (
    <span className="asignado" title={`Asignado a ${nombre}`}>
      {avatarUrl && !fotoRota ? (
        <img
          className="asignado-avatar asignado-foto"
          src={avatarUrl}
          alt=""
          loading="lazy"
          referrerPolicy="no-referrer"
          draggable={false}
          onError={() => setFotoRota(true)}
        />
      ) : (
        <span className="asignado-avatar" style={{ backgroundColor: colorAvatar(nombre) }} aria-hidden="true">
          {iniciales(nombre)}
        </span>
      )}
      <span className={compacto ? "visually-hidden" : "asignado-nombre"}>{compacto ? nombre : nombreCorto(nombre)}</span>
    </span>
  );
}
