import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import logo from "../assets/logo.jpeg";
import { useAuth } from "../auth/AuthContext";

interface NavItem {
  to: string;
  label: string;
  icon: string;
  disabled?: boolean;
}

// Dashboards todavía no está construido (Incremento 4 del roadmap) — se
// muestra deshabilitado para que la estructura completa del sistema sea
// visible desde ya.
const NAV_ITEMS: NavItem[] = [
  { to: "/casos", label: "Casos", icon: "bi-folder2-open" },
  { to: "/pentesting", label: "Pentesting", icon: "bi-bug" },
  { to: "/dashboards", label: "Dashboards", icon: "bi-graph-up", disabled: true },
];

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
            item.disabled ? (
              <span key={item.to} className="sidebar-link disabled" title="Próximamente">
                <i className={`bi ${item.icon}`} />
                {item.label}
              </span>
            ) : (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}
              >
                <i className={`bi ${item.icon}`} />
                {item.label}
              </NavLink>
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
