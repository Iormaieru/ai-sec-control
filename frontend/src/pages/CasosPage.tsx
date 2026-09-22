import { useAuth } from "../auth/AuthContext";

export function CasosPage() {
  const { user, logout } = useAuth();

  return (
    <main>
      <header className="page-header">
        <h1>Casos</h1>
        <div>
          <span>{user?.username}</span>
          <button onClick={logout}>Salir</button>
        </div>
      </header>
      <p>Listado de casos (T12).</p>
    </main>
  );
}
