import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import logo from "../assets/logo-aisec.jpeg";
import { ApiError } from "../api/client";
import { enviarRespuestas, getFormulario, guardarBorrador, type RespuestaFormulario } from "../api/cuestionarios";
import type { EnvioResultado, Formulario, PreguntaFormulario, RespuestaValor } from "../api/types";
import { RESPUESTA_LABELS } from "../threatModel/labels";

const OPCIONES: { valor: RespuestaValor; ayuda: string }[] = [
  { valor: "SI", ayuda: "" },
  { valor: "NO", ayuda: "" },
  { valor: "NA_ARQ", ayuda: "La solución no tiene ese componente." },
  { valor: "NA_FASE", ayuda: "Todavía no corresponde en esta etapa del proyecto." },
];

type Respuestas = Record<string, { respuesta: RespuestaValor; comentario: string }>;

/** Formulario que abre el contacto desde el enlace del email. Sin login y
 * fuera del AppShell: el token de la URL es la única credencial. */
export function CuestionarioPublicoPage() {
  const { token = "" } = useParams<{ token: string }>();
  const [formulario, setFormulario] = useState<Formulario | null>(null);
  const [respuestas, setRespuestas] = useState<Respuestas>({});
  const [cargaError, setCargaError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [cambiosSinGuardar, setCambiosSinGuardar] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [resultado, setResultado] = useState<EnvioResultado | null>(null);

  useEffect(() => {
    getFormulario(token)
      .then((data) => {
        setFormulario(data);
        setRespuestas(
          Object.fromEntries(
            data.preguntas.map((p) => [p.pregunta_id, { respuesta: p.respuesta, comentario: p.comentario ?? "" }]),
          ),
        );
      })
      .catch((err) =>
        setCargaError(
          err instanceof ApiError && err.status !== 422 ? err.detail : "No se pudo abrir el cuestionario",
        ),
      );
  }, [token]);

  useEffect(() => {
    if (!cambiosSinGuardar) return;
    const avisar = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", avisar);
    return () => window.removeEventListener("beforeunload", avisar);
  }, [cambiosSinGuardar]);

  const porDominio = useMemo(() => {
    const grupos = new Map<string, PreguntaFormulario[]>();
    for (const p of formulario?.preguntas ?? []) {
      const clave = `${p.dominio_codigo} — ${p.dominio_nombre}`;
      grupos.set(clave, [...(grupos.get(clave) ?? []), p]);
    }
    return grupos;
  }, [formulario]);

  const total = formulario?.preguntas.length ?? 0;
  const respondidas = Object.values(respuestas).filter((r) => r.respuesta !== "PENDIENTE").length;

  function actualizar(preguntaId: string, cambio: Partial<Respuestas[string]>) {
    setRespuestas((prev) => ({ ...prev, [preguntaId]: { ...prev[preguntaId], ...cambio } }));
    setCambiosSinGuardar(true);
    setAviso(null);
  }

  function payload(): RespuestaFormulario[] {
    return Object.entries(respuestas).map(([pregunta_id, r]) => ({
      pregunta_id,
      respuesta: r.respuesta,
      comentario: r.comentario.trim() || null,
    }));
  }

  async function handleGuardar() {
    setError(null);
    setOcupado(true);
    try {
      await guardarBorrador(token, payload());
      setCambiosSinGuardar(false);
      setAviso("Guardado. Podés cerrar esta página y seguir más tarde con el mismo enlace.");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "No se pudo guardar");
    } finally {
      setOcupado(false);
    }
  }

  async function handleEnviar() {
    const faltan = total - respondidas;
    const mensaje =
      faltan > 0
        ? `Quedan ${faltan} pregunta(s) sin responder. Una vez enviado no vas a poder modificarlo. ¿Enviar igual?`
        : "Una vez enviado no vas a poder modificarlo. ¿Enviar las respuestas?";
    if (!window.confirm(mensaje)) return;

    setError(null);
    setOcupado(true);
    try {
      const res = await enviarRespuestas(token, payload());
      setCambiosSinGuardar(false);
      setResultado(res);
      window.scrollTo({ top: 0 });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "No se pudieron enviar las respuestas");
    } finally {
      setOcupado(false);
    }
  }

  if (cargaError || resultado) {
    return (
      <main className="login-page">
        <div className="card login-card cuestionario-mensaje">
          <div className="card-body p-4 p-sm-5 text-center">
            <img src={logo} alt="AI-SEC Control" className="login-logo" />
            {resultado ? (
              <>
                <i className="bi bi-check-circle-fill text-success fs-1" />
                <h1 className="h4 mt-2">¡Gracias! Recibimos tus respuestas</h1>
                <p className="text-muted mb-0">
                  Se registraron {resultado.aplicadas} respuesta(s).
                  {resultado.omitidas > 0 &&
                    ` ${resultado.omitidas} ya las había respondido el equipo de seguridad y se mantuvieron.`}
                </p>
              </>
            ) : (
              <>
                <i className="bi bi-exclamation-circle text-warning fs-1" />
                <p className="mt-2 mb-0">{cargaError}</p>
              </>
            )}
          </div>
        </div>
      </main>
    );
  }

  if (!formulario) {
    return (
      <div className="d-flex justify-content-center align-items-center" style={{ minHeight: "100svh" }}>
        <div className="spinner-border text-primary" role="status">
          <span className="visually-hidden">Cargando…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="cuestionario-page">
      <header className="cuestionario-header">
        <div className="cuestionario-container d-flex align-items-center gap-3">
          <img src={logo} alt="" className="cuestionario-logo" />
          <div>
            <p className="mb-0 small opacity-75">Cuestionario de seguridad de IA</p>
            <h1 className="h4 mb-0">{formulario.nombre_proyecto}</h1>
            <p className="mb-0 small opacity-75">{formulario.empresa_responsable}</p>
          </div>
        </div>
      </header>

      <main className="cuestionario-container py-4">
        <div className="card mb-4">
          <div className="card-body">
            <p className="mb-2">Hola {formulario.contacto_nombre}:</p>
            <p className="mb-2">
              Respondé cada pregunta sobre la solución. Si querés aclarar algo, usá el campo de comentario.
              Podés guardar y volver más tarde con el mismo enlace, que vence el{" "}
              {new Date(formulario.expira_at).toLocaleDateString("es-AR")}.
            </p>
            <p className="mb-0 text-muted small">
              Cuando termines, presioná <strong>Enviar respuestas</strong>. Después de enviar no se pueden modificar.
            </p>
          </div>
        </div>

        {total === 0 && (
          <div className="alert alert-info">
            No hay preguntas pendientes: el equipo de seguridad ya respondió todo el cuestionario.
          </div>
        )}

        {[...porDominio.entries()].map(([dominio, preguntas]) => (
          <section key={dominio} className="mb-4">
            <h2 className="h5 mb-3">{dominio}</h2>
            {preguntas.map((pregunta) => (
              <PreguntaCard
                key={pregunta.pregunta_id}
                pregunta={pregunta}
                valor={respuestas[pregunta.pregunta_id]}
                onChange={(cambio) => actualizar(pregunta.pregunta_id, cambio)}
              />
            ))}
          </section>
        ))}
      </main>

      {total > 0 && (
        <footer className="cuestionario-footer">
          <div className="cuestionario-container d-flex flex-wrap align-items-center gap-2 py-2">
            <div className="flex-grow-1">
              <div className="small text-muted">
                {respondidas} de {total} respondidas
                {cambiosSinGuardar && " · cambios sin guardar"}
              </div>
              <div className="progress cuestionario-progress" role="progressbar" aria-valuenow={respondidas} aria-valuemin={0} aria-valuemax={total}>
                <div className="progress-bar" style={{ width: `${(respondidas / total) * 100}%` }} />
              </div>
            </div>
            <button className="btn btn-outline-primary" onClick={handleGuardar} disabled={ocupado}>
              Guardar y seguir después
            </button>
            <button className="btn btn-primary" onClick={handleEnviar} disabled={ocupado}>
              Enviar respuestas
            </button>
          </div>
          {(error || aviso) && (
            <div className="cuestionario-container pb-2">
              <div className={`alert ${error ? "alert-danger" : "alert-success"} py-2 mb-0`}>{error ?? aviso}</div>
            </div>
          )}
        </footer>
      )}
    </div>
  );
}

function PreguntaCard({
  pregunta,
  valor,
  onChange,
}: {
  pregunta: PreguntaFormulario;
  valor: Respuestas[string];
  onChange: (cambio: Partial<Respuestas[string]>) => void;
}) {
  const nombre = `respuesta-${pregunta.pregunta_id}`;
  const ayuda = pregunta.instrucciones_es ?? pregunta.explicacion_es;

  return (
    <div className={`card mb-3 ${valor.respuesta !== "PENDIENTE" ? "border-success-subtle" : ""}`}>
      <div className="card-body">
        <p className="fw-semibold mb-2">
          {pregunta.dominio_codigo}-{pregunta.numero}. {pregunta.texto_es}
        </p>
        {ayuda && (
          <details className="mb-2 small">
            <summary className="text-primary">¿Cómo responder?</summary>
            <p className="mb-1 mt-1 text-muted">{ayuda}</p>
            {pregunta.evidencia_esperada && (
              <p className="mb-0 text-muted">
                <strong>Evidencia esperada:</strong> {pregunta.evidencia_esperada}
              </p>
            )}
          </details>
        )}

        <div className="d-flex flex-wrap gap-3 mb-2" role="radiogroup">
          {OPCIONES.map((opcion) => (
            <div className="form-check" key={opcion.valor} title={opcion.ayuda || undefined}>
              <input
                className="form-check-input"
                type="radio"
                name={nombre}
                id={`${nombre}-${opcion.valor}`}
                checked={valor.respuesta === opcion.valor}
                onChange={() => onChange({ respuesta: opcion.valor })}
              />
              <label className="form-check-label" htmlFor={`${nombre}-${opcion.valor}`}>
                {RESPUESTA_LABELS[opcion.valor]}
              </label>
            </div>
          ))}
          {valor.respuesta !== "PENDIENTE" && (
            <button
              type="button"
              className="btn btn-link btn-sm p-0 text-muted"
              onClick={() => onChange({ respuesta: "PENDIENTE" })}
            >
              Limpiar
            </button>
          )}
        </div>

        <textarea
          className="form-control form-control-sm"
          rows={2}
          maxLength={4000}
          placeholder="Comentario (opcional)"
          value={valor.comentario}
          onChange={(e) => onChange({ comentario: e.target.value })}
        />
      </div>
    </div>
  );
}
