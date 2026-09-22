import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getCaso } from "../api/casos";
import { ApiError } from "../api/client";
import {
  actualizarRespuesta,
  getCasoScore,
  listCasoPreguntas,
  listDominios,
  seleccionarDominioCompleto,
} from "../api/threatModel";
import type { Caso, CasoPregunta, CasoScore, Dominio, RespuestaValor } from "../api/types";
import { ESTADO_LABELS, RESPUESTA_LABELS, RESPUESTA_OPTIONS, SEMAFORO_LABELS, TIER_LABELS, formatPct } from "../threatModel/labels";

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

  if (loading) return <p>Cargando…</p>;
  if (!caso) return <p className="error">{error ?? "Caso no encontrado"}</p>;

  return (
    <main>
      <p>
        <Link to={`/casos/${caso.id}`}>← Volver al caso</Link>
      </p>
      <h1>Modelado de amenazas — {caso.nombre_proyecto}</h1>
      {error && <p className="error">{error}</p>}

      {score && <ScoreDashboard score={score} />}

      <section>
        <h2>Agregar preguntas por dominio</h2>
        <div className="dominio-buttons">
          {dominios.map((dominio) => {
            const seleccionadas = preguntasPorDominio.get(dominio.codigo)?.length ?? 0;
            const completo = seleccionadas === dominio.total_preguntas;
            return (
              <button
                key={dominio.id}
                onClick={() => handleAgregarDominio(dominio.codigo)}
                disabled={completo}
                title={dominio.nombre}
              >
                {dominio.codigo} ({seleccionadas}/{dominio.total_preguntas})
              </button>
            );
          })}
        </div>
      </section>

      {[...preguntasPorDominio.entries()].map(([dominioCodigo, preguntasDelDominio]) => (
        <section key={dominioCodigo}>
          <h2>{dominioCodigo}</h2>
          <table className="preguntas-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Pregunta</th>
                <th>Tier</th>
                <th>Respuesta</th>
                <th>Estado</th>
                <th>Pts.</th>
                <th>Riesgo Residual</th>
                <th>Mitig. %</th>
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
                      className="mitigacion-input"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </main>
  );
}

function ScoreDashboard({ score }: { score: CasoScore }) {
  return (
    <section>
      <h2>Score</h2>
      <div className={`score-card score-card--${score.global_score.semaforo}`}>
        <strong>Global</strong>
        <span>{formatPct(score.global_score.compliance_pct)} cumplimiento</span>
        <span>{formatPct(score.global_score.residual_pct)} riesgo residual</span>
        <span>{SEMAFORO_LABELS[score.global_score.semaforo]}</span>
        <span>{formatPct(score.global_score.completitud_pct)} completitud</span>
        <span>{score.global_score.brechas_criticas} brechas críticas</span>
      </div>
      <div className="domain-cards">
        {score.dominios.map((d) => (
          <div key={d.dominio_codigo} className={`score-card score-card--${d.semaforo}`}>
            <strong>
              {d.dominio_codigo} — {d.dominio_nombre}
            </strong>
            <span>{formatPct(d.compliance_pct)} cumplimiento</span>
            <span>{formatPct(d.residual_pct)} riesgo residual</span>
            <span>{SEMAFORO_LABELS[d.semaforo]}</span>
            <span>
              {d.respondidas}/{d.total_preguntas} respondidas
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
