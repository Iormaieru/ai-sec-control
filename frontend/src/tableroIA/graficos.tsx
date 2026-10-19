import { useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { TEXTO_SECUNDARIO, GRILLA, SERIE, SUPERFICIE, diaCorto, numero } from "./paleta";

const EJE = { fontSize: 12, fill: TEXTO_SECUNDARIO };

// --- tooltip: el valor manda, el nombre de la serie acompaña ---

interface FilaTooltip {
  name?: string | number;
  value?: unknown;
  color?: string;
}

function Tip({ active, payload, label, etiqueta }: { active?: boolean; payload?: readonly FilaTooltip[]; label?: unknown; etiqueta?: (l: string) => string }) {
  if (!active || !payload?.length) return null;
  const titulo = String(label ?? "");
  return (
    <div className="viz-tooltip">
      <div className="viz-tooltip-titulo">{etiqueta ? etiqueta(titulo) : titulo}</div>
      {[...payload].reverse().map((fila) => (
        <div key={String(fila.name)} className="viz-tooltip-fila">
          <span className="viz-tooltip-key" style={{ background: fila.color }} />
          <strong>{numero(Number(fila.value ?? 0))}</strong>
          <span>{fila.name}</span>
        </div>
      ))}
    </div>
  );
}

// --- tarjeta con vista de tabla (los valores siempre se pueden leer sin hover) ---

export interface Columna<T> {
  titulo: string;
  valor: (fila: T) => ReactNode;
  numero?: boolean;
}

export function TarjetaGrafico<T>({
  titulo,
  descripcion,
  columnas,
  filas,
  vacio,
  children,
}: {
  titulo: string;
  descripcion?: ReactNode;
  columnas: Columna<T>[];
  filas: T[];
  vacio?: boolean;
  children: ReactNode;
}) {
  const [tabla, setTabla] = useState(false);
  return (
    <div className="card h-100">
      <div className="card-body">
        <div className="d-flex justify-content-between align-items-start gap-2 mb-2">
          <div>
            <h2 className="h6 mb-0">{titulo}</h2>
            {descripcion && <div className="small text-body-secondary">{descripcion}</div>}
          </div>
          <button
            type="button"
            className="btn btn-sm btn-link text-decoration-none flex-shrink-0"
            onClick={() => setTabla((v) => !v)}
            aria-pressed={tabla}
          >
            <i className={`bi ${tabla ? "bi-bar-chart" : "bi-table"} me-1`} />
            {tabla ? "Gráfico" : "Tabla"}
          </button>
        </div>
        {vacio ? (
          <div className="text-body-secondary small py-5 text-center">Sin datos en el período.</div>
        ) : tabla ? (
          <div className="viz-tabla">
            <table className="table table-sm mb-0">
              <thead>
                <tr>
                  {columnas.map((c) => (
                    <th key={c.titulo} className={c.numero ? "text-end" : undefined}>
                      {c.titulo}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filas.map((fila, i) => (
                  <tr key={i}>
                    {columnas.map((c) => (
                      <td key={c.titulo} className={c.numero ? "text-end font-monospace" : "text-break"}>
                        {c.valor(fila)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          children
        )}
      </div>
    </div>
  );
}

/** Leyenda en el orden de las series, con el texto en tinta neutra (el color va sólo en la marca). */
function Leyenda({ series, forma }: { series: Serie[]; forma: "caja" | "linea" }) {
  return (
    <div className="viz-leyenda">
      {series.map((s) => (
        <span key={s.clave}>
          <span className={forma === "caja" ? "viz-leyenda-caja" : "viz-leyenda-linea"} style={{ background: s.color }} />
          {s.nombre}
        </span>
      ))}
    </div>
  );
}

// --- barras por día (apiladas si hay más de una serie) ---

export interface Serie {
  clave: string;
  nombre: string;
  color: string;
}

export function BarrasPorDia<T extends { dia: string }>({ datos, series, alto = 260 }: { datos: T[]; series: Serie[]; alto?: number }) {
  return (
    <ResponsiveContainer width="100%" height={alto}>
      <BarChart data={datos} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap={2}>
        <CartesianGrid vertical={false} stroke={GRILLA} />
        <XAxis dataKey="dia" tickFormatter={diaCorto} tick={EJE} tickLine={false} axisLine={{ stroke: GRILLA }} minTickGap={16} />
        <YAxis tick={EJE} tickLine={false} axisLine={false} allowDecimals={false} tickFormatter={numero} width={48} />
        <Tooltip cursor={{ fill: "rgba(0,0,0,0.04)" }} content={(p) => <Tip {...p} etiqueta={diaCorto} />} />
        {series.length > 1 && <Legend content={() => <Leyenda series={series} forma="caja" />} />}
        {series.map((s, i) => (
          <Bar
            key={s.clave}
            dataKey={s.clave}
            name={s.nombre}
            stackId="a"
            fill={s.color}
            stroke={SUPERFICIE}
            strokeWidth={series.length > 1 ? 1 : 0}
            radius={i === series.length - 1 ? [4, 4, 0, 0] : 0}
            maxBarSize={28}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

// --- líneas por día ---

export function LineasPorDia<T extends { dia: string }>({ datos, series, alto = 260 }: { datos: T[]; series: Serie[]; alto?: number }) {
  return (
    <ResponsiveContainer width="100%" height={alto}>
      <LineChart data={datos} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={GRILLA} />
        <XAxis dataKey="dia" tickFormatter={diaCorto} tick={EJE} tickLine={false} axisLine={{ stroke: GRILLA }} minTickGap={16} />
        <YAxis tick={EJE} tickLine={false} axisLine={false} allowDecimals={false} tickFormatter={numero} width={48} />
        <Tooltip cursor={{ stroke: TEXTO_SECUNDARIO, strokeWidth: 1 }} content={(p) => <Tip {...p} etiqueta={diaCorto} />} />
        <Legend content={() => <Leyenda series={series} forma="linea" />} />
        {series.map((s) => (
          <Line
            key={s.clave}
            dataKey={s.clave}
            name={s.nombre}
            stroke={s.color}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, stroke: SUPERFICIE, strokeWidth: 2 }}
            type="linear"
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

// --- ranking (barras horizontales con el valor al final) ---

export function Ranking<T extends { nombre: string }>({
  datos,
  clave,
  nombreSerie,
  color = SERIE[0],
  colores,
  anchoEtiqueta = 170,
}: {
  datos: T[];
  clave: keyof T & string;
  nombreSerie: string;
  color?: string;
  /** Un color por fila (p. ej. estados), en lugar de uno solo. */
  colores?: string[];
  anchoEtiqueta?: number;
}) {
  const alto = Math.max(120, datos.length * 30 + 16);
  const recortar = (v: string) => (v.length > 26 ? `${v.slice(0, 25)}…` : v);
  return (
    <ResponsiveContainer width="100%" height={alto}>
      <BarChart data={datos} layout="vertical" margin={{ top: 0, right: 48, left: 0, bottom: 0 }} barCategoryGap={4}>
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="nombre"
          width={anchoEtiqueta}
          tick={{ ...EJE, fill: "#292b2c" }}
          tickFormatter={recortar}
          tickLine={false}
          axisLine={false}
          interval={0}
        />
        <Tooltip cursor={{ fill: "rgba(0,0,0,0.04)" }} content={(p) => <Tip {...p} />} />
        <Bar
          dataKey={clave as string}
          name={nombreSerie}
          fill={color}
          radius={[0, 4, 4, 0]}
          maxBarSize={20}
          isAnimationActive={false}
        >
          {colores?.map((c, i) => <Cell key={i} fill={c} />)}
          <LabelList position="right" formatter={(v: unknown) => numero(Number(v))} style={{ fontSize: 12, fill: TEXTO_SECUNDARIO }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
