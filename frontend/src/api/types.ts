export type UserRole = "admin" | "user";

export interface User {
  id: string;
  username: string;
  full_name: string | null;
  role: UserRole;
  is_active: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export type CasoTipo = "candidato" | "ingresado" | "herramienta_tercero";
export type CasoEstado =
  | "abierto"
  | "en_analisis"
  | "esperando_proveedor"
  | "cerrado_aprobado"
  | "rechazado";

export interface Contacto {
  id: string;
  nombre: string;
  email: string | null;
  rol: string | null;
}

export interface Caso {
  id: string;
  gdld: string | null;
  empresa_responsable: string;
  nombre_proyecto: string;
  tipo: CasoTipo;
  estado: CasoEstado;
  created_at: string;
  updated_at: string;
  contactos: Contacto[];
}

export type RespuestaValor = "SI" | "NO" | "NA_ARQ" | "NA_FASE" | "PENDIENTE";
export type Estado = "cumple" | "brecha" | "pendiente" | "no_aplica_arquitectura" | "no_aplica_fase";
export type Tier = "critico" | "alto" | "estandar";
export type Semaforo = "solido" | "moderado" | "vulnerable" | "critico" | "sin_evaluar";

export interface CasoPregunta {
  caso_pregunta_id: string;
  pregunta_id: string;
  dominio_codigo: string;
  numero: number;
  texto_es: string;
  texto_en: string;
  tier: Tier;
  multiplicador: number;
  respuesta: RespuestaValor;
  estado: Estado;
  pts_obtenidos: number | null;
  maximo_aplicable: number;
  riesgo_residual: number | null;
  control_compensatorio: string | null;
  factor_mitigacion_pct: number | null;
  owner_responsable: string | null;
  accion_remediacion: string | null;
  fecha_objetivo: string | null;
  evidencia_esperada: string | null;
  observaciones: string | null;
  instrucciones_respuesta_es: string | null;
  instrucciones_respuesta_en: string | null;
}

export interface DomainScore {
  dominio_codigo: string;
  dominio_nombre: string;
  peso: number;
  total_preguntas: number;
  respondidas: number;
  na_total: number;
  pendientes: number;
  cumple: number;
  brechas_criticas: number;
  compliance_pct: number;
  residual_pct: number;
  contrib_cumplimiento: number;
  contrib_residual: number;
  gap_ponderado: number;
  semaforo: Semaforo;
}

export interface GlobalScore {
  compliance_pct: number;
  residual_pct: number;
  completitud_pct: number;
  brechas_criticas: number;
  semaforo: Semaforo;
}

export interface CasoScore {
  dominios: DomainScore[];
  global_score: GlobalScore;
}

export interface DocumentoAnalizado {
  id: string;
  nombre_archivo: string;
  clasificacion: string;
  preguntas_recomendadas: CasoPregunta[];
}

export interface PreguntaCatalogo {
  id: string;
  dominio_id: string;
  numero: number;
  texto_es: string;
  texto_en: string;
  tipo: "control" | "riesgo";
  polaridad: "positiva" | "negativa";
  tier: Tier;
  multiplicador: number;
  impacto_primario: string | null;
  referencias_regulatorias: string | null;
  justificacion_tier: string | null;
  explicacion_control_es: string | null;
  explicacion_control_en: string | null;
}

export interface Dominio {
  id: string;
  codigo: string;
  nombre: string;
  peso: number;
  total_preguntas: number;
}

export type Severidad = "baja" | "media" | "alta" | "critica";

export interface HerramientaPentest {
  id: string;
  nombre: string;
  descripcion: string | null;
  url_referencia: string | null;
}

export interface PentestResultado {
  id: string;
  caso_id: string;
  herramienta_id: string;
  herramienta_nombre: string;
  hallazgos: string;
  severidad: Severidad;
  fecha: string;
}

export interface PeriodoCantidad {
  periodo: string;
  cantidad: number;
}

export interface ModeladoCaso {
  caso_id: string;
  nombre_proyecto: string;
  empresa_responsable: string;
  tipo: CasoTipo;
  compliance_pct: number;
  residual_pct: number;
  completitud_pct: number;
  brechas_criticas: number;
  semaforo: Semaforo;
}

export interface Metricas {
  proyectos_ingresados: {
    total: number;
    por_tipo: Record<CasoTipo, number>;
    por_mes: PeriodoCantidad[];
  };
  analisis: {
    casos_analizados: number;
    documentos_analizados: number;
    por_tipo: Record<CasoTipo, number>;
  };
  modelados: {
    cantidad: number;
    promedio_compliance_pct: number | null;
    promedio_residual_pct: number | null;
    por_semaforo: Record<string, number>;
    casos: ModeladoCaso[];
  };
  pentesting: {
    total: number;
    casos_con_pentest: number;
    por_herramienta: { nombre: string; cantidad: number }[];
    por_severidad: Record<Severidad, number>;
  };
}
