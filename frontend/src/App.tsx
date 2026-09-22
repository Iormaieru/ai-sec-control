import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { CasoDetailPage } from "./pages/CasoDetailPage";
import { CasoPreguntasPage } from "./pages/CasoPreguntasPage";
import { CasosPage } from "./pages/CasosPage";
import { LoginPage } from "./pages/LoginPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/casos"
        element={
          <ProtectedRoute>
            <CasosPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/casos/:casoId"
        element={
          <ProtectedRoute>
            <CasoDetailPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/casos/:casoId/preguntas"
        element={
          <ProtectedRoute>
            <CasoPreguntasPage />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/casos" replace />} />
    </Routes>
  );
}
