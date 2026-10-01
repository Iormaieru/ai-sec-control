import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import logo from "../assets/logo-aisec.jpeg";
import { useAuth } from "../auth/AuthContext";

interface NavLeaf {
  to: string;
  label: string;
  icon: string;
  disabled?: boolean;
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
  { to: "/dashboards", label: "Dashboards", icon: "bi-graph-up" },
];

function isGroup(item: NavItem): item is NavGroup {
  return "children" in item;
}

function SidebarLink({ item, sub }: { item: NavLeaf; sub?: boolean }) {
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
      {item.label}
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
              <SidebarLink key={item.to} item={item} />
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
