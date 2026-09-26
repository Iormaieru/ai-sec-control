import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { DashboardPage } from "./pages/DashboardPage";
import { CasoDetailPage } from "./pages/CasoDetailPage";
import { CasoPreguntasPage } from "./pages/CasoPreguntasPage";
import { CasosPage } from "./pages/CasosPage";
import { EstandarDetailPage } from "./pages/pentesting/EstandarDetailPage";
import { EstandaresPage } from "./pages/pentesting/EstandaresPage";
import { HerramientasPage } from "./pages/pentesting/HerramientasPage";
import { PentestDetailPage } from "./pages/pentesting/PentestDetailPage";
import { PentestsPage } from "./pages/pentesting/PentestsPage";
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
      <Route path="/pentesting" element={<Navigate to="/pentesting/gestion" replace />} />
      <Route
        path="/pentesting/gestion"
        element={
          <ProtectedRoute>
            <PentestsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/pentesting/gestion/:pentestId"
        element={
          <ProtectedRoute>
            <PentestDetailPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/pentesting/estandares"
        element={
          <ProtectedRoute>
            <EstandaresPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/pentesting/estandares/:estandarId"
        element={
          <ProtectedRoute>
            <EstandarDetailPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/pentesting/herramientas"
        element={
          <ProtectedRoute>
            <HerramientasPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/dashboards"
        element={
          <ProtectedRoute>
            <DashboardPage />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/casos" replace />} />
    </Routes>
  );
}
