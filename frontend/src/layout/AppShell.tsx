import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { getResumenAlertas } from "../api/alertas";
import logo from "../assets/logo-aisec.jpeg";
import { useAuth } from "../auth/AuthContext";

interface NavLeaf {
  to: string;
  label: string;
  icon: string;
  disabled?: boolean;
  /** Muestra al lado la cantidad de pendientes de ese sector. */
  contador?: "alertas";
}

interface NavGroup {
  // Prefijo de ruta del módulo: el grupo se abre solo si la ruta actual cae adentro.
  base: string;
  label: string;
  icon: string;
  children: NavLeaf[];
}

type NavItem = NavLeaf | NavGroup;

const NAV_ITEMS: NavItem[] = [
  { to: "/casos", label: "Casos", icon: "bi-folder2-open" },
  {
    base: "/pentesting",
    label: "Pentesting",
    icon: "bi-bug",
    children: [
      { to: "/pentesting/gestion", label: "Gestión", icon: "bi-clipboard-check" },
      { to: "/pentesting/estandares", label: "Estándares", icon: "bi-journal-text" },
      { to: "/pentesting/herramientas", label: "Herramientas", icon: "bi-tools" },
    ],
  },
  { to: "/alertas", label: "Alertas", icon: "bi-bell", contador: "alertas" },
  {
    base: "/dashboards",
    label: "Dashboards",
    icon: "bi-graph-up",
    children: [
      { to: "/dashboards/general", label: "General", icon: "bi-speedometer2" },
      { to: "/dashboards/seguridad-ia", label: "Seguridad de IA", icon: "bi-shield-lock" },
    ],
  },
];

/** Alertas nuevas, para el contador del menú (se actualiza cada minuto). */
function useAlertasNuevas(): number {
  const [nuevas, setNuevas] = useState(0);
  useEffect(() => {
    const actualizar = () =>
      getResumenAlertas()
        .then((r) => setNuevas(r.nuevas))
        .catch(() => undefined);
    actualizar();
    const timer = setInterval(actualizar, 60000);
    return () => clearInterval(timer);
  }, []);
  return nuevas;
}

function isGroup(item: NavItem): item is NavGroup {
  return "children" in item;
}

function SidebarLink({ item, sub, contador }: { item: NavLeaf; sub?: boolean; contador?: number }) {
  const className = `sidebar-link${sub ? " sidebar-sublink" : ""}`;
  if (item.disabled) {
    return (
      <span className={`${className} disabled`} title="Próximamente">
        <i className={`bi ${item.icon}`} />
        {item.label}
      </span>
    );
  }
  return (
    <NavLink to={item.to} className={({ isActive }) => `${className}${isActive ? " active" : ""}`}>
      <i className={`bi ${item.icon}`} />
      <span className="flex-grow-1">{item.label}</span>
      {!!contador && (
        <span className="badge rounded-pill text-bg-danger" title={`${contador} nueva(s)`}>
          {contador}
        </span>
      )}
    </NavLink>
  );
}

function SidebarGroup({ group }: { group: NavGroup }) {
  const { pathname } = useLocation();
  const dentro = pathname === group.base || pathname.startsWith(`${group.base}/`);
  const [abierto, setAbierto] = useState(dentro);

  // Al navegar hacia el módulo (p. ej. desde un link en otra página) se despliega.
  useEffect(() => {
    if (dentro) setAbierto(true);
  }, [dentro]);

  return (
    <div>
      <button
        type="button"
        className={`sidebar-link sidebar-group-toggle${dentro ? " in-group" : ""}`}
        aria-expanded={abierto}
        onClick={() => setAbierto((v) => !v)}
      >
        <i className={`bi ${group.icon}`} />
        <span className="flex-grow-1 text-start">{group.label}</span>
        <i className={`bi bi-chevron-${abierto ? "down" : "right"} sidebar-chevron`} />
      </button>
      {abierto && (
        <div className="sidebar-submenu">
          {group.children.map((child) => (
            <SidebarLink key={child.to} item={child} sub />
          ))}
        </div>
      )}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const alertasNuevas = useAlertasNuevas();

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <img src={logo} alt="AI-SEC Control" />
          <span>
            AI-SEC
            <br />
            Control
          </span>
        </div>

        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) =>
            isGroup(item) ? (
              <SidebarGroup key={item.base} group={item} />
            ) : (
              <SidebarLink
                key={item.to}
                item={item}
                contador={item.contador === "alertas" ? alertasNuevas : undefined}
              />
            ),
          )}
        </nav>

        <div className="sidebar-footer">
          <div className="d-flex align-items-center justify-content-between">
            <span className="text-truncate">{user?.username}</span>
            <button className="btn btn-sm btn-outline-light" onClick={logout}>
              Salir
            </button>
          </div>
        </div>
      </aside>

      <div className="app-content">{children}</div>
    </div>
  );
}
