import uuid

from pydantic import BaseModel


class PeriodoCantidad(BaseModel):
    periodo: str  # "YYYY-MM"
    cantidad: int


class NombreCantidad(BaseModel):
    nombre: str
    cantidad: int


class ProyectosIngresados(BaseModel):
    total: int
    por_tipo: dict[str, int]
    por_mes: list[PeriodoCantidad]


class Analisis(BaseModel):
    casos_analizados: int
    documentos_analizados: int
    por_tipo: dict[str, int]


class ModeladoCaso(BaseModel):
    caso_id: uuid.UUID
    nombre_proyecto: str
    empresa_responsable: str
    tipo: str
    compliance_pct: float
    residual_pct: float
    completitud_pct: float
    brechas_criticas: int
    semaforo: str


class Modelados(BaseModel):
    cantidad: int
    promedio_compliance_pct: float | None
    promedio_residual_pct: float | None
    por_semaforo: dict[str, int]
    casos: list[ModeladoCaso]


class Pentesting(BaseModel):
    total: int
    casos_con_pentest: int
    por_herramienta: list[NombreCantidad]
    por_severidad: dict[str, int]


class MetricasOut(BaseModel):
    proyectos_ingresados: ProyectosIngresados
    analisis: Analisis
    modelados: Modelados
    pentesting: Pentesting
