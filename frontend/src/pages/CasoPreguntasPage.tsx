import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { getCaso } from "../api/casos";
import { ApiError } from "../api/client";
import { analyzeDocument, downloadExportDocx } from "../api/documents";
import {
  actualizarRespuesta,
  getCasoScore,
  listCasoPreguntas,
  listDominios,
  seleccionarDominioCompleto,
} from "../api/threatModel";
import type {
  Caso,
  CasoPregunta,
  CasoScore,
  DocumentoAnalizado,
  Dominio,
  RespuestaValor,
} from "../api/types";
import {
  ESTADO_LABELS,
  RESPUESTA_LABELS,
  RESPUESTA_OPTIONS,
  SEMAFORO_LABELS,
  TIER_LABELS,
  formatPct,
} from "../threatModel/labels";

export function CasoPreguntasPage() {
  const { casoId } = useParams<{ casoId: string }>();
  const [caso, setCaso] = useState<Caso | null>(null);
  const [dominios, setDominios] = useState<Dominio[]>([]);
  const [preguntas, setPreguntas] = useState<CasoPregunta[]>([]);
  const [score, setScore] = useState<CasoScore | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function loadAll() {
    if (!casoId) return;
    setLoading(true);
    try {
      const [casoData, dominiosData, preguntasData, scoreData] = await Promise.all([
        getCaso(casoId),
        listDominios(),
        listCasoPreguntas(casoId),
        getCasoScore(casoId),
      ]);
      setCaso(casoData);
      setDominios(dominiosData);
      setPreguntas(preguntasData);
      setScore(scoreData);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "No se pudo cargar la información del caso");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [casoId]);

  async function refreshPreguntasYScore() {
    if (!casoId) return;
    const [preguntasData, scoreData] = await Promise.all([listCasoPreguntas(casoId), getCasoScore(casoId)]);
    setPreguntas(preguntasData);
    setScore(scoreData);
  }

  async function handleAgregarDominio(dominioCodigo: string) {
    if (!casoId) return;
    setError(null);
    try {
      await seleccionarDominioCompleto(casoId, dominioCodigo);
      await refreshPreguntasYScore();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "No se pudieron agregar las preguntas");
    }
  }

  async function handleRespuestaChange(pregunta: CasoPregunta, respuesta: RespuestaValor) {
    if (!casoId) return;
    setError(null);
    try {
      const updated = await actualizarRespuesta(casoId, pregunta.pregunta_id, {
        respuesta,
        control_compensatorio: pregunta.control_compensatorio,
        factor_mitigacion_pct: pregunta.factor_mitigacion_pct,
        owner_responsable: pregunta.owner_responsable,
      });
      setPreguntas((prev) => prev.map((p) => (p.pregunta_id === pregunta.pregunta_id ? updated : p)));
      const scoreData = await getCasoScore(casoId);
      setScore(scoreData);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "No se pudo guardar la respuesta");
    }
  }

  async function handleMitigacionCommit(pregunta: CasoPregunta, value: string) {
    if (!casoId) return;
    const factor = value === "" ? null : Number(value);
    setError(null);
    try {
      const updated = await actualizarRespuesta(casoId, pregunta.pregunta_id, {
        respuesta: pregunta.respuesta,
        control_compensatorio: pregunta.control_compensatorio,
        factor_mitigacion_pct: factor,
        owner_responsable: pregunta.owner_responsable,
      });
      setPreguntas((prev) => prev.map((p) => (p.pregunta_id === pregunta.pregunta_id ? updated : p)));
      const scoreData = await getCasoScore(casoId);
      setScore(scoreData);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "No se pudo guardar el factor de mitigación");
    }
  }

  const preguntasPorDominio = useMemo(() => {
    const groups = new Map<string, CasoPregunta[]>();
    for (const p of preguntas) {
      const list = groups.get(p.dominio_codigo) ?? [];
      list.push(p);
      groups.set(p.dominio_codigo, list);
    }
    return groups;
  }, [preguntas]);

  if (loading) {
    return (
      <div className="spinner-border text-primary" role="status">
        <span className="visually-hidden">Cargando…</span>
      </div>
    );
  }
  if (!caso) return <div className="alert alert-danger">{error ?? "Caso no encontrado"}</div>;

  return (
    <>
      <Link
        to={`/casos/${caso.id}`}
        className="d-inline-flex align-items-center gap-1 mb-3 text-decoration-none"
      >
        <i className="bi bi-arrow-left" /> Volver al caso
      </Link>
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h1 className="h3 mb-0">Modelado de amenazas — {caso.nombre_proyecto}</h1>
        <button
          className="btn btn-outline-primary"
          onClick={() => downloadExportDocx(caso.id, caso.nombre_proyecto.replace(/\s+/g, "_"))}
        >
          <i className="bi bi-file-earmark-word me-1" /> Descargar informe Word
        </button>
      </div>
      {error && <div className="alert alert-danger">{error}</div>}

      <DocumentAnalysisCard casoId={caso.id} onAnalyzed={refreshPreguntasYScore} />

      {score && <ScoreDashboard score={score} />}

      <div className="card mb-4">
        <div className="card-body">
          <h2 className="h5">Agregar preguntas por dominio</h2>
          <div className="d-flex gap-2 flex-wrap">
            {dominios.map((dominio) => {
              const seleccionadas = preguntasPorDominio.get(dominio.codigo)?.length ?? 0;
              const completo = seleccionadas === dominio.total_preguntas;
              return (
                <button
                  key={dominio.id}
                  className={`btn btn-sm ${completo ? "btn-success" : "btn-outline-primary"}`}
                  onClick={() => handleAgregarDominio(dominio.codigo)}
                  disabled={completo}
                  title={dominio.nombre}
                >
                  {completo && <i className="bi bi-check-lg me-1" />}
                  {dominio.codigo} ({seleccionadas}/{dominio.total_preguntas})
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {[...preguntasPorDominio.entries()].map(([dominioCodigo, preguntasDelDominio]) => (
        <div className="card mb-4" key={dominioCodigo}>
          <div className="card-header fw-semibold">{dominioCodigo}</div>
          <div className="table-responsive">
            <table className="table table-hover mb-0 align-middle preguntas-table">
              <thead className="table-light">
                <tr>
                  <th>#</th>
                  <th>Pregunta</th>
                  <th>Tier</th>
                  <th>Respuesta</th>
                  <th>Estado</th>
                  <th>Pts.</th>
                  <th>Riesgo Residual</th>
                  <th>Mitig. %</th>
                  <th>IA</th>
                </tr>
              </thead>
              <tbody>
                {preguntasDelDominio.map((pregunta) => (
                  <tr key={pregunta.caso_pregunta_id}>
                    <td>{pregunta.numero}</td>
                    <td className="pregunta-texto">{pregunta.texto_es}</td>
                    <td>{TIER_LABELS[pregunta.tier]}</td>
                    <td>
                      <select
                        className="form-select form-select-sm"
                        value={pregunta.respuesta}
                        onChange={(e) => handleRespuestaChange(pregunta, e.target.value as RespuestaValor)}
                      >
                        {RESPUESTA_OPTIONS.map((opt) => (
                          <option key={opt} value={opt}>
                            {RESPUESTA_LABELS[opt]}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>{ESTADO_LABELS[pregunta.estado]}</td>
                    <td>{pregunta.pts_obtenidos ?? "-"}</td>
                    <td>{pregunta.riesgo_residual ?? "-"}</td>
                    <td>
                      <input
                        type="number"
                        min={0}
                        max={100}
                        defaultValue={pregunta.factor_mitigacion_pct ?? ""}
                        onBlur={(e) => handleMitigacionCommit(pregunta, e.target.value)}
                        className="form-control form-control-sm mitigacion-input"
                      />
                    </td>
                    <td>
                      {pregunta.instrucciones_respuesta_es && (
                        <i
                          className="bi bi-info-circle text-primary"
                          title={`ES: ${pregunta.instrucciones_respuesta_es}\n\nEN: ${pregunta.instrucciones_respuesta_en ?? ""}`}
                        />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </>
  );
}

function DocumentAnalysisCard({ casoId, onAnalyzed }: { casoId: string; onAnalyzed: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DocumentoAnalizado | null>(null);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
    setResult(null);
    setError(null);
  }

  async function handleAnalyze() {
    if (!file) return;
    setAnalyzing(true);
    setError(null);
    try {
      const analisis = await analyzeDocument(casoId, file);
      setResult(analisis);
      await onAnalyzed();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "No se pudo analizar el documento");
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <div className="card mb-4">
      <div className="card-body">
        <h2 className="h5">Analizar documento con IA</h2>
        <p className="text-muted small">
          Subí la arquitectura del proyecto o la documentación de la herramienta (PDF o Word). La IA
          clasifica la solución y recomienda qué preguntas del catálogo aplican, con instrucciones de
          cómo responder cada una.
        </p>
        <div className="d-flex gap-2 align-items-center flex-wrap">
          <input
            type="file"
            className="form-control"
            style={{ maxWidth: 360 }}
            accept=".pdf,.docx"
            onChange={handleFileChange}
          />
          <button className="btn btn-primary" onClick={handleAnalyze} disabled={!file || analyzing}>
            {analyzing ? "Analizando…" : "Analizar"}
          </button>
        </div>
        {error && <div className="alert alert-danger mt-3 mb-0 py-2">{error}</div>}
        {result && (
          <div className="alert alert-success mt-3 mb-0">
            <strong>Clasificación:</strong> {result.clasificacion}
            <br />
            <strong>{result.preguntas_recomendadas.length}</strong> pregunta(s) recomendada(s) agregada(s)
            al alcance del caso.
          </div>
        )}
      </div>
    </div>
  );
}

function ScoreDashboard({ score }: { score: CasoScore }) {
  return (
    <div className="mb-4">
      <h2 className="h5">Score</h2>
      <div className={`card mb-3 score-card score-card--${score.global_score.semaforo}`}>
        <div className="card-body">
          <h3 className="h6">Global</h3>
          <div className="d-flex gap-4 flex-wrap">
            <span>{formatPct(score.global_score.compliance_pct)} cumplimiento</span>
            <span>{formatPct(score.global_score.residual_pct)} riesgo residual</span>
            <span>{SEMAFORO_LABELS[score.global_score.semaforo]}</span>
            <span>{formatPct(score.global_score.completitud_pct)} completitud</span>
            <span>{score.global_score.brechas_criticas} brechas críticas</span>
          </div>
        </div>
      </div>
      <div className="row row-cols-1 row-cols-md-2 row-cols-xl-4 g-3">
        {score.dominios.map((d) => (
          <div className="col" key={d.dominio_codigo}>
            <div className={`card h-100 score-card score-card--${d.semaforo}`}>
              <div className="card-body">
                <h3 className="h6 mb-2">
                  {d.dominio_codigo} — {d.dominio_nombre}
                </h3>
                <div className="small d-flex flex-column gap-1">
                  <span>{formatPct(d.compliance_pct)} cumplimiento</span>
                  <span>{formatPct(d.residual_pct)} riesgo residual</span>
                  <span>{SEMAFORO_LABELS[d.semaforo]}</span>
                  <span>
                    {d.respondidas}/{d.total_preguntas} respondidas
                  </span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
