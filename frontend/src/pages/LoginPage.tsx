import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import logo from "../assets/logo-aisec.jpeg";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      navigate("/casos", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "No se pudo iniciar sesión");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <div className="card login-card">
        <div className="card-body p-4 p-sm-5">
          <img src={logo} alt="AI-SEC Control" className="login-logo" />
          <p className="login-brand-name">AI-SEC Control</p>
          <p className="login-brand-tagline">Gestión de amenazas y seguridad de IA</p>

          <form onSubmit={handleSubmit}>
            <div className="mb-3">
              <label htmlFor="username" className="form-label">
                Usuario
              </label>
              <input
                id="username"
                className="form-control"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoFocus
                required
              />
            </div>
            <div className="mb-3">
              <label htmlFor="password" className="form-label">
                Contraseña
              </label>
              <input
                id="password"
                type="password"
                className="form-control"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error && (
              <div className="alert alert-danger py-2" role="alert">
                {error}
              </div>
            )}
            <button type="submit" className="btn btn-primary w-100" disabled={submitting}>
              {submitting ? "Ingresando…" : "Ingresar"}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
