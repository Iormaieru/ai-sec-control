import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import logo from "../assets/logo-aisec.jpeg";
import { ApiError } from "../api/client";
import { enviarRespuestas, getFormulario, guardarBorrador, type RespuestaFormulario } from "../api/cuestionarios";
import type { EnvioResultado, Formulario, PreguntaFormulario, RespuestaValor } from "../api/types";
import { idiomaDelNavegador, TEXTOS_CUESTIONARIO, type TextosCuestionario } from "../threatModel/cuestionarioTextos";

const OPCIONES = ["SI", "NO", "NA_ARQ", "NA_FASE"] as const;

type Respuestas = Record<string, { respuesta: RespuestaValor; comentario: string }>;

/** Formulario que abre el contacto desde el enlace del email. Sin login y
 * fuera del AppShell: el token de la URL es la única credencial. Todo se
 * muestra en el idioma elegido al enviar la invitación. */
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
  const t = TEXTOS_CUESTIONARIO[formulario?.idioma ?? idiomaDelNavegador()];

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
          err instanceof ApiError && err.status !== 422
            ? err.detail
            : TEXTOS_CUESTIONARIO[idiomaDelNavegador()].errorCarga,
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
      setAviso(t.guardado);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t.errorGuardar);
    } finally {
      setOcupado(false);
    }
  }

  async function handleEnviar() {
    const faltan = total - respondidas;
    const mensaje = faltan > 0 ? t.confirmarFaltan(faltan) : t.confirmarEnviar;
    if (!window.confirm(mensaje)) return;

    setError(null);
    setOcupado(true);
    try {
      const res = await enviarRespuestas(token, payload());
      setCambiosSinGuardar(false);
      setResultado(res);
      window.scrollTo({ top: 0 });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t.errorEnviar);
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
                <h1 className="h4 mt-2">{t.graciasTitulo}</h1>
                <p className="text-muted mb-0">{t.graciasDetalle(resultado.aplicadas, resultado.omitidas)}</p>
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
          <span className="visually-hidden">{t.cargando}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="cuestionario-page" lang={formulario.idioma}>
      <header className="cuestionario-header">
        <div className="cuestionario-container d-flex align-items-center gap-3">
          <img src={logo} alt="" className="cuestionario-logo" />
          <div>
            <p className="mb-0 small opacity-75">{t.titulo}</p>
            <h1 className="h4 mb-0">{formulario.nombre_proyecto}</h1>
            <p className="mb-0 small opacity-75">{formulario.empresa_responsable}</p>
          </div>
        </div>
      </header>

      <main className="cuestionario-container py-4">
        <div className="card mb-4">
          <div className="card-body">
            <p className="mb-2">{t.saludo(formulario.contacto_nombre)}</p>
            <p className="mb-2">{t.instrucciones(new Date(formulario.expira_at).toLocaleDateString(t.locale))}</p>
            <p className="mb-0 text-muted small">
              {t.alTerminar[0]}
              <strong>{t.alTerminar[1]}</strong>
              {t.alTerminar[2]}
            </p>
          </div>
        </div>

        {total === 0 && <div className="alert alert-info">{t.sinPendientes}</div>}

        {[...porDominio.entries()].map(([dominio, preguntas]) => (
          <section key={dominio} className="mb-4">
            <h2 className="h5 mb-3">{dominio}</h2>
            {preguntas.map((pregunta) => (
              <PreguntaCard
                key={pregunta.pregunta_id}
                pregunta={pregunta}
                valor={respuestas[pregunta.pregunta_id]}
                t={t}
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
                {t.progreso(respondidas, total)}
                {cambiosSinGuardar && ` · ${t.cambiosSinGuardar}`}
              </div>
              <div
                className="progress cuestionario-progress"
                role="progressbar"
                aria-valuenow={respondidas}
                aria-valuemin={0}
                aria-valuemax={total}
              >
                <div className="progress-bar" style={{ width: `${(respondidas / total) * 100}%` }} />
              </div>
            </div>
            <button className="btn btn-outline-primary" onClick={handleGuardar} disabled={ocupado}>
              {t.guardar}
            </button>
            <button className="btn btn-primary" onClick={handleEnviar} disabled={ocupado}>
              {t.enviar}
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
  t,
  onChange,
}: {
  pregunta: PreguntaFormulario;
  valor: Respuestas[string];
  t: TextosCuestionario;
  onChange: (cambio: Partial<Respuestas[string]>) => void;
}) {
  const nombre = `respuesta-${pregunta.pregunta_id}`;
  const ayuda = pregunta.instrucciones ?? pregunta.explicacion;

  return (
    <div className={`card mb-3 ${valor.respuesta !== "PENDIENTE" ? "border-success-subtle" : ""}`}>
      <div className="card-body">
        <p className="fw-semibold mb-2">
          {pregunta.dominio_codigo}-{pregunta.numero}. {pregunta.texto}
        </p>
        {ayuda && (
          <details className="mb-2 small">
            <summary className="text-primary">{t.comoResponder}</summary>
            <p className="mb-1 mt-1 text-muted">{ayuda}</p>
            {pregunta.evidencia_esperada && (
              <p className="mb-0 text-muted">
                <strong>{t.evidenciaEsperada}</strong> {pregunta.evidencia_esperada}
              </p>
            )}
          </details>
        )}

        <div className="d-flex flex-wrap gap-3 mb-2" role="radiogroup">
          {OPCIONES.map((opcion) => (
            <div className="form-check" key={opcion} title={t.ayudaOpciones[opcion]}>
              <input
                className="form-check-input"
                type="radio"
                name={nombre}
                id={`${nombre}-${opcion}`}
                checked={valor.respuesta === opcion}
                onChange={() => onChange({ respuesta: opcion })}
              />
              <label className="form-check-label" htmlFor={`${nombre}-${opcion}`}>
                {t.opciones[opcion]}
              </label>
            </div>
          ))}
          {valor.respuesta !== "PENDIENTE" && (
            <button
              type="button"
              className="btn btn-link btn-sm p-0 text-muted"
              onClick={() => onChange({ respuesta: "PENDIENTE" })}
            >
              {t.limpiar}
            </button>
          )}
        </div>

        <textarea
          className="form-control form-control-sm"
          rows={2}
          maxLength={4000}
          placeholder={t.comentario}
          value={valor.comentario}
          onChange={(e) => onChange({ comentario: e.target.value })}
        />
      </div>
    </div>
  );
}
