import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { AppShell } from "../layout/AppShell";
import { useAuth } from "./AuthContext";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="d-flex justify-content-center align-items-center" style={{ minHeight: "100svh" }}>
        <div className="spinner-border text-primary" role="status">
          <span className="visually-hidden">Cargando…</span>
        </div>
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return <AppShell>{children}</AppShell>;
}
