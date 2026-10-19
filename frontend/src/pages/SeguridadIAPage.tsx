import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { listReglas } from "../api/alertas";
import { ApiError } from "../api/client";
import { descargarCsvIA, descargarExcelIA, getTableroIA, type FiltrosTableroIA, type TablaCSV } from "../api/tableroIA";
import type { EstadoAlerta, PoblacionIA, ReglaAlerta, SeveridadAlerta, TableroIA } from "../api/types";
import { ESTADO_LABELS, SEVERIDAD_LABELS, fechaHora } from "../alertas/labels";
import {
  BarrasPorDia,
  LineasPorDia,
  Ranking,
  TarjetaGrafico,
  type Serie,
} from "../tableroIA/graficos";
import { ESTADO, SERIE, diaCorto, numero } from "../tableroIA/paleta";

type Rango = "7" | "30" | "90" | "personalizado";

const SEVERIDADES: Serie[] = [
  { clave: "critica", nombre: "Crítica", color: ESTADO.critico },
  { clave: "alta", nombre: "Alta", color: ESTADO.serio },
  { clave: "media", nombre: "Media", color: ESTADO.aviso },
  { clave: "baja", nombre: "Baja", color: ESTADO.neutro },
];

const SENSIBLES: Serie[] = [
  { clave: "Upload", nombre: "Subidas de archivos", color: SERIE[0] },
  { clave: "Post", nombre: "Prompts (Post)", color: SERIE[1] },
  { clave: "CallToolRequest", nombre: "Herramientas ejecutadas por agentes", color: SERIE[2] },
];

const ESTADOS: EstadoAlerta[] = ["nueva", "en_revision", "resuelta", "descartada"];

function isoLocal(fecha: Date): string {
  const desfase = fecha.getTimezoneOffset() * 60000;
  return new Date(fecha.getTime() - desfase).toISOString().slice(0, 10);
}

function ultimosDias(n: number): { desde: string; hasta: string } {
  const hoy = new Date();
  const desde = new Date(hoy);
  desde.setDate(hoy.getDate() - (n - 1));
  return { desde: isoLocal(desde), hasta: isoLocal(hoy) };
}

function horas(valor: number | null): string {
  if (valor === null) return "—";
  if (valor >= 48) return `${(valor / 24).toLocaleString("es-AR", { maximumFractionDigits: 1 })} d`;
  return `${valor.toLocaleString("es-AR", { maximumFractionDigits: 1 })} h`;
}

function Indicador({ titulo, valor, detalle, alerta }: { titulo: string; valor: string; detalle?: string; alerta?: boolean }) {
  return (
    <div className="col">
      <div className="card h-100">
        <div className="card-body py-3">
          <div className="small text-body-secondary">{titulo}</div>
          <div className="viz-hero">
            {alerta && <i className="bi bi-exclamation-triangle-fill text-danger fs-6 me-1" aria-label="Requiere atención" />}
            {valor}
          </div>
          {detalle && <div className="small text-body-secondary">{detalle}</div>}
        </div>
      </div>
    </div>
  );
}

export function SeguridadIAPage() {
  const [rango, setRango] = useState<Rango>("30");
  const [filtros, setFiltros] = useState<FiltrosTableroIA>(ultimosDias(30));
  const [datos, setDatos] = useState<TableroIA | null>(null);
  const [reglas, setReglas] = useState<ReglaAlerta[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Filtros de los últimos datos recibidos: mientras no coincidan con los actuales, está recargando.
  const [cargadoCon, setCargadoCon] = useState<FiltrosTableroIA | null>(null);
  const [descargando, setDescargando] = useState(false);

  useEffect(() => {
    listReglas()
      .then(setReglas)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    let vigente = true;
    getTableroIA(filtros)
      .then((d) => vigente && (setDatos(d), setError(null)))
      .catch((err) => vigente && setError(err instanceof ApiError ? err.detail : "No se pudo cargar el tablero"))
      .finally(() => vigente && setCargadoCon(filtros));
    return () => {
      vigente = false;
    };
  }, [filtros]);
  const cargando = cargadoCon !== filtros;

  function actualizar(cambios: Partial<FiltrosTableroIA>) {
    setFiltros((prev) => ({ ...prev, ...cambios }));
  }

  function elegirRango(valor: Rango) {
    setRango(valor);
    if (valor !== "personalizado") actualizar(ultimosDias(Number(valor)));
  }

  async function exportar(accion: (periodo: string) => Promise<void>) {
    if (!datos) return;
    setDescargando(true);
    try {
      await accion(`${datos.desde}_${datos.hasta}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "No se pudo descargar el archivo");
    } finally {
      setDescargando(false);
    }
  }

  const sensibles = useMemo(
    () => datos?.actividades_sensibles.map((d) => ({ dia: d.dia, ...d.actividades })) ?? [],
    [datos],
  );
  const estados = useMemo(
    () => ESTADOS.map((e) => ({ nombre: ESTADO_LABELS[e], cantidad: datos?.alertas_por_estado[e] ?? 0 })),
    [datos],
  );
  const cobertura = useMemo(() => {
    const c = datos?.cobertura_tenable;
    return [
      { nombre: "Con agente", cantidad: c?.con_agente ?? 0 },
      { nombre: "Por escaneo", cantidad: c?.por_escaneo ?? 0 },
      { nombre: "En Tenable sin inventario", cantidad: c?.sin_inventario ?? 0 },
      { nombre: "Fuera de Tenable", cantidad: c?.fuera_de_tenable ?? 0 },
    ];
  }, [datos]);
  const poblacion = useMemo(
    () =>
      datos?.poblacion.map((p) => ({
        nombre: p.poblacion === "externos" ? "Externos (bmexternos)" : "Internos",
        usuarios: p.usuarios,
        eventos: p.eventos,
      })) ?? [],
    [datos],
  );

  const ind = datos?.indicadores;
  const totalEventos = (filas: { [k: string]: number | string }[], claves: string[]) =>
    filas.reduce((s, f) => s + claves.reduce((t, k) => t + Number(f[k] ?? 0), 0), 0);

  return (
    <>
      <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
        <div>
          <h1 className="h3 mb-0">Seguridad de IA</h1>
          <div className="small text-body-secondary">
            Uso de IA visto por Netskope y cobertura del inventario de Tenable
            {datos?.tenable_actualizado_at && <> (inventario actualizado {fechaHora(datos.tenable_actualizado_at)})</>}.
          </div>
        </div>
        <div className="d-flex flex-wrap gap-2">
          <button className="btn btn-primary" disabled={!datos || descargando} onClick={() => exportar((p) => descargarExcelIA(filtros, p))}>
            <i className="bi bi-file-earmark-excel me-1" /> Excel
          </button>
          <div className="btn-group" role="group" aria-label="Exportar CSV">
            {(["alertas", "eventos", "actividad"] as TablaCSV[]).map((tabla) => (
              <button
                key={tabla}
                className="btn btn-outline-primary"
                disabled={!datos || descargando}
                onClick={() => exportar((p) => descargarCsvIA(filtros, tabla, p))}
                title={`Descargar ${tabla} en CSV`}
              >
                {tabla === "alertas" && <i className="bi bi-filetype-csv me-1" />}
                {tabla === "alertas" ? "CSV: alertas" : tabla === "eventos" ? "eventos" : "actividad diaria"}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="row g-2 mb-3 align-items-end">
        <div className="col-auto">
          <label className="form-label mb-1 small">Período</label>
          <select className="form-select" value={rango} onChange={(e) => elegirRango(e.target.value as Rango)}>
            <option value="7">Últimos 7 días</option>
            <option value="30">Últimos 30 días</option>
            <option value="90">Últimos 90 días</option>
            <option value="personalizado">Personalizado</option>
          </select>
        </div>
        {rango === "personalizado" && (
          <>
            <div className="col-auto">
              <label className="form-label mb-1 small">Desde</label>
              <input type="date" className="form-control" value={filtros.desde ?? ""} onChange={(e) => e.target.value && actualizar({ desde: e.target.value })} />
            </div>
            <div className="col-auto">
              <label className="form-label mb-1 small">Hasta</label>
              <input type="date" className="form-control" value={filtros.hasta ?? ""} onChange={(e) => e.target.value && actualizar({ hasta: e.target.value })} />
            </div>
          </>
        )}
        <div className="col-auto">
          <label className="form-label mb-1 small">Regla</label>
          <select className="form-select" value={filtros.regla_id ?? ""} onChange={(e) => actualizar({ regla_id: e.target.value || undefined })}>
            <option value="">Todas</option>
            {reglas.map((r) => (
              <option key={r.id} value={r.id}>
                {r.nombre}
              </option>
            ))}
          </select>
        </div>
        <div className="col-auto">
          <label className="form-label mb-1 small">Severidad</label>
          <select
            className="form-select"
            value={filtros.severidad ?? ""}
            onChange={(e) => actualizar({ severidad: (e.target.value || undefined) as SeveridadAlerta | undefined })}
          >
            <option value="">Todas</option>
            {Object.entries(SEVERIDAD_LABELS).map(([valor, etiqueta]) => (
              <option key={valor} value={valor}>
                {etiqueta}
              </option>
            ))}
          </select>
        </div>
        <div className="col-auto">
          <label className="form-label mb-1 small">Usuarios</label>
          <select
            className="form-select"
            value={filtros.poblacion ?? ""}
            onChange={(e) => actualizar({ poblacion: (e.target.value || undefined) as PoblacionIA | undefined })}
          >
            <option value="">Todos</option>
            <option value="internos">Internos</option>
            <option value="externos">Externos (bmexternos)</option>
          </select>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}
      {!datos && cargando && <div className="text-body-secondary">Cargando…</div>}

      {datos && ind && (
        <div className={cargando ? "viz-recargando" : undefined}>
          <div className="row row-cols-2 row-cols-md-4 g-3 mb-3">
            <Indicador
              titulo="Alertas abiertas"
              valor={numero(ind.alertas_abiertas)}
              detalle={`${numero(ind.criticas_altas_abiertas)} críticas o altas`}
              alerta={ind.criticas_altas_abiertas > 0}
            />
            <Indicador titulo="Usuarios con actividad de IA" valor={numero(ind.usuarios_con_actividad)} detalle={`${numero(ind.eventos)} eventos en el período`} />
            <Indicador titulo="Apps de IA detectadas" valor={numero(ind.apps_detectadas)} detalle="vistas por Netskope" />
            <Indicador
              titulo="Equipos fuera de Tenable"
              valor={numero(ind.equipos_fuera_de_tenable)}
              detalle={`de ${numero(ind.equipos_con_actividad)} con actividad de IA`}
              alerta={ind.equipos_fuera_de_tenable > 0}
            />
            <Indicador titulo="Tiempo medio de atención" valor={horas(ind.horas_medias_atencion)} detalle="desde que se genera la alerta" />
            <Indicador titulo="Tiempo medio de cierre" valor={horas(ind.horas_medias_cierre)} detalle="hasta resolverla o descartarla" />
            <Indicador titulo="Externos con actividad" valor={numero(ind.externos_con_actividad)} detalle="cuentas @bmexternos" />
            <Indicador titulo="Equipos con actividad de IA" valor={numero(ind.equipos_con_actividad)} detalle="según las alertas de Netskope" />
          </div>

          <div className="row g-3">
            <div className="col-12">
              <TarjetaGrafico
                titulo="Eventos de IA por día, por severidad de la regla"
                descripcion="Reglas de alerta y de métrica. Un evento que cumple dos reglas cuenta en las dos."
                vacio={totalEventos(datos.eventos_por_dia, ["critica", "alta", "media", "baja"]) === 0}
                columnas={[
                  { titulo: "Día", valor: (f) => diaCorto(f.dia) },
                  ...SEVERIDADES.map((s) => ({ titulo: s.nombre, valor: (f: (typeof datos.eventos_por_dia)[number]) => numero(f[s.clave as SeveridadAlerta]), numero: true })),
                ]}
                filas={datos.eventos_por_dia}
              >
                <BarrasPorDia datos={datos.eventos_por_dia} series={SEVERIDADES} />
              </TarjetaGrafico>
            </div>

            <div className="col-lg-6">
              <TarjetaGrafico
                titulo="Alertas nuevas por día"
                descripcion="Por la fecha del primer evento."
                vacio={datos.alertas_nuevas_por_dia.every((d) => d.cantidad === 0)}
                columnas={[
                  { titulo: "Día", valor: (f) => diaCorto(f.dia) },
                  { titulo: "Alertas", valor: (f) => numero(f.cantidad), numero: true },
                ]}
                filas={datos.alertas_nuevas_por_dia}
              >
                <BarrasPorDia datos={datos.alertas_nuevas_por_dia} series={[{ clave: "cantidad", nombre: "Alertas nuevas", color: SERIE[0] }]} />
              </TarjetaGrafico>
            </div>

            <div className="col-lg-6">
              <TarjetaGrafico
                titulo="Actividades sensibles en el tiempo"
                descripcion="Subidas de archivos, prompts y herramientas ejecutadas por agentes (MCP)."
                vacio={totalEventos(sensibles, SENSIBLES.map((s) => s.clave)) === 0}
                columnas={[
                  { titulo: "Día", valor: (f) => diaCorto(f.dia) },
                  ...SENSIBLES.map((s) => ({ titulo: s.nombre, valor: (f: (typeof sensibles)[number]) => numero(Number((f as Record<string, unknown>)[s.clave] ?? 0)), numero: true })),
                ]}
                filas={sensibles}
              >
                <LineasPorDia datos={sensibles} series={SENSIBLES} />
              </TarjetaGrafico>
            </div>

            <div className="col-lg-6">
              <TarjetaGrafico
                titulo="Apps de IA más usadas"
                descripcion="Por cantidad de usuarios."
                vacio={datos.top_apps.length === 0}
                columnas={[
                  { titulo: "App", valor: (f) => f.nombre },
                  { titulo: "Usuarios", valor: (f) => numero(f.usuarios), numero: true },
                  { titulo: "Eventos", valor: (f) => numero(f.eventos), numero: true },
                ]}
                filas={datos.top_apps}
              >
                <Ranking datos={datos.top_apps} clave="usuarios" nombreSerie="Usuarios" />
              </TarjetaGrafico>
            </div>

            <div className="col-lg-6">
              <TarjetaGrafico
                titulo="Usuarios con más actividad de riesgo"
                descripcion="Eventos en reglas de alerta (no incluye las de métrica)."
                vacio={datos.top_usuarios.length === 0}
                columnas={[
                  { titulo: "Usuario", valor: (f) => f.nombre },
                  { titulo: "Eventos", valor: (f) => numero(f.eventos), numero: true },
                  { titulo: "Reglas", valor: (f) => numero(f.reglas), numero: true },
                ]}
                filas={datos.top_usuarios}
              >
                <Ranking datos={datos.top_usuarios} clave="eventos" nombreSerie="Eventos" anchoEtiqueta={210} />
              </TarjetaGrafico>
            </div>

            <div className="col-lg-4">
              <TarjetaGrafico
                titulo="Internos y externos"
                descripcion="Usuarios con actividad de IA."
                vacio={poblacion.every((p) => p.usuarios === 0)}
                columnas={[
                  { titulo: "Usuarios", valor: (f) => f.nombre },
                  { titulo: "Cantidad", valor: (f) => numero(f.usuarios), numero: true },
                  { titulo: "Eventos", valor: (f) => numero(f.eventos), numero: true },
                ]}
                filas={poblacion}
              >
                <Ranking datos={poblacion} clave="usuarios" nombreSerie="Usuarios" anchoEtiqueta={150} />
              </TarjetaGrafico>
            </div>

            <div className="col-lg-4">
              <TarjetaGrafico
                titulo="Estado de las alertas"
                descripcion={<>Alertas con actividad en el período. <Link to="/alertas">Ver alertas</Link></>}
                vacio={estados.every((e) => e.cantidad === 0)}
                columnas={[
                  { titulo: "Estado", valor: (f) => f.nombre },
                  { titulo: "Alertas", valor: (f) => numero(f.cantidad), numero: true },
                ]}
                filas={estados}
              >
                <Ranking datos={estados} clave="cantidad" nombreSerie="Alertas" anchoEtiqueta={110} />
              </TarjetaGrafico>
            </div>

            <div className="col-lg-4">
              <TarjetaGrafico
                titulo="Cobertura de Tenable"
                descripcion="Equipos con actividad de IA según su estado en el inventario."
                vacio={cobertura.every((c) => c.cantidad === 0)}
                columnas={[
                  { titulo: "Cobertura", valor: (f) => f.nombre },
                  { titulo: "Equipos", valor: (f) => numero(f.cantidad), numero: true },
                ]}
                filas={cobertura}
              >
                <Ranking
                  datos={cobertura}
                  clave="cantidad"
                  nombreSerie="Equipos"
                  colores={[ESTADO.bien, SERIE[0], ESTADO.aviso, ESTADO.critico]}
                  anchoEtiqueta={170}
                />
              </TarjetaGrafico>
            </div>

            <div className="col-lg-6">
              <TarjetaGrafico
                titulo="Software de IA en el inventario de Tenable"
                descripcion="Equipos con cada software instalado (todo el inventario, sin filtros)."
                vacio={datos.software_tenable.length === 0}
                columnas={[
                  { titulo: "Software", valor: (f) => f.nombre },
                  { titulo: "Equipos", valor: (f) => numero(f.cantidad), numero: true },
                ]}
                filas={datos.software_tenable}
              >
                <Ranking datos={datos.software_tenable} clave="cantidad" nombreSerie="Equipos" anchoEtiqueta={120} />
              </TarjetaGrafico>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
