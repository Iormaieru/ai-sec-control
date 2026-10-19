import datetime as dt

from pydantic import BaseModel


class IndicadoresIA(BaseModel):
    alertas_abiertas: int
    criticas_altas_abiertas: int
    usuarios_con_actividad: int
    apps_detectadas: int
    externos_con_actividad: int
    eventos: int
    equipos_con_actividad: int
    equipos_fuera_de_tenable: int
    horas_medias_atencion: float | None  # desde que se crea la alerta hasta que alguien la toma
    horas_medias_cierre: float | None  # hasta que se resuelve o descarta


class DiaPorSeveridad(BaseModel):
    dia: dt.date
    baja: int = 0
    media: int = 0
    alta: int = 0
    critica: int = 0


class DiaCantidad(BaseModel):
    dia: dt.date
    cantidad: int


class DiaPorActividad(BaseModel):
    dia: dt.date
    actividades: dict[str, int]


class TopApp(BaseModel):
    nombre: str
    usuarios: int
    eventos: int


class TopUsuario(BaseModel):
    nombre: str
    eventos: int
    reglas: int


class NombreCantidad(BaseModel):
    nombre: str
    cantidad: int


class PoblacionOut(BaseModel):
    poblacion: str
    usuarios: int
    eventos: int


class CoberturaTenable(BaseModel):
    con_agente: int = 0
    por_escaneo: int = 0  # inventariado con escaneo con credenciales, sin agente
    sin_inventario: int = 0  # Tenable lo conoce pero no tiene su software
    fuera_de_tenable: int = 0


class TableroIAOut(BaseModel):
    desde: dt.date
    hasta: dt.date
    indicadores: IndicadoresIA
    eventos_por_dia: list[DiaPorSeveridad]
    alertas_nuevas_por_dia: list[DiaCantidad]
    top_apps: list[TopApp]
    top_usuarios: list[TopUsuario]
    poblacion: list[PoblacionOut]
    alertas_por_estado: dict[str, int]
    actividades_sensibles: list[DiaPorActividad]
    cobertura_tenable: CoberturaTenable
    software_tenable: list[NombreCantidad]  # equipos del inventario con cada software de IA
    tenable_actualizado_at: dt.datetime | None
