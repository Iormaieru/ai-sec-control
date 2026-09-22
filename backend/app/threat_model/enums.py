import enum


class RespuestaValor(str, enum.Enum):
    SI = "SI"
    NO = "NO"
    NA_ARQ = "NA_ARQ"
    NA_FASE = "NA_FASE"
    PENDIENTE = "PENDIENTE"


class Estado(str, enum.Enum):
    CUMPLE = "cumple"
    BRECHA = "brecha"
    PENDIENTE = "pendiente"
    NO_APLICA_ARQUITECTURA = "no_aplica_arquitectura"
    NO_APLICA_FASE = "no_aplica_fase"
